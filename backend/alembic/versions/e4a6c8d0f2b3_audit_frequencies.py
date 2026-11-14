"""Auditor frequencies: audit_checks.frequency and the "audit" routine kind

2026-11-13 (Marcelo): every Auditor check is classified by frequency and the
audit schedule moves from the single Hermes cron `ecosystem-weekly-audit`
(Athos, Sunday 19:00, every enabled check at once) to four Operação 24x7
routines, one per tier, each running its tier's checks as one Auditor batch.

- ``audit_checks.frequency`` (daily|weekly|monthly|quarterly, NOT NULL,
  default weekly) backfilled from the approved classification by name. A
  check not in it keeps "weekly", the frequency the Sunday audit gave it.
- ``agent_routines.kind`` gains "audit", with ``audit_frequency`` (set exactly
  when kind = 'audit', unique per tier) and ``agent_routine_runs.audit_batch_id``
  (the batch that is the occurrence's evidence).

The four routines themselves are *not* created here: they belong to the Athos
agent row, which is data, not schema. ``python -m app.core.audit_routines``
creates them, disabled (docs/runbooks/auditor-frequencies.md).

Revision ID: e4a6c8d0f2b3
Revises: d2e4f6a8b0c1
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e4a6c8d0f2b3"
down_revision = "d2e4f6a8b0c1"
branch_labels = None
depends_on = None

SCHEMA = "company"
FREQUENCIES = ("daily", "weekly", "monthly", "quarterly")
OLD_KINDS = ("monitoring", "maintenance", "improvement", "report", "coordination")
NEW_KINDS = (*OLD_KINDS, "audit")


def _ids(*numbers: int) -> list[str]:
    return [f"ECO-{number:03d}" for number in numbers]


# Frozen copy of app.core.audit_catalog.AUDIT_CHECK_FREQUENCIES as approved.
CLASSIFICATION = {
    "daily": _ids(5, 6, 7, 9, 10, 15, 18, 20, 22, 46, 47, 49, 51, 52, 54, 57, 59, 60, 61, 64, 66),
    "weekly": _ids(4, 8, 12, 13, 14, 17, 19, 24, 27, 28, 29, 39, 40, 41, 44, 45, 53, 62, 63, 65),
    "monthly": _ids(1, 2, 3, 11, 16, 23, 25, 26, 30, *range(31, 39), 42, 43),
    "quarterly": _ids(58),
}
ECO_023_OLD = "Complete ecosystem audit is scheduled weekly on Sunday at 19:00"
ECO_023_NEW = (
    "Every audit tier is scheduled: the four Operação 24x7 audit routines (daily, weekly, "
    "monthly, quarterly at 19:00), or the legacy Sunday 19:00 cron"
)


def upgrade() -> None:
    op.add_column(
        "audit_checks",
        sa.Column("frequency", sa.String(20), nullable=False, server_default="weekly"),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_audit_checks_frequency", "audit_checks", f"frequency IN {FREQUENCIES!r}", schema=SCHEMA
    )
    bind = op.get_bind()
    for frequency, names in CLASSIFICATION.items():
        bind.execute(
            sa.text("UPDATE company.audit_checks SET frequency = :f WHERE name = ANY(:names)"),
            {"f": frequency, "names": names},
        )
    # Only the canonical text is replaced: an operator's own wording stays.
    bind.execute(
        sa.text("UPDATE company.audit_checks SET description = :new WHERE name = 'ECO-023' AND description = :old"),
        {"new": ECO_023_NEW, "old": ECO_023_OLD},
    )

    op.drop_constraint("ck_agent_routines_kind", "agent_routines", schema=SCHEMA, type_="check")
    op.create_check_constraint("ck_agent_routines_kind", "agent_routines", f"kind IN {NEW_KINDS!r}", schema=SCHEMA)
    op.add_column("agent_routines", sa.Column("audit_frequency", sa.String(20), nullable=True), schema=SCHEMA)
    op.create_check_constraint(
        "ck_agent_routines_audit_tier", "agent_routines",
        "(kind = 'audit') = (audit_frequency IS NOT NULL)", schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_agent_routines_audit_frequency", "agent_routines",
        f"audit_frequency IS NULL OR audit_frequency IN {FREQUENCIES!r}", schema=SCHEMA,
    )
    op.create_index(
        "uq_agent_routines_audit_frequency", "agent_routines", ["audit_frequency"], unique=True,
        schema=SCHEMA, postgresql_where=sa.text("kind = 'audit'"),
    )
    op.add_column(
        "agent_routine_runs",
        sa.Column("audit_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_company_agent_routine_runs_audit_batch_id", "agent_routine_runs", ["audit_batch_id"], schema=SCHEMA
    )


def downgrade() -> None:
    # Audit routines (and their runs, by cascade) cannot exist without the kind.
    op.execute("DELETE FROM company.agent_routines WHERE kind = 'audit'")
    op.drop_index("ix_company_agent_routine_runs_audit_batch_id", "agent_routine_runs", schema=SCHEMA)
    op.drop_column("agent_routine_runs", "audit_batch_id", schema=SCHEMA)
    op.drop_index("uq_agent_routines_audit_frequency", "agent_routines", schema=SCHEMA)
    op.drop_constraint("ck_agent_routines_audit_frequency", "agent_routines", schema=SCHEMA, type_="check")
    op.drop_constraint("ck_agent_routines_audit_tier", "agent_routines", schema=SCHEMA, type_="check")
    op.drop_column("agent_routines", "audit_frequency", schema=SCHEMA)
    op.drop_constraint("ck_agent_routines_kind", "agent_routines", schema=SCHEMA, type_="check")
    op.create_check_constraint("ck_agent_routines_kind", "agent_routines", f"kind IN {OLD_KINDS!r}", schema=SCHEMA)
    op.execute(
        sa.text("UPDATE company.audit_checks SET description = :old WHERE name = 'ECO-023' AND description = :new")
        .bindparams(old=ECO_023_OLD, new=ECO_023_NEW)
    )
    op.drop_constraint("ck_audit_checks_frequency", "audit_checks", schema=SCHEMA, type_="check")
    op.drop_column("audit_checks", "frequency", schema=SCHEMA)
