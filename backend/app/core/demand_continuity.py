"""The thread of a task and its explicit outcomes (Messages phase 2, 2026-11-19).

Marcelo: "o controle das tarefas dos agentes precisa ser coeso". A task is
followed as a thread -- original -> attempts -> check -> continuation ->
outcome -- linked in the database, never by a "#N" in the text
(docs/architecture/MESSAGES_GUIA.md §13.2). A thread leaves the decision screen
only with an explicit outcome, and each one archives with who and why:

- ``continue``: a new task with only what is missing, ``continues_id`` set;
- ``done_by``: another (completed) task did the work, ``done_by_id`` set;
- ``close_delivered``: delivered, with the evidence cited; it also counts as a
  delivery, so the same content is never dispatched again;
- the check's ``ORIGEM:`` line decides (``apply_origin_verdict``): CONCLUÍDA
  closes the original, PARCIAL/BLOQUEADA leaves it in Decisões with the
  continuation recommended.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.core.demand_workflow import (
    WorkflowBlocked, approval_fingerprint, archive_with_reason, record_transition, requires_reconciliation,
)
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent

CONTINUITY_ACTIONS = ("continue", "done_by", "close_delivered")
THREAD_LIMIT = 40
# Content that only runs restricted (instructor/STI groups, approvals of their
# writes, Maia/Lara personal channels) never becomes an ordinary agent task, a
# model's input or another task's evidence (independent review, 2026-11-19).
PRIVATE_CHANNELS = frozenset({"personal", "whatsapp", "whatsapp_group"})
PRIVATE_AREA_PREFIXES = ("instructor:", "sti:", "sti_approval:", "agent_action:")


async def is_private(db, demand, agents=None):
    """True for work outside the shared "athos" domain or in a restricted flow."""
    from app.core.message_triage_context import domain_for
    from app.db.models.agent import Agent

    if demand.channel in PRIVATE_CHANNELS or (demand.context_area or "").startswith(PRIVATE_AREA_PREFIXES):
        return True
    if agents is None:
        ids = [i for i in (demand.from_agent_id, demand.target_agent_id, demand.incubation_owner_id) if i]
        agents = {a.id: a for a in (await db.scalars(select(Agent).where(Agent.id.in_(ids)))).all()} if ids else {}
    return domain_for(demand, agents) != "athos"


def _excerpt(value, limit):
    text = (value or "").strip() or "(não registrado)"
    return text if len(text) <= limit else text[:limit] + "\n[Extrato: consulte a mensagem original.]"


async def continuity_blocker(db, demand, *, direct_moodle=False):
    """Why none of the three outcomes can be recorded now, or None."""
    from app.core.demand_failure_check import _is_mission_task

    if direct_moodle:
        return "moodle_flow_required"
    if demand.status == "archived":
        return "archived"
    if demand.consolidated_into_id:
        return "open_summary"
    if demand.dispatch_status in ("dispatched", "running") or (demand.agent_run_id and demand.dispatch_status is None):
        return "execution_active"
    if requires_reconciliation(demand):
        return "reconciliation_required"
    if demand.origin_type != "task":
        return "not_task"
    if await is_private(db, demand):
        return "private_flow"
    if await _is_mission_task(db, demand):
        # Mission work closes through its own review and acceptance.
        return "mission_flow"
    return None


def _parent_id(row):
    return row.continues_id or row.failure_check_source_id or row.reply_to_id


async def thread_of(db, demand):
    """Every task linked to this one, oldest first, each with its role.

    Walks up to the root through continues/check/reply links, then down
    through the same links plus "done by". Bounded: a thread is a handful of
    tasks; THREAD_LIMIT keeps a pathological chain from loading the table.
    """
    from app.core.demand_brief import origin_verdict

    root, seen = demand, {demand.id}
    while (parent_id := _parent_id(root)) and parent_id not in seen and len(seen) < THREAD_LIMIT:
        parent = await db.get(AgentDemand, parent_id)
        if parent is None:
            break
        seen.add(parent.id)
        root = parent
    rows, frontier = {root.id: root}, [root.id]
    while frontier and len(rows) < THREAD_LIMIT:
        children = (await db.scalars(select(AgentDemand).where(or_(
            AgentDemand.continues_id.in_(frontier), AgentDemand.failure_check_source_id.in_(frontier),
            AgentDemand.reply_to_id.in_(frontier), AgentDemand.done_by_id.in_(frontier))).limit(THREAD_LIMIT))).all()
        frontier = [c.id for c in children if c.id not in rows]
        rows.update({c.id: c for c in children})
    done_by_ids = [r.done_by_id for r in rows.values() if r.done_by_id and r.done_by_id not in rows]
    if done_by_ids:
        rows.update({r.id: r for r in (await db.scalars(select(AgentDemand).where(AgentDemand.id.in_(done_by_ids)))).all()})

    def role(row):
        if row.id == root.id:
            return "original"
        if row.done_by_id in rows:
            return "covered"  # closed because a task of this thread did its work
        if row.failure_check_source_id:
            return "check"
        if row.continues_id:
            return "continuation"
        if row.reply_to_id:
            return "reply"
        return "done_by"

    return [{"id": str(r.id), "number": r.number, "subject": r.subject, "role": role(r),
             "status": r.status, "dispatch_status": r.dispatch_status, "current": r.id == demand.id,
             "parent_id": str(_parent_id(r)) if _parent_id(r) else None,
             "done_by_id": str(r.done_by_id) if r.done_by_id else None,
             "verdict": origin_verdict(r.dispatch_result) if r.failure_check_source_id else None,
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "decision_reason": r.decision_reason}
            for r in sorted(rows.values(), key=lambda r: (r.created_at or datetime.min.replace(tzinfo=timezone.utc), r.number or 0))]


async def _new_continuation(db, source, missing, *, actor):
    if source.from_agent_id is None or source.target_agent_id is None or not (source.working_path or "").startswith("/"):
        raise HTTPException(400, "Define sender, executor and absolute working directory before continuing")
    now = datetime.now(timezone.utc)
    body = (
        f"Continuação da tarefa #{source.number} (id={source.id}).\n"
        f"Origem navegável: /demands?message={source.id}\n"
        "Faça somente o que falta, descrito abaixo. Verifique primeiro o que a tarefa original já produziu "
        "e não repita efeitos já realizados.\n\n"
        f"## O que falta\n{missing.strip()}\n\n"
        f"## Pedido original\n{_excerpt(source.body, 20000)}\n\n"
        f"## Último resultado registrado\n{_excerpt((source.dispatch_result or '')[-8000:], 8000)}\n"
    )
    continuation = AgentDemand(
        continues_id=source.id, from_agent=source.from_agent, from_agent_id=source.from_agent_id,
        target_agent_id=source.target_agent_id,
        subject=f"Continuação de #{source.number}: {source.subject}"[:255], body=body,
        origin_type="task", origin_id=source.origin_id, project_id=source.project_id,
        development_request_id=source.development_request_id, context_area=source.context_area,
        working_path=source.working_path, fixed_agent=source.fixed_agent, channel="agent",
        requires_response=False, requires_approval=source.requires_approval,
        approval_status="pending" if source.requires_approval else None,
        # Work that needed approval still needs it; the rest goes to the queue.
        scheduled_at=None if source.requires_approval else now,
    )
    db.add(continuation)
    await db.flush()
    record_transition(db, continuation, "continuation_opened", actor=actor,
                      extra={"continues_id": str(source.id), "continues_number": source.number})
    return continuation


async def apply_continuity(db, demand, payload, *, actor):
    """Record one of the three outcomes; archives the task with who and why.

    Caller holds the row lock (FOR UPDATE) and commits.
    """
    from app.db.models.moodle_approval import MoodleApproval

    if payload.expected_updated_at is not None and demand.updated_at != payload.expected_updated_at:
        raise WorkflowBlocked("This message changed; refresh it before deciding")
    direct_moodle = await db.scalar(select(MoodleApproval.id).where(MoodleApproval.message_id == demand.id)) is not None
    blocker = await continuity_blocker(db, demand, direct_moodle=direct_moodle)
    if blocker:
        raise WorkflowBlocked(f"This outcome can't be recorded now ({blocker})")
    reason = (payload.reason or "").strip()
    created = None
    if payload.action == "continue":
        created = await _new_continuation(db, demand, reason, actor=actor)
        archive_with_reason(db, demand, actor=actor, source="continuation",
                            reason=f"Continuada por #{created.number}: {reason}",
                            extra={"continuation_id": str(created.id), "continuation_number": created.number})
    elif payload.action == "done_by":
        other = await db.scalar(select(AgentDemand).where(AgentDemand.number == payload.related_number))
        if other is None or other.id == demand.id:
            raise HTTPException(404, "Task not found")
        if other.dispatch_status != "completed":
            # Only work that actually finished can stand for this one.
            raise WorkflowBlocked("The task that did the work must have a completed execution")
        if await is_private(db, other):
            raise WorkflowBlocked("A task of a restricted flow can't stand for this one")
        demand.done_by_id = other.id
        archive_with_reason(db, demand, actor=actor, source="done_by",
                            reason=f"Feito por #{other.number}" + (f": {reason}" if reason else ""),
                            extra={"done_by_id": str(other.id), "done_by_number": other.number})
    else:  # close_delivered
        evidence = payload.evidence_ref.strip()
        # Counts as a delivery of this exact content (message_triage.verified_delivery),
        # so the same task is never dispatched again by any path.
        db.add(AuditEvent(entity_type="agent_demand", entity_id=demand.id, event_type="message_work_resolved",
                          actor=actor, payload={"content_hash": approval_fingerprint(demand),
                                                "evidence_ref": evidence, "summary": reason}))
        archive_with_reason(db, demand, actor=actor, source="delivered",
                            reason=f"Entregue: {reason}", extra={"evidence_ref": evidence})
    demand.scheduled_at = None
    return created


async def apply_origin_verdict(db, check, *, actor="system"):
    """A finished failure check decides its original by its ``ORIGEM:`` line.

    CONCLUÍDA closes the original (archived, reason quoting the check);
    PARCIAL/BLOQUEADA keep it in Decisões, now recommending a continuation.
    No line, or an original that moved on (archived, retried, uncertain,
    consolidated), changes nothing. Caller commits.
    """
    from app.core.demand_brief import origin_verdict

    verdict = origin_verdict(check.dispatch_result)
    if verdict is None or check.failure_check_source_id is None:
        return None
    source = await db.scalar(select(AgentDemand).where(AgentDemand.id == check.failure_check_source_id)
                             .with_for_update().execution_options(populate_existing=True))
    if source is None or source.dispatch_status != "failed":
        return None
    from app.db.models.moodle_approval import MoodleApproval
    direct_moodle = await db.scalar(select(MoodleApproval.id).where(MoodleApproval.message_id == source.id)) is not None
    # Same gate as the operator's buttons: never a Moodle, mission, restricted,
    # uncertain, archived or consolidated original (independent review).
    if await continuity_blocker(db, source, direct_moodle=direct_moodle) is not None:
        return None
    if verdict == "completed":
        # The check is the evidence; it also counts as a delivery of this exact
        # content, so no path dispatches the original again (independent review).
        db.add(AuditEvent(entity_type="agent_demand", entity_id=source.id, event_type="message_work_resolved",
                          actor=actor, payload={"content_hash": approval_fingerprint(source),
                                                "evidence_ref": f"message:{check.id}",
                                                "summary": f"Checagem #{check.number}: ORIGEM CONCLUÍDA"}))
        archive_with_reason(db, source, actor=actor, source="failure_check",
                            reason=f"Checagem #{check.number}: ORIGEM CONCLUÍDA",
                            extra={"check_id": str(check.id), "check_number": check.number, "verdict": verdict})
        source.scheduled_at = None
    else:
        label = "PARCIAL" if verdict == "partial" else "BLOQUEADA"
        source.decision_reason = f"Checagem #{check.number}: ORIGEM {label}; falta decidir a continuação."
        record_transition(db, source, "origin_verdict", actor=actor,
                          extra={"check_id": str(check.id), "check_number": check.number, "verdict": verdict})
    return verdict


async def link_continuation(db, demand, continues_number, *, sender_id, closer_id=None):
    """An agent's ``send_agent_message(continues=N)``: link it, and when the
    authenticated caller owns the original's failure, close that original.

    Anyone may link (it is only a reference). Closing needs ``closer_id``: the
    agent proven by its own ``agt_`` credential (``assert_acts_as``), never a
    sender id from the body -- the bridge token is shared (independent review).
    That agent must be the original's sender or executor, and the original a
    known failure that ``continuity_blocker`` lets close (no Moodle, mission,
    restricted flow, running or uncertain run). Caller commits.
    """
    source = await db.scalar(select(AgentDemand).where(AgentDemand.number == continues_number).with_for_update())
    if source is None or source.id == demand.id:
        raise HTTPException(404, f"Message #{continues_number} not found")
    demand.continues_id = source.id
    record_transition(db, demand, "continuation_opened", actor=f"agent:{sender_id}" if sender_id else "system",
                      extra={"continues_id": str(source.id), "continues_number": source.number})
    from app.db.models.moodle_approval import MoodleApproval
    direct_moodle = await db.scalar(select(MoodleApproval.id).where(MoodleApproval.message_id == source.id)) is not None
    if (closer_id is not None and closer_id == sender_id and closer_id in (source.from_agent_id, source.target_agent_id)
            and source.dispatch_status == "failed"
            and await continuity_blocker(db, source, direct_moodle=direct_moodle) is None):
        archive_with_reason(db, source, actor=f"agent:{sender_id}", source="continuation",
                            reason=f"Continuada por #{demand.number}",
                            extra={"continuation_id": str(demand.id), "continuation_number": demand.number})
        source.scheduled_at = None
    return source
