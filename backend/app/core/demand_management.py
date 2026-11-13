"""Bounded operator queries and shared presentation of execution constraints."""
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.api.schemas.demand import DemandOut
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentQuestion
from app.db.models.moodle_approval import MoodleApproval
from app.core.demand_workflow import requires_reconciliation as uncertain
from app.db.models.message_triage import MessageTriageResult
from app.core.message_triage_revision import context_revision_sql

WORK_VIEWS = ("decision", "processing", "waiting", "resolved", "attention", "approval", "incubation", "failed", "queued", "running", "completed", "archived")
WORK_GROUPS = ("all", "tasks", "incubation")


def failure_category(demand):
    if demand.dispatch_status != "failed":
        return None
    if uncertain(demand):
        return "uncertain"
    error = (demand.dispatch_error or "").lower()
    if "temporarily unavailable" in error:
        return "transport"
    if "ended as" in error:
        return "runner_terminal"
    return "configuration" if error else "unknown"


def work_state_sql():
    blocked = exists(select(AgentQuestion.id).where(AgentQuestion.origin_demand_id == AgentDemand.id,
        AgentQuestion.blocking.is_(True), AgentQuestion.status == "pending"))
    return case(
        (AgentDemand.status == "archived", "archived"),
        (and_(AgentDemand.dispatch_status == "failed", or_(
            and_(AgentDemand.agent_run_id.isnot(None), or_(AgentDemand.dispatch_error.is_(None), AgentDemand.dispatch_error == "")),
            AgentDemand.dispatch_error.ilike("%uncertain%"))), "uncertain"),
        (AgentDemand.dispatch_status == "failed", "failed"),
        (or_(AgentDemand.dispatch_status.in_(("dispatched", "running")),
            and_(AgentDemand.dispatch_status.is_(None), AgentDemand.agent_run_id.isnot(None))), "running"),
        (AgentDemand.dispatch_status == "completed", "completed"),
        (and_(AgentDemand.requires_approval.is_(True), AgentDemand.approval_status == "rejected"), "rejected"),
        (blocked, "question"),
        (and_(AgentDemand.requires_approval.is_(True), or_(AgentDemand.approval_status.is_(None), AgentDemand.approval_status != "approved")), "approval"),
        (and_(AgentDemand.origin_type == "incubation", AgentDemand.incubation_state == "decision_pending"), "overdue"),
        (AgentDemand.origin_type == "incubation", "incubation"), else_="queued")


def active_failure_check_sql(demand=AgentDemand):
    """A diagnostic of this failure is still on its way: not the operator's turn yet."""
    check = aliased(AgentDemand)
    return exists(select(check.id).where(check.failure_check_source_id == demand.id,
        check.status != "archived", or_(check.dispatch_status.is_(None),
            check.dispatch_status.notin_(("completed", "failed")))))


def human_failure_sql(demand=AgentDemand):
    """A known failure or an uncertain run that only a person can move forward.

    Covers the dispatch failures Messages shows as "needs correction" and the
    uncertain runs that need reconciliation (``requires_reconciliation``: both
    have ``dispatch_status='failed'``). Left out: archived/consolidated items
    (already decided), incubations (their owner agent decides), direct Moodle
    messages (the Moodle flow decides them; a new proposal is the way out) and a
    failure whose automatic diagnostic is still open.
    """
    return and_(demand.dispatch_status == "failed", demand.status != "archived",
        demand.consolidated_into_id.is_(None), demand.origin_type != "incubation",
        ~exists(select(MoodleApproval.id).where(MoodleApproval.message_id == demand.id)),
        ~active_failure_check_sql(demand))


def operator_state_sql():
    question=exists(select(AgentQuestion.id).where(AgentQuestion.origin_demand_id==AgentDemand.id,
        AgentQuestion.status=="pending",AgentQuestion.blocking.is_(True)))
    current=and_(MessageTriageResult.message_id==AgentDemand.id,
                 MessageTriageResult.source_updated_at==AgentDemand.updated_at,
                 MessageTriageResult.context_versions["revision"]==context_revision_sql())
    def analyzed(state):
        return exists(select(MessageTriageResult.message_id).where(current,MessageTriageResult.operator_state==state))
    return case(
        (AgentDemand.status=="archived","resolved"),
        (or_(question,and_(AgentDemand.requires_approval.is_(True),or_(
            AgentDemand.approval_status.is_(None),AgentDemand.approval_status=="pending"))),"decision"),
        (or_(AgentDemand.dispatch_status.in_(("dispatched","running")),and_(
            AgentDemand.dispatch_status.is_(None),AgentDemand.agent_run_id.isnot(None))),"processing"),
        # Before the triage result: a model's "waiting"/"resolved" for a failed
        # attempt never takes it off the operator's desk. A proven resolution
        # archives the message, which the first branch already covers.
        (human_failure_sql(),"decision"),
        (analyzed("resolved"),"resolved"),(analyzed("waiting"),"waiting"),
        (AgentDemand.dispatch_status=="completed","resolved"),
        (AgentDemand.origin_type=="incubation","waiting"),else_="processing")


