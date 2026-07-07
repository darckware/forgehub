"""SQLAlchemy models for the Tool domain — registry of agent-built tools.

Table owned by this module: agent_tools.

Every Hermes agent builds its own operational tooling (e.g. Aegis, the
cybersecurity agent, writes network scanners, system monitors, report
generators). This registry records each of those tools: where the file
lives on disk (`file_path`), what it does (`description`), which agent is
responsible for it (`agent_id` → company.agents), and a free-form
`category` (network, monitoring, reporting, ...). It is an inventory tied
to the responsible agent — the file itself stays wherever the agent keeps
it; ForgeHub only records and governs the reference.

Conventions (binding, see db/base.py):
    - UUID PK, Python-side default (uuid.uuid4), never server-side.
    - TimestampMixin provides created_at/updated_at.
    - Cross-domain FK declared as a string target ("company.agents.id");
      the Agent model is intentionally not imported here.
    - Status is String + CheckConstraint, not a native enum. `category` is
      deliberately NOT check-constrained — it is an open taxonomy that
      grows as agents build new kinds of tools.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

AGENT_TOOL_STATUSES = ("active", "deprecated", "archived")


class AgentTool(Base, TimestampMixin):
    """One tool built and maintained by an agent."""

    __tablename__ = "agent_tools"
    __table_args__ = (
        UniqueConstraint("agent_id", "name", name="uq_agent_tools_agent_id_name"),
        CheckConstraint(
            f"status IN {AGENT_TOOL_STATUSES}", name="ck_agent_tools_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # What the tool does — required: an inventory entry without a functional
    # description is useless for governance.
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Absolute path (or host-meaningful path) of the tool's file.
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
