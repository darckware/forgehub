"""Agents asking Marcelo (MCP `ask_marcelo`): delivery and the answer's way back.

Spec: docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md §5.

Three rules shape this module:

- **Quiet hours.** 23:00-07:00 (America/Sao_Paulo) only urgent questions reach
  Telegram (decision 8, 2026-10-02). A non-urgent one asked at night gets
  `notify_after` = 07:00 and waits; the 08:00 briefing lists it anyway.
- **Which bot.** A Telegram reply lands in the conversation of the bot that
  sent the question, so that bot's agent is the only one who can record it.
  An agent whose charter escalates `telegram_direct` (and has a home chat)
  uses its own bot; everyone else goes through Athos's, with the asker named.
- **The answer is a Task.** It reaches the asker as an ordinary Messages Task
  (from the relay agent, or self-addressed when the asker relayed itself), so
  it wakes the agent through the same executor, deadline and failure path as
  any work -- not a side channel the agent has to remember to poll.
"""
import logging
import uuid
from collections.abc import Awaitable, Callable, Collection
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification
from app.db.models.operations import AgentCharter, AgentQuestion

logger = logging.getLogger(__name__)

QUIET_TZ = ZoneInfo("America/Sao_Paulo")
QUIET_START = time(23, 0)
QUIET_END = time(7, 0)
COORDINATOR_SLUG = "athos"
def _bridge_messages_url() -> str:
    # Per call, like core/feedback.py: CHAT_BRIDGE_URL is the one switch point.
    return f"{settings.CHAT_BRIDGE_URL.rstrip('/')}/v1/messages/send"

# (profile_slug or None, "telegram:<chat>", text) -> raises on failure.
TelegramSender = Callable[[str | None, str, str], Awaitable[None]]


def notify_after_for(now: datetime, urgent: bool) -> datetime:
    """When a question may reach Telegram: now, unless it is quiet time and
    the question isn't urgent -- then the end of the quiet window."""
    if urgent:
        return now
    local = now.astimezone(QUIET_TZ)
    clock = local.time()
    if clock >= QUIET_START:
        wake_day = local.date() + timedelta(days=1)
    elif clock < QUIET_END:
        wake_day = local.date()
    else:
        return now
    return datetime.combine(wake_day, QUIET_END, tzinfo=QUIET_TZ).astimezone(timezone.utc)


def _home_chat(agent: Agent | None) -> str | None:
    if agent is None or not agent.profile_slug:
        return None
    from app.core.agent_telegram import read_profile_home_chat

    try:
        return read_profile_home_chat(agent.home_path, agent.runtime_type, agent.profile_slug)
    except Exception:  # an unreadable profile must not break asking
        return None


async def resolve_relay(db: AsyncSession, asker: Agent) -> tuple[Agent | None, str | None]:
    """(relay agent, Telegram chat id). The asker itself when its charter says
    `telegram_direct` and it has a home chat; otherwise Athos. (None, None)
    when nobody can send -- the question stays on the screen only."""
    charter = (
        await db.execute(select(AgentCharter).where(AgentCharter.agent_id == asker.id))
    ).scalar_one_or_none()
    if charter is not None and charter.escalation == "telegram_direct" and asker.telegram_account:
        chat = _home_chat(asker)
        if chat:
            return asker, chat
    coordinator = (
        await db.execute(select(Agent).where(Agent.profile_slug == COORDINATOR_SLUG))
    ).scalar_one_or_none()
    chat = _home_chat(coordinator)
    if coordinator is not None and chat:
        return coordinator, chat
    return None, None


def compose_telegram_text(question: AgentQuestion, asker: Agent) -> str:
    flags = []
    if question.urgent:
        flags.append("URGENTE")
    if question.blocking:
        flags.append("bloqueante")
    header = f"❓ Pergunta #{question.number} de {asker.name}"
    if flags:
        header += f" [{', '.join(flags)}]"
    parts = [header, "", question.question.strip()]
    if question.context:
        parts += ["", f"Contexto: {question.context.strip()}"]
    if question.recommendation:
        parts += ["", f"Recomendação: {question.recommendation.strip()}"]
    parts += [
        "",
        f"Responda aqui começando com #{question.number} (ex.: \"#{question.number} sim\") "
        "ou pela tela Operação → Dúvidas.",
    ]
    return "\n".join(parts)


