"""Represent a decision whose committed execution still needs finalization."""
from alembic import op
import sqlalchemy as sa

revision = "e5e1c3d78ba6"
down_revision = "e4d0b2c67a95"
branch_labels = None
depends_on = None


def _replace(expression):
    op.drop_constraint("ck_mission_decisions_status", "mission_decisions", schema="company", type_="check")
    op.create_check_constraint("ck_mission_decisions_status", "mission_decisions", expression, schema="company")


def upgrade():
    _replace("status IN ('pending', 'applied', 'refused', 'deferred', 'undone')")


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM company.mission_decisions WHERE status = 'pending'")):
        raise RuntimeError("Reconcile pending mission decisions before downgrade; their state cannot be discarded")
    _replace("status IN ('applied', 'refused', 'deferred', 'undone')")
