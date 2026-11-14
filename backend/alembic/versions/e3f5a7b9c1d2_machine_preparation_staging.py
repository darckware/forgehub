"""Stage machine credentials until verified; never rewrite active legacy access."""
from alembic import op
import sqlalchemy as sa

revision = "e3f5a7b9c1d2"
down_revision = "d2e4f6a8b0c1"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in [("pending_ssh_key_ref", sa.String(36)),
                       ("pending_public_key_encrypted", sa.Text()),
                       ("pending_login_password_ref", sa.String(36)),
                       ("pending_ssh_port", sa.Integer())]:
        op.add_column("servers", sa.Column(name, kind, nullable=True), schema="company")


def downgrade():
    for name in ["pending_ssh_port", "pending_login_password_ref",
                 "pending_public_key_encrypted", "pending_ssh_key_ref"]:
        op.drop_column("servers", name, schema="company")