async def _bridge_send(profile: str | None, target: str, text: str) -> None:
    payload = {"target": target, "message": text}
    if profile:
        payload["profile"] = profile
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            _bridge_messages_url(), json=payload, headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
        )
        response.raise_for_status()


async def create_question(
    db: AsyncSession,
    asker: Agent,
    *,
    question: str,
    context: str | None = None,
    recommendation: str | None = None,
    blocking: bool = False,
    urgent: bool = False,
    origin_demand_id: uuid.UUID | None = None,
) -> AgentQuestion:
    """Record a question for Marcelo and its bell notification; the Telegram
    message goes with the next delivery pass. Shared by the MCP `ask_marcelo`
    route and the mission cycle's `ask_marcelo` decision (M0.8). Caller commits."""
    relay, chat = await resolve_relay(db, asker)
    now = datetime.now(timezone.utc)
    row = AgentQuestion(
        agent_id=asker.id,
        relay_agent_id=relay.id if relay else None,
        telegram_chat=chat,
        question=question.strip(),
        context=(context or "").strip() or None,
        recommendation=(recommendation or "").strip() or None,
        blocking=blocking,
        urgent=urgent,
        origin_demand_id=origin_demand_id,
        notify_after=notify_after_for(now, urgent),
    )
    db.add(row)
    await db.flush()
    db.add(
        Notification(
            source="system",
            severity="warning" if urgent or blocking else "info",
            title=f"Pergunta #{row.number} de {asker.name}",
            message=row.question[:500],
            event_key=f"agent-question:{row.id}",
            occurred_at=now,
        )
    )
    return row


async def run_question_delivery_pass(
    db: AsyncSession,
    now: datetime | None = None,
    send: TelegramSender | None = None,
    ids: Collection[uuid.UUID] | None = None,
) -> int:
    """Send every pending question whose `notify_after` has come and that no
    Telegram message has carried yet. A failed send keeps `telegram_sent_at`
    NULL (the next pass retries) and records why in `telegram_error`.
    `ids` restricts the pass to those questions (tests share the production
    database and must never touch a real question). Returns how many were
    sent."""
    now = now or datetime.now(timezone.utc)
    send = send or _bridge_send
    query = select(AgentQuestion).where(
        AgentQuestion.status == "pending",
        AgentQuestion.telegram_sent_at.is_(None),
        AgentQuestion.notify_after <= now,
    )
    if ids is not None:
        query = query.where(AgentQuestion.id.in_(list(ids)))
    rows = await db.execute(query.order_by(AgentQuestion.number).limit(20))
    sent = 0
    for question in rows.scalars():
        asker = await db.get(Agent, question.agent_id)
        relay = await db.get(Agent, question.relay_agent_id) if question.relay_agent_id else None
        if asker is None:
            continue
        if relay is None or not question.telegram_chat:
            relay, chat = await resolve_relay(db, asker)
            if relay is None:
                question.telegram_error = "no agent with a Telegram home chat can relay this question"
                continue
            question.relay_agent_id, question.telegram_chat = relay.id, chat
        profile = relay.profile_slug if relay.telegram_account else None
        try:
            await send(profile, f"telegram:{question.telegram_chat}", compose_telegram_text(question, asker))
        except Exception as exc:
            logger.warning("Question #%s: Telegram delivery failed: %s", question.number, exc)
            question.telegram_error = str(exc)[:1000]
            continue
        question.telegram_sent_at, question.telegram_error = now, None
        sent += 1
    await db.commit()
    return sent


def compose_answer_message(question: AgentQuestion) -> str:
    lines = [
        f"O Marcelo respondeu a sua pergunta #{question.number}.",
        "",
        "## Pergunta",
        question.question.strip(),
        "",
        "## Resposta",
        (question.answer or "").strip(),
        "",
    ]
    if question.blocking:
        lines.append("Retome o trabalho que estava bloqueado por esta pergunta, seguindo a resposta.")
    else:
        lines.append("Aplique a resposta ao trabalho a que ela se refere.")
    return "\n".join(lines)


