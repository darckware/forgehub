"""Agents: autonomous_runs, dispatched work without permission prompts.

A dispatched run is headless, so a CLI that asks to approve a tool gets it
auto-denied and the run ends with nothing done (Dartan's review #41628). The
external runtimes in the roster (Porthus/claude, Aramis/codex, Dartan/agy)
start with it on, per Marcelo on 2026-10-28; new agents default to off.

Revision ID: e4b8c1d7a9f3
Revises: 7a024b36d981
"""
import sqlalchemy as sa
from alembic import op

revision = "e4b8c1d7a9f3"
down_revision = "7a024b36d981"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agents",
        sa.Column("autonomous_runs", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="company",
    )
    op.execute(
        "UPDATE company.agents SET autonomous_runs = true "
        "WHERE profile_slug IN ('porthus', 'aramis', 'dartan')"
    )


def downgrade():
    op.drop_column("agents", "autonomous_runs", schema="company")
