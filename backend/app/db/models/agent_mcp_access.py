"""Which ForgeHub MCP servers each agent gets, and how its two sensitive actions run (MCP split plan,
decision D4 and the "Agentes e MCP do ForgeHub" screen, Marcelo 2026-11-15; business rules MCP-005,
MCP-023).

One row per agent. ``servers`` lists the optional servers (the core ``forgehub`` server -- Messages --
is implicit and always on; ``forgehub_personal`` only for the agents personal_contacts allows).
``restart_mode`` / ``query_mode``: ``direct`` runs at once, ``approval`` turns the call into a request
for Marcelo's approval (core/agent_action_requests.py). Nothing is ever refused.
"""
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

ACTION_MODES = ("direct", "approval")


class AgentMcpAccess(Base, TimestampMixin):
    __tablename__ = "agent_mcp_access"
    __table_args__ = (
        CheckConstraint("restart_mode IN ('direct','approval')", name="ck_agent_mcp_access_restart_mode"),
        CheckConstraint("query_mode IN ('direct','approval')", name="ck_agent_mcp_access_query_mode"),
    )

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.agents.id", ondelete="CASCADE"), primary_key=True
    )
    servers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    restart_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="approval", server_default="approval")
    query_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="approval", server_default="approval")
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