async def record_answer(
    db: AsyncSession,
    question: AgentQuestion,
    answer: str,
    *,
    via: str,
    by: str,
    dispatch_at: datetime | None = None,
) -> AgentDemand:
    """Lock and recheck the question, then commit one answer/continuation.

    Identical repeated answers recover the existing task; conflicting answers
    or cancelled questions remain blocked. Caller checks relay/operator authority.
    """
    from app.core.dispatch_targets import DISPATCH_ADMISSION_LOCK
    # Keep the same lock order as canonical dispatch/attempt allocation.
    await db.execute(select(func.pg_advisory_xact_lock(DISPATCH_ADMISSION_LOCK)))
    question = await db.scalar(select(AgentQuestion).where(AgentQuestion.id == question.id)
        .with_for_update().execution_options(populate_existing=True))
    if question is None:
        raise HTTPException(404, "Question not found")
    normalized_answer = answer.strip()
    if question.status == "answered" and question.answer == normalized_answer and question.reply_demand_id:
        previous = await db.get(AgentDemand, question.reply_demand_id)
        if previous is not None:
            return previous
    if question.status != "pending":
        raise HTTPException(409, f"Question #{question.number} is already {question.status}; reconcile its recorded answer")
    now = datetime.now(timezone.utc)
    question.answer = normalized_answer
    question.answered_at = now
    question.answered_via = via
    question.answered_by = by
    question.status = "answered"
    return await _continue_asker(db, question, subject=f"[Resposta] Pergunta #{question.number}",
        message=compose_answer_message(question), by=by, now=now, dispatch_at=dispatch_at,
        notice=f"Pergunta #{question.number} respondida", event_key=f"agent-question-answered:{question.id}")


def compose_cancellation_message(question: AgentQuestion, reason: str) -> str:
    return "\n".join([
        f"O Marcelo arquivou a sua pergunta #{question.number} sem responder.",
        "",
        "## Pergunta",
        question.question.strip(),
        "",
        "## Motivo",
        reason.strip(),
        "",
        "Nenhuma resposta virá: siga sem ela se for possível, ou encerre reportando STATUS: BLOCKED.",
    ])


async def record_cancellation(db: AsyncSession, question: AgentQuestion, reason: str, *, by: str) -> AgentDemand:
    """Close a pending question without an answer and tell the asker, in one commit.

    Same continuation path as an answer (a Messages task to the asker with
    reply_to_id = the blocked message, the same attempt handling), so the
    blocked work never resumes silently: the agent reads why no answer is
    coming. Anything but a pending question is a 409.
    """
    from app.core.dispatch_targets import DISPATCH_ADMISSION_LOCK
    from app.db.models.governance import AuditEvent

    await db.execute(select(func.pg_advisory_xact_lock(DISPATCH_ADMISSION_LOCK)))
    question = await db.scalar(select(AgentQuestion).where(AgentQuestion.id == question.id)
        .with_for_update().execution_options(populate_existing=True))
    if question is None:
        raise HTTPException(404, "Question not found")
    if question.status != "pending":
        raise HTTPException(409, f"Question #{question.number} is already {question.status}")
    question.status = "cancelled"
    db.add(AuditEvent(entity_type="agent_question", entity_id=question.id, event_type="question_cancelled",
        actor=by, payload={"reason": reason.strip(), "number": question.number,
                           "origin_demand_id": str(question.origin_demand_id) if question.origin_demand_id else None}))
    return await _continue_asker(db, question, subject=f"[Pergunta #{question.number} cancelada]",
        message=compose_cancellation_message(question, reason), by=by, now=datetime.now(timezone.utc),
        notice=f"Pergunta #{question.number} arquivada sem resposta", event_key=f"agent-question-cancelled:{question.id}")


