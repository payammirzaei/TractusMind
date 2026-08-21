from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.state.models import Base


class UserAccount(Base):
    __tablename__ = "app_user"
    __table_args__ = (
        Index("ux_app_user_oidc_identity", "oidc_issuer", "oidc_subject", unique=True),
        Index("ux_app_user_username", "username", unique=True),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    display_name: Mapped[str] = mapped_column(String(120))
    auth_type: Mapped[str] = mapped_column(String(20), default="api_key", index=True)
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    password_salt: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    api_key_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    api_key_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    oidc_issuer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
