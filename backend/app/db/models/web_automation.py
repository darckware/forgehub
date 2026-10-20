"""Reusable structured browser routines and standalone (Product-less) apps.

A routine or macro instruction set targets exactly one of Product or
StandaloneApp -- see WEB_AUTOMATION_TARGET_CHECK on each table. StandaloneApp
exists for pointing the shared Workspace browser (and Automations/Macro) at a
site that doesn't warrant full Product onboarding (no version/pipeline/
module) -- just a name and a URL.

`WebAutomationTestRun` (added for background app testing, 2026-07-28) records
one execution of a routine -- or an ad hoc run with inline steps and no saved
routine (the MCP-tool trigger path never has a saved routine to point at) --
in either `mode`: "background" (a dedicated, isolated CDP Chromium the
operator never has to watch, see host-bridge/app.py) or "visible" (delegates
to the existing shared Workspace Browser's synchronous `run_routine`, so the
operator can watch it live in the Web App pane; the row here exists purely
so the run lands in the same history/status list either way). Carries its
own product_id/standalone_app_id (same one-of-two-targets shape as the
routine/macro tables above) rather than only deriving it from `routine_id`,
since an ad hoc run has no routine row to derive it from.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

WEB_AUTOMATION_TARGET_CHECK = (
    "(product_id IS NOT NULL AND standalone_app_id IS NULL) "
    "OR (product_id IS NULL AND standalone_app_id IS NOT NULL)"
)

WEB_AUTOMATION_TEST_RUN_MODES = ("background", "visible")
WEB_AUTOMATION_TEST_RUN_TRIGGERS = ("slash_command", "mcp_tool", "manual")
WEB_AUTOMATION_TEST_RUN_STATUSES = ("queued", "running", "passed", "failed", "error")


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
    # Whether this routine shows up as a background-test option (the
    # "Background tests" tab / the /testar dialog). A routine can exist for
    # other purposes (macro reference, ad hoc /run from the automation
    # panel) without being offered there.
    background_test_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


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


class WebAutomationTestRun(Base, TimestampMixin):
    __tablename__ = "web_automation_test_runs"
    __table_args__ = (
        CheckConstraint(WEB_AUTOMATION_TARGET_CHECK, name="ck_web_automation_test_run_one_target"),
        CheckConstraint(
            "mode IN ('background', 'visible')", name="ck_web_automation_test_run_mode"
        ),
        CheckConstraint(
            "triggered_by IN ('slash_command', 'mcp_tool', 'manual')",
            name="ck_web_automation_test_run_triggered_by",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'error')",
            name="ck_web_automation_test_run_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable: an ad hoc run (mcp_tool trigger with inline steps, or no
    # saved routine yet) has nothing to point at here.
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.web_automation_routines.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.products.id", ondelete="CASCADE"), nullable=True
    )
    standalone_app_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.standalone_apps.id", ondelete="CASCADE"), nullable=True
    )
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued", server_default="queued")
    # Correlates to the host-bridge's own job id for mode="background" (the
    # isolated CDP instance's test-run id) -- unused for mode="visible",
    # which finishes synchronously within the dispatching request.
    bridge_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Plain text/markdown, same shape as AgentDemand.dispatch_result -- a
    # human-readable pass/fail narrative, not just the raw step JSON.
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_paths: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
