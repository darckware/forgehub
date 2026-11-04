"""Create the svc-agente user and its read-only profile for agent screen sessions.

Revision ID: d5e93a7b2c18
Revises: c4d82f6e1a97
"""
import secrets
import uuid

from alembic import op
import sqlalchemy as sa

from app.core.security import hash_password

revision = "d5e93a7b2c18"
down_revision = "c4d82f6e1a97"
branch_labels = None
depends_on = None

PROFILE = "Agente leitura"
USERNAME = "svc-agente"
MODULES = ("product", "projects", "pipeline", "backlog", "tasks", "agents", "artifacts", "governance",
           "foundation", "crons", "deploy", "demands", "docs", "auditor")


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("agents", sa.Column("screen_access_enabled", sa.Boolean(), nullable=False,
                                      server_default=sa.false()), schema="company")
    profile_id = uuid.uuid4()
    bind.execute(sa.text(
        "INSERT INTO company.profiles (id, name, description) VALUES (:id, :name, :description)"
    ), {"id": profile_id, "name": PROFILE, "description": "Somente leitura, para agentes testarem telas e fazerem manuais."})
    for module in MODULES:
        bind.execute(sa.text(
            "INSERT INTO company.profile_permissions (id, profile_id, module, can_view, can_query, can_write, can_delete) "
            "VALUES (:id, :profile_id, :module, true, true, false, false)"
        ), {"id": uuid.uuid4(), "profile_id": profile_id, "module": module})
    bind.execute(sa.text(
        "INSERT INTO company.profile_action_permissions (id, profile_id, action_key, allowed) "
        "VALUES (:id, :profile_id, 'demands.view', true)"
    ), {"id": uuid.uuid4(), "profile_id": profile_id})
    # Nobody knows this password: the account only opens through agent sessions.
    bind.execute(sa.text(
        "INSERT INTO company.users (id, username, hashed_password, full_name, is_active, is_admin, profile_id) "
        "VALUES (:id, :username, :password, :full_name, true, false, :profile_id)"
    ), {"id": uuid.uuid4(), "username": USERNAME, "password": hash_password(secrets.token_urlsafe(48)),
        "full_name": "Conta de serviço dos agentes", "profile_id": profile_id})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM company.users WHERE username = :username"), {"username": USERNAME})
    bind.execute(sa.text("DELETE FROM company.profiles WHERE name = :name"), {"name": PROFILE})
    op.drop_column("agents", "screen_access_enabled", schema="company")
