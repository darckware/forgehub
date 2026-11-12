"""Completion and incident ordering without database or bridge access."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import audit as routes
from app.db.models.audit import AuditCheck, AuditCheckRun
from app.db.models.demand import AgentDemand

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("source", ["manual", "remediation-verification", "athos-remediation"])
async def test_evidence_is_timestamped_when_execution_finishes(monkeypatch, source):
    class Clock:
        instant = NOW

        @classmethod
        def now(cls, tz):
            return cls.instant

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, *args, **kwargs):
            Clock.instant = NOW + timedelta(minutes=2)
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"exit_code": 0, "reply": "done"})

    monkeypatch.setattr(routes, "datetime", Clock)
    monkeypatch.setattr(routes.httpx, "AsyncClient", Client)
    check = AuditCheck(id=uuid.uuid4(), name="test ordering", command="true", timeout_seconds=5)
    if source == "athos-remediation":
        run = await routes._delegate_remediation_to_athos(check, None)
    else:
        run = await routes._execute_check(check, source)
    assert run.created_at == NOW + timedelta(minutes=2)


@pytest.mark.parametrize("incoming_status,newest_status", [("ok", "fail"), ("fail", "ok")])
async def test_delayed_older_verdict_cannot_change_newer_incident(monkeypatch, incoming_status, newest_status):
    check = AuditCheck(id=uuid.uuid4(), name="test ordering", command="true", agent_profile="test-suite")
    incoming = AuditCheckRun(id=uuid.uuid4(), check_id=check.id, status=incoming_status, created_at=NOW)
    newest = AuditCheckRun(id=uuid.uuid4(), check_id=check.id, status=newest_status, created_at=NOW+timedelta(seconds=1))
    recovered = newest_status == "ok"
    demand = AgentDemand(id=uuid.uuid4(), subject=f"[Auditor:{check.id}] Restore", body="original evidence" + ("\n[Auditor recovery] latest ok" if recovered else ""), status="archived" if recovered else "new")
    initial = (demand.status, demand.body)
    created = []

    async def execute(query):
        entity = query.column_descriptions[0].get("entity")
        value = newest if entity is AuditCheckRun else demand if entity is AgentDemand else uuid.uuid4()
        return SimpleNamespace(scalar_one_or_none=lambda: value)

    async def create(db, payload, **kwargs):
        created.append(payload)
        return SimpleNamespace(id=uuid.uuid4())

    monkeypatch.setattr(routes, "create_demand_and_notify", create)
    db = SimpleNamespace(flush=AsyncMock(), execute=execute, add=lambda value: None)
    assert await routes._sync_check_incident(db, check, incoming) is False
    assert (demand.status, demand.body) == initial
    assert created == []


async def test_slow_batch_keeps_individual_completion_and_does_not_reopen_manual_recovery(monkeypatch):
    first = AuditCheck(id=uuid.uuid4(), name="first", command="true", agent_profile="test-suite")
    slow = AuditCheck(id=uuid.uuid4(), name="slow", command="true", agent_profile="test-suite")
    manual = AuditCheckRun(id=uuid.uuid4(), check_id=first.id, status="ok", requested_by="manual", created_at=NOW+timedelta(seconds=1))
    incident = AgentDemand(id=uuid.uuid4(), subject=f"[Auditor:{first.id}] Restore", status="archived", body="[Auditor recovery] manual recovery")
    stored = [manual]
    created = []

    class Clock:
        @classmethod
        def now(cls, tz):
            return NOW + timedelta(seconds=2)

    async def execute_check(check, requested_by):
        return AuditCheckRun(id=uuid.uuid4(), check_id=check.id, status="fail" if check is first else "ok", requested_by=requested_by, created_at=NOW if check is first else NOW+timedelta(seconds=2))

    async def execute(query):
        entity = query.column_descriptions[0].get("entity")
        value = (max((run for run in stored if run.check_id == first.id), key=lambda run: (run.created_at, run.id))
                 if entity is AuditCheckRun else incident if entity is AgentDemand else first.id)
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [first, slow]), scalar_one_or_none=lambda: value)

    async def create(db, payload, **kwargs):
        created.append(payload)

    original_sync = routes._sync_check_incident

    async def sync(db, check, run):
        return await original_sync(db, check, run) if check is first else False

    db = SimpleNamespace(execute=execute, add=stored.append, flush=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(routes, "datetime", Clock)
    monkeypatch.setattr(routes, "_execute_check", execute_check)
    monkeypatch.setattr(routes, "_sync_check_incident", sync)
    monkeypatch.setattr(routes, "create_demand_and_notify", create)
    monkeypatch.setattr("app.core.dispatch_signal.wake_scheduled_dispatch", lambda: None)
    runs = await routes._run_enabled_checks(db, "cron")
    assert created == []
    assert incident.status == "archived"
    assert runs[0].created_at == NOW
    assert runs[1].created_at == NOW+timedelta(seconds=2)
    assert runs[0].batch_id is not None
    assert runs[0].batch_id == runs[1].batch_id
    assert manual.batch_id is None


async def test_stale_failed_remediation_cannot_create_manual_inbox_after_newer_ok(monkeypatch):
    check = AuditCheck(id=uuid.uuid4(), name="stale remediation", command="true", agent_profile="test-suite")
    newest = AuditCheckRun(id=uuid.uuid4(), check_id=check.id, status="ok", created_at=NOW+timedelta(seconds=1))
    repair = AuditCheckRun(id=uuid.uuid4(), check_id=check.id, status="ok", created_at=NOW-timedelta(seconds=1), requested_by="athos-remediation", exit_code=0, output="done", duration_ms=1)
    verification = AuditCheckRun(id=uuid.uuid4(), check_id=check.id, status="fail", created_at=NOW, requested_by="remediation-verification", exit_code=1, output="old failure", duration_ms=1)
    created = []

    async def execute(query):
        return SimpleNamespace(scalar_one_or_none=lambda: newest)

    async def create(db, payload, **kwargs):
        created.append(payload)
        return SimpleNamespace(id=uuid.uuid4())

    db = SimpleNamespace(execute=execute, add=lambda row: None, flush=AsyncMock(), commit=AsyncMock(), refresh=AsyncMock())
    monkeypatch.setattr(routes, "_get_check_or_404", AsyncMock(return_value=check))
    monkeypatch.setattr(routes, "_remediation_problems_on_host", AsyncMock(return_value=[]))
    monkeypatch.setattr(routes, "_delegate_remediation_to_athos", AsyncMock(return_value=repair))
    monkeypatch.setattr(routes, "_execute_check", AsyncMock(return_value=verification))
    monkeypatch.setattr(routes, "create_demand_and_notify", create)
    result = await routes.remediate_check(check.id, db=db, _admin=object())
    assert created == []
    assert result.escalated_to_inbox is False
    assert result.verification_run.status == "fail"
