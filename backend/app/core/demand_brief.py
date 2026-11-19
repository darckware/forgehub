"""The "Analisar" brief of one stuck task (2026-11-19, Marcelo: "um botão de analise para mim
saber o que vou fazer ... preciso ter referencia do que vou fazer").

Rule-based only: what the task is about, why it is stuck, what already happened
around it, and what the operator can do, each option with its consequence and
one recommended. It reads facts, never asks a model, so it answers even when the
model provider is down (the 2026-11-15/17 analyses failed that way). Whether the
work was already done by another agent (section 4) is the model's part, later.

Codes, not sentences: the screen translates them.
"""
import re

from sqlalchemy import and_, or_, select

from app.core.demand_management import stuck_reason, work_item, work_state_sql
from app.core.demand_workflow import requires_reconciliation
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand

ORIGIN_VERDICT = re.compile(r"^\s*ORIGEM\s*:\s*(CONCLU[IÍ]DA|PARCIAL|BLOQUEADA)\b", re.IGNORECASE | re.MULTILINE)

# Recommended next step per stuck reason, in order of preference: the first one
# the item actually allows is recommended.
RECOMMENDATION = {
    "uncertain_run": ("reconcile", "confirm_inactive"),
    "failure_unresolved": ("retry", "archive"),
    "retry_limit": ("authorize_retry", "archive"),
    "quota_reset_unknown": ("authorize_retry", "archive"),
    "quota_not_resumed": ("authorize_retry", "archive"),
    "incubation_overdue": ("approve", "postpone", "drop"),
    "approval_pending": ("approve", "reject"),
    "queue_stuck": (),
    "blocking_question": (),
}


def origin_verdict(text):
    match = ORIGIN_VERDICT.search(text or "")
    if not match:
        return None
    return {"CONCLUIDA": "completed", "CONCLUÍDA": "completed", "PARCIAL": "partial",
            "BLOQUEADA": "blocked"}[match.group(1).upper()]


def _short(text, limit=600):
    text = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _ref(row):
    return {"id": str(row.id), "number": row.number, "subject": row.subject,
            "status": row.status, "dispatch_status": row.dispatch_status}


async def demand_brief(db, demand):
    state = await db.scalar(select(work_state_sql()).select_from(AgentDemand).where(AgentDemand.id == demand.id))
    item = await work_item(db, demand, state)
    stuck = item["stuck"]
    names = {a.id: a.name for a in (await db.scalars(select(Agent).where(Agent.id.in_(
        [i for i in (demand.from_agent_id, demand.target_agent_id, demand.incubation_owner_id) if i])))).all()}

    checks = (await db.scalars(select(AgentDemand).where(AgentDemand.failure_check_source_id == demand.id)
              .order_by(AgentDemand.created_at))).all()
    replies = (await db.scalars(select(AgentDemand).where(AgentDemand.reply_to_id == demand.id)
               .order_by(AgentDemand.created_at))).all()
    # Later work that names this one: the continuity a thread will record
    # explicitly (phase 2); until then, a mention of "#<number>" is a hint only.
    mentions = (await db.scalars(select(AgentDemand).where(
        AgentDemand.id != demand.id, AgentDemand.created_at > demand.created_at,
        AgentDemand.failure_check_source_id.is_distinct_from(demand.id),
        # "#123" but not "#1234" (independent review).
        or_(AgentDemand.subject.op("~")(rf"#{demand.number}([^0-9]|$)"),
            AgentDemand.body.op("~")(rf"#{demand.number}([^0-9]|$)")))
        .order_by(AgentDemand.created_at.desc()).limit(10))).all()
    summary = await db.get(AgentDemand, demand.consolidated_into_id) if demand.consolidated_into_id else None

    held_by = None
    if stuck and stuck["reason"] == "queue_stuck" and demand.target_agent_id:
        holder = await db.scalar(select(AgentDemand).where(
            AgentDemand.target_agent_id == demand.target_agent_id, AgentDemand.id != demand.id,
            AgentDemand.dispatch_status == "failed", AgentDemand.status != "archived",
            or_(and_(AgentDemand.agent_run_id.isnot(None),
                     or_(AgentDemand.dispatch_error.is_(None), AgentDemand.dispatch_error == "")),
                AgentDemand.dispatch_error.ilike("%uncertain%"))).limit(1))
        held_by = _ref(holder) if holder is not None and requires_reconciliation(holder) else None

    allowed = item["allowed_actions"]
    recommended = next((a for a in RECOMMENDATION.get(stuck["reason"], ()) if a in allowed), None) if stuck else None
    options = [{"action": a, "recommended": a == recommended} for a in allowed if a not in ("restore",)]
    options.sort(key=lambda o: not o["recommended"])

    return {
        "id": str(demand.id), "number": demand.number,
        "about": {
            "subject": demand.subject, "summary": _short(demand.body),
            "requested_by": names.get(demand.from_agent_id) or demand.from_agent,
            "executor": names.get(demand.target_agent_id) or names.get(demand.incubation_owner_id),
            "context": item.get("display_context"), "working_path": demand.working_path,
            "origin_type": demand.origin_type, "created_at": demand.created_at.isoformat(),
        },
        "stuck": stuck,
        "held_by": held_by,
        "history": {
            "attempts": demand.dispatch_attempts or 0, "retry_limit": demand.retry_limit or 3,
            "last_error": _short(demand.dispatch_error, 400) or None,
            "last_result": _short((demand.dispatch_result or "")[-1500:], 600) or None,
            "checks": [{**_ref(c), "verdict": origin_verdict(c.dispatch_result)} for c in checks],
            "replies": [_ref(r) for r in replies],
            "mentioned_by": [_ref(m) for m in mentions],
            "consolidated_into": _ref(summary) if summary else None,
        },
        "options": options,
        "blocked": item["blocked_actions"],
        "analysis": item.get("analysis"),
        # The agent-work item itself, so the screen can act on it even when it
        # is not on the list page (opened from Messages).
        "item": item,
    }


__all__ = ["demand_brief", "origin_verdict", "stuck_reason"]
