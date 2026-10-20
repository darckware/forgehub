"""Bounded operator queries and shared presentation of execution constraints."""
from sqlalchemy import and_, case, exists, func, or_, select

from app.api.schemas.demand import DemandOut
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentQuestion
from app.core.demand_workflow import requires_reconciliation as uncertain

WORK_VIEWS = ("attention", "approval", "incubation", "failed", "queued", "running", "completed", "archived")


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
        (or_(blocked, and_(AgentDemand.requires_approval.is_(True), or_(AgentDemand.approval_status.is_(None), AgentDemand.approval_status != "approved"))), "approval"),
        (and_(AgentDemand.origin_type == "incubation", AgentDemand.incubation_state == "decision_pending"), "overdue"),
        (AgentDemand.origin_type == "incubation", "incubation"), else_="queued")


def view_filter(view, state):
    if view == "attention":
        return state.in_(("approval", "rejected", "uncertain", "failed", "overdue", "incubation"))
    if view == "approval":
        return state.in_(("approval", "rejected"))
    if view == "failed":
        return state.in_(("failed", "uncertain"))
    if view == "incubation":
        return and_(AgentDemand.status != "archived", AgentDemand.origin_type == "incubation")
    return state == view


async def work_item(db, demand, state):
    active = state == "running"
    linked_history = bool(await db.scalar(select(AgentDemand.id).where(AgentDemand.consolidated_into_id == demand.id).limit(1)))
    blocked_question = bool(await db.scalar(select(AgentQuestion.id).where(AgentQuestion.origin_demand_id == demand.id,
        AgentQuestion.status == "pending", AgentQuestion.blocking.is_(True)).limit(1)))
    actions, blocked = [], {}
    for action in ("approve", "reject", "postpone", "drop", "archive", "restore", "delete", "reconcile", "retry", "authorize_retry", "request_approval",
                   "record_investigation", "confirm_inactive"):
        reason = None
        if action in ("record_investigation", "confirm_inactive"):
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
    return {**DemandOut.model_validate(demand).model_dump(mode="json"), "work_state": state,
        "failure_category": category, "recovery_state": "reconciliation_required" if uncertain(demand) else
        "failed" if demand.dispatch_status == "failed" else "none",
        "allowed_actions": actions, "blocked_actions": blocked}


async def list_agent_work(db, *, view="attention", search="", agent_id=None, context=None,
                          created_from=None, created_to=None, page=1, page_size=25):
    state = work_state_sql()
    filters = []
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
    counts = {name: int(await db.scalar(select(func.count()).select_from(AgentDemand).where(*filters, view_filter(name, state)))) for name in WORK_VIEWS}
    total = counts[view]
    page = min(page, max(1, (total + page_size - 1) // page_size))
    rows = (await db.execute(select(AgentDemand, state.label("work_state")).where(*filters, view_filter(view, state))
        .order_by(AgentDemand.created_at.desc(), AgentDemand.id).offset((page - 1) * page_size).limit(page_size))).all()
    contexts = (await db.execute(select(AgentDemand.project_id, AgentDemand.context_area).distinct())).all()
    return {"items": [await work_item(db, demand, work_state) for demand, work_state in rows],
        "total": total, "counts": counts, "page": page, "page_size": page_size,
        "contexts": [{"project_id": str(project) if project else None, "area": area} for project, area in contexts]}
