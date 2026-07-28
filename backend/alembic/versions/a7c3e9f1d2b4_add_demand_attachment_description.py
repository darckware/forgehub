"""add demand_attachments.description

Revision ID: a7c3e9f1d2b4
Revises: e6f8a2c4d7b9
Create Date: 2026-07-27 16:30:00.000000

An optional caption for a file attached to a message: what it is and why it
was sent. The filename alone often can't carry that ("relatorio.pdf"), and
the message body is a poor place for it once there is more than one
attachment.

Nullable with no server default: an attachment uploaded without a
description is the normal case, and "" would be indistinguishable from a
description someone deliberately cleared.

Chains onto e6f8a2c4d7b9 (the demand lineage). The repo has had two
independent Alembic heads since before this change -- this keeps the count
at two rather than adding a third.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e9f1d2b4"
down_revision: Union[str, Sequence[str], None] = "e6f8a2c4d7b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "demand_attachments",
        sa.Column("description", sa.String(length=500), nullable=True),
        schema="company",
    )


def downgrade() -> None:
    op.drop_column("demand_attachments", "description", schema="company")
