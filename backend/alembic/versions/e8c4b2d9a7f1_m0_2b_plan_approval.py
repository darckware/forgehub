"""M0.2b: governed mission plan approval, unique dependencies, one skill store.

Plano Integrado Onda 1, M0.2b (docs/architecture/MCP_MISSION_TOOLS_SPEC.md
§5.3, §5.4, §7):

- ``mission_plan_submissions``: what a ``submit_project_plan`` put up for
  approval (the plan, the task ids the baseline will authorize, the plan hash
  and the automatic checks), one row per governed ``ApprovalRequest``.
- ``project_plans.change_request_id``: the approved change request a
  post-baseline plan applies (§7 item 6).
- Policy ``Mission plan approval v1`` bound to ``project_plan``
  (``deny_self_approval``, ``human_only``, ``expires_hours: 168``).
- ``task_dependencies``: ``UNIQUE (task_id, depends_on_task_id)``. Duplicates
  are collapsed into the oldest row; every removed row is kept in
  ``audit_events`` (``task_dependency_duplicate_removed``), not lost.
- DT-M0-1: ``task_required_skills`` is the one store of a task's required
  skills. ``project_tasks.required_skill_ids`` (M0.0) is folded into it as
  mandatory rows and dropped; ``UNIQUE (task_id, skill_id)`` after collapsing
  duplicates the same audited way. An id that is not a skill can't be a row
  (FK); it is recorded in ``audit_events`` instead.

Downgrade restores the column (from the mandatory rows) and drops the rest;
it refuses while a governed ``project_plan`` approval request exists. The
collapsed duplicates are not recreated (their content stays in the audit).

Revision ID: e8c4b2d9a7f1
Revises: c5a8e2f71d04
"""
import hashlib
import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e8c4b2d9a7f1"
down_revision = "c5a8e2f71d04"
branch_labels = None
depends_on = None

SCHEMA = "company"
ACTOR = "migration e8c4b2d9a7f1"
POLICY_ID = "6c1f7a52-0b8e-4c55-9d3e-5a9d2f6b1e01"
VERSION_ID = "6c1f7a52-0b8e-4c55-9d3e-5a9d2f6b1e02"
BINDING_ID = "6c1f7a52-0b8e-4c55-9d3e-5a9d2f6b1e03"
POLICY_NAME = "Mission plan approval v1"
RULES = json.dumps({"deny_self_approval": True, "human_only": True, "expires_hours": 168}, sort_keys=True)


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _uuid(name: str, fk: str | None = None, *, nullable: bool = False, ondelete: str | None = None,
           primary_key: bool = False) -> sa.Column:
    args = [sa.ForeignKey(f"{SCHEMA}.{fk}", ondelete=ondelete)] if fk else []
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable, primary_key=primary_key)


def _collapse_duplicates(table: str, key: tuple[str, str], event_type: str) -> None:
    """Keep the oldest row of each duplicate key; audit then delete the rest."""
    a, b = key
    ranked = f"""
        SELECT id, task_id, row_number() OVER (PARTITION BY {a}, {b} ORDER BY created_at, id) AS rn
        FROM {SCHEMA}.{table}
    """
    op.execute(f"""
        INSERT INTO {SCHEMA}.audit_events (id, entity_type, entity_id, event_type, actor, payload, created_at, updated_at)
        SELECT gen_random_uuid(), 'project_task', r.task_id, '{event_type}', '{ACTOR}',
               to_jsonb(t.*) || jsonb_build_object('reason', 'unique ({a}, {b}) added by M0.2b'), now(), now()
        FROM ({ranked}) r JOIN {SCHEMA}.{table} t ON t.id = r.id
        WHERE r.rn > 1
    """)
    op.execute(f"DELETE FROM {SCHEMA}.{table} WHERE id IN (SELECT id FROM ({ranked}) r WHERE r.rn > 1)")