async def _continue_asker(db: AsyncSession, question: AgentQuestion, *, subject: str, message: str, by: str,
                          now: datetime, notice: str, event_key: str, dispatch_at: datetime | None = None) -> AgentDemand:
    """Caller has locked the question and set its outcome. Creates the asker's
    continuation task, wires it to the blocked task's attempt, commits."""
    # Local import: demand.py's routes module imports a lot; keep this
    # module importable from main.py's loops without pulling it in early.
    from app.api.routes.demand import create_demand_and_notify
    from app.api.schemas.demand import DemandSubmitIn

    asker = await db.get(Agent, question.agent_id)
    sender = (await db.get(Agent, question.relay_agent_id) if question.relay_agent_id else None) or asker
    demand = await create_demand_and_notify(
        db,
        DemandSubmitIn(
            from_agent=sender.profile_slug or sender.name,
            from_agent_id=sender.id,
            target_agent_id=asker.id,
            subject=subject[:255],
            body=message,
            origin_type="task",
            scheduled_at=dispatch_at or now,
        ),
        commit=False,
        notify=False,
    )
    demand.reply_to_id = question.origin_demand_id
    if question.origin_demand_id:
        from app.core.mission import project_id_for_task_source
        from app.core.task_attempts import create_task_attempt
        from app.db.models.orchestration import TaskExecutionReview
        from app.db.models.task import ProjectTask, TaskAssignment, TaskExecution

        source = await db.get(AgentDemand, question.origin_demand_id, populate_existing=True)
        review = await db.scalar(select(TaskExecutionReview).where(
            TaskExecutionReview.runtime_session_ref == str(source.id))) if source else None
        if review is None and source is not None:
            from app.db.models.governance import AuditEvent
            recorded_review = await db.scalar(select(AuditEvent.payload["review_id"].astext).where(
                AuditEvent.event_type.in_(("review_requested", "review_continuation_created")),
                AuditEvent.payload["demand_id"].astext == str(source.id)).limit(1))
            if recorded_review:
                review = await db.get(TaskExecutionReview, uuid.UUID(recorded_review))
        previous_id = review.execution_id if review else (source.task_execution_id if source else None)
        previous = await db.get(TaskExecution, previous_id) if previous_id else None
        task_id = previous.task_id if previous else (source.origin_id if source and source.origin_type == "task" else None)
        task = await db.scalar(select(ProjectTask).where(ProjectTask.id == task_id)
            .with_for_update().execution_options(populate_existing=True)) if task_id else None
        if task is not None:
            demand.origin_id = task.id
            demand.project_id = await project_id_for_task_source(db, task.planning_item_id, task.change_request_id)
            demand.working_path = source.working_path
            demand.mission_context_version_id = source.mission_context_version_id
            demand.fixed_agent = True
            if review is not None:
                review = await db.scalar(select(TaskExecutionReview).where(TaskExecutionReview.id == review.id)
                    .with_for_update().execution_options(populate_existing=True))
            review_closed = review is not None and (review.status not in {"pending", "running"}
                                                    or review.runtime_session_ref != str(source.id))
            if review_closed or task.status in {"done", "deployed", "cancelled"}:
                from app.db.models.governance import AuditEvent
                demand.status = "archived"
                demand.scheduled_at = None
                demand.decision_reason = "Retorno preservado no histórico; a tarefa de origem já foi encerrada."
                db.add(AuditEvent(entity_type="agent_demand", entity_id=demand.id,
                    event_type="question_answer_recorded_for_closed_task", actor=by,
                    payload={"question_id": str(question.id), "task_id": str(task.id),
                             "source_message_id": str(source.id), "task_status": task.status}))
            elif review is not None:
                # Keep the reviewed attempt and its reviewer identity. Only
                # the run carrying the review's remaining work changes.
                review.runtime_session_ref = str(demand.id)
                demand.body = source.body + "\n\n" + message
                from app.db.models.governance import AuditEvent
                db.add(AuditEvent(entity_type="project_task", entity_id=task.id, event_type="review_continuation_created",
                    actor=by, payload={"review_id": str(review.id), "demand_id": str(demand.id),
                                       "source_message_id": str(source.id), "question_id": str(question.id)}))
            else:
                assignment_id = previous.assignment_id if previous else await db.scalar(select(TaskAssignment.id).where(
                    TaskAssignment.task_id == task.id, TaskAssignment.agent_id == asker.id,
                    TaskAssignment.status == "active").order_by(TaskAssignment.created_at.desc()).limit(1))
                execution = await create_task_attempt(db, task.id, assignment_id)
                execution.runtime_session_ref = str(demand.id)
                demand.task_execution_id = execution.id
    question.reply_demand_id = demand.id
    db.add(
        Notification(
            source="system",
            severity="info",
            title=notice,
            message=f"{asker.name}: {question.question[:200]}",
            event_key=event_key,
            occurred_at=now,
        )
    )
    await db.commit()
    await db.refresh(demand)
    if demand.scheduled_at is not None and demand.scheduled_at <= datetime.now(timezone.utc):
        from app.core.dispatch_signal import wake_scheduled_dispatch

        wake_scheduled_dispatch()
    return demand
