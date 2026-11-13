"""Independent worker observations and additive module audit coverage.

No historical run is rewritten or deleted; no Foundation database is touched.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '4c219b76ae03'
down_revision = '1994f24fd6e1'
branch_labels = None
depends_on = None

NEW_CHECKS = (
 ('ECO-061','operations','athos','All five operational workers have explicit policy and recent completed passes'),
 ('ECO-062','mission','athos','Mission state, baseline, orchestrator membership and enabled coordination routines are consistent'),
 ('ECO-063','factory','daedalus','Factory task origins and project traceability are consistent without invalidating accepted history'),
 ('ECO-064','remote','hephaestus','All enabled registered machines have fresh observations and host executions retain progress and agent Task linkage'),
 ('ECO-065','security','aegis','Browser session metadata is consistent and has no activity after expiry'),
 ('ECO-066','operations','athos','Routine occurrences meet deadlines and required demand and evidence links'),
)
REVISED = {
 'ECO-005': 'The single shared Hermes gateway is active and healthy',
 'ECO-006': 'ForgeHub host bridge services are active',
 'ECO-053': 'Recent Hermes Messages tasks have authenticated Activity delivery; other channels are unverified',
}


def upgrade():
    op.create_table('operational_worker_observations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('worker_name',sa.String(80),nullable=False),
        sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('interval_seconds',sa.Integer(),nullable=False),
        sa.Column('active_run_id',postgresql.UUID(as_uuid=True)),
        sa.Column('last_status',sa.String(16),nullable=False),
        sa.Column('last_started_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('last_finished_at',sa.DateTime(timezone=True)),
        sa.Column('last_success_at',sa.DateTime(timezone=True)),
        sa.Column('error_type',sa.String(80)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.text('now()')),
        sa.UniqueConstraint('worker_name',name='uq_worker_observations_name'),
        sa.CheckConstraint("last_status IN ('starting','running','ok','error','disabled')",name='ck_worker_observations_status'),
        sa.CheckConstraint('interval_seconds > 0',name='ck_worker_observations_interval'),schema='company')
    bind=op.get_bind()
    for name,category,owner,description in NEW_CHECKS:
        bind.execute(sa.text('''INSERT INTO company.audit_checks
            (id,name,description,category,command,agent_profile,enabled,timeout_seconds)
            VALUES (gen_random_uuid(),:name,:description,:category,:command,:owner,true,55)
            ON CONFLICT (name) DO NOTHING'''),dict(name=name,category=category,owner=owner,
            description=description,command=f'python3 /root/.hermes/profiles/athos/scripts/checklist_verifier.py --check {name}'))
    for name,description in REVISED.items():
        bind.execute(sa.text('UPDATE company.audit_checks SET description=:description,updated_at=now() WHERE name=:name'),
                     dict(name=name,description=description))


def downgrade():
    # Preserve runs and IDs even on rollback. Disabled rows explicitly say the
    # rolled-back code cannot verify these modules.
    op.execute("UPDATE company.audit_checks SET enabled=false WHERE name IN ('ECO-061','ECO-062','ECO-063','ECO-064','ECO-065','ECO-066')")
    op.drop_table('operational_worker_observations',schema='company')
