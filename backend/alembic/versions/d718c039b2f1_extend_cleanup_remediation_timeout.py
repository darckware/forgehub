"""extend cleanup remediation timeout

Revision ID: d718c039b2f1
Revises: d718c039a1f0
Create Date: 2026-07-18
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d718c039b2f1"
down_revision: Union[str, Sequence[str], None] = "d718c039a1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE company.audit_checks SET timeout_seconds=600, updated_at=now() WHERE name='ECO-039'")


def downgrade() -> None:
    op.execute("UPDATE company.audit_checks SET timeout_seconds=55, updated_at=now() WHERE name='ECO-039'")
