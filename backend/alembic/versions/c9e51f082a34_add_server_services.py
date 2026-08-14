"""Add server_services (what runs on a server, and where to open it)

2026-08-14, Marcelo: "preciso ao clicar na linha abri o link dos serviços de
cada servidor, informando o Ip e porta de acesso... Exemplo: 172.15.2.3:8000".
The inventory only ever answered "how do I get a shell", so the ports people
use daily lived in someone's memory.

The row holds the port and how to address it, never the host: that comes from
the parent server, so changing a server's IP moves its services with it. FK
cascades because a service cannot outlive the machine it runs on.

Revision ID: c9e51f082a34
Revises: b8d3c05f1e77
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c9e51f082a34"
down_revision = "b8d3c05f1e77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "server_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "server_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company.servers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("scheme", sa.String(length=10), nullable=False, server_default="http"),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "server_id",
            "port",
            "path",
            name="uq_server_service_endpoint",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint("scheme IN ('http', 'https')", name="ck_server_services_scheme"),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_server_services_port"),
        schema="company",
    )
    op.create_index(
        "ix_server_services_server_id", "server_services", ["server_id"], schema="company"
    )


def downgrade() -> None:
    op.drop_index("ix_server_services_server_id", table_name="server_services", schema="company")
    op.drop_table("server_services", schema="company")
