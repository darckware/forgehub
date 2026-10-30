"""M0.0b: mission planning records.

Plano Integrado Onda 1, M0.0b (docs/architecture/MCP_MISSION_TOOLS_SPEC.md
§2.6): the records the P1-P8 exit conditions and the dossier transition read.
`project_tasks` gains `target_environment`/`environment_prerequisites`; six
new tables hold the plan version author, per-layer and cross reviews,
Marcelo's waivers, review items with dispositions and decisions, the sampled
verification and the dossier version.

Downgrade drops them without touching missions, plans or baselines; records
written meanwhile are lost (dump them first if a mission is mid-planning).

Revision ID: c5a8e2f71d04
Revises: d3f7a1c9e2b5
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c5a8e2f71d04"
down_revision = "d3f7a1c9e2b5"
branch_labels = None
depends_on = None

SCHEMA = "company"
REVIEW_LAYERS = (
    "architecture", "backend", "frontend", "security", "lgpd",
    "infrastructure", "documentation", "business",
)
DISPOSITIONS = ("accept", "adjust", "reject")


def _in(values) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _uuid(name: str, fk: str | None = None, *, nullable: bool = False, ondelete: str | None = None,
           primary_key: bool = False) -> sa.Column:
    args = [sa.ForeignKey(f"{SCHEMA}.{fk}", ondelete=ondelete)] if fk else []
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable, primary_key=primary_key)


def upgrade():
    op.add_column("project_tasks", sa.Column("target_environment", sa.String(20), nullable=True), schema=SCHEMA)
    op.add_column(
        "project_tasks", sa.Column("environment_prerequisites", postgresql.ARRAY(sa.Text()), nullable=True),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_project_tasks_target_environment", "project_tasks",
        "target_environment IS NULL OR target_environment IN ('test', 'homolog', 'production')",
        schema=SCHEMA,
    )

    op.create_table(
        "mission_plan_versions",
        _uuid("project_plan_id", "project_plans.id", ondelete="CASCADE", primary_key=True),
        _uuid("mission_project_id", "projects.id", ondelete="CASCADE"),
        sa.Column("author_type", sa.String(10), nullable=False),
        _uuid("author_id"),
        sa.Column("author_name", sa.String(150), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("author_type IN ('user', 'agent')", name="ck_mission_plan_versions_author_type"),
        schema=SCHEMA,
    )

    op.create_table(
        "mission_plan_reviews",
        _uuid("id", primary_key=True),
        _uuid("mission_project_id", "projects.id", ondelete="CASCADE"),
        _uuid("project_plan_id", "project_plans.id", ondelete="CASCADE"),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("layer", sa.String(20), nullable=False),
        _uuid("reviewer_agent_id", "agents.id"),
        _uuid("artifact_version_id", "artifact_versions.id"),
        sa.Column("summary", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("kind IN ('layer', 'cross')", name="ck_mission_plan_reviews_kind"),
        sa.CheckConstraint(f"layer IN {_in(REVIEW_LAYERS)}", name="ck_mission_plan_reviews_layer"),
        sa.UniqueConstraint("project_plan_id", "kind", "layer", "reviewer_agent_id",
                            name="uq_mission_plan_reviews_reviewer"),
        schema=SCHEMA,
    )
    op.create_index("ix_mission_plan_reviews_plan", "mission_plan_reviews", ["project_plan_id"], schema=SCHEMA)

    op.create_table(
        "mission_review_waivers",
        _uuid("id", primary_key=True),
        _uuid("mission_project_id", "projects.id", ondelete="CASCADE"),
        _uuid("project_plan_id", "project_plans.id", ondelete="CASCADE"),
        sa.Column("layer", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(150), nullable=False),
        _uuid("decided_by_user_id", "users.id"),
        *_timestamps(),
        sa.CheckConstraint(f"layer IN {_in(REVIEW_LAYERS)}", name="ck_mission_review_waivers_layer"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_review_waivers_reason"),
        sa.UniqueConstraint("project_plan_id", "layer", name="uq_mission_review_waivers_layer"),
        schema=SCHEMA,
    )

    op.create_table(
        "mission_review_items",
        _uuid("id", primary_key=True),
        _uuid("review_id", "mission_plan_reviews.id", ondelete="CASCADE"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("disposition", sa.String(10), nullable=True),
        sa.Column("disposition_reason", sa.Text(), nullable=True),
        sa.Column("disposed_by", sa.String(150), nullable=True),
        sa.Column("disposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_marcelo_decision", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("marcelo_decision", sa.String(10), nullable=True),
        sa.Column("marcelo_reason", sa.Text(), nullable=True),
        sa.Column("marcelo_decided_by", sa.String(150), nullable=True),
        _uuid("marcelo_user_id", "users.id", nullable=True),
        sa.Column("marcelo_decided_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("length(btrim(text)) > 0", name="ck_mission_review_items_text"),
        sa.CheckConstraint(f"disposition IS NULL OR disposition IN {_in(DISPOSITIONS)}",
                           name="ck_mission_review_items_disposition"),
        sa.CheckConstraint(
            "(disposition IS NULL) = (disposition_reason IS NULL) "
            "AND (disposition_reason IS NULL OR length(btrim(disposition_reason)) > 0)",
            name="ck_mission_review_items_disposition_reason",
        ),
        sa.CheckConstraint(
            f"marcelo_decision IS NULL OR (needs_marcelo_decision AND marcelo_decision IN {_in(DISPOSITIONS)})",
            name="ck_mission_review_items_marcelo_decision",
        ),
        sa.CheckConstraint(
            "(marcelo_decision IS NULL) = (marcelo_reason IS NULL) "
            "AND (marcelo_decision IS NULL) = (marcelo_decided_by IS NULL) "
            "AND (marcelo_decision IS NULL) = (marcelo_user_id IS NULL) "
            "AND (marcelo_decision IS NULL) = (marcelo_decided_at IS NULL) "
            "AND (marcelo_reason IS NULL OR length(btrim(marcelo_reason)) > 0)",
            name="ck_mission_review_items_marcelo_fields",
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_mission_review_items_review", "mission_review_items", ["review_id"], schema=SCHEMA)

    op.create_table(
        "mission_plan_verifications",
        _uuid("id", primary_key=True),
        _uuid("mission_project_id", "projects.id", ondelete="CASCADE"),
        _uuid("project_plan_id", "project_plans.id", ondelete="CASCADE"),
        _uuid("verifier_agent_id", "agents.id"),
        sa.Column("sampled_item_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
                  server_default="{}", nullable=False),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("result IN ('confirmed', 'discrepancies')", name="ck_mission_plan_verifications_result"),
        schema=SCHEMA,
    )
    op.create_index("ix_mission_plan_verifications_plan", "mission_plan_verifications",
                    ["project_plan_id", "created_at"], schema=SCHEMA)

    op.create_table(
        "mission_dossiers",
        _uuid("id", primary_key=True),
        _uuid("mission_project_id", "projects.id", ondelete="CASCADE"),
        _uuid("artifact_version_id", "artifact_versions.id"),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("registered_by_type", sa.String(10), nullable=False),
        _uuid("registered_by_id"),
        sa.Column("registered_by", sa.String(150), nullable=False),
        *_timestamps(),
        sa.CheckConstraint("file_sha256 ~ '^[0-9a-f]{64}$'", name="ck_mission_dossiers_file_sha256"),
        sa.CheckConstraint("registered_by_type IN ('user', 'agent')", name="ck_mission_dossiers_registered_by_type"),
        schema=SCHEMA,
    )
    op.create_index("ix_mission_dossiers_mission", "mission_dossiers", ["mission_project_id", "created_at"],
                    schema=SCHEMA)


def downgrade():
    op.drop_index("ix_mission_dossiers_mission", table_name="mission_dossiers", schema=SCHEMA)
    op.drop_table("mission_dossiers", schema=SCHEMA)
    op.drop_index("ix_mission_plan_verifications_plan", table_name="mission_plan_verifications", schema=SCHEMA)
    op.drop_table("mission_plan_verifications", schema=SCHEMA)
    op.drop_index("ix_mission_review_items_review", table_name="mission_review_items", schema=SCHEMA)
    op.drop_table("mission_review_items", schema=SCHEMA)
    op.drop_table("mission_review_waivers", schema=SCHEMA)
    op.drop_index("ix_mission_plan_reviews_plan", table_name="mission_plan_reviews", schema=SCHEMA)
    op.drop_table("mission_plan_reviews", schema=SCHEMA)
    op.drop_table("mission_plan_versions", schema=SCHEMA)
    op.drop_constraint("ck_project_tasks_target_environment", "project_tasks", type_="check", schema=SCHEMA)
    op.drop_column("project_tasks", "environment_prerequisites", schema=SCHEMA)
    op.drop_column("project_tasks", "target_environment", schema=SCHEMA)
