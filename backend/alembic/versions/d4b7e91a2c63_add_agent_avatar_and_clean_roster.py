"""add agent avatar and clean invalid roster rows

Revision ID: d4b7e91a2c63
Revises: a1d5e29b7c46
Create Date: 2026-08-29

The data cleanup is intentionally asymmetric: archived Hermes identities are
soft-retired, while rows whose slug proves they came from automated fixtures
and their fixture-owned chats are removed. Downgrade cannot recreate test
garbage and therefore only removes the avatar column.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b7e91a2c63"
down_revision: Union[str, Sequence[str], None] = "a1d5e29b7c46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACTIVE_HERMES_SLUGS = (
    "aegis",
    "athos",
    "atlas",
    "daedalus",
    "hephaestus",
    "kairos",
    "mnemosyne",
    "scriba",
    "themis",
)

_FIXTURE_PREDICATE = """
    profile_slug = 'test-suite'
    OR profile_slug LIKE 'channel-test-a-%'
    OR profile_slug LIKE 'channel-test-b-%'
    OR profile_slug LIKE 'chat-group-test-%'
    OR profile_slug LIKE 'fb-%'
"""


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("avatar_data_url", sa.Text(), nullable=True),
        schema="company",
    )

    fixture_ids = f"SELECT id FROM company.agents WHERE {_FIXTURE_PREDICATE}"
    session_ids = f"SELECT id FROM company.chat_sessions WHERE agent_id IN ({fixture_ids})"
    op.execute(sa.text(f"DELETE FROM company.chat_artifacts WHERE session_id IN ({session_ids})"))
    op.execute(sa.text(f"DELETE FROM company.chat_messages WHERE session_id IN ({session_ids})"))
    op.execute(sa.text(f"DELETE FROM company.chat_session_participants WHERE session_id IN ({session_ids})"))
    op.execute(sa.text(f"DELETE FROM company.chat_sessions WHERE id IN ({session_ids})"))
    op.execute(sa.text(f"DELETE FROM company.responsibility_areas WHERE owner_agent_id IN ({fixture_ids})"))
    op.execute(sa.text(f"DELETE FROM company.task_assignments WHERE agent_id IN ({fixture_ids})"))
    op.execute(sa.text(f"DELETE FROM company.agents WHERE id IN ({fixture_ids})"))

    quoted_slugs = ", ".join(f"'{slug}'" for slug in _ACTIVE_HERMES_SLUGS)
    op.execute(
        sa.text(
            "UPDATE company.agents SET is_active = false, status = 'retired' "
            "WHERE runtime_type = 'hermes' AND is_active = true "
            f"AND profile_slug NOT IN ({quoted_slugs})"
        )
    )


def downgrade() -> None:
    op.drop_column("agents", "avatar_data_url", schema="company")
