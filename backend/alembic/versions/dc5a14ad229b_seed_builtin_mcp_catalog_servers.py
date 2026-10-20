"""seed builtin mcp catalog servers

Revision ID: dc5a14ad229b
Revises: a128eb1942f6
Create Date: 2026-07-28 10:50:09.619360

Pre-populates the MCP catalog (mcp_catalog_servers) with a handful of
well-known MCP servers, so the operator has real starting points instead of
an empty catalog -- per Marcelo's request ("adiciona no cadastro do MCP os
principais"). `env` values are placeholders (never real credentials); the
operator fills in the real key before assigning a builtin server to any
agent/project. `is_builtin=True` is a display hint only (e.g. a badge) --
these rows are editable/deletable like any other catalog entry.

Package names/versions for third-party MCP servers change over time; these
are the well-known ones as of this writing, not a guarantee they still
resolve -- an operator hitting a stale package name just edits the row
(same as with a manually-entered one), no different from any config drift.
`args`/`env` use ON CONFLICT DO NOTHING keyed on the UNIQUE `name` column,
so re-running this migration (or a name an operator already registered
themselves) is a no-op rather than an error.
"""
import json
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc5a14ad229b'
down_revision: Union[str, Sequence[str], None] = 'a128eb1942f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


BUILTIN_SERVERS = [
    {
        "name": "github",
        "description": "Read/write GitHub repos, issues, PRs.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "YOUR_TOKEN_HERE"},
    },
    {
        "name": "notion",
        "description": "Read/write Notion pages and databases.",
        "command": "npx",
        "args": ["-y", "@notionhq/notion-mcp-server"],
        "env": {"NOTION_API_KEY": "YOUR_API_KEY_HERE"},
    },
    {
        "name": "slack",
        "description": "Read/send Slack messages, list channels.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "YOUR_BOT_TOKEN_HERE", "SLACK_TEAM_ID": "YOUR_TEAM_ID_HERE"},
    },
    {
        "name": "google-drive",
        "description": "Search and read Google Drive files.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gdrive"],
        "env": {"GDRIVE_CREDENTIALS_PATH": "YOUR_CREDENTIALS_PATH_HERE"},
    },
    {
        "name": "postgres",
        "description": "Read-only queries against a Postgres database.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres", "YOUR_CONNECTION_STRING_HERE"],
        "env": {},
    },
    {
        "name": "brave-search",
        "description": "Web search via the Brave Search API.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "YOUR_API_KEY_HERE"},
    },
    {
        "name": "playwright",
        "description": "Browser automation (navigate, click, screenshot).",
        "command": "npx",
        "args": ["-y", "@playwright/mcp@latest"],
        "env": {},
    },
    {
        "name": "memory",
        "description": "Simple persistent knowledge-graph memory for an agent.",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"],
        "env": {},
    },
]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    for server in BUILTIN_SERVERS:
        conn.execute(
            sa.text(
                """
                INSERT INTO company.mcp_catalog_servers
                    (id, name, description, transport, command, args, env, url,
                     is_builtin, apply_to_all_agents, created_at, updated_at)
                VALUES
                    (:id, :name, :description, 'stdio', :command, :args, :env, NULL,
                     true, false, now(), now())
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "name": server["name"],
                "description": server["description"],
                "command": server["command"],
                "args": json.dumps(server["args"]),
                "env": json.dumps(server["env"]),
            },
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    names = [s["name"] for s in BUILTIN_SERVERS]
    conn.execute(
        sa.text("DELETE FROM company.mcp_catalog_servers WHERE name = ANY(:names) AND is_builtin = true"),
        {"names": names},
    )
