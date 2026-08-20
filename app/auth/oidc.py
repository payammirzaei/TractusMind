import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from app.auth.store import AuthStore, UserIdentity, UserRole
from app.core.config import Settings


class OIDCAuthenticationError(RuntimeError):
    pass


class OIDCProviderError(OIDCAuthenticationError):
    pass


@dataclass(frozen=True)
class OIDCMetadata:
    issuer: str
    jwks_uri: str


class OIDCAuthenticator:
    """Verify one configured OIDC issuer and persist trusted external identities."""

    def __init__(self, settings: Settings, store: AuthStore) -> None:
        self.settings = settings
        self.store = store
        self._client = httpx.AsyncClient(timeout=settings.oidc_http_timeout_seconds)
        self._metadata: OIDCMetadata | None = None
        self._jwks: dict[str, Any] | None = None
        self._cache_expires_at = 0.0
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def authenticate(self, token: str) -> UserIdentity | None:
        if not self.settings.oidc_enabled or not self.settings.oidc_issuer_url:
            return None
        if len(token) > 16_384:
            raise OIDCAuthenticationError("OIDC bearer token is too large")

        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise OIDCAuthenticationError("Malformed JWT header") from exc

        algorithm = str(header.get("alg") or "")
        if algorithm not in self.settings.oidc_algorithm_list:
            raise OIDCAuthenticationError("JWT algorithm is not allowed")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise OIDCAuthenticationError("JWT header is missing kid")

        metadata, jwks = await self._configuration()
        key = self._find_key(jwks, kid)
        if key is None:
            metadata, jwks = await self._configuration(force=True)
            key = self._find_key(jwks, kid)
        if key is None:
            raise OIDCAuthenticationError("No matching JWKS key")

        options = {
            "require": ["exp", "iss", "sub"],
            "verify_aud": self.settings.oidc_audience is not None,
        }
        try:
            claims = jwt.decode(
                token,
                key=jwt.PyJWK.from_dict(key).key,
                algorithms=self.settings.oidc_algorithm_list,
                audience=self.settings.oidc_audience,
                issuer=metadata.issuer,
                options=options,
            )
        except jwt.PyJWTError as exc:
            raise OIDCAuthenticationError("JWT verification failed") from exc

        subject = claims.get("sub")
        issuer = claims.get("iss")
        if not isinstance(subject, str) or not subject or len(subject) > 500:
            raise OIDCAuthenticationError("JWT subject is invalid")
        if not isinstance(issuer, str) or issuer != metadata.issuer:
            raise OIDCAuthenticationError("JWT issuer is invalid")

        role = self._resolve_role(claims)
        display_name = self._display_name(claims, subject)
        return await self.store.authenticate_oidc_identity(
            issuer=issuer,
            subject=subject,
            display_name=display_name,
            role=role,
        )

    async def _configuration(self, *, force: bool = False) -> tuple[OIDCMetadata, dict[str, Any]]:
        now = time.monotonic()
        if (
            not force
            and self._metadata is not None
            and self._jwks is not None
            and now < self._cache_expires_at
        ):
            return self._metadata, self._jwks

        async with self._lock:
            now = time.monotonic()
            if (
                not force
                and self._metadata is not None
                and self._jwks is not None
                and now < self._cache_expires_at
            ):
                return self._metadata, self._jwks

            configured_issuer = (self.settings.oidc_issuer_url or "").rstrip("/")
            self._validate_provider_url(configured_issuer)
            discovery_url = f"{configured_issuer}/.well-known/openid-configuration"
            discovery = await self._get_json(discovery_url)
            issuer = discovery.get("issuer")
            jwks_uri = discovery.get("jwks_uri")
            if issuer != configured_issuer:
                raise OIDCProviderError("OIDC discovery issuer mismatch")
            if not isinstance(jwks_uri, str) or not jwks_uri:
                raise OIDCProviderError("OIDC discovery is missing jwks_uri")
            self._validate_provider_url(jwks_uri)

            jwks = await self._get_json(jwks_uri)
            keys = jwks.get("keys")
            if not isinstance(keys, list) or not keys:
                raise OIDCProviderError("JWKS contains no keys")

            self._metadata = OIDCMetadata(issuer=issuer, jwks_uri=jwks_uri)
            self._jwks = jwks
            self._cache_expires_at = time.monotonic() + self.settings.oidc_cache_ttl_seconds
            return self._metadata, self._jwks

    async def _get_json(self, url: str) -> dict[str, Any]:
        try:
            response = await self._client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OIDCProviderError("OIDC provider request failed") from exc
        if not isinstance(payload, dict):
            raise OIDCProviderError("OIDC provider returned invalid JSON")
        return payload

    def _validate_provider_url(self, url: str) -> None:
        parsed = httpx.URL(url)
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            raise OIDCProviderError("OIDC provider URL is invalid")
        if self.settings.app_env != "development" and parsed.scheme != "https":
            raise OIDCProviderError("OIDC provider URLs must use HTTPS outside development")

    @staticmethod
    def _find_key(jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
        keys = jwks.get("keys")
        if not isinstance(keys, list):
            return None
        for key in keys:
            if isinstance(key, dict) and key.get("kid") == kid:
                return key
        return None

    def _resolve_role(self, claims: dict[str, Any]) -> UserRole:
        roles: set[str] = set()
        for path in self.settings.oidc_role_claim_list:
            value = self._claim_path(claims, path)
            if isinstance(value, str):
                roles.add(value.casefold())
            elif isinstance(value, list):
                roles.update(str(item).casefold() for item in value)

        admins = {role.casefold() for role in self.settings.oidc_admin_role_list}
        operators = {role.casefold() for role in self.settings.oidc_operator_role_list}
        if roles & admins:
            return UserRole.ADMIN
        if roles & operators:
            return UserRole.OPERATOR
        return UserRole.USER

    def _display_name(self, claims: dict[str, Any], subject: str) -> str:
        for path in self.settings.oidc_display_name_claim_list:
            value = self._claim_path(claims, path)
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
        return subject[:120]

    @staticmethod
    def _claim_path(claims: dict[str, Any], path: str) -> Any:
        current: Any = claims
        for segment in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
        return current
