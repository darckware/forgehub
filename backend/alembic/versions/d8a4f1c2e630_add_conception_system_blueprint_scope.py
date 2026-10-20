"""add conception system blueprint and project scope

Revision ID: d8a4f1c2e630
Revises: c7f9a3e2b541
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8a4f1c2e630"
down_revision: Union[str, Sequence[str], None] = "c7f9a3e2b541"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "company"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute(sa.text("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE c.conname = 'ck_products_status'
                  AND t.relname = 'products' AND n.nspname = 'company'
            ) THEN
                ALTER TABLE company.products DROP CONSTRAINT ck_products_status;
            END IF;
        END $$
    """))
    op.create_check_constraint(
        "ck_products_status", "products", "status IN ('concept','active','inactive','archived')", schema=SCHEMA
    )

    op.create_table(
        "development_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_ref", sa.String(500)),
        sa.Column("requested_by", sa.String(255)),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("triage_result", postgresql.JSONB()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_id"], [f"{SCHEMA}.products.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "request_type IN ('new_product','feature','bug','maintenance','research','compliance','incident_follow_up')",
            name="ck_development_requests_type",
        ),
        sa.CheckConstraint(
            "status IN ('received','triaging','accepted','rejected','converted','cancelled')",
            name="ck_development_requests_status",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "product_concepts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("current_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", sa.String(255)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_id"], [f"{SCHEMA}.products.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('draft','in_review','approved','rework','hold','rejected','superseded')",
            name="ck_product_concepts_status",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "product_concept_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("concept_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("problem_statement", sa.Text(), nullable=False),
        sa.Column("vision", sa.Text()),
        sa.Column("stakeholders", postgresql.JSONB()),
        sa.Column("personas", postgresql.JSONB()),
        sa.Column("objectives", postgresql.JSONB()),
        sa.Column("success_metrics", postgresql.JSONB()),
        sa.Column("constraints", postgresql.JSONB()),
        sa.Column("assumptions", postgresql.JSONB()),
        sa.Column("risks", postgresql.JSONB()),
        sa.Column("scope_summary", sa.Text()),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(255)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["concept_id"], [f"{SCHEMA}.product_concepts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("concept_id", "revision", name="uq_concept_revisions_concept_revision"),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_product_concepts_current_revision",
        "product_concepts", "product_concept_revisions",
        ["current_revision_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL",
    )

    op.create_table(
        "system_blueprints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("current_revision_id", postgresql.UUID(as_uuid=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_id"], [f"{SCHEMA}.products.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )
    op.create_table(
        "system_blueprint_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("blueprint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("concept_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("product_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("created_by", sa.String(255)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["blueprint_id"], [f"{SCHEMA}.system_blueprints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_revision_id"], [f"{SCHEMA}.product_concept_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_version_id"], [f"{SCHEMA}.product_versions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("blueprint_id", "revision", name="uq_blueprint_revisions_blueprint_revision"),
        sa.CheckConstraint("status IN ('draft','in_review','approved','superseded')", name="ck_blueprint_revisions_status"),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_system_blueprints_current_revision",
        "system_blueprints", "system_blueprint_revisions",
        ["current_revision_id"], ["id"], source_schema=SCHEMA, referent_schema=SCHEMA, ondelete="SET NULL",
    )

    op.create_table(
        "system_elements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stable_key", sa.String(160), nullable=False),
        sa.Column("family", sa.String(30), nullable=False),
        sa.Column("element_type", sa.String(40), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("lifecycle_status", sa.String(30), nullable=False),
        sa.Column("criticality", sa.String(20), nullable=False),
        sa.Column("owner_ref", sa.String(255)),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["product_id"], [f"{SCHEMA}.products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], [f"{SCHEMA}.system_elements.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("product_id", "stable_key", name="uq_system_elements_product_stable_key"),
        sa.CheckConstraint(
            "family IN ('business','process','experience','interface','domain','application','data','runtime','assurance')",
            name="ck_system_elements_family",
        ),
        sa.CheckConstraint(
            "element_type IN ('capability','module','persona','journey','process','process_step','use_case',"
            "'application','channel','route','screen','form','report','ui_component','api','endpoint','command',"
            "'query','event','webhook','integration','domain_entity','value_object','business_rule',"
            "'authorization_rule','service','handler','class','method','workflow','job','datastore','schema',"
            "'table','field','index','view','procedure','migration','runtime_component','queue','cache',"
            "'deployment_unit','environment_target','test_scenario','metric','log_signal','alert','slo','health_check')",
            name="ck_system_elements_type",
        ),
        sa.CheckConstraint("lifecycle_status IN ('proposed','active','deprecated','removed')", name="ck_system_elements_lifecycle"),
        schema=SCHEMA,
    )
    op.create_table(
        "system_element_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("system_element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blueprint_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("spec_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("source_ref", sa.String(500)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["system_element_id"], [f"{SCHEMA}.system_elements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blueprint_revision_id"], [f"{SCHEMA}.system_blueprint_revisions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("blueprint_revision_id", "system_element_id", name="uq_element_revisions_blueprint_element"),
        schema=SCHEMA,
    )
    op.create_table(
        "system_element_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("blueprint_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_type", sa.String(40), nullable=False),
        sa.Column("attributes", postgresql.JSONB()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["blueprint_revision_id"], [f"{SCHEMA}.system_blueprint_revisions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_element_id"], [f"{SCHEMA}.system_elements.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_element_id"], [f"{SCHEMA}.system_elements.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "blueprint_revision_id", "from_element_id", "to_element_id", "relation_type",
            name="uq_system_element_relations_revision_edge",
        ),
        sa.CheckConstraint("from_element_id <> to_element_id", name="ck_system_element_relations_not_self"),
        sa.CheckConstraint(
            "relation_type IN ('contains','precedes','navigates_to','invokes','implements','governed_by',"
            "'reads','writes','emits','consumes','depends_on','persists_as','runs_on','deployed_to','verified_by')",
            name="ck_system_element_relations_type",
        ),
        schema=SCHEMA,
    )

    op.create_table(
        "project_scopes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blueprint_base_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("created_by", sa.String(255)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], [f"{SCHEMA}.projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blueprint_base_revision_id"], [f"{SCHEMA}.system_blueprint_revisions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "revision", name="uq_project_scopes_project_revision"),
        sa.CheckConstraint("status IN ('draft','in_review','baselined','superseded')", name="ck_project_scopes_status"),
        schema=SCHEMA,
    )
    op.create_table(
        "project_scope_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_scope_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("system_element_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("base_element_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("target_element_revision_id", postgresql.UUID(as_uuid=True)),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("applicability", sa.String(30), nullable=False),
        sa.Column("rationale", sa.Text()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_scope_id"], [f"{SCHEMA}.project_scopes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["system_element_id"], [f"{SCHEMA}.system_elements.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["base_element_revision_id"], [f"{SCHEMA}.system_element_revisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_element_revision_id"], [f"{SCHEMA}.system_element_revisions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("project_scope_id", "system_element_id", name="uq_project_scope_items_scope_element"),
        sa.CheckConstraint("change_type IN ('add','modify','remove','deprecate','verify')", name="ck_project_scope_items_change_type"),
        sa.CheckConstraint("applicability IN ('required','optional','not_applicable')", name="ck_project_scope_items_applicability"),
        sa.CheckConstraint("applicability <> 'not_applicable' OR rationale IS NOT NULL", name="ck_project_scope_items_na_rationale"),
        schema=SCHEMA,
    )
    op.create_table(
        "scope_item_acceptance_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_scope_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criterion", sa.Text(), nullable=False),
        sa.Column("verification_type", sa.String(50), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_scope_item_id"], [f"{SCHEMA}.project_scope_items.id"], ondelete="CASCADE"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "scope_item_acceptance_criteria", "project_scope_items", "project_scopes",
        "system_element_relations", "system_element_revisions", "system_elements",
    ):
        op.drop_table(table, schema=SCHEMA)
    op.drop_constraint("fk_system_blueprints_current_revision", "system_blueprints", schema=SCHEMA, type_="foreignkey")
    op.drop_table("system_blueprint_revisions", schema=SCHEMA)
    op.drop_table("system_blueprints", schema=SCHEMA)
    op.drop_constraint("fk_product_concepts_current_revision", "product_concepts", schema=SCHEMA, type_="foreignkey")
    op.drop_table("product_concept_revisions", schema=SCHEMA)
    op.drop_table("product_concepts", schema=SCHEMA)
    op.drop_table("development_requests", schema=SCHEMA)
    op.execute(sa.text("ALTER TABLE company.products DROP CONSTRAINT IF EXISTS ck_products_status"))
    op.create_check_constraint(
        "ck_products_status", "products", "status IN ('active','inactive','archived')", schema=SCHEMA
    )
