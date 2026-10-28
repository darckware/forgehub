"""Persist origin on directly registered demands, independently of suggestions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = '8d71e3a2f609'
down_revision = '6b20f44a9e12'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('personal_demands', sa.Column('origin', pg.JSONB(), nullable=True), schema='company')
    op.add_column('personal_demands', sa.Column('origin_key', sa.String(64), nullable=True), schema='company')
    op.add_column('personal_demands', sa.Column('completed_by', sa.String(50), nullable=True), schema='company')
    op.create_unique_constraint('uq_personal_demand_origin_key', 'personal_demands', ['origin_key'], schema='company')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM company.personal_demands WHERE origin IS NOT NULL OR completed_by IS NOT NULL)')).scalar():
        raise RuntimeError('Direct demand origins exist; retain the additive schema')
    op.drop_constraint('uq_personal_demand_origin_key', 'personal_demands', schema='company')
    op.drop_column('personal_demands', 'origin_key', schema='company')
    op.drop_column('personal_demands', 'origin', schema='company')
    op.drop_column('personal_demands', 'completed_by', schema='company')
