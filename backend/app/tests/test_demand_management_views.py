from sqlalchemy import Boolean, Column, MetaData, String, Table, create_engine, select


def test_decision_and_approval_views_keep_task_types_separate():
    from app.core.demand_management import view_filter

    work = Table("work", MetaData(), Column("id", String), Column("status", String),
        Column("work_state", String), Column("operator_state", String), Column("origin_type", String),
        Column("blocked_question", Boolean), Column("requires_approval", Boolean), Column("approval_status", String))
    rows = [
        {"id": "correction", "status": "new", "work_state": "failed", "operator_state": "decision",
         "origin_type": "task", "blocked_question": False, "requires_approval": False, "approval_status": None},
        {"id": "approval", "status": "new", "work_state": "approval", "operator_state": "decision",
         "origin_type": "task", "blocked_question": False, "requires_approval": True, "approval_status": "pending"},
        {"id": "question", "status": "new", "work_state": "question", "operator_state": "decision",
         "origin_type": "task", "blocked_question": True, "requires_approval": False, "approval_status": None},
        {"id": "incubation", "status": "new", "work_state": "approval", "operator_state": "decision",
         "origin_type": "incubation", "blocked_question": False, "requires_approval": True, "approval_status": "pending"},
    ]
    decisions = view_filter("decision", work.c.work_state, operator=work.c.operator_state,
        demand=work.c, question=work.c.blocked_question)
    approvals = view_filter("approvals_queue", work.c.work_state, operator=work.c.operator_state,
        demand=work.c, question=work.c.blocked_question)
    with create_engine("sqlite://").begin() as connection:
        work.create(connection)
        connection.execute(work.insert(), rows)
        decision_ids = set(connection.scalars(select(work.c.id).where(decisions, work.c.origin_type == "task")))
        approval_ids = set(connection.scalars(select(work.c.id).where(approvals)))
    assert decision_ids == {"correction"}
    assert approval_ids == {"approval"}
