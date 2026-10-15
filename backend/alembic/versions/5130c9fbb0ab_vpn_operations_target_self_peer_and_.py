"""vpn operations target self/peer and target name

Remote Access rework (2026-10-15): operations target "self" (this server) or
a tailnet "peer" by stable ID, replacing the fixed local/remote pair. Old
values stay allowed so existing history rows remain valid.

Revision ID: 5130c9fbb0ab
Revises: b4d8f1c2e973
Create Date: 2026-10-15 13:06:34.597939

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5130c9fbb0ab'
down_revision: Union[str, Sequence[str], None] = 'b4d8f1c2e973'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("vpn_operation_events", sa.Column("target_node_id", sa.String(64), nullable=True), schema="company")
    op.add_column("vpn_operation_events", sa.Column("target_name", sa.String(255), nullable=True), schema="company")
    op.drop_constraint("ck_vpn_operation_events_target", "vpn_operation_events", schema="company", type_="check")
    op.create_check_constraint(
        "ck_vpn_operation_events_target",
        "vpn_operation_events",
        "target IN ('self', 'peer', 'local', 'remote')",
        schema="company",
    )


def downgrade() -> None:
    op.execute("DELETE FROM company.vpn_operation_events WHERE target IN ('self', 'peer')")
    op.drop_constraint("ck_vpn_operation_events_target", "vpn_operation_events", schema="company", type_="check")
    op.create_check_constraint(
        "ck_vpn_operation_events_target",
        "vpn_operation_events",
        "target IN ('local', 'remote')",
        schema="company",
    )
    op.drop_column("vpn_operation_events", "target_name", schema="company")
    op.drop_column("vpn_operation_events", "target_node_id", schema="company")
