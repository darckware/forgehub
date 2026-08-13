"""rename demand backlog to incubation and add its invariants

Two changes, one concept (2026-08-13).

1. `origin_type` value "backlog" -> "incubation". The product already
   spends the word "backlog" on version planning (the `backlog` domain's
   PlanningItem/FeatureRequest/BugReport), and Marcelo separated the two
   explicitly: "Backlog de tarefas de projeto é planejamento futuro e
   backlog de messages é outro conceito". Same shape as the migration that
   retired the "demand" value (f1b3d5a7c9e2): backfill every existing row
   first, then tighten the CHECK, so no row is ever momentarily illegal.

2. The three invariants that make a forgotten item unrepresentable, as
   real constraints rather than route-layer politeness -- an owner, an
   explicit state (with a mandatory reason when dropped), and a deadline
   to decide. See AgentDemand's own docstrings for the reasoning.

Existing rows are backfilled owner = target_agent_id -> from_agent_id.
Any row where neither exists cannot satisfy invariant 1 and is archived
instead of being deleted or given a fabricated owner: it is exactly the
ownerless item this redesign removes, and silently inventing an owner
would hide that it ever existed.

Revision ID: c4e81a90f3d7
Revises: f4b8d1a6c3e9
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4e81a90f3d7'
down_revision: Union[str, Sequence[str], None] = 'f4b8d1a6c3e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"
TABLE = "agent_demands"


def upgrade() -> None:
    # --- 1. new columns (all nullable: a task carries none of them) ---
    op.add_column(
        TABLE,
        sa.Column("incubation_owner_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_agent_demands_incubation_owner_id_agents",
        TABLE,
        "agents",
        ["incubation_owner_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.add_column(TABLE, sa.Column("incubation_state", sa.String(length=20), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("matures_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("drop_reason", sa.Text(), nullable=True), schema=SCHEMA)

    # --- 2. backfill BEFORE tightening any constraint ---
    # Drop the old value check first: the UPDATE below writes a value the
    # existing constraint would reject.
    op.drop_constraint("ck_agent_demands_origin_type", TABLE, schema=SCHEMA, type_="check")
    op.execute(f"UPDATE {SCHEMA}.{TABLE} SET origin_type = 'incubation' WHERE origin_type = 'backlog'")

    # Ownerless rows can't satisfy invariant 1. Archive rather than delete
    # or invent an owner -- see this module's docstring.
    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
           SET status = 'archived'
         WHERE origin_type = 'incubation'
           AND target_agent_id IS NULL
           AND from_agent_id IS NULL
           AND status <> 'archived'
        """
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
           SET origin_type = 'task'
         WHERE origin_type = 'incubation'
           AND target_agent_id IS NULL
           AND from_agent_id IS NULL
        """
    )

    op.execute(
        f"""
        UPDATE {SCHEMA}.{TABLE}
           SET incubation_owner_id = COALESCE(target_agent_id, from_agent_id),
               incubation_state    = 'incubating',
               matures_at          = COALESCE(created_at, now()) + interval '3 days'
         WHERE origin_type = 'incubation'
        """
    )

    # --- 3. constraints, now that every row already satisfies them ---
    op.alter_column(TABLE, "origin_type", server_default="incubation", schema=SCHEMA)
    op.create_check_constraint(
        "ck_agent_demands_origin_type",
        TABLE,
        "origin_type IN ('task', 'incubation')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_agent_demands_incubation_owner",
        TABLE,
        "origin_type <> 'incubation' OR incubation_owner_id IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_agent_demands_incubation_state",
        TABLE,
        "incubation_state IS NULL OR incubation_state IN "
        "('incubating', 'decision_pending', 'promoted', 'dropped')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_agent_demands_incubation_state_required",
        TABLE,
        "origin_type <> 'incubation' OR incubation_state IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_agent_demands_drop_reason",
        TABLE,
        "incubation_state <> 'dropped' OR drop_reason IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_agent_demands_matures_at",
        TABLE,
        "origin_type <> 'incubation' OR matures_at IS NOT NULL",
        schema=SCHEMA,
    )


def downgrade() -> None:
    for name in (
        "ck_agent_demands_matures_at",
        "ck_agent_demands_drop_reason",
        "ck_agent_demands_incubation_state_required",
        "ck_agent_demands_incubation_state",
        "ck_agent_demands_incubation_owner",
        "ck_agent_demands_origin_type",
    ):
        op.drop_constraint(name, TABLE, schema=SCHEMA, type_="check")

    op.execute(f"UPDATE {SCHEMA}.{TABLE} SET origin_type = 'backlog' WHERE origin_type = 'incubation'")
    op.alter_column(TABLE, "origin_type", server_default="backlog", schema=SCHEMA)
    op.create_check_constraint(
        "ck_agent_demands_origin_type",
        TABLE,
        "origin_type IN ('task', 'backlog')",
        schema=SCHEMA,
    )

    op.drop_constraint(
        "fk_agent_demands_incubation_owner_id_agents", TABLE, schema=SCHEMA, type_="foreignkey"
    )
    for col in ("drop_reason", "matures_at", "incubation_state", "incubation_owner_id"):
        op.drop_column(TABLE, col, schema=SCHEMA)
