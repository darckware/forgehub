"""User model for authentication and access control."""
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

UI_LANGUAGES = ("en", "pt-BR", "es")


class User(Base, TimestampMixin):
    """Application user — owns an auth token and optionally has admin rights."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Self-uploaded profile photo, stored as a "data:image/...;base64,..."
    # URI directly in the row -- no static-file mount exists for user
    # content yet, and avatars are small enough that this is simpler than
    # standing up file storage just for this.
    avatar_data_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # TOTP two-factor authentication fields.
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    totp_recovery_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    # App shell language (sidebar, dialogs, forms) -- independent of the
    # AI chat's response language (SystemConfig.chat_response_language).
    # Frontend applies it via i18next; see frontend/src/i18n/index.ts.
    ui_language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="pt-BR", server_default="pt-BR"
    )

    profile: Mapped[object] = relationship(
        "Profile", foreign_keys=[profile_id], lazy="select"
    )

    __table_args__ = (
        CheckConstraint("ui_language IN ('en', 'pt-BR', 'es')", name="ck_users_ui_language"),
    )
