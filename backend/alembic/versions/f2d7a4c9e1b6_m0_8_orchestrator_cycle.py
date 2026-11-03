"""M0.8: orchestrator decision cycle (availability, locks, context pack).

Plano Integrado Onda 1, M0.8 (docs/architecture/MISSION_ORCHESTRATOR_CYCLE_SPEC.md
§2-§6, MCP_MISSION_TOOLS_SPEC.md §6.1):

- ``agent_availability``: an executor out of quota until a known time (§3.3).
- ``mission_cycle_locks``: Marcelo's lock on a mission's cycle or one task (§5).
- ``mission_context_versions``: the versioned context pack (§3.6).
- ``mission_dependencies``: a mission starts after another completes (§6.3).
- ``mission_skill_proposals``: a missing skill becomes a proposal (§3.6).
- ``agent_routines.mission_project_id``: the routine that runs a mission's cycle (§2.1).
- ``project_missions.cycle_rerun_requested`` / ``cycle_event_cursor`` (§2.2).
- ``agent_demands.mission_context_version_id``: the pack version a dispatch carried.

Only additions; downgrade drops them (decisions stay in ``mission_decisions``).

Revision ID: f2d7a4c9e1b6
Revises: f3a9c6d1b8e2
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2d7a4c9e1b6"
down_revision = "f3a9c6d1b8e2"
branch_labels = None
depends_on = None

SCHEMA = "company"
UUID = postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "agent_availability",
        sa.Column("agent_id", UUID, sa.ForeignKey(f"{SCHEMA}.agents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("unavailable_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("source_demand_id", UUID, sa.ForeignKey(f"{SCHEMA}.agent_demands.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("recorded_by", sa.String(150), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_agent_availability_reason"),
        schema=SCHEMA,
    )
    op.create_table(
        "mission_cycle_locks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("mission_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey(f"{SCHEMA}.project_tasks.id", ondelete="CASCADE"), nullable=True),
        sa.Column("locked_by", sa.String(150), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", sa.String(150), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_cycle_locks_reason"),
        schema=SCHEMA,
    )
    op.create_index("ix_mission_cycle_locks_mission", "mission_cycle_locks",
                    ["mission_project_id", "released_at"], schema=SCHEMA)
    op.create_table(
        "mission_context_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_type", sa.String(10), nullable=False),
        sa.Column("created_by_id", UUID, nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("project_id", "version", name="uq_mission_context_versions_version"),
        sa.CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="ck_mission_context_versions_hash"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_context_versions_reason"),
        sa.CheckConstraint("created_by_type IN ('user', 'agent', 'system')",
                           name="ck_mission_context_versions_created_by_type"),
        schema=SCHEMA,
    )
    op.create_table(
        "mission_dependencies",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("mission_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("depends_on_mission_project_id", UUID,
                  sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.String(150), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("mission_project_id", "depends_on_mission_project_id",
                            name="uq_mission_dependencies_pair"),
        sa.CheckConstraint("mission_project_id <> depends_on_mission_project_id",
                           name="ck_mission_dependencies_self"),
        schema=SCHEMA,
    )
    op.create_table(
        "mission_skill_proposals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("mission_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey(f"{SCHEMA}.project_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("skill_id", UUID, sa.ForeignKey(f"{SCHEMA}.skills.id", ondelete="SET NULL"), nullable=True),
        sa.Column("agent_id", UUID, sa.ForeignKey(f"{SCHEMA}.agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_agent_id", UUID, sa.ForeignKey(f"{SCHEMA}.agents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("proposed_by", sa.String(150), nullable=False),
        sa.Column("demand_id", UUID, sa.ForeignKey(f"{SCHEMA}.agent_demands.id", ondelete="SET NULL"), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('assign_other_agent', 'grant_to_agent', 'create_skill')",
                           name="ck_mission_skill_proposals_kind"),
        sa.CheckConstraint("status IN ('proposed', 'accepted', 'rejected')", name="ck_mission_skill_proposals_status"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_skill_proposals_reason"),
        schema=SCHEMA,
    )
    op.create_index("ix_mission_skill_proposals_mission", "mission_skill_proposals",
                    ["mission_project_id", "created_at"], schema=SCHEMA)

    op.add_column("agent_routines", sa.Column(
        "mission_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="SET NULL"), nullable=True,
    ), schema=SCHEMA)
    op.create_index("ix_company_agent_routines_mission_project_id", "agent_routines", ["mission_project_id"],
                    schema=SCHEMA)
    op.add_column("project_missions", sa.Column(
        "cycle_rerun_requested", sa.Boolean(), nullable=False, server_default=sa.false(),
    ), schema=SCHEMA)
    op.add_column("project_missions", sa.Column("cycle_event_cursor", sa.DateTime(timezone=True), nullable=True),
                  schema=SCHEMA)
    op.add_column("agent_demands", sa.Column(
        "mission_context_version_id", UUID,
        sa.ForeignKey(f"{SCHEMA}.mission_context_versions.id", ondelete="SET NULL"), nullable=True,
    ), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("agent_demands", "mission_context_version_id", schema=SCHEMA)
    op.drop_column("project_missions", "cycle_event_cursor", schema=SCHEMA)
    op.drop_column("project_missions", "cycle_rerun_requested", schema=SCHEMA)
    op.drop_index("ix_company_agent_routines_mission_project_id", table_name="agent_routines", schema=SCHEMA)
    op.drop_column("agent_routines", "mission_project_id", schema=SCHEMA)
    op.drop_index("ix_mission_skill_proposals_mission", table_name="mission_skill_proposals", schema=SCHEMA)
    op.drop_table("mission_skill_proposals", schema=SCHEMA)
    op.drop_table("mission_dependencies", schema=SCHEMA)
    op.drop_table("mission_context_versions", schema=SCHEMA)
    op.drop_index("ix_mission_cycle_locks_mission", table_name="mission_cycle_locks", schema=SCHEMA)
    op.drop_table("mission_cycle_locks", schema=SCHEMA)
    op.drop_table("agent_availability", schema=SCHEMA)
