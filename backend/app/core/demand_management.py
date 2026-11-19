"""Bounded operator queries and shared presentation of execution constraints."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.api.schemas.demand import DemandOut
from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentQuestion
from app.db.models.moodle_approval import MoodleApproval
from app.core.demand_workflow import effective_dispatch_attempts, requires_reconciliation as uncertain
from app.db.models.message_triage import MessageTriageResult
from app.core.message_triage_revision import context_revision_sql

# Decisions holds only stuck work (2026-11-19, Marcelo: "A preocupação são com as
# tarefas travadas por algum motivo"). Past these limits a wait is not a wait any more.
QUEUE_STUCK_AFTER = timedelta(minutes=30)
QUOTA_STUCK_AFTER = timedelta(minutes=30)
INCUBATION_STUCK_AFTER = timedelta(days=3)

WORK_VIEWS = ("stuck", "decision", "approvals_queue", "processing", "waiting", "resolved", "attention", "approval", "incubation", "failed", "queued", "running", "completed", "archived")
# "decisions": tasks and incubations together, Moodle messages left to their own flow.
WORK_GROUPS = ("all", "tasks", "incubation", "decisions")


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
        (AgentDemand.dispatch_status == "waiting_quota", "waiting"),
        (and_(AgentDemand.dispatch_status == "completed", AgentDemand.dispatch_outcome == "waiting_reply"), "waiting"),
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


def _not_moodle(demand=AgentDemand):
    return ~exists(select(MoodleApproval.id).where(MoodleApproval.message_id == demand.id))


def agent_running_sql(demand=AgentDemand):
    """The task's agent is busy with a run that is still alive (dispatched,
    running or reserved). Waiting behind it is normal, not stuck: a run may take
    up to DISPATCH_TIMEOUT_MINUTES. An uncertain run is not alive -- that queue
    *is* stuck, and the brief names the run holding it (independent review)."""
    other = aliased(AgentDemand)
    return exists(select(other.id).where(other.target_agent_id == demand.target_agent_id, other.id != demand.id,
        or_(other.dispatch_status.in_(("dispatched", "running")),
            and_(other.dispatch_status.is_(None), other.agent_run_id.isnot(None)))))


def stuck_wait_sql(demand=AgentDemand):
    """A wait that stopped being one: nothing will move it without a person.

    - quota: reset unknown, or past the reset by QUOTA_STUCK_AFTER and still
      waiting (protected work, context changed or no run evidence);
    - queue: a due Task not started QUEUE_STUCK_AFTER after its time (busy
      agent, dependency, capacity, unavailable executor);
    - incubation: its owner was asked to decide INCUBATION_STUCK_AFTER ago.
    Moodle messages keep their own flow and are left out.
    """
    now = func.now()
    quota = and_(demand.dispatch_status == "waiting_quota", or_(demand.quota_reset_at.is_(None),
        demand.quota_reset_at <= now - QUOTA_STUCK_AFTER))
    queue = and_(demand.origin_type == "task", demand.dispatch_status.is_(None), demand.agent_run_id.is_(None),
        demand.scheduled_at.isnot(None), demand.scheduled_at <= now - QUEUE_STUCK_AFTER,
        or_(demand.requires_approval.is_(False), demand.approval_status == "approved"),
        ~agent_running_sql(demand))
    incubation = and_(demand.origin_type == "incubation", demand.incubation_state == "decision_pending",
        demand.matures_at <= now - INCUBATION_STUCK_AFTER)
    return and_(demand.status != "archived", demand.consolidated_into_id.is_(None), _not_moodle(demand),
                or_(quota, queue, incubation))


def blocking_question_sql(demand=AgentDemand):
    return exists(select(AgentQuestion.id).where(AgentQuestion.origin_demand_id == demand.id,
        AgentQuestion.status == "pending", AgentQuestion.blocking.is_(True)))


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
        (stuck_wait_sql(),"decision"),
        (AgentDemand.dispatch_status=="waiting_quota","waiting"),
        (and_(AgentDemand.dispatch_status=="completed",AgentDemand.dispatch_outcome=="waiting_reply"),"waiting"),
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


def view_filter(view, state, *, operator=None, demand=AgentDemand, question=None, stuck=None):
    if view == "stuck":
        # Pessoal -> Tarefas dos agentes -> Decisoes (2026-11-19): only stuck work.
        # Tasks as in "decision" (approvals and blocking questions have their own
        # tabs); an incubation only once its owner left the decision overdue.
        operator = operator_state_sql() if operator is None else operator
        question = blocking_question_sql(demand) if question is None else question
        stuck = stuck_wait_sql(demand) if stuck is None else stuck
        pending_approval = and_(demand.requires_approval.is_(True),
            or_(demand.approval_status.is_(None), demand.approval_status == "pending"))
        return and_(demand.status != "archived", operator == "decision", or_(
            and_(demand.origin_type == "task", ~question, ~pending_approval),
            and_(demand.origin_type == "incubation", stuck)))
    if view == "approvals_queue":
        # Pessoal -> Tarefas dos agentes -> Aprovacoes holds only work waiting for
        # Marcelo's authorization. Pending task authorizations and blocking-question
        # tasks are excluded from the separate operator Decisions queue.
        operator = operator_state_sql() if operator is None else operator
        question = blocking_question_sql(demand) if question is None else question
        return and_(demand.status != "archived", demand.origin_type == "task", operator == "decision", ~question,
                    demand.requires_approval.is_(True),
                    or_(demand.approval_status.is_(None), demand.approval_status == "pending"))
    if view == "decision":
        operator = operator_state_sql() if operator is None else operator
        question = blocking_question_sql(demand) if question is None else question
        pending_approval = and_(demand.requires_approval.is_(True),
            or_(demand.approval_status.is_(None), demand.approval_status == "pending"))
        # Incubations retain their guarded decision flow. For task rows, the
        # Decisions tab excludes approvals and blocking questions shown elsewhere.
        task_decision = or_(demand.origin_type != "task", and_(~question, ~pending_approval))
        return and_(demand.status != "archived", operator == "decision", task_decision)
    if view in ("processing","waiting","resolved"):
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


STUCK_REASONS = ("uncertain_run", "failure_unresolved", "retry_limit", "quota_reset_unknown",
                 "quota_not_resumed", "queue_stuck", "incubation_overdue", "approval_pending", "blocking_question")


async def stuck_reason(db, demand, *, blocked_question=False, direct_moodle=False, wait_summary=None, now=None):
    """Why this work is stuck and since when, in the operator's terms; None when it moves by itself.

    Same facts as operator_state_sql's "decision", one reason per item so the
    card can say it (2026-11-19). `held` counts the queued Tasks an uncertain run
    keeps from starting; `detail` carries the classifier's cause for a stuck queue.
    """
    if demand.status == "archived" or demand.consolidated_into_id or direct_moodle:
        return None
    now = now or datetime.now(timezone.utc)
    def out(reason, since, **extra):
        return {"reason": reason, "since": since.isoformat() if since else None, **extra}
    if uncertain(demand):
        held = await db.scalar(select(func.count(AgentDemand.id)).where(
            AgentDemand.target_agent_id == demand.target_agent_id, AgentDemand.id != demand.id,
            AgentDemand.status != "archived", AgentDemand.dispatch_status.is_(None),
            AgentDemand.origin_type == "task", AgentDemand.scheduled_at.isnot(None)))
        return out("uncertain_run", demand.updated_at, held=int(held or 0))
    if blocked_question:
        return out("blocking_question", demand.updated_at)
    if demand.requires_approval and demand.approval_status in (None, "pending") and demand.dispatch_status is None:
        return out("approval_pending", demand.updated_at)
    if demand.dispatch_status == "failed" and demand.origin_type != "incubation":
        if await db.scalar(select(active_failure_check_sql(demand))):
            return None
        reason = "retry_limit" if effective_dispatch_attempts(demand) >= (demand.retry_limit or 3) else "failure_unresolved"
        return out(reason, demand.updated_at, error=(demand.dispatch_error or "")[:500] or None)
    if demand.dispatch_status == "waiting_quota":
        if demand.quota_reset_at is None:
            return out("quota_reset_unknown", demand.task_execution_at or demand.updated_at)
        if demand.quota_reset_at <= now - QUOTA_STUCK_AFTER:
            from app.core.quota_wait import quota_resume_blocker
            return out("quota_not_resumed", demand.quota_reset_at, blocker=quota_resume_blocker(demand, now))
        return None
    if (demand.origin_type == "task" and demand.dispatch_status is None and not demand.agent_run_id
            and demand.scheduled_at and demand.scheduled_at <= now - QUEUE_STUCK_AFTER
            and (not demand.requires_approval or demand.approval_status == "approved")
            and not await db.scalar(select(agent_running_sql(demand)))):
        return out("queue_stuck", demand.scheduled_at, detail=wait_summary)
    if (demand.origin_type == "incubation" and demand.incubation_state == "decision_pending"
            and demand.matures_at and demand.matures_at <= now - INCUBATION_STUCK_AFTER):
        return out("incubation_overdue", demand.matures_at)
    return None


async def work_item(db, demand, state, wait_summary=None):
    active = state == "running"
    linked_history = bool(await db.scalar(select(AgentDemand.id).where(AgentDemand.consolidated_into_id == demand.id).limit(1)))
    blocked_question = bool(await db.scalar(select(AgentQuestion.id).where(AgentQuestion.origin_demand_id == demand.id,
        AgentQuestion.status == "pending", AgentQuestion.blocking.is_(True)).limit(1)))
    moodle = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == demand.id))
    direct_moodle = moodle is not None
    if moodle is None and demand.failure_check_source_id:
        moodle = await db.scalar(select(MoodleApproval).where(MoodleApproval.message_id == demand.failure_check_source_id))
    from app.core.quota_wait import is_factory_quota_continuation
    factory_continuation = await is_factory_quota_continuation(db, demand)
    actions, blocked = [], {}
    for action in ("approve", "reject", "postpone", "drop", "archive", "restore", "delete", "reconcile", "retry", "authorize_retry", "request_approval",
                   "record_investigation", "confirm_inactive"):
        reason = None
        if direct_moodle and not (action == "archive" and moodle.state in ("finished", "rejected")
                                  and not active and demand.status != "archived"):
            # decide_demand accepts archiving once the Moodle flow is over; the
            # button follows the same rule instead of staying disabled.
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
            elif demand.dispatch_status == "waiting_quota":
                from datetime import datetime, timezone
                from app.core.quota_wait import quota_resume_blocker
                reason = ("quota_effects_review_required" if action == "retry" else
                          quota_resume_blocker(demand, datetime.now(timezone.utc)))
            elif demand.dispatch_status != "failed" or demand.origin_type != "task":
                reason = "no_terminal_failure"
            elif action == "retry" and (effective_dispatch_attempts(demand) >= (demand.retry_limit or 3)):
                reason = "retry_limit"
            elif action == "retry" and demand.requires_approval and demand.approval_status != "approved":
                reason = "approval_required"
        elif action in ("approve", "reject"):
            if demand.dispatch_status is not None:
                reason = "execution_has_outcome"
            elif action == "approve":
                if blocked_question:
                    reason = "blocking_question"
                elif (not demand.from_agent_id and not factory_continuation) or not demand.target_agent_id or not (demand.working_path or "").startswith("/"):
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
    stuck = await stuck_reason(db, demand, blocked_question=blocked_question, direct_moodle=direct_moodle,
                               wait_summary=wait_summary)
    return {**DemandOut.model_validate(demand).model_dump(mode="json"), "work_state": state, "stuck": stuck,
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
        if group != "decisions":
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
        AgentDemand.requires_approval, AgentDemand.approval_status,
        state.label("work_state"), operator_state_sql().label("operator_state"),
        blocking_question_sql().label("blocked_question"), stuck_wait_sql().label("stuck_wait"))
        .where(*filters).cte("classified_agent_work").prefix_with("MATERIALIZED", dialect="postgresql"))
    columns = classified.c

    def classified_filter(name):
        return view_filter(name, columns.work_state, operator=columns.operator_state, demand=columns,
                           question=columns.blocked_question, stuck=columns.stuck_wait)

    count_row = (await db.execute(select(*(func.count().filter(classified_filter(name)).label(name)
        for name in WORK_VIEWS)).select_from(classified))).mappings().one()
    counts = {name: int(count_row[name]) for name in WORK_VIEWS}
    total = counts[view]
    page = min(page, max(1, (total + page_size - 1) // page_size))
    rows = (await db.execute(select(AgentDemand, columns.work_state)
        .join(classified, AgentDemand.id == columns.id).where(classified_filter(view))
        .order_by(AgentDemand.created_at.desc(), AgentDemand.id).offset((page - 1) * page_size).limit(page_size))).all()
    contexts = (await db.execute(select(AgentDemand.project_id, AgentDemand.context_area).where(*filters).distinct())).all()
    from app.core.message_classification import classify_messages
    labels = await classify_messages(db, [demand for demand, _ in rows]) if rows else {}
    return {"items": [await work_item(db, demand, work_state, (labels.get(demand.id) or {}).get("classification_summary"))
                      for demand, work_state in rows],
        "total": total, "counts": counts, "page": page, "page_size": page_size,
        "contexts": [{"project_id": str(project) if project else None, "area": area} for project, area in contexts]}
