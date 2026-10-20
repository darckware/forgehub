"""add agents.telegram_account

Every agent speaks through its *own* Telegram bot, each with a separate
TELEGRAM_BOT_TOKEN in its profile .env -- Athos is @HermesAthosbot, Atlas
another, and so on (2026-08-13, Marcelo: "tenho outros agentes no telegram.
No caso do athos a conta do telegram é HermesAthosbot").

That makes "reply on Telegram" not one destination but thirteen. A request
that arrived through Athos' bot has to be answered through Athos' bot, or it
surfaces in the wrong conversation from the wrong sender. The chat id can't
express this: TELEGRAM_HOME_CHANNEL is the same value (Marcelo's own,
1085550644) in every profile.

The account name is stored here rather than read from the profile .env
because the .env carries the token, not the username -- and the token is
deliberately never copied into ForgeHub (core/agent_telegram.py reduces it to
a boolean before it leaves the module).

Nullable and unbackfilled: an agent with no Telegram bot is a normal state,
and guessing a username from a slug would invent accounts that may not exist.

Revision ID: a7d51c93f8b2
Revises: f2a6d38e91b4
Create Date: 2026-08-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7d51c93f8b2'
down_revision: Union[str, Sequence[str], None] = 'f2a6d38e91b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("telegram_account", sa.String(length=100), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("agents", "telegram_account", schema=SCHEMA)
