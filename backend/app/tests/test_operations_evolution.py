"""Deterministic, reversible proposals for the 24x7 operation."""

from types import SimpleNamespace

from app.core.operations_evolution import execution_signals, suggest_routine_change


def test_execution_signals_keep_unknown_cost_separate_from_zero():
    demand = SimpleNamespace(
        dispatched_at=None, task_execution_at=None,
        dispatch_result="## Resultado\nNada a fazer.\n## Evidência\nCheck verde.",
    )
    signals = execution_signals(demand)
    assert signals.duration_ms is None
    assert signals.cost_usd is None
    assert signals.evidence_received is True
    assert signals.no_action is True


def test_three_consecutive_failures_propose_a0_pause():
    routine = SimpleNamespace(id="r1", enabled=True, instructions="Verify health")
    runs = [SimpleNamespace(status=s, evidence_received=None, no_action=None)
            for s in ("failed", "failed", "failed")]
    proposal = suggest_routine_change(routine, runs)
    assert proposal is not None
    assert proposal.autonomy_level == "A0"
    assert proposal.new_state == {"enabled": False}
    assert proposal.previous_state == {"enabled": True}


def test_missing_evidence_proposes_a1_instruction_repair():
    routine = SimpleNamespace(id="r2", enabled=True, instructions="Verify health")
    runs = [SimpleNamespace(status="completed", evidence_received=False, no_action=False) for _ in range(3)]
    proposal = suggest_routine_change(routine, runs)
    assert proposal is not None
    assert proposal.autonomy_level == "A1"
    assert "evidência" in proposal.new_state["instructions"].lower()
    assert proposal.previous_state == {"instructions": "Verify health"}


def test_successful_recent_run_breaks_failure_streak():
    routine = SimpleNamespace(id="r3", enabled=True, instructions="Verify health")
    runs = [SimpleNamespace(status=s, evidence_received=True, no_action=False)
            for s in ("failed", "completed", "failed", "failed")]
    assert suggest_routine_change(routine, runs) is None
