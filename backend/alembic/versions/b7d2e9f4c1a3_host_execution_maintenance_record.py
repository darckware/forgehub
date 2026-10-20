"""Maintenance record on host executions: why it ran and which client ticket/demand it serves.

Revision ID: b7d2e9f4c1a3
Revises: a9c4e7f2b1d6

2026-10-19 (Marcelo approved): one machine account (`darckware`), with who did
what kept by ForgeHub. Every execution can carry the reason it ran (required
for agents) and the Darckware work item it belongs to (`ticket` or `demand`,
Darckware's id -- no FK, the item lives in Darckware), so a machine's
maintenance history reads as attended work, not loose commands.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7d2e9f4c1a3"
down_revision = "a9c4e7f2b1d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("host_executions", sa.Column("reason", sa.Text(), nullable=True), schema="company")
    op.add_column("host_executions", sa.Column("darckware_item_kind", sa.String(length=20), nullable=True), schema="company")
    op.add_column("host_executions", sa.Column("darckware_item_id", sa.String(length=64), nullable=True), schema="company")
    op.create_check_constraint(
        "ck_host_executions_darckware_item",
        "host_executions",
        "(darckware_item_kind IS NULL AND darckware_item_id IS NULL) OR "
        "(darckware_item_kind IN ('ticket', 'demand') AND darckware_item_id IS NOT NULL)",
        schema="company",
    )


def downgrade() -> None:
    op.drop_constraint("ck_host_executions_darckware_item", "host_executions", schema="company")
    op.drop_column("host_executions", "darckware_item_id", schema="company")
    op.drop_column("host_executions", "darckware_item_kind", schema="company")
    op.drop_column("host_executions", "reason", schema="company")
