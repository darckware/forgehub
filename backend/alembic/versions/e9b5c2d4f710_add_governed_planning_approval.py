"""add governed planning approval

Revision ID: e9b5c2d4f710
Revises: d8a4f1c2e630
"""
from typing import Sequence, Union
import hashlib

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e9b5c2d4f710"
down_revision: Union[str, Sequence[str], None] = "d8a4f1c2e630"
branch_labels = None
depends_on = None
SCHEMA = "company"

POLICY_ID = "6a8cd45e-c93b-4f0d-94fc-806bc391db81"
VERSION_ID = "3ec2a36b-ed86-4867-8054-b92d79f60fa4"
BINDING_ID = "02a44a68-fc15-4adb-af04-98a6d0c36317"
RULES = '{"require_valid_blueprint":true,"deny_self_approval":true,"required_action":"governance.approval.decide","expires_hours":72}'


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "profile_action_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_key", sa.String(150), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["profile_id"], [f"{SCHEMA}.profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("profile_id", "action_key", name="uq_profile_action_permission"), schema=SCHEMA,
    )
    op.create_table(
        "agent_service_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(150), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)), *_timestamps(),
        sa.ForeignKeyConstraint(["agent_id"], [f"{SCHEMA}.agents.id"], ondelete="CASCADE"), schema=SCHEMA,
    )
    op.create_table(
        "policy_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("rules_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("schema_snapshot", postgresql.JSONB()),
        sa.Column("evaluator_type", sa.String(50), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), *_timestamps(),
        sa.ForeignKeyConstraint(["policy_id"], [f"{SCHEMA}.policies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("policy_id", "version", name="uq_policy_versions_policy_version"), schema=SCHEMA,
    )
    op.create_table(
        "policy_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_until", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False), *_timestamps(),
        sa.ForeignKeyConstraint(["policy_version_id"], [f"{SCHEMA}.policy_versions.id"], ondelete="CASCADE"), schema=SCHEMA,
    )
    op.create_table(
        "policy_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("evaluator_version", sa.String(50), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False), *_timestamps(),
        sa.ForeignKeyConstraint(["policy_binding_id"], [f"{SCHEMA}.policy_bindings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_version_id"], [f"{SCHEMA}.policy_versions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("policy_version_id", "input_hash", name="uq_policy_evaluation_version_input"), schema=SCHEMA,
    )
    op.create_table(
        "authority_delegations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("grantor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grantee_type", sa.String(20), nullable=False),
        sa.Column("grantee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(30), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("project_id", postgresql.UUID(as_uuid=True)),
        sa.Column("allowed_actions", postgresql.JSONB(), nullable=False),
        sa.Column("max_risk", sa.String(20), nullable=False),
        sa.Column("budget_limit", sa.Numeric(14, 2)),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.Text()), *_timestamps(),
        sa.ForeignKeyConstraint(["grantor_user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], [f"{SCHEMA}.products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], [f"{SCHEMA}.projects.id"], ondelete="CASCADE"), schema=SCHEMA,
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", sa.String(100), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_hash", sa.String(64), nullable=False),
        sa.Column("approval_type", sa.String(100), nullable=False),
        sa.Column("policy_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("requested_by_type", sa.String(20), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_name", sa.String(150), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(150), unique=True), *_timestamps(),
        sa.ForeignKeyConstraint(["policy_evaluation_id"], [f"{SCHEMA}.policy_evaluations.id"], ondelete="RESTRICT"), schema=SCHEMA,
    )
    op.create_index(
        "uq_approval_requests_pending_target", "approval_requests",
        ["target_type", "target_id", "target_revision_id", "approval_type"], unique=True,
        schema=SCHEMA, postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "approval_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("decided_by_type", sa.String(20), nullable=False),
        sa.Column("decided_by_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by_name", sa.String(150), nullable=False),
        sa.Column("authority_source", sa.String(50), nullable=False),
        sa.Column("delegation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("comments", sa.Text()),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column("idempotency_key", sa.String(150), unique=True), *_timestamps(),
        sa.ForeignKeyConstraint(["approval_request_id"], [f"{SCHEMA}.approval_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["delegation_id"], [f"{SCHEMA}.authority_delegations.id"], ondelete="SET NULL"), schema=SCHEMA,
    )
    op.execute(sa.text("""
        INSERT INTO company.policies (id,name,description,policy_type,rules,is_active,entity_type,created_at,updated_at)
        VALUES (CAST(:policy_id AS uuid),'Concept approval v1','Governed approval for ProductConcept and System Map','approval_required',CAST(:rules AS jsonb),true,'product_concept',now(),now())
        ON CONFLICT (name) DO NOTHING
    """).bindparams(policy_id=POLICY_ID, rules=RULES))
    op.execute(sa.text("""
        INSERT INTO company.policy_versions (id,policy_id,version,rules_snapshot,evaluator_type,content_hash,status,created_at,updated_at)
        SELECT CAST(:version_id AS uuid), id, 1, CAST(:rules AS jsonb), 'structured', :content_hash, 'active', now(), now()
        FROM company.policies WHERE name='Concept approval v1'
        ON CONFLICT (policy_id,version) DO NOTHING
    """).bindparams(version_id=VERSION_ID, rules=RULES, content_hash=hashlib.sha256(RULES.encode()).hexdigest()))
    op.execute(sa.text("""
        INSERT INTO company.policy_bindings (id,policy_version_id,target_type,priority,is_active,created_at,updated_at)
        SELECT CAST(:binding_id AS uuid), id, 'product_concept', 100, true, now(), now()
        FROM company.policy_versions WHERE id=CAST(:version_id AS uuid)
        ON CONFLICT DO NOTHING
    """).bindparams(binding_id=BINDING_ID, version_id=VERSION_ID))


def downgrade() -> None:
    for table in (
        "approval_decisions", "approval_requests", "authority_delegations", "policy_evaluations",
        "policy_bindings", "policy_versions", "agent_service_credentials", "profile_action_permissions",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.execute(sa.text("DELETE FROM company.policies WHERE id=:id").bindparams(id=POLICY_ID))
