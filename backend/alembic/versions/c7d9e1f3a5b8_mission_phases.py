"""mission phases: ordered executor-project links with homologation and approval

2026-11-12 (docs/architecture/MISSION_PHASES_PLAN.md): a
mission_project_links row created through POST /missions/{id}/phases is a
phase of its mission (``is_phase``) -- position, name, objective,
phase_status and the homologation/decision record. Planning items and tasks
gain a nullable ``position`` (order inside the project / planning item).
PROJECT_AGENT_ROLES gains ``homologation``, so the four CHECKs built from that
tuple are recreated.

Hand-written, same pattern as f4b8d1a6c3e9 for the role CHECKs. Existing
links are NOT turned into phases: they stay ``is_phase = false`` with
position/name NULL, so the plan hash of an already-baselined mission does not
change.

Revision ID: c7d9e1f3a5b8
Revises: a3c5e7f9b1d2
Create Date: 2026-11-12
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c7d9e1f3a5b8"
down_revision = "a3c5e7f9b1d2"
branch_labels = None
depends_on = None

SCHEMA = "company"

PREVIOUS_PROJECT_AGENT_ROLES = (
    "coordinator", "planner", "architect", "designer", "developer",
    "data_engineer", "qa", "security_reviewer", "reviewer",
    "release_manager", "documentation", "compliance", "knowledge_management",
)
PROJECT_AGENT_ROLES = PREVIOUS_PROJECT_AGENT_ROLES + ("homologation",)

PHASE_STATUSES = ("planned", "in_progress", "homologating", "awaiting_approval", "approved", "returned")

# (constraint, table, expression template)
ROLE_CHECKS = (
    ("ck_project_agent_memberships_role", "project_agent_memberships", "role IN {roles!r}"),
    ("ck_agents_default_role", "agents", "default_role IS NULL OR default_role IN {roles!r}"),
    ("ck_chat_channel_members_role", "chat_channel_members", "role IS NULL OR role IN {roles!r}"),
    ("ck_chat_channel_tasks_role_required", "chat_channel_tasks", "role_required IS NULL OR role_required IN {roles!r}"),
)


def _recreate_role_checks(roles: tuple[str, ...]) -> None:
    for name, table, template in ROLE_CHECKS:
        op.drop_constraint(name, table, schema=SCHEMA, type_="check")
        op.create_check_constraint(name, table, template.format(roles=roles), schema=SCHEMA)


def upgrade() -> None:
    op.add_column("mission_project_links", sa.Column(
        "is_phase", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("position", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("name", sa.String(255), nullable=True), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("objective", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column(
        "phase_status", sa.String(24), nullable=False, server_default="planned"), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column(
        "homologator_agent_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey(f"{SCHEMA}.agents.id", name="fk_mission_project_links_homologator_agent_id"),
        nullable=True), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column(
        "homologation_demand_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey(f"{SCHEMA}.agent_demands.id", ondelete="SET NULL",
                      name="fk_mission_project_links_homologation_demand_id"),
        nullable=True), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("homologation_verdict", sa.String(16), nullable=True),
                  schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("homologation_summary", sa.Text(), nullable=True),
                  schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("homologation_evidence", sa.Text(), nullable=True),
                  schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("homologated_at", sa.DateTime(timezone=True), nullable=True),
                  schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("decided_by", sa.String(150), nullable=True), schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
                  schema=SCHEMA)
    op.add_column("mission_project_links", sa.Column("decision_reason", sa.Text(), nullable=True), schema=SCHEMA)

    op.create_unique_constraint(
        "uq_mission_project_links_position", "mission_project_links", ["mission_project_id", "position"],
        schema=SCHEMA, deferrable=True, initially="DEFERRED",
    )
    op.create_check_constraint("ck_mission_project_links_position", "mission_project_links", "position >= 1",
                               schema=SCHEMA)
    op.create_check_constraint(
        "ck_mission_project_links_phase_fields", "mission_project_links",
        "NOT is_phase OR (position IS NOT NULL AND name IS NOT NULL)", schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_mission_project_links_phase_status", "mission_project_links",
        f"phase_status IN {PHASE_STATUSES!r}", schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_mission_project_links_homologation_verdict", "mission_project_links",
        "homologation_verdict IS NULL OR homologation_verdict IN ('approved', 'rejected')", schema=SCHEMA,
    )

    op.add_column("planning_items", sa.Column("position", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column("project_tasks", sa.Column("position", sa.Integer(), nullable=True), schema=SCHEMA)

    _recreate_role_checks(PROJECT_AGENT_ROLES)


def downgrade() -> None:
    # A homologation membership has no place in the previous vocabulary.
    op.execute(f"UPDATE {SCHEMA}.project_agent_memberships SET status = 'released', role = 'reviewer' "
               "WHERE role = 'homologation'")
    op.execute(f"UPDATE {SCHEMA}.agents SET default_role = NULL WHERE default_role = 'homologation'")
    op.execute(f"UPDATE {SCHEMA}.chat_channel_members SET role = NULL WHERE role = 'homologation'")
    op.execute(f"UPDATE {SCHEMA}.chat_channel_tasks SET role_required = NULL WHERE role_required = 'homologation'")
    _recreate_role_checks(PREVIOUS_PROJECT_AGENT_ROLES)

    op.drop_column("project_tasks", "position", schema=SCHEMA)
    op.drop_column("planning_items", "position", schema=SCHEMA)

    for name in ("ck_mission_project_links_homologation_verdict", "ck_mission_project_links_phase_status",
                 "ck_mission_project_links_phase_fields", "ck_mission_project_links_position"):
        op.drop_constraint(name, "mission_project_links", schema=SCHEMA, type_="check")
    op.drop_constraint("uq_mission_project_links_position", "mission_project_links", schema=SCHEMA, type_="unique")
    for column in ("decision_reason", "decided_at", "decided_by", "homologated_at", "homologation_evidence",
                   "homologation_summary", "homologation_verdict", "homologation_demand_id",
                   "homologator_agent_id", "phase_status", "objective", "name", "position", "is_phase"):
        op.drop_column("mission_project_links", column, schema=SCHEMA)
