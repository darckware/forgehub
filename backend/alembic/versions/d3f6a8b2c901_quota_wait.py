"""Nonterminal quota waits keep their run evidence and executor binding."""
from alembic import op
import sqlalchemy as sa

revision = "d3f6a8b2c901"
down_revision = "b8e2c4a6d1f9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agent_demands", sa.Column("quota_reset_at", sa.DateTime(timezone=True)), schema="company")
    op.add_column("agent_demands", sa.Column("quota_wait_fingerprint", sa.String(64)), schema="company")
    op.add_column("agent_demands", sa.Column("quota_dispatch_attempts", sa.Integer(), nullable=False, server_default="0"), schema="company")
    op.drop_constraint("ck_agent_demands_dispatch_status", "agent_demands", schema="company", type_="check")
    op.create_check_constraint("ck_agent_demands_dispatch_status", "agent_demands", "dispatch_status IS NULL OR dispatch_status IN ('dispatched','running','completed','failed','waiting_quota')", schema="company")


def downgrade():
    # Downgrade cannot erase live waits or their run bindings.
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM company.agent_demands WHERE dispatch_status='waiting_quota')")).scalar():
        raise RuntimeError("Resolve quota waits before downgrading; run evidence must be preserved")
    op.drop_constraint("ck_agent_demands_dispatch_status", "agent_demands", schema="company", type_="check")
    op.create_check_constraint("ck_agent_demands_dispatch_status", "agent_demands", "dispatch_status IS NULL OR dispatch_status IN ('dispatched','running','completed','failed')", schema="company")
    for name in ("quota_dispatch_attempts", "quota_wait_fingerprint", "quota_reset_at"):
        op.drop_column("agent_demands", name, schema="company")
