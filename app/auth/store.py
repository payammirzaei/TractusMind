import asyncio
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

import jwt
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.auth.models import UserAccount
from app.db import verify_database_revision

_SESSION_PREFIX = "tm_session."
_SESSION_TYPE = "tractusmind-session"
_PASSWORD_DUMMY_SALT = bytes(32)


class UserRole(StrEnum):
    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return {
            UserRole.USER: 0,
            UserRole.OPERATOR: 1,
            UserRole.ADMIN: 2,
        }[self]

    def allows(self, required: "UserRole") -> bool:
        return self.rank >= required.rank


class ExternalRoleManagedError(RuntimeError):
    pass


@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    display_name: str
    api_key_prefix: str | None
    enabled: bool
    role: UserRole
    auth_type: str
    username: str | None = None


@dataclass(frozen=True)
class UserCredential:
    user: UserIdentity
    api_key: str


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _new_api_key() -> str:
    return "tm_" + secrets.token_urlsafe(32)


def _normalize_username(username: str) -> str:
    return username.strip().casefold()


def _password_digest(password: str, salt: bytes) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    ).hex()


class AuthStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._schema_ready = False
        self._schema_lock = asyncio.Lock()

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with self._schema_lock:
            if self._schema_ready:
                return
            await verify_database_revision(self.engine)
            self._schema_ready = True

    async def create_user(
        self,
        display_name: str,
        *,
        role: UserRole = UserRole.USER,
    ) -> UserCredential:
        await self.ensure_schema()
        api_key = _new_api_key()
        async with self.sessions.begin() as session:
            user = UserAccount(
                display_name=display_name.strip(),
                auth_type="api_key",
                role=role.value,
                api_key_prefix=api_key[:12],
                api_key_hash=_hash_api_key(api_key),
            )
            session.add(user)
            await session.flush()
            identity = self._identity(user)
        return UserCredential(user=identity, api_key=api_key)

    async def set_password_user(
        self,
        *,
        username: str,
        password: str,
        display_name: str,
        role: UserRole = UserRole.USER,
        user_id: str | None = None,
    ) -> UserIdentity:
        """Create or convert one local account without ever persisting the plaintext password."""
        await self.ensure_schema()
        normalized = _normalize_username(username)
        if not normalized or len(normalized) > 80:
            raise ValueError("username must contain 1-80 characters")
        if len(password) < 12:
            raise ValueError("password must contain at least 12 characters")
        clean_name = display_name.strip()
        if not clean_name:
            raise ValueError("display_name must not be blank")

        salt = secrets.token_bytes(32)
        password_hash = _password_digest(password, salt)
        async with self.sessions.begin() as session:
            user = await session.get(UserAccount, user_id) if user_id else None
            if user is None:
                user = await session.scalar(
                    select(UserAccount).where(UserAccount.username == normalized)
                )
            if user is None:
                user = UserAccount(user_id=user_id or str(uuid4()), display_name=clean_name)
                session.add(user)
            else:
                conflicting = await session.scalar(
                    select(UserAccount).where(
                        UserAccount.username == normalized,
                        UserAccount.user_id != user.user_id,
                    )
                )
                if conflicting is not None:
                    raise ValueError("username is already in use")

            user.display_name = clean_name[:120]
            user.auth_type = "password"
            user.role = role.value
            user.username = normalized
            user.password_salt = salt.hex()
            user.password_hash = password_hash
            user.api_key_prefix = None
            user.api_key_hash = None
            user.oidc_issuer = None
            user.oidc_subject = None
            user.enabled = True
            await session.flush()
            return self._identity(user)

    async def authenticate(self, api_key: str) -> UserIdentity | None:
        await self.ensure_schema()
        digest = _hash_api_key(api_key)
        async with self.sessions() as session:
            user = await session.scalar(
                select(UserAccount).where(
                    UserAccount.auth_type == "api_key",
                    UserAccount.api_key_hash == digest,
                    UserAccount.enabled.is_(True),
                )
            )
        return self._identity(user) if user is not None else None

    async def authenticate_password(self, username: str, password: str) -> UserIdentity | None:
        await self.ensure_schema()
        normalized = _normalize_username(username)
        async with self.sessions() as session:
            user = await session.scalar(
                select(UserAccount).where(
                    UserAccount.auth_type == "password",
                    UserAccount.username == normalized,
                    UserAccount.enabled.is_(True),
                )
            )

        salt = _PASSWORD_DUMMY_SALT
        expected = "0" * 64
        if user is not None and user.password_salt and user.password_hash:
            try:
                salt = bytes.fromhex(user.password_salt)
            except ValueError:
                return None
            expected = user.password_hash
        candidate = _password_digest(password, salt)
        if user is None or not secrets.compare_digest(candidate, expected):
            return None
        return self._identity(user)

    @staticmethod
    def issue_session(
        identity: UserIdentity,
        *,
        signing_key: str,
        ttl_seconds: int,
    ) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": identity.user_id,
            "typ": _SESSION_TYPE,
            "iat": now,
            "exp": now + timedelta(seconds=ttl_seconds),
            "jti": secrets.token_urlsafe(18),
        }
        token = jwt.encode(payload, signing_key, algorithm="HS256")
        return _SESSION_PREFIX + token

    async def authenticate_session(
        self,
        token: str,
        *,
        signing_key: str,
    ) -> UserIdentity | None:
        await self.ensure_schema()
        if not token.startswith(_SESSION_PREFIX):
            return None
        encoded = token.removeprefix(_SESSION_PREFIX)
        try:
            payload = jwt.decode(encoded, signing_key, algorithms=["HS256"])
        except jwt.InvalidTokenError:
            return None
        if payload.get("typ") != _SESSION_TYPE:
            return None
        user_id = payload.get("sub")
        if not isinstance(user_id, str) or not user_id:
            return None
        async with self.sessions() as session:
            user = await session.get(UserAccount, user_id)
        if user is None or not user.enabled or user.auth_type != "password":
            return None
        return self._identity(user)

    async def authenticate_oidc_identity(
        self,
        *,
        issuer: str,
        subject: str,
        display_name: str,
        role: UserRole,
    ) -> UserIdentity | None:
        """Create/update one trusted external identity without overriding local disable state."""
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            statement = (
                insert(UserAccount)
                .values(
                    user_id=str(uuid4()),
                    display_name=display_name[:120],
                    auth_type="oidc",
                    role=role.value,
                    oidc_issuer=issuer,
                    oidc_subject=subject,
                    username=None,
                    password_salt=None,
                    password_hash=None,
                    api_key_prefix=None,
                    api_key_hash=None,
                    enabled=True,
                )
                .on_conflict_do_nothing(index_elements=["oidc_issuer", "oidc_subject"])
            )
            await session.execute(statement)
            user = await session.scalar(
                select(UserAccount).where(
                    UserAccount.auth_type == "oidc",
                    UserAccount.oidc_issuer == issuer,
                    UserAccount.oidc_subject == subject,
                )
            )
            if user is None:
                raise RuntimeError("OIDC identity upsert did not resolve a user")
            if not user.enabled:
                return None
            user.display_name = display_name[:120]
            user.role = role.value
            await session.flush()
            return self._identity(user)

    async def list_users(self, limit: int = 200) -> list[UserIdentity]:
        await self.ensure_schema()
        statement = select(UserAccount).order_by(UserAccount.created_at.desc()).limit(limit)
        async with self.sessions() as session:
            users = (await session.scalars(statement)).all()
        return [self._identity(user) for user in users]

    async def rotate_api_key(self, user_id: str) -> UserCredential | None:
        await self.ensure_schema()
        api_key = _new_api_key()
        async with self.sessions.begin() as session:
            user = await session.get(UserAccount, user_id)
            if user is None or user.auth_type != "api_key":
                return None
            user.api_key_prefix = api_key[:12]
            user.api_key_hash = _hash_api_key(api_key)
            await session.flush()
            identity = self._identity(user)
        return UserCredential(user=identity, api_key=api_key)

    async def update_user(
        self,
        user_id: str,
        *,
        enabled: bool | None = None,
        role: UserRole | None = None,
    ) -> UserIdentity | None:
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            user = await session.get(UserAccount, user_id)
            if user is None:
                return None
            if role is not None and user.auth_type == "oidc":
                raise ExternalRoleManagedError(
                    "OIDC user roles are managed by identity-provider claims"
                )
            if enabled is not None:
                user.enabled = enabled
            if role is not None:
                user.role = role.value
            await session.flush()
            return self._identity(user)

    async def set_enabled(self, user_id: str, enabled: bool) -> UserIdentity | None:
        return await self.update_user(user_id, enabled=enabled)

    @staticmethod
    def _identity(user: UserAccount) -> UserIdentity:
        return UserIdentity(
            user_id=user.user_id,
            display_name=user.display_name,
            api_key_prefix=user.api_key_prefix,
            enabled=user.enabled,
            role=UserRole(user.role),
            auth_type=user.auth_type,
            username=user.username,
        )