def view_filter(view, state, *, operator=None, demand=AgentDemand):
    if view in ("decision","processing","waiting","resolved"):
        operator = operator_state_sql() if operator is None else operator
        return and_(demand.status!="archived",operator==view)
    if view == "attention":
        return state.in_(("approval", "question", "rejected", "uncertain", "failed", "overdue", "incubation"))
    if view == "approval":
        return state.in_(("approval", "rejected"))
    if view == "failed":
        return state.in_(("failed", "uncertain"))
    if view == "incubation":
        return and_(demand.status != "archived", demand.origin_type == "incubation")
    return state == view


async def work_item(db, demand, state):
    active = state == "running"
    linked_history = bool(await db.scalar(select(AgentDemand.id).where(AgentDemand.consolidated_into_id == demand.id).limit(1)))
    blocked_question = bool(await db.scalar(select(AgentQuestion.id).where(AgentQuestion.origin_demand_id == demand.id,
        AgentQuestion.status == "pending", AgentQuestion.blocking.is_(True)).limit(1)))
    moodle = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == demand.id))
    direct_moodle = moodle is not None
    if moodle is None and demand.failure_check_source_id:
        moodle = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == demand.failure_check_source_id))
    actions, blocked = [], {}
    for action in ("approve", "reject", "postpone", "drop", "archive", "restore", "delete", "reconcile", "retry", "authorize_retry", "request_approval",
                   "record_investigation", "confirm_inactive"):
        reason = None
        if direct_moodle:
            reason = "moodle_flow_required"
        elif action == "archive" and uncertain(demand):
            reason = "reconciliation_required"
        elif action in ("record_investigation", "confirm_inactive"):
            if not uncertain(demand):
                reason = "no_uncertain_outcome"
            elif demand.consolidated_into_id:
                reason = "open_summary"
        elif action == "reconcile":
            if not demand.agent_run_id or demand.dispatch_status != "failed":
                reason = "no_recorded_failure"
        elif action == "delete":
            if active or uncertain(demand):
                reason = "reconciliation_required" if uncertain(demand) else "execution_active"
            elif linked_history:
                reason = "linked_history"
        elif active:
            reason = "execution_active"
        elif demand.consolidated_into_id:
            reason = "open_summary"
        elif action == "restore":
            if demand.status != "archived":
                reason = "not_archived"
        elif demand.status == "archived":
            reason = "archived"
        elif action in ("retry", "authorize_retry"):
            if uncertain(demand):
                reason = "reconciliation_required"
            elif demand.dispatch_status != "failed" or demand.origin_type != "task":
                reason = "no_terminal_failure"
            elif action == "retry" and (demand.dispatch_attempts >= (demand.retry_limit or 3)):
                reason = "retry_limit"
            elif action == "retry" and demand.requires_approval and demand.approval_status != "approved":
                reason = "approval_required"
        elif action in ("approve", "reject"):
            if demand.dispatch_status is not None:
                reason = "execution_has_outcome"
            elif action == "approve":
                if blocked_question:
                    reason = "blocking_question"
                elif not demand.from_agent_id or not demand.target_agent_id or not (demand.working_path or "").startswith("/"):
                    reason = "execution_context_missing"
        elif action in ("postpone", "drop") and demand.origin_type != "incubation":
            reason = "not_incubation"
        if reason:
            blocked[action] = reason
        else:
            actions.append(action)
    category = failure_category(demand)
    from app.core.message_triage_context import context_stamp, display_context, source_stamp
    analysis=await db.get(MessageTriageResult,demand.id)
    if analysis:
        context_fingerprint, _ = await context_stamp(db, demand, analysis.context_versions.get("related", {}).keys())
        if (analysis.source_fingerprint != source_stamp(demand)
                or analysis.context_fingerprint != context_fingerprint):
            analysis = None
    operator=await db.scalar(select(operator_state_sql()).select_from(AgentDemand).where(AgentDemand.id==demand.id))
    return {**DemandOut.model_validate(demand).model_dump(mode="json"), "work_state": state,
        "operator_state":operator,"display_context":display_context(demand),
        "analysis":{k:getattr(analysis,k) for k in ("category","summary","reason","recommendation",
            "proposed_action","related_message_id","evidence_refs","analyzed_at","applied_action")} if analysis else None,
        "failure_category": category, "recovery_state": "reconciliation_required" if uncertain(demand) else
        "failed" if demand.dispatch_status == "failed" else "none",
        "allowed_actions": actions, "blocked_actions": blocked,
        "moodle_approval": {"request_id": str(moodle.request_id), "message_id": str(moodle.message_id),
            "state": moodle.state, "outcome": moodle.outcome, "direct": direct_moodle} if moodle else None}


