import asyncio
import hashlib
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.auth.models import UserAccount
from app.db import verify_database_revision


@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    display_name: str
    api_key_prefix: str
    enabled: bool


@dataclass(frozen=True)
class UserCredential:
    user: UserIdentity
    api_key: str


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _new_api_key() -> str:
    return "tm_" + secrets.token_urlsafe(32)


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

    async def create_user(self, display_name: str) -> UserCredential:
        await self.ensure_schema()
        api_key = _new_api_key()
        async with self.sessions.begin() as session:
            user = UserAccount(
                display_name=display_name.strip(),
                api_key_prefix=api_key[:12],
                api_key_hash=_hash_api_key(api_key),
            )
            session.add(user)
            await session.flush()
            identity = self._identity(user)
        return UserCredential(user=identity, api_key=api_key)

    async def authenticate(self, api_key: str) -> UserIdentity | None:
        await self.ensure_schema()
        digest = _hash_api_key(api_key)
        async with self.sessions() as session:
            user = await session.scalar(
                select(UserAccount).where(
                    UserAccount.api_key_hash == digest,
                    UserAccount.enabled.is_(True),
                )
            )
        return self._identity(user) if user is not None else None

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
            if user is None:
                return None
            user.api_key_prefix = api_key[:12]
            user.api_key_hash = _hash_api_key(api_key)
            await session.flush()
            identity = self._identity(user)
        return UserCredential(user=identity, api_key=api_key)

    async def set_enabled(self, user_id: str, enabled: bool) -> UserIdentity | None:
        await self.ensure_schema()
        async with self.sessions.begin() as session:
            user = await session.get(UserAccount, user_id)
            if user is None:
                return None
            user.enabled = enabled
            await session.flush()
            identity = self._identity(user)
        return identity

    @staticmethod
    def _identity(user: UserAccount) -> UserIdentity:
        return UserIdentity(
            user_id=user.user_id,
            display_name=user.display_name,
            api_key_prefix=user.api_key_prefix,
            enabled=user.enabled,
        )