def upgrade():
    # -- Unique dependencies (§5.4) ------------------------------------------
    _collapse_duplicates("task_dependencies", ("task_id", "depends_on_task_id"), "task_dependency_duplicate_removed")
    op.create_unique_constraint("uq_task_dependencies_pair", "task_dependencies",
                                ["task_id", "depends_on_task_id"], schema=SCHEMA)

    # -- DT-M0-1: one store of required skills --------------------------------
    # A duplicate that was mandatory keeps the kept row mandatory.
    op.execute(f"""
        UPDATE {SCHEMA}.task_required_skills k SET is_mandatory = true
        WHERE NOT k.is_mandatory AND EXISTS (
            SELECT 1 FROM {SCHEMA}.task_required_skills d
            WHERE d.task_id = k.task_id AND d.skill_id = k.skill_id AND d.id <> k.id AND d.is_mandatory)
    """)
    _collapse_duplicates("task_required_skills", ("task_id", "skill_id"), "task_required_skill_duplicate_removed")
    op.create_unique_constraint("uq_task_required_skills_pair", "task_required_skills",
                                ["task_id", "skill_id"], schema=SCHEMA)
    listed = f"SELECT t.id AS task_id, unnest(t.required_skill_ids) AS skill_id FROM {SCHEMA}.project_tasks t"
    op.execute(f"""
        INSERT INTO {SCHEMA}.audit_events (id, entity_type, entity_id, event_type, actor, payload, created_at, updated_at)
        SELECT gen_random_uuid(), 'project_task', l.task_id, 'task_required_skill_unknown_dropped', '{ACTOR}',
               jsonb_build_object('skill_id', l.skill_id, 'reason', 'required_skill_ids folded into task_required_skills'),
               now(), now()
        FROM ({listed}) l WHERE NOT EXISTS (SELECT 1 FROM {SCHEMA}.skills s WHERE s.id = l.skill_id)
    """)
    op.execute(f"""
        INSERT INTO {SCHEMA}.task_required_skills (id, task_id, skill_id, is_mandatory, created_at, updated_at)
        SELECT gen_random_uuid(), l.task_id, l.skill_id, true, now(), now()
        FROM (SELECT DISTINCT * FROM ({listed}) x) l
        WHERE EXISTS (SELECT 1 FROM {SCHEMA}.skills s WHERE s.id = l.skill_id)
        ON CONFLICT (task_id, skill_id) DO UPDATE SET is_mandatory = true
    """)
    op.drop_column("project_tasks", "required_skill_ids", schema=SCHEMA)

    # -- The plan a change request is applied by (§7 item 6) -----------------
    op.add_column("project_plans", _uuid("change_request_id", "change_requests.id", nullable=True,
                                         ondelete="SET NULL"), schema=SCHEMA)

    # -- What a submit_project_plan put up for approval (§5.3, §7) -----------
    op.create_table(
        "mission_plan_submissions",
        _uuid("approval_request_id", "approval_requests.id", ondelete="CASCADE", primary_key=True),
        _uuid("mission_project_id", "projects.id", ondelete="CASCADE"),
        _uuid("project_plan_id", "project_plans.id", ondelete="CASCADE"),
        _uuid("change_request_id", "change_requests.id", nullable=True, ondelete="SET NULL"),
        sa.Column("task_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("plan_hash", sa.String(64), nullable=False),
        sa.Column("checks", postgresql.JSONB(), nullable=False),
        sa.Column("submitted_by_type", sa.String(10), nullable=False),
        _uuid("submitted_by_id"),
        sa.Column("submitted_by", sa.String(150), nullable=False),
        sa.Column("idempotency_key", sa.String(150), nullable=True),
        _uuid("baseline_id", "plan_baselines.id", nullable=True, ondelete="SET NULL"),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.String(150), nullable=True),
        sa.Column("withdrawn_reason", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("submitted_by_type IN ('user', 'agent')",
                           name="ck_mission_plan_submissions_submitted_by_type"),
        sa.CheckConstraint("cardinality(task_ids) > 0", name="ck_mission_plan_submissions_task_ids"),
        schema=SCHEMA,
    )
    op.create_index("ix_mission_plan_submissions_mission", "mission_plan_submissions",
                    ["mission_project_id", "created_at"], schema=SCHEMA)

    # -- Policy mission_plan_approval (§7 item 2) ----------------------------
    op.execute(sa.text(f"""
        INSERT INTO {SCHEMA}.policies (id,name,description,policy_type,rules,is_active,entity_type,created_at,updated_at)
        VALUES (CAST(:policy_id AS uuid), :name,
                'Governed approval of a mission plan baseline: a person (admin) decides, never the submitter',
                'approval_required', CAST(:rules AS jsonb), true, 'project_plan', now(), now())
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
        SELECT CAST(:binding_id AS uuid), id, 'project_plan', 100, true, now(), now()
        FROM {SCHEMA}.policy_versions WHERE id = CAST(:version_id AS uuid)
        ON CONFLICT DO NOTHING
    """).bindparams(binding_id=BINDING_ID, version_id=VERSION_ID))


def downgrade():
    conn = op.get_bind()
    pending = conn.execute(sa.text(
        f"SELECT count(*) FROM {SCHEMA}.approval_requests WHERE target_type = 'project_plan'"
    )).scalar()
    if pending:
        raise RuntimeError(
            f"Refusing to downgrade: {pending} governed project_plan approval request(s) exist; "
            "their submissions and policy would be lost. Dump them first."
        )
    op.execute(sa.text(f"""
        DELETE FROM {SCHEMA}.policy_evaluations WHERE policy_version_id = CAST(:version_id AS uuid)
    """).bindparams(version_id=VERSION_ID))
    op.execute(sa.text(f"DELETE FROM {SCHEMA}.policy_bindings WHERE id = CAST(:id AS uuid)").bindparams(id=BINDING_ID))
    op.execute(sa.text(f"DELETE FROM {SCHEMA}.policy_versions WHERE id = CAST(:id AS uuid)").bindparams(id=VERSION_ID))
    op.execute(sa.text(f"DELETE FROM {SCHEMA}.policies WHERE id = CAST(:id AS uuid)").bindparams(id=POLICY_ID))

    op.drop_index("ix_mission_plan_submissions_mission", table_name="mission_plan_submissions", schema=SCHEMA)
    op.drop_table("mission_plan_submissions", schema=SCHEMA)
    op.drop_column("project_plans", "change_request_id", schema=SCHEMA)

    op.add_column("project_tasks", sa.Column(
        "required_skill_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}", nullable=False,
    ), schema=SCHEMA)
    op.execute(f"""
        UPDATE {SCHEMA}.project_tasks t SET required_skill_ids = s.ids
        FROM (SELECT task_id, array_agg(skill_id ORDER BY created_at, id) AS ids
              FROM {SCHEMA}.task_required_skills WHERE is_mandatory GROUP BY task_id) s
        WHERE s.task_id = t.id
    """)
    op.drop_constraint("uq_task_required_skills_pair", "task_required_skills", type_="unique", schema=SCHEMA)
    op.drop_constraint("uq_task_dependencies_pair", "task_dependencies", type_="unique", schema=SCHEMA)
