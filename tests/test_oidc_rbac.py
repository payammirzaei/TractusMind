import json
import time

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.ops_auth import require_ops_admin, require_ops_operator
from app.auth.oidc import OIDCAuthenticator, OIDCAuthenticationError
from app.auth.store import UserIdentity, UserRole
from app.core.config import Settings


class FakeAuthStore:
    def __init__(self) -> None:
        self.oidc_calls: list[dict[str, object]] = []
        self.api_users: dict[str, UserIdentity] = {}

    async def authenticate_oidc_identity(self, **kwargs) -> UserIdentity:
        self.oidc_calls.append(kwargs)
        return UserIdentity(
            user_id="11111111-1111-4111-8111-111111111111",
            display_name=str(kwargs["display_name"]),
            api_key_prefix=None,
            enabled=True,
            role=kwargs["role"],
            auth_type="oidc",
        )

    async def authenticate(self, api_key: str) -> UserIdentity | None:
        return self.api_users.get(api_key)


def _keypair(kid: str) -> tuple[object, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private_key, jwk


def _token(private_key, *, issuer: str, kid: str, roles: list[str]) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "sub": "enterprise-user-42",
            "aud": "tractusmind-api",
            "exp": now + 300,
            "iat": now,
            "name": "Enterprise User",
            "realm_access": {"roles": roles},
        },
        private_key,
        algorithm="RS256",
        headers={"kid": kid},
    )


async def test_oidc_verifies_jwks_and_maps_admin_role() -> None:
    issuer = "https://id.example.com/realms/tractusmind"
    private_key, jwk = _keypair("key-1")
    store = FakeAuthStore()
    settings = Settings(
        app_env="production",
        oidc_enabled=True,
        oidc_issuer_url=issuer,
        oidc_audience="tractusmind-api",
        oidc_admin_roles="tractusmind-admin",
        oidc_operator_roles="tractusmind-operator",
    )
    authenticator = OIDCAuthenticator(settings, store)  # type: ignore[arg-type]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(
                200,
                json={"issuer": issuer, "jwks_uri": f"{issuer}/protocol/openid-connect/certs"},
            )
        return httpx.Response(200, json={"keys": [jwk]})

    await authenticator._client.aclose()
    authenticator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        identity = await authenticator.authenticate(
            _token(
                private_key,
                issuer=issuer,
                kid="key-1",
                roles=["tractusmind-admin"],
            )
        )
    finally:
        await authenticator.close()

    assert identity is not None
    assert identity.role is UserRole.ADMIN
    assert identity.auth_type == "oidc"
    assert store.oidc_calls[0]["issuer"] == issuer
    assert store.oidc_calls[0]["subject"] == "enterprise-user-42"


async def test_oidc_rejects_wrong_audience() -> None:
    issuer = "https://id.example.com/realms/tractusmind"
    private_key, jwk = _keypair("key-1")
    store = FakeAuthStore()
    settings = Settings(
        app_env="production",
        oidc_enabled=True,
        oidc_issuer_url=issuer,
        oidc_audience="different-api",
    )
    authenticator = OIDCAuthenticator(settings, store)  # type: ignore[arg-type]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={"issuer": issuer, "jwks_uri": f"{issuer}/jwks"})
        return httpx.Response(200, json={"keys": [jwk]})

    await authenticator._client.aclose()
    authenticator._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        try:
            await authenticator.authenticate(
                _token(private_key, issuer=issuer, kid="key-1", roles=[])
            )
        except OIDCAuthenticationError:
            pass
        else:
            raise AssertionError("wrong audience token must be rejected")
    finally:
        await authenticator.close()


class OpsAuthStore:
    def __init__(self, role: UserRole) -> None:
        self.role = role

    async def authenticate(self, _api_key: str) -> UserIdentity:
        return UserIdentity(
            user_id="22222222-2222-4222-8222-222222222222",
            display_name="Ops User",
            api_key_prefix="tm_test",
            enabled=True,
            role=self.role,
            auth_type="api_key",
        )


def _rbac_app(role: UserRole) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = OpsAuthStore(role)
    app.state.oidc_auth = None

    @app.get("/operator", dependencies=[Depends(require_ops_operator)])
    async def operator_route() -> dict[str, str]:
        return {"ok": "operator"}

    @app.post("/admin", dependencies=[Depends(require_ops_admin)])
    async def admin_route() -> dict[str, str]:
        return {"ok": "admin"}

    return app


def test_operator_cannot_use_admin_route() -> None:
    client = TestClient(_rbac_app(UserRole.OPERATOR))
    headers = {"Authorization": "Bearer tm_operator"}

    assert client.get("/operator", headers=headers).status_code == 200
    assert client.post("/admin", headers=headers).status_code == 403


def test_admin_inherits_operator_access() -> None:
    client = TestClient(_rbac_app(UserRole.ADMIN))
    headers = {"Authorization": "Bearer tm_admin"}

    assert client.get("/operator", headers=headers).status_code == 200
    assert client.post("/admin", headers=headers).status_code == 200
