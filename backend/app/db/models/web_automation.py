"""Reusable structured browser routines and standalone (Product-less) apps.

A routine or macro instruction set targets exactly one of Product or
StandaloneApp -- see WEB_AUTOMATION_TARGET_CHECK on each table. StandaloneApp
exists for pointing the shared Workspace browser (and Automations/Macro) at a
site that doesn't warrant full Product onboarding (no version/pipeline/
module) -- just a name and a URL.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

WEB_AUTOMATION_TARGET_CHECK = (
    "(product_id IS NOT NULL AND standalone_app_id IS NULL) "
    "OR (product_id IS NULL AND standalone_app_id IS NOT NULL)"
)


class StandaloneApp(Base, TimestampMixin):
    __tablename__ = "standalone_apps"
    __table_args__ = (UniqueConstraint("name", name="uq_standalone_app_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)


class WebAutomationRoutine(Base, TimestampMixin):
    __tablename__ = "web_automation_routines"
    __table_args__ = (
        UniqueConstraint("product_id", "standalone_app_id", "name", name="uq_web_automation_routine_target_name"),
        CheckConstraint(WEB_AUTOMATION_TARGET_CHECK, name="ck_web_automation_routine_one_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=True
    )
    standalone_app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.standalone_apps.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)


class MacroInstructionSet(Base, TimestampMixin):
    """A saved list of free-text instructions for Athos to carry out on the
    shared Workspace browser -- unlike WebAutomationRoutine's structured
    steps, these are natural language and only ever "run" by seeding the
    Assistant composer (see MANUAL.md's Assistant Policy: explicit
    instruction from the composer, never auto-sent)."""

    __tablename__ = "macro_instruction_sets"
    __table_args__ = (
        UniqueConstraint("product_id", "standalone_app_id", "name", name="uq_macro_instruction_set_target_name"),
        CheckConstraint(WEB_AUTOMATION_TARGET_CHECK, name="ck_macro_instruction_set_one_target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=True
    )
    standalone_app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.standalone_apps.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    lines: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
