"""Agents hold their own sessions; the shared svc-agente user is gone.

Marcelo, 2026-11-04: svc-agente was discontinued. An agent enters with its own
token, under the access control. The profile "Agente leitura" stays: it is what
the screens use to decide which modules agents may see.

Revision ID: a3f1c7d92e04
Revises: f26b87d314c9
"""
import secrets
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from app.core.security import hash_password

revision = "a3f1c7d92e04"
down_revision = "f26b87d314c9"
branch_labels = None
depends_on = None

USERNAME = "svc-agente"
PROFILE = "Agente leitura"


def upgrade() -> None:
    op.add_column("user_sessions", sa.Column("agent_id", UUID(as_uuid=True), nullable=True), schema="company")
    op.create_foreign_key("user_sessions_agent_id_fkey", "user_sessions", "agents", ["agent_id"], ["id"],
                          source_schema="company", referent_schema="company", ondelete="CASCADE")
    op.create_index("ix_company_user_sessions_agent_id", "user_sessions", ["agent_id"], schema="company")
    op.alter_column("user_sessions", "user_id", nullable=True, schema="company")
    # Keep the connection history, closed: those tokens carry the old identity.
    op.execute(sa.text(
        "UPDATE company.user_sessions s SET agent_id = a.id, user_id = NULL, is_active = false "
        "FROM company.agents a, company.users u "
        "WHERE u.username = :u AND s.user_id = u.id AND s.agent_name = COALESCE(a.profile_slug, a.name)"
    ).bindparams(u=USERNAME))
    # A session of no known agent goes with the user, by cascade.
    op.execute(sa.text("DELETE FROM company.users WHERE username = :u").bindparams(u=USERNAME))
    op.create_check_constraint("ck_user_sessions_one_owner", "user_sessions",
                               "(user_id IS NULL) <> (agent_id IS NULL)", schema="company")


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_constraint("ck_user_sessions_one_owner", "user_sessions", schema="company")
    op.execute("DELETE FROM company.user_sessions WHERE agent_id IS NOT NULL")
    op.alter_column("user_sessions", "user_id", nullable=False, schema="company")
    op.drop_index("ix_company_user_sessions_agent_id", table_name="user_sessions", schema="company")
    op.drop_constraint("user_sessions_agent_id_fkey", "user_sessions", schema="company", type_="foreignkey")
    op.drop_column("user_sessions", "agent_id", schema="company")
    bind.execute(sa.text(
        "INSERT INTO company.users (id, username, hashed_password, full_name, is_active, is_admin, profile_id) "
        "SELECT :id, :username, :password, :full_name, true, false, id FROM company.profiles WHERE name = :profile"
    ), {"id": uuid.uuid4(), "username": USERNAME, "password": hash_password(secrets.token_urlsafe(48)),
        "full_name": "Conta de serviço dos agentes", "profile": PROFILE})
