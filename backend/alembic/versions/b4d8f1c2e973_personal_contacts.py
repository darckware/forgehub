"""Personal contacts, their WhatsApp history with context, capture suggestions and the Maia's rules

Marcelo, 2026-10-14: "adiciona uma aba dos contatos do whatsapp e seus históricos dos contexto ...
capturar as demandas, tarefas e anotações ... uma aba de contexto da Maia, uma regra de atendimento".
Contacts move from knowledge_base/marcelo/pessoal (Markdown) into the database; the one-off import is
app/scripts/import_personal_contacts.py. See app/db/models/personal.py.

Revision ID: b4d8f1c2e973
Revises: a7c2e9f41b85
Create Date: 2026-10-14
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b4d8f1c2e973"
down_revision = "a7c2e9f41b85"
branch_labels = None
depends_on = None

SCHEMA = "company"
DEFAULT_CATEGORIES = ("familia", "parentes", "amigos", "trabalho_semed", "cliente_darckware", "outros", "a_classificar")


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    categories = op.create_table(
        "personal_contact_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False, unique=True),
        *_ts(),
        schema=SCHEMA,
    )
    op.bulk_insert(categories, [{"id": uuid.uuid4(), "key": k} for k in DEFAULT_CATEGORIES])

    op.create_table(
        "personal_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False, server_default=""),
        sa.Column("category", sa.String(40), nullable=False, server_default="a_classificar"),
        sa.Column("relation", sa.String(200), nullable=False, server_default=""),
        sa.Column("birthday", sa.String(10), nullable=False, server_default=""),
        sa.Column("observations", sa.Text(), nullable=False, server_default=""),
        sa.Column("who_is", sa.Text(), nullable=False, server_default=""),
        sa.Column("how_to_treat", sa.Text(), nullable=False, server_default=""),
        sa.Column("other_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(50), nullable=False, server_default="marcelo"),
        *_ts(),
        schema=SCHEMA,
    )

    op.create_table(
        "personal_contact_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.personal_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False, server_default="in"),
        sa.Column("author", sa.String(100), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="whatsapp"),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("context_status", sa.String(10), nullable=False, server_default="pending"),
        *_ts(),
        sa.CheckConstraint("direction IN ('in', 'out', 'note')", name="ck_personal_contact_messages_direction"),
        sa.CheckConstraint("context_status IN ('pending', 'done', 'skipped', 'failed')",
                           name="ck_personal_contact_messages_context_status"),
        schema=SCHEMA,
    )
    op.create_index("ix_company_personal_contact_messages_contact_id", "personal_contact_messages", ["contact_id"], schema=SCHEMA)
    op.create_index("ix_company_personal_contact_messages_at", "personal_contact_messages", ["at"], schema=SCHEMA)

    op.create_table(
        "personal_capture_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.personal_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey(f"{SCHEMA}.personal_contact_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("details", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("created_item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
        sa.CheckConstraint("kind IN ('demand', 'task', 'note')", name="ck_personal_capture_suggestions_kind"),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'dismissed')", name="ck_personal_capture_suggestions_status"),
        schema=SCHEMA,
    )
    op.create_index("ix_company_personal_capture_suggestions_contact_id", "personal_capture_suggestions", ["contact_id"], schema=SCHEMA)

    settings = op.create_table(
        "personal_assistant_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("wait_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("capture_enabled", sa.Boolean(), nullable=False, server_default="true"),
        *_ts(),
        schema=SCHEMA,
    )
    op.bulk_insert(settings, [{"id": uuid.uuid4(), "instructions": "", "wait_minutes": 5, "capture_enabled": True}])


def downgrade() -> None:
    op.drop_table("personal_assistant_settings", schema=SCHEMA)
    op.drop_index("ix_company_personal_capture_suggestions_contact_id", table_name="personal_capture_suggestions", schema=SCHEMA)
    op.drop_table("personal_capture_suggestions", schema=SCHEMA)
    op.drop_index("ix_company_personal_contact_messages_at", table_name="personal_contact_messages", schema=SCHEMA)
    op.drop_index("ix_company_personal_contact_messages_contact_id", table_name="personal_contact_messages", schema=SCHEMA)
    op.drop_table("personal_contact_messages", schema=SCHEMA)
    op.drop_table("personal_contacts", schema=SCHEMA)
    op.drop_table("personal_contact_categories", schema=SCHEMA)
