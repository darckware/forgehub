"""A routine briefing must route recent failures before claiming completion."""
import re
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.demand import AgentDemand
from app.db.models.operations import AgentRoutine, AgentRoutineRun

BRIEFING_TITLE = "Briefing matinal ao Marcelo"
BRIEFING_ACTION_CONTRACT = """## Tratamento obrigatório das falhas
Consulte as tarefas originais das rotinas com falha nas últimas 24 horas, incluindo
dispatch_error e dispatch_result. Não declare saúde verde/amarela nem STATUS: DONE
apenas por listar falhas ou recomendar trabalho futuro. Encaminhe cada falha a uma
tarefa real do responsável pelo Messages, ou cite uma tarefa de tratamento existente.
No resultado, registre uma linha ACTION: #origem -> #tratamento para cada falha,
com responsável, ação e bloqueio/prazo. A tarefa de tratamento deve citar #origem.
Falhas sem encaminhamento exigem STATUS: PARTIAL ou BLOCKED.
Métrica ausente/zerada e never_ran não comprovam saúde: confira a fonte e encaminhe
a lacuna de observabilidade. Não execute uma auditoria inteira para corrigir a exibição.
Enviar uma tarefa a si mesmo com channel=telegram não comprova entrega no Telegram;
use o envio oficial autorizado e registre o comprovante de entrega.
"""

_ACTION = re.compile(r"^ACTION:[ \t]*#(\d+)[ \t]*->[ \t]*#(\d+)(?:[ \t]+[^\r\n]*)?$", re.MULTILINE)


def missing_briefing_actions(
    failures: Sequence[AgentDemand], followups: Sequence[AgentDemand],
    report: str, briefing: AgentDemand,
) -> list[int]:
    """Validate references against stored tasks, not a prose promise of action."""
    actions = {(int(source), int(target)) for source, target in _ACTION.findall(report)}
    missing = []
    for failure in failures:
        source_ref = re.compile(rf"#{failure.number}\b")
        valid = any(
            (failure.number, task.number) in actions
            and task.id not in (briefing.id, failure.id)
            and task.from_agent_id is not None
            and task.target_agent_id is not None
            and task.origin_type == "task"
            and task.status != "archived"
            and task.dispatch_status != "failed"
            and task.created_at >= failure.created_at
            and "briefing" not in task.subject.casefold()
            and source_ref.search(task.body or "")
            for task in followups
        )
        if not valid:
            missing.append(failure.number)
    return missing


async def briefing_failure_reason(
    db: AsyncSession, briefing: AgentDemand, report: str,
) -> str | None:
    # Only the real scheduled briefing is subject to this contract. Ordinary
    # messages and archived history keep their existing completion semantics.
    if briefing.subject != f"[Rotina] {BRIEFING_TITLE}":
        return None
    routine_run = await db.scalar(
        select(AgentRoutineRun.id).join(AgentRoutine).where(
            AgentRoutineRun.demand_id == briefing.id,
            AgentRoutine.title == BRIEFING_TITLE,
        )
    )
    if routine_run is None:
        return None
    failures = list((await db.scalars(
        select(AgentDemand).join(AgentRoutineRun, AgentRoutineRun.demand_id == AgentDemand.id).where(
            AgentDemand.dispatch_status == "failed",
            AgentDemand.status != "archived",
            AgentRoutineRun.occurrence_at >= briefing.created_at - timedelta(hours=24),
            AgentRoutineRun.occurrence_at <= briefing.created_at,
        )
    )).all())
    if not failures:
        return None
    followups = list((await db.scalars(select(AgentDemand).where(
        AgentDemand.origin_type == "task",
        AgentDemand.created_at >= min(task.created_at for task in failures),
        AgentDemand.id != briefing.id,
    ))).all())
    missing = missing_briefing_actions(failures, followups, report, briefing)
    if missing:
        return "Briefing lacks verified follow-up tasks for routine failures: " + ", ".join(f"#{n}" for n in missing)
    return None
