"""PromptCommand model — reusable chat prompt commands.

Rows in this table back the Chat Commands page and are surfaced in the chat
composer's slash-command picker beside Hermes-native commands. Selecting one
inserts its Markdown prompt into the composer; it is not executed by Hermes's
SAFE_SLASH_COMMANDS dispatcher.
"""
import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PromptCommand(Base, TimestampMixin):
    __tablename__ = "prompt_commands"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(240), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