async def list_agent_work(db, *, view="attention", search="", agent_id=None, context=None,
                          created_from=None, created_to=None, page=1, page_size=25, group="all"):
    state = work_state_sql()
    filters = []
    if group != "all":
        filters.append(~exists(select(MoodleApproval.id).where(MoodleApproval.message_id == AgentDemand.id)))
        filters.append(AgentDemand.origin_type == "incubation" if group == "incubation" else AgentDemand.origin_type == "task")
    if search.strip():
        term = search.strip().removeprefix("#")
        # Match literal wildcard characters; an operator's search is not SQL syntax.
        match = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(or_(AgentDemand.subject.ilike(f"%{match}%", escape="\\"),
            AgentDemand.body.ilike(f"%{match}%", escape="\\"),
            AgentDemand.number == int(term) if term.isdecimal() else False))
    if agent_id:
        filters.append(func.coalesce(AgentDemand.incubation_owner_id, AgentDemand.target_agent_id, AgentDemand.from_agent_id) == agent_id)
    if context and context != "all":
        if context.startswith("project:"):
            import uuid
            try:
                filters.append(AgentDemand.project_id == uuid.UUID(context[8:]))
            except ValueError:
                from fastapi import HTTPException
                raise HTTPException(422, "Invalid project context") from None
        elif context.startswith("area:"):
            filters.extend((AgentDemand.project_id.is_(None), AgentDemand.context_area == context[5:]))
        elif context == "unclassified":
            filters.extend((AgentDemand.project_id.is_(None), AgentDemand.context_area.is_(None)))
    if created_from:
        filters.append(AgentDemand.created_at >= created_from)
    if created_to:
        filters.append(AgentDemand.created_at <= created_to)
    # PostgreSQL materializes classification before any view predicate. The
    # linked freshness expression is evaluated once per filtered demand in
    # each of the count/page queries, regardless of the number of views.
    classified = (select(AgentDemand.id, AgentDemand.status, AgentDemand.origin_type,
        state.label("work_state"), operator_state_sql().label("operator_state"))
        .where(*filters).cte("classified_agent_work").prefix_with("MATERIALIZED", dialect="postgresql"))
    columns = classified.c

    def classified_filter(name):
        return view_filter(name, columns.work_state, operator=columns.operator_state, demand=columns)

    count_row = (await db.execute(select(*(func.count().filter(classified_filter(name)).label(name)
        for name in WORK_VIEWS)).select_from(classified))).mappings().one()
    counts = {name: int(count_row[name]) for name in WORK_VIEWS}
    total = counts[view]
    page = min(page, max(1, (total + page_size - 1) // page_size))
    rows = (await db.execute(select(AgentDemand, columns.work_state)
        .join(classified, AgentDemand.id == columns.id).where(classified_filter(view))
        .order_by(AgentDemand.created_at.desc(), AgentDemand.id).offset((page - 1) * page_size).limit(page_size))).all()
    contexts = (await db.execute(select(AgentDemand.project_id, AgentDemand.context_area).where(*filters).distinct())).all()
    return {"items": [await work_item(db, demand, work_state) for demand, work_state in rows],
        "total": total, "counts": counts, "page": page, "page_size": page_size,
        "contexts": [{"project_id": str(project) if project else None, "area": area} for project, area in contexts]}
