"""M0.0: mission project type and minimal coordination base.

Plano Integrado Onda 1, M0.0 (docs/architecture/MCP_MISSION_TOOLS_SPEC.md
§2, §3.1, §6.1; MISSION_ORCHESTRATOR_CYCLE_SPEC.md §4):
- projects.project_type accepts 'mission';
- project_missions (state machine + planning pipeline columns);
- mission_project_links, mission_acceptance_criteria, mission_criterion_tasks;
- mission_decisions (M0.0 records planning stage changes there);
- project_tasks.required_skill_ids.

Downgrade refuses while any mission project exists: turning a mission into a
common project silently is a decision for the operator, never the migration.

Revision ID: f2c7a4e9b1d3
Revises: e4b8c1d7a9f3
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2c7a4e9b1d3"
down_revision = "e4b8c1d7a9f3"
branch_labels = None
depends_on = None

SCHEMA = "company"
UUID = postgresql.UUID(as_uuid=True)

MISSION_STATES = (
    "draft", "planning", "ready", "active", "verifying",
    "awaiting_acceptance", "paused", "completed", "cancelled",
)
PLANNING_STAGES = (
    "draft_plan", "auto_check", "critical_review", "consolidation",
    "cross_review", "decisions", "application", "baseline",
)
REVIEW_LAYERS = (
    "architecture", "backend", "frontend", "security", "lgpd",
    "infrastructure", "documentation", "business",
)
DECISION_ACTIONS = (
    "dispatch", "schedule", "reassign", "request_review", "return", "reprocess",
    "integrate", "reverify", "ask_marcelo", "pause", "defer", "undo", "lock",
    "unlock", "advance_planning",
)


def _in(values):
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade():
    op.drop_constraint("ck_projects_project_type", "projects", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_projects_project_type", "projects",
        "project_type IN ('creation', 'maintenance', 'mission')", schema=SCHEMA,
    )

    op.create_table(
        "project_missions",
        sa.Column("project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("paused_from_state", sa.String(30), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("orchestrator_agent_id", UUID, sa.ForeignKey(f"{SCHEMA}.agents.id"), nullable=False),
        sa.Column("autonomy_level", sa.String(2), nullable=False, server_default="N0"),
        sa.Column("brief_artifact_id", UUID, sa.ForeignKey(f"{SCHEMA}.artifacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("current_baseline_id", UUID, sa.ForeignKey(f"{SCHEMA}.plan_baselines.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("budget_limit", sa.Numeric(14, 2), nullable=True),
        sa.Column("paused_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("state_reason", sa.Text(), nullable=True),
        sa.Column("acceptance_request_id", UUID, sa.ForeignKey(f"{SCHEMA}.approval_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("planning_stage", sa.String(20), nullable=True),
        sa.Column("risk_level", sa.String(10), nullable=True),
        sa.Column("required_review_layers", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        *_timestamps(),
        sa.CheckConstraint(f"state IN {_in(MISSION_STATES)}", name="ck_project_missions_state"),
        sa.CheckConstraint("(state = 'paused') = (paused_from_state IS NOT NULL)", name="ck_project_missions_paused_from_state"),
        sa.CheckConstraint(
            f"paused_from_state IS NULL OR paused_from_state IN {_in(MISSION_STATES)}",
            name="ck_project_missions_paused_from_state_value",
        ),
        sa.CheckConstraint("priority BETWEEN 1 AND 1000", name="ck_project_missions_priority"),
        sa.CheckConstraint("autonomy_level IN ('N0', 'N1', 'N2', 'N3')", name="ck_project_missions_autonomy_level"),
        sa.CheckConstraint(
            f"planning_stage IS NULL OR planning_stage IN {_in(PLANNING_STAGES)}",
            name="ck_project_missions_planning_stage",
        ),
        sa.CheckConstraint("risk_level IS NULL OR risk_level IN ('low', 'medium', 'high')", name="ck_project_missions_risk_level"),
        sa.CheckConstraint(
            f"required_review_layers <@ ARRAY{list(REVIEW_LAYERS)!r}::varchar[]",
            name="ck_project_missions_review_layers",
        ),
        sa.CheckConstraint("paused_seconds >= 0", name="ck_project_missions_paused_seconds"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_project_missions_orchestrator_state", "project_missions",
        ["orchestrator_agent_id", "state"], schema=SCHEMA,
    )

    op.create_table(
        "mission_project_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("mission_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("executor_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("linked_by", sa.String(150), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("mission_project_id", "executor_project_id", name="uq_mission_project_links_pair"),
        sa.CheckConstraint("mission_project_id <> executor_project_id", name="ck_mission_project_links_distinct"),
        schema=SCHEMA,
    )

    op.create_table(
        "mission_acceptance_criteria",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("mission_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("verification_method", sa.Text(), nullable=False),
        sa.Column("verifier_agent_id", UUID, sa.ForeignKey(f"{SCHEMA}.agents.id"), nullable=True),
        sa.Column("verifier_is_marcelo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("evidence_ref", sa.String(500), nullable=True),
        sa.Column("decided_by", sa.String(150), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("mission_project_id", "code", name="uq_mission_acceptance_criteria_code"),
        sa.CheckConstraint(
            "(verifier_agent_id IS NOT NULL) <> verifier_is_marcelo",
            name="ck_mission_acceptance_criteria_one_verifier",
        ),
        sa.CheckConstraint("status IN ('open', 'proven', 'failed')", name="ck_mission_acceptance_criteria_status"),
        schema=SCHEMA,
    )

    op.create_table(
        "mission_criterion_tasks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "criterion_id", UUID,
            sa.ForeignKey(f"{SCHEMA}.mission_acceptance_criteria.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("task_id", UUID, sa.ForeignKey(f"{SCHEMA}.project_tasks.id", ondelete="RESTRICT"), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("criterion_id", "task_id", name="uq_mission_criterion_tasks_pair"),
        schema=SCHEMA,
    )

    op.create_table(
        "mission_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("mission_project_id", UUID, sa.ForeignKey(f"{SCHEMA}.projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", UUID, nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("task_id", UUID, sa.ForeignKey(f"{SCHEMA}.project_tasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("demand_id", UUID, sa.ForeignKey(f"{SCHEMA}.agent_demands.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "review_id", UUID,
            sa.ForeignKey(f"{SCHEMA}.task_execution_reviews.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("question_id", UUID, sa.ForeignKey(f"{SCHEMA}.agent_questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("facts", postgresql.JSONB(), nullable=True),
        sa.Column("autonomy_level", sa.String(2), nullable=False),
        sa.Column("actor_type", sa.String(20), nullable=False),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("actor_name", sa.String(150), nullable=False),
        sa.Column("authority_source", sa.String(30), nullable=False),
        sa.Column(
            "delegation_id", UUID,
            sa.ForeignKey(f"{SCHEMA}.authority_delegations.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("refusal_code", sa.String(60), nullable=True),
        sa.Column(
            "undone_by_decision_id", UUID,
            sa.ForeignKey(f"{SCHEMA}.mission_decisions.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(150), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(f"action IN {_in(DECISION_ACTIONS)}", name="ck_mission_decisions_action"),
        sa.CheckConstraint(
            "status IN ('applied', 'refused', 'deferred', 'undone')", name="ck_mission_decisions_status"
        ),
        sa.CheckConstraint("autonomy_level IN ('N0', 'N1', 'N2', 'N3')", name="ck_mission_decisions_autonomy_level"),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_mission_decisions_reason"),
        sa.UniqueConstraint("actor_type", "actor_id", "idempotency_key", name="uq_mission_decisions_actor_key"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_mission_decisions_mission", "mission_decisions",
        ["mission_project_id", "created_at"], schema=SCHEMA,
    )

    op.add_column(
        "project_tasks",
        sa.Column("required_skill_ids", postgresql.ARRAY(UUID), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )


def downgrade():
    bind = op.get_bind()
    missions = bind.execute(
        sa.text(f"SELECT count(*) FROM {SCHEMA}.projects WHERE project_type = 'mission'")
    ).scalar_one()
    if missions:
        raise RuntimeError(
            f"Refusing to downgrade M0.0: {missions} mission project(s) exist. "
            "Decide what to do with them (cancel and remove, or keep this revision); "
            "a downgrade never turns a mission into a common project."
        )

    op.drop_column("project_tasks", "required_skill_ids", schema=SCHEMA)
    op.drop_index("ix_mission_decisions_mission", table_name="mission_decisions", schema=SCHEMA)
    op.drop_table("mission_decisions", schema=SCHEMA)
    op.drop_table("mission_criterion_tasks", schema=SCHEMA)
    op.drop_table("mission_acceptance_criteria", schema=SCHEMA)
    op.drop_table("mission_project_links", schema=SCHEMA)
    op.drop_index("ix_project_missions_orchestrator_state", table_name="project_missions", schema=SCHEMA)
    op.drop_table("project_missions", schema=SCHEMA)

    op.drop_constraint("ck_projects_project_type", "projects", schema=SCHEMA, type_="check")
    op.create_check_constraint(
        "ck_projects_project_type", "projects",
        "project_type IN ('creation', 'maintenance')", schema=SCHEMA,
    )
