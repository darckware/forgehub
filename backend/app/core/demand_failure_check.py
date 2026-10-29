"""Atomic continuation of known failed attempts through the existing work queue."""
from datetime import datetime, timedelta, timezone
import re
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demand_workflow import record_transition, requires_reconciliation
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand, DemandAttachment


def quota_reset_at(output: str, reference: datetime) -> datetime | None:
    """Only the provider's explicit time and timezone; no quota/date guesses."""
    if not re.search(r"(?:hit your .*limit|usage limit|quota.*exceeded)", output, re.I):
        return None
    match = re.search(r"resets (\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*\(([A-Za-z_]+/[A-Za-z_/]+)\)", output, re.I)
    if match is None:
        return None
    hour, minute = int(match[1]), int(match[2] or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    try:
        zone = ZoneInfo(match[4])
    except ZoneInfoNotFoundError:
        return None
    local = reference.astimezone(zone)
    reset = local.replace(hour=hour % 12 + (12 if match[3].lower() == "pm" else 0), minute=minute, second=0, microsecond=0)
    if reset <= local:
        reset += timedelta(days=1)
    return reset


def _excerpt(value: str | None, limit: int) -> str:
    text = value or "(não registrado)"
    return text if len(text) <= limit else text[:limit] + "\n[Extrato: consulte a mensagem original para o conteúdo completo.]"


async def ensure_failure_check(db: AsyncSession, source_id: UUID) -> AgentDemand | None:
    """Caller commits. Lock, child insert and archive share one transaction.

    Never retries original work or drops a runner identity. A failed diagnostic
    task cannot generate another diagnostic task. Unknown outcomes stay blocked.
    """
    source = await db.scalar(select(AgentDemand).where(AgentDemand.id == source_id).with_for_update())
    if source is None or source.failure_check_source_id is not None:
        return None
    existing = await db.scalar(select(AgentDemand).where(AgentDemand.failure_check_source_id == source.id))
    if existing is not None:
        return existing
    if (source.status == "archived" or source.consolidated_into_id is not None
            or source.origin_type != "task" or source.dispatch_status != "failed"
            or requires_reconciliation(source) or "ended as 'stale'" in (source.dispatch_error or "")):
        return None
    owner_id = source.from_agent_id or source.target_agent_id
    if owner_id is None:
        return None
    owner = await db.get(Agent, owner_id)
    if owner is None:
        return None
    now = datetime.now(timezone.utc)
    reset = quota_reset_at(source.dispatch_result or "", source.task_execution_at or now)
    target_id = owner_id
    scheduled_at = now
    resume_note = ""
    if reset is not None and source.target_agent_id is not None:
        executor = await db.get(Agent, source.target_agent_id)
        if executor is not None and executor.runtime_type in ("claude", "codex", "agy", "antigravity"):
            target_id = executor.id
            scheduled_at = max(now, reset + timedelta(minutes=5))
            resume_note = (
                f"## Continuação após limite de uso\nReset informado pelo provedor: {reset.isoformat()}.\n"
                f"Checagem/continuação programada: {scheduled_at.isoformat()}.\n"
                "Neste caso de limite reconhecido, verifique primeiro os efeitos da tentativa anterior; "
                "se o trabalho estiver pendente, continue somente o escopo original já autorizado, sem "
                "duplicar operações. Preserve o papel de executor/revisor e as aprovações existentes.\n\n"
            )
    attachments = list((await db.scalars(select(DemandAttachment).where(DemandAttachment.demand_id == source.id))).all())
    purpose = (
        "Esta é uma checagem com continuação programada após reset confirmado, dentro do escopo original."
        if resume_note else
        "Esta é uma checagem de diagnóstico, não uma autorização para repetir a operação original."
    )
    body = (
        f"Checagem da tentativa da mensagem #{source.number} (id={source.id}).\n"
        f"Origem navegável: /demands?message={source.id}\n"
        f"{purpose}\n"
        "Consulte o pedido original completo e as evidências. Determine se o trabalho já foi realizado "
        "apesar do erro, ficou parcial ou está bloqueado. Verifique os efeitos já produzidos antes de "
        "recomendar nova tentativa. Não publique nem envie mensagens externas por causa do pedido copiado.\n"
        "Se concluído, relate evidências verificadas. Se houver pendência, registre causa, o que já foi "
        "feito e o que falta; encaminhe a correção autorizada ao responsável por Messages citando esta "
        "checagem e a mensagem original. Não crie checagem desta checagem. Se faltar autorização ou não "
        "puder verificar, declare STATUS: BLOCKED.\n"
        "Limite de uso: identifique o reset no erro do provedor, com data e fuso. Reagende a continuação "
        "para depois desse reset ou encaminhe ao desenvolvedor disponível (Codex/Aramis, Claude/Porthus, "
        "agy/Dartan), mantendo o mesmo papel, escopo, evidências e origem. Não invente horários. "
        "Revisor substituto não pode ser o implementador. Não repita efeitos já realizados.\n\n"
        f"{resume_note}"
        f"## Identidade e contexto\nAssunto: {_excerpt(source.subject, 1000)}\n"
        f"Solicitante: {source.from_agent} ({source.from_agent_id})\nExecutor original: {source.target_agent_id}\n"
        f"Projeto: {source.project_id}; tarefa de projeto: {source.origin_id}\n"
        f"Diretório: {source.working_path}; área: {source.context_area}\n"
        f"Canal de origem (somente contexto): {source.channel}/{source.channel_ref}\n"
        f"Run ID: {source.agent_run_id}; tentativas: {source.dispatch_attempts}\n\n"
        f"## Pedido original\n{_excerpt(source.body, 25000)}\n\n"
        f"## Comando original\n{_excerpt(source.command_text, 8000)}\n\n"
        f"## Motivo do erro\n{_excerpt(source.dispatch_error, 8000)}\n\n"
        f"## Resultado e evidências da tentativa\n{_excerpt(source.dispatch_result, 30000)}\n\n"
        "## Anexos preservados na origem\n" + _excerpt("\n".join(
            f"- {a.filename}: /api/v1/demands/{source.id}/attachments/{a.id}/download" for a in attachments
        ), 8000)
    )
    check = AgentDemand(
        failure_check_source_id=source.id,
        from_agent=source.from_agent, from_agent_id=owner_id, target_agent_id=target_id,
        subject=f"Checagem de #{source.number}: {source.subject}"[:500], body=body,
        origin_type="task", origin_id=source.origin_id, project_id=source.project_id,
        development_request_id=source.development_request_id, context_area=source.context_area,
        working_path=source.working_path, scheduled_at=scheduled_at,
        requires_response=False, channel="agent", channel_ref=None,
        requires_approval=source.requires_approval,
        approval_status="pending" if source.requires_approval else None,
    )
    db.add(check)
    await db.flush()
    source.status = "archived"
    source.decision_reason = f"Tentativa preservada; acompanhamento pela checagem #{check.number}."
    record_transition(db, source, "failure_check_created", extra={"check_id": str(check.id), "check_number": check.number})
    record_transition(db, check, "failure_check_opened", extra={"source_id": str(source.id), "source_run_id": source.agent_run_id})
    return check


async def run_failure_check_pass(db: AsyncSession) -> int:
    """Reconcile known historical failures through the same queue, no replay."""
    source_ids = list((await db.scalars(select(AgentDemand.id).where(
        AgentDemand.dispatch_status == "failed", AgentDemand.status != "archived",
        AgentDemand.failure_check_source_id.is_(None), AgentDemand.consolidated_into_id.is_(None),
        AgentDemand.origin_type == "task",
        AgentDemand.dispatch_error.isnot(None),
        AgentDemand.dispatch_error.not_ilike("%uncertain%"),
        AgentDemand.dispatch_error.not_ilike("%ended as 'stale'%"),
        or_(AgentDemand.from_agent_id.isnot(None), AgentDemand.target_agent_id.isnot(None)),
        AgentDemand.id.not_in(select(AgentDemand.failure_check_source_id).where(AgentDemand.failure_check_source_id.isnot(None))),
    ).order_by(AgentDemand.created_at).limit(50))).all())
    created = 0
    for source_id in source_ids:
        check = await ensure_failure_check(db, source_id)
        if check is not None:
            created += 1
    if created:
        await db.commit()
    return created
