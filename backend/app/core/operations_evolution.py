"""Small, deterministic signals and change proposals for agent routines.

The retrospective may suggest only changes whose previous state can be
restored exactly. Higher-risk proposals remain subject to Marcelo's approval.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ExecutionSignals:
    duration_ms: int | None
    cost_usd: Decimal | None
    evidence_received: bool
    no_action: bool


@dataclass(frozen=True)
class RoutineChangeProposal:
    summary: str
    rationale: str
    autonomy_level: str
    metric_name: str
    previous_state: dict[str, Any]
    new_state: dict[str, Any]


_EVIDENCE_HEADER = re.compile(r"(?:^|\n)\s*(?:#{1,4}\s*)?evid[eê]ncia\s*:?[ \t]*\n?", re.IGNORECASE)
_NO_ACTION = re.compile(r"\bnada a fazer\b|\bsem (?:ação|acao|alterações|alteracoes)\b", re.IGNORECASE)
_EVIDENCE_INSTRUCTION = "\n\nAo concluir, inclua uma seção 'Evidência' com o que foi verificado e o resultado concreto."


def execution_signals(demand: Any) -> ExecutionSignals:
    result = demand.dispatch_result or ""
    started = demand.dispatched_at
    finished = demand.task_execution_at
    duration = max(0, round((finished - started).total_seconds() * 1000)) if started and finished else None
    match = _EVIDENCE_HEADER.search(result)
    evidence = bool(match and result[match.end():].strip())
    return ExecutionSignals(
        duration_ms=duration,
        # The bridge does not persist ForgeRouter usage for a Messages run.
        # Unknown cost must remain unknown, never silently become $0.
        cost_usd=None,
        evidence_received=evidence,
        no_action=bool(_NO_ACTION.search(result)),
    )


def suggest_routine_change(routine: Any, recent_runs: list[Any]) -> RoutineChangeProposal | None:
    """Runs are newest first; only a current, consecutive pattern qualifies."""
    if not routine.enabled or len(recent_runs) < 3:
        return None
    latest = recent_runs[:3]
    if all(run.status == "failed" for run in latest):
        return RoutineChangeProposal(
            summary="Pausar rotina após três falhas seguidas",
            rationale="Três execuções consecutivas falharam; evitar repetição até diagnóstico do dono.",
            autonomy_level="A0", metric_name="failed_runs",
            previous_state={"enabled": True}, new_state={"enabled": False},
        )
    if all(run.status == "completed" and run.evidence_received is False for run in latest):
        if _EVIDENCE_INSTRUCTION.strip() in routine.instructions:
            return None
        return RoutineChangeProposal(
            summary="Reforçar evidência na instrução da rotina",
            rationale="Três resultados completos chegaram sem seção de evidência verificável.",
            autonomy_level="A1", metric_name="evidence_rate",
            previous_state={"instructions": routine.instructions},
            new_state={"instructions": routine.instructions.rstrip() + _EVIDENCE_INSTRUCTION},
        )
    return None
