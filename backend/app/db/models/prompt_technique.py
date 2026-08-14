"""Catalog of strategies used by Aegis to improve a draft prompt.

Unlike ``PromptCommand``, which is a complete reusable prompt inserted by a
slash command, a technique is composable metadata plus a trusted instruction
fragment.  The UI can explain a technique before selection and the backend can
combine compatible techniques without accepting arbitrary templates from the
browser.
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


PROMPT_TECHNIQUE_CATEGORIES = (
    "text",
    "structure",
    "reasoning",
    "software",
    "agentic",
    "research",
    "content",
    "marketing",
    "social_media",
    "soft_skills",
    "agent_skills",
    "design",
    "automation",
    "image",
    "video",
)
PROMPT_TECHNIQUE_EFFORTS = ("low", "medium", "high", "very_high")
PROMPT_TECHNIQUE_SELECTION_MODES = ("primary", "addon", "both")


class PromptTechnique(Base, TimestampMixin):
    __tablename__ = "prompt_techniques"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_use: Mapped[str] = mapped_column(Text, nullable=False)
    when_to_avoid: Mapped[str | None] = mapped_column(Text)
    requirements: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    compatible_with: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    conflicts_with: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    match_terms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    instruction_template: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text)
    effort: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    selection_mode: Mapped[str] = mapped_column(String(12), nullable=False, default="both")
    template_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            f"category IN {PROMPT_TECHNIQUE_CATEGORIES}",
            name="ck_prompt_techniques_category",
        ),
        CheckConstraint(
            f"effort IN {PROMPT_TECHNIQUE_EFFORTS}",
            name="ck_prompt_techniques_effort",
        ),
        CheckConstraint(
            f"selection_mode IN {PROMPT_TECHNIQUE_SELECTION_MODES}",
            name="ck_prompt_techniques_selection_mode",
        ),
        CheckConstraint("template_version > 0", name="ck_prompt_techniques_template_version"),
        CheckConstraint("sort_order >= 0", name="ck_prompt_techniques_sort_order"),
        Index("ix_prompt_techniques_catalog", "is_active", "category", "sort_order"),
    )
