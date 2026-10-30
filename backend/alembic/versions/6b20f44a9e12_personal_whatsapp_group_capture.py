"""Monitored WhatsApp groups and traceable capture suggestions.

Revision ID: 6b20f44a9e12
Revises: 7d3a9e5c2b18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '6b20f44a9e12'
down_revision = '7d3a9e5c2b18'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('personal_whatsapp_groups',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('whatsapp_id', sa.String(160), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True)),
        sa.Column('created_by', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), schema='company')
    op.alter_column('personal_capture_suggestions', 'contact_id', nullable=True, schema='company')
    for column in (
        sa.Column('group_id', pg.UUID(as_uuid=True)),
        sa.Column('source_message_ref', sa.String(64)),
        sa.Column('source_author', sa.String(255)),
        sa.Column('source_author_id', sa.String(160)),
        sa.Column('source_at', sa.DateTime(timezone=True)),
        sa.Column('capture_key', sa.String(64)),
    ):
        op.add_column('personal_capture_suggestions', column, schema='company')
    op.create_foreign_key('fk_capture_whatsapp_group', 'personal_capture_suggestions', 'personal_whatsapp_groups', ['group_id'], ['id'], source_schema='company', referent_schema='company', ondelete='RESTRICT')
    op.create_index('ix_personal_capture_suggestions_group_id', 'personal_capture_suggestions', ['group_id'], schema='company')
    op.create_unique_constraint('uq_personal_capture_key', 'personal_capture_suggestions', ['capture_key'], schema='company')
    op.create_check_constraint('ck_personal_capture_origin', 'personal_capture_suggestions', '(contact_id IS NOT NULL AND group_id IS NULL) OR (contact_id IS NULL AND group_id IS NOT NULL)', schema='company')


def downgrade():
    # Never delete group-origin personal work to force a rollback.
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT EXISTS (SELECT 1 FROM company.personal_capture_suggestions WHERE group_id IS NOT NULL) OR EXISTS (SELECT 1 FROM company.personal_whatsapp_groups)')).scalar():
        raise RuntimeError('Group registry/captures exist; keep the additive schema or reconcile them before downgrade')
    op.drop_constraint('ck_personal_capture_origin', 'personal_capture_suggestions', schema='company')
    op.drop_constraint('uq_personal_capture_key', 'personal_capture_suggestions', schema='company')
    op.drop_index('ix_personal_capture_suggestions_group_id', table_name='personal_capture_suggestions', schema='company')
    op.drop_constraint('fk_capture_whatsapp_group', 'personal_capture_suggestions', schema='company')
    for name in ('capture_key', 'source_at', 'source_author_id', 'source_author', 'source_message_ref', 'group_id'):
        op.drop_column('personal_capture_suggestions', name, schema='company')
    op.alter_column('personal_capture_suggestions', 'contact_id', nullable=False, schema='company')
    op.drop_table('personal_whatsapp_groups', schema='company')
