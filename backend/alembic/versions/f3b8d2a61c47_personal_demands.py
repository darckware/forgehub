"""Personal domain: demands grouped by user-defined types (the Pessoal screen's Demandas tab)

Marcelo, 2026-10-14: "faltou adicionar uma aba de demandas que posso adicionar e agrupar por tipo.
Os tipo posso cadastrar e remover dentro da própria tela". See app/db/models/personal.py.

Revision ID: f3b8d2a61c47
Revises: e1a4c7b92d30
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f3b8d2a61c47"
down_revision = "e1a4c7b92d30"
branch_labels = None
depends_on = None

SCHEMA = "company"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "personal_demand_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="marcelo"),
        *_timestamps(),
        schema=SCHEMA,
    )
    op.create_table(
        "personal_demands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.personal_demand_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="marcelo"),
        *_timestamps(),
        sa.CheckConstraint("status IN ('open', 'done')", name="ck_personal_demands_status"),
        schema=SCHEMA,
    )
    op.create_index("ix_company_personal_demands_type_id", "personal_demands", ["type_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_company_personal_demands_type_id", table_name="personal_demands", schema=SCHEMA)
    op.drop_table("personal_demands", schema=SCHEMA)
    op.drop_table("personal_demand_types", schema=SCHEMA)
