"""Off-site backup targets and runs, seeded with one target per project.

Revision ID: 7d8820d5bfb2
Revises: e6a1c8d3f9b2
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "7d8820d5bfb2"
down_revision = "e6a1c8d3f9b2"
branch_labels = None
depends_on = None

# (name, label, paths, excludes, postgres container, system state)
SEED = [
    ("sistema", "Sistema (Hermes, Foundation e configurações)",
     ["/root/.hermes", "/root/memory", "/root/db", "/root/.config", "/root/.ssh", "/root/.forgehub",
      "/root/.forgevault", "/root/forgehub-data", "/root/media", "/root/docs", "/root/agents", "/etc"],
     # Live Postgres data directories: the dumps are what restores consistently.
     ["/root/db/forgehub-postgres", "/root/db/forgerouter-postgres", "/root/db/hindsight-postgres"],
     "hindsight_postgres", True),
    ("agentes-externos", "Agentes externos (Claude Code, Codex, agy)",
     ["/root/.claude", "/root/.claude.json", "/root/.codex", "/root/.gemini"], [], None, False),
    ("forgehub", "ForgeHub", ["/root/project/forgehub"], [], "forgehub_postgres", False),
    ("darckware", "Darckware", ["/root/project/darckware"], [], "darckware-postgres", False),
    ("coreti", "CoreTI", ["/root/project/coreti"], [], "coreti_postgres", False),
    ("forgerouter", "ForgeRouter", ["/root/project/forgerouter"], [], "forgerouter_postgres", False),
    ("forgevault", "ForgeVault", ["/root/project/forgevault"], [], "forgevault-postgres-1", False),
    ("duplica", "Duplica", ["/root/project/duplica"], [], None, False),
    ("saedas", "SAEDAS", ["/root/project/saedas", "/root/project/SaedasMigration"], [], "saedas_postgres", False),
    ("rustdesk-server", "Servidor RustDesk (chave e banco)", ["/root/project/remoto"], [], None, False),
    ("darckware-remote", "Darckware Remote (instalador)", ["/root/project/darckware-remote"], [], None, False),
    ("nexo", "Nexo", ["/root/project/nexo"], [], None, False),
    ("filenest", "Filenest", ["/root/project/filenest"], [], None, False),
    ("osintkey", "OsintKey", ["/root/project/osintkey"], [], None, False),
    ("outros", "Outros (agentes, marketing, backups Darckware)",
     ["/root/project/agentes", "/root/project/marketing", "/root/project/darckware-backups", "/root/project/rustdesk"],
     [], None, False),
]


def upgrade():
    op.create_table(
        "offsite_backup_targets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("paths", JSONB, nullable=False),
        sa.Column("excludes", JSONB, nullable=False, server_default="[]"),
        sa.Column("postgres_container", sa.String(255), nullable=True),
        sa.Column("include_system_state", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="company",
    )
    op.create_table(
        "offsite_backup_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "target_id", UUID(as_uuid=True),
            sa.ForeignKey("company.offsite_backup_targets.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("target_name", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", sa.String(64), nullable=True),
        sa.Column("files_new", sa.Integer, nullable=True),
        sa.Column("data_added", sa.BigInteger, nullable=True),
        sa.Column("total_bytes", sa.BigInteger, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'ok', 'failed', 'interrupted')", name="ck_offsite_backup_run_status"
        ),
        sa.CheckConstraint("trigger IN ('schedule', 'manual')", name="ck_offsite_backup_run_trigger"),
        schema="company",
    )
    op.create_index(
        "ix_company_offsite_backup_runs_target_id", "offsite_backup_runs", ["target_id"], schema="company"
    )
    op.create_index(
        "ix_offsite_backup_runs_target_started", "offsite_backup_runs", ["target_name", "started_at"], schema="company"
    )

    targets = sa.table(
        "offsite_backup_targets",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("label", sa.String),
        sa.column("paths", JSONB),
        sa.column("excludes", JSONB),
        sa.column("postgres_container", sa.String),
        sa.column("include_system_state", sa.Boolean),
        sa.column("enabled", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        schema="company",
    )
    op.bulk_insert(targets, [
        {"id": uuid.uuid4(), "name": name, "label": label, "paths": paths, "excludes": excludes,
         "postgres_container": container, "include_system_state": system_state, "enabled": True,
         "sort_order": index * 10}
        for index, (name, label, paths, excludes, container, system_state) in enumerate(SEED)
    ])


def downgrade():
    op.drop_index("ix_offsite_backup_runs_target_started", table_name="offsite_backup_runs", schema="company")
    op.drop_index("ix_company_offsite_backup_runs_target_id", table_name="offsite_backup_runs", schema="company")
    op.drop_table("offsite_backup_runs", schema="company")
    op.drop_table("offsite_backup_targets", schema="company")
