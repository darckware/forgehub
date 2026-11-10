"""Seed human-only final mission acceptance using the governed approval ledger."""
import hashlib
import json
import sqlalchemy as sa
from alembic import op
revision = "e6f2d4a89cb7"
down_revision = "e5e1c3d78ba6"
branch_labels = None
depends_on = None
SCHEMA = "company"
POLICY_ID = "5f7b02c9-66e2-42b7-9480-5ff322fd9f21"
VERSION_ID = "7c6e7991-c0c2-4fb4-9ef3-e6820d1c996a"
BINDING_ID = "27cbeb82-3f52-4329-8775-85581d50c840"
POLICY_NAME = "Mission final acceptance v1"
RULES = json.dumps({"deny_self_approval": True, "human_only": True, "expires_hours": 168}, sort_keys=True)


def upgrade():
    op.execute(sa.text(f"""
        INSERT INTO {SCHEMA}.policies (id,name,description,policy_type,rules,is_active,entity_type,created_at,updated_at)
        VALUES (CAST(:policy_id AS uuid), :name,
                'Governed approval of a mission final delivery: a person (admin) decides, never the submitter',
                'approval_required', CAST(:rules AS jsonb), true, 'mission_dossier', now(), now())
        ON CONFLICT (name) DO NOTHING
    """).bindparams(policy_id=POLICY_ID, name=POLICY_NAME, rules=RULES))
    op.execute(sa.text(f"""
        INSERT INTO {SCHEMA}.policy_versions (id,policy_id,version,rules_snapshot,evaluator_type,content_hash,status,created_at,updated_at)
        SELECT CAST(:version_id AS uuid), id, 1, CAST(:rules AS jsonb), 'structured', :content_hash, 'active', now(), now()
        FROM {SCHEMA}.policies WHERE name = :name
        ON CONFLICT (policy_id, version) DO NOTHING
    """).bindparams(version_id=VERSION_ID, rules=RULES, name=POLICY_NAME,
                    content_hash=hashlib.sha256(RULES.encode()).hexdigest()))
    op.execute(sa.text(f"""
        INSERT INTO {SCHEMA}.policy_bindings (id,policy_version_id,target_type,priority,is_active,created_at,updated_at)
        SELECT CAST(:binding_id AS uuid), id, 'mission_dossier', 100, true, now(), now()
        FROM {SCHEMA}.policy_versions WHERE id = CAST(:version_id AS uuid)
        ON CONFLICT DO NOTHING
    """).bindparams(binding_id=BINDING_ID, version_id=VERSION_ID))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM company.approval_requests WHERE target_type = 'mission_dossier'")):
        raise RuntimeError("Cannot remove acceptance policy while its governed requests exist")
    for table, field, value in [("policy_evaluations", "policy_version_id", VERSION_ID),
        ("policy_bindings", "id", BINDING_ID), ("policy_versions", "id", VERSION_ID), ("policies", "id", POLICY_ID)]:
        op.execute(sa.text(f"DELETE FROM company.{table} WHERE {field} = CAST(:id AS uuid)").bindparams(id=value))
