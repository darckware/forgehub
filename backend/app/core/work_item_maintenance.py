"""Remote maintenance seen from a Darckware ticket/demand (remote-access
support plan, Fase 3, 2026-11-12 -- docs/architecture/REMOTE_ACCESS_SUPPORT_ADJUSTMENTS_PLAN.md).

Two directions, both keyed by the item (kind + Darckware id):

* An agent run inside a "Pedir ao agente" task inherits the task's item
  (`resolve_task_item`, called by `host_execution.launch_execution` for every
  path that records an execution): the agent may omit it, but may not name a
  different one (422 `DARCKWARE_ITEM_MISMATCH`).
* The item's detail lists what ran for it (`item_maintenance`): executions
  with `darckware_item_kind/id` = the item, and the agent tasks behind them,
  each finished task with a *proposed* note and minutes. Proposing writes
  nothing; only the operator's confirmation (client_ops `...:record`) writes
  to Darckware, once per Messages task: a `maintenance_recording` attempt is
  committed before any Darckware write and closed by `maintenance_recorded`
  or `maintenance_record_discarded`; one left open (timeout, 5xx, failure
  after the time entry) blocks new records until an admin settles it.

The proposal counts only the task's own runs that did run on a machine (all
skipped = not counted), only once every run is over, by the union of their
intervals (overlapping runs once), rounded up to 30 min, min 30. The note is
client-facing -- Darckware shows a time entry's description and a resolution
in the client portal -- so it names machines, a plain description of what ran
and the outcome, never a task number, agent, command text or internal id.

Executions a person started (no agent task) are listed but never proposed:
the operator records them with the ordinary "Registrar horas". A unit keyed
by a set of execution ids would need its own idempotency key that changes
whenever another manual run is added -- the simpler correct option is to
leave them out of the proposal.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import Agent
from app.db.models.demand import DEMAND_TERMINAL_DISPATCH_STATUSES, AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.server import Server

#: AuditEvent written by "Pedir ao agente" (host_execution.REQUEST_EVENT);
#: repeated here to keep this module import-light.
REQUEST_EVENT = "agent_maintenance_request"
#: AuditEvents (entity_type darckware_<kind>, payload agent_demand_id +
#: attempt_id) of one recording attempt: `recording` is committed before any
#: Darckware call; `recorded` closes it as done, `discarded` as not written.
#: A `recording` with neither is an attempt whose outcome is unknown.
RECORDING_EVENT = "maintenance_recording"
RECORDED_EVENT = "maintenance_recorded"
DISCARDED_EVENT = "maintenance_record_discarded"
#: Minutes are proposed in blocks of this size (Darckware bills the same way).
BLOCK_MINUTES = 30
MAX_MINUTES = 24 * 60


def same_item_id(a: str | None, b: str | None) -> bool:
    """Darckware ids are UUIDs; compare them canonically (case, braces)."""
    if a is None or b is None:
        return a is b
    try:
        return uuid.UUID(str(a).strip()) == uuid.UUID(str(b).strip())
    except ValueError:
        return str(a).strip().lower() == str(b).strip().lower()


async def task_item(db: AsyncSession, demand_id: uuid.UUID) -> tuple[str, str] | None:
    """The Darckware item a Messages task serves, if "Pedir ao agente" gave it one.

    An approved maintenance proposal runs under a new task (maintenance_proposal
    `open_run_task`); that task serves the item of the task the proposal came from.
    """
    spec = (await db.execute(
        select(AuditEvent).where(AuditEvent.entity_type == REQUEST_EVENT, AuditEvent.entity_id == demand_id)
        .order_by(AuditEvent.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    if spec is not None:
        payload = spec.payload or {}
        kind, item_id = payload.get("darckware_item_kind"), payload.get("darckware_item_id")
        return (kind, item_id) if kind and item_id else None
    from app.db.models.maintenance_proposal import MaintenanceProposal

    proposal_ids = (await db.scalars(
        select(MaintenanceProposal.id).where(MaintenanceProposal.agent_demand_id == demand_id)
    )).all()
    if not proposal_ids:
        return None
    approved = (await db.execute(
        select(AuditEvent).where(AuditEvent.entity_type == "maintenance_proposal",
                                 AuditEvent.entity_id.in_(proposal_ids), AuditEvent.event_type == "approved")
        .order_by(AuditEvent.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    origin = (approved.payload or {}).get("origin_demand_id") if approved else None
    if not origin or uuid.UUID(origin) == demand_id:
        return None
    origin_spec = (await db.execute(
        select(AuditEvent).where(AuditEvent.entity_type == REQUEST_EVENT, AuditEvent.entity_id == uuid.UUID(origin))
        .order_by(AuditEvent.created_at.desc()).limit(1)
    )).scalar_one_or_none()
    payload = (origin_spec.payload or {}) if origin_spec else {}
    kind, item_id = payload.get("darckware_item_kind"), payload.get("darckware_item_id")
    return (kind, item_id) if kind and item_id else None


async def resolve_task_item(
    db: AsyncSession, demand_id: uuid.UUID | None, given: tuple[str, str] | None
) -> tuple[str, str] | None:
    """The item an agent execution records: the task's when the agent passed
    none; refused when the agent named a different one."""
    if demand_id is None:
        return given
    expected = await task_item(db, demand_id)
    if expected is None:
        return given
    if given is None:
        return expected
    if given[0] != expected[0] or not same_item_id(given[1], expected[1]):
        raise HTTPException(422, {
            "code": "DARCKWARE_ITEM_MISMATCH",
            "message": (f"This task serves Darckware {expected[0]} {expected[1]}; "
                        f"omit the item or pass that one (got {given[0]} {given[1]})"),
        })
    return expected


def proposed_minutes(seconds: float) -> int:
    """Worked time (union of the runs' intervals), rounded up to 30 min, at least 30."""
    minutes = max(BLOCK_MINUTES, math.ceil(max(seconds, 0) / 60 / BLOCK_MINUTES) * BLOCK_MINUTES)
    return min(minutes, MAX_MINUTES)


def _duration(execution: HostExecution) -> float:
    if execution.finished_at is None:
        return 0.0
    return max((execution.finished_at - execution.started_at).total_seconds(), 0.0)


def union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    """Length of the union of the intervals: overlapping runs count once."""
    total, current = 0.0, None
    for start, end in sorted(i for i in intervals if i[1] > i[0]):
        if current is None or start > current[1]:
            if current is not None:
                total += (current[1] - current[0]).total_seconds()
            current = [start, end]
        else:
            current[1] = max(current[1], end)
    if current is not None:
        total += (current[1] - current[0]).total_seconds()
    return total


def _verdict(statuses: list[str]) -> str:
    if any(s in ("pending", "running") for s in statuses):
        return "running"
    if any(s == "failed" for s in statuses):
        return "failed"
    if any(s == "succeeded" for s in statuses):
        return "succeeded"
    return "nothing_ran"


def _what(execution: HostExecution) -> str:
    """For the operator's list (never the client-facing note)."""
    if execution.script_name:
        return f"script {execution.script_name}" + (f" v{execution.script_version}" if execution.script_version else "")
    first = (execution.command or "").strip().splitlines()[0:1]
    text = first[0] if first else ""
    return f"comando {text[:120]}" if text else "comando"


_OUTCOME = {"succeeded": "concluída com sucesso", "failed": "não concluída"}


def proposed_note(executions: list[dict[str, Any]]) -> str:
    """Client-facing text (Darckware shows a time entry's description and a
    resolution in the client portal): machine names, a plain description of
    what ran and the outcome -- no task number, agent, command text or id."""
    machines = sorted({m["name"] for e in executions for m in e["machines"] if m["verdict"] != "nothing_ran"})
    lines = [f"Manutenção remota realizada em: {', '.join(machines) or '—'}."]
    for e in executions:
        what = f"rotina de manutenção \"{e['script_name']}\"" if e["script_name"] else "comando de suporte"
        ran = [m for m in e["machines"] if m["verdict"] in _OUTCOME]
        by_outcome: dict[str, list[str]] = {}
        for m in ran:
            by_outcome.setdefault(m["verdict"], []).append(m["name"])
        parts = [f"{_OUTCOME[v]} em {', '.join(names)}" for v, names in sorted(by_outcome.items(), reverse=True)]
        lines.append(f"- {what[:1].upper()}{what[1:]}: {'; '.join(parts)}.")
    return "\n".join(lines)[:4000]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def maintenance_error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code, {"code": code, "message": message, **extra})


async def item_maintenance(db: AsyncSession, kind: str, item_id: uuid.UUID) -> dict[str, Any]:
    """What ran for this item and, per finished agent task, the proposal.

    Read-only: nothing is written here, in ForgeHub or in Darckware."""
    key = str(item_id)
    executions = list((await db.scalars(
        select(HostExecution).where(HostExecution.darckware_item_kind == kind,
                                    func.lower(func.trim(HostExecution.darckware_item_id)) == key)
        .order_by(HostExecution.started_at.desc())
    )).all())
    ids = [e.id for e in executions]
    results: dict[uuid.UUID, list[HostExecutionResult]] = {i: [] for i in ids}
    if ids:
        for r in (await db.scalars(select(HostExecutionResult).where(HostExecutionResult.execution_id.in_(ids)))).all():
            results[r.execution_id].append(r)
    server_ids = {r.server_id for rs in results.values() for r in rs if r.server_id}
    clients = dict((await db.execute(
        select(Server.id, Server.darckware_client_id).where(Server.id.in_(server_ids))
    )).all()) if server_ids else {}

    # Tasks: those "Pedir ao agente" opened for the item, plus any task an
    # execution of the item answers (older requests didn't store the item).
    task_ids = set((await db.scalars(
        select(AuditEvent.entity_id).where(
            AuditEvent.entity_type == REQUEST_EVENT,
            AuditEvent.payload["darckware_item_kind"].astext == kind,
            func.lower(AuditEvent.payload["darckware_item_id"].astext) == key,
        )
    )).all())
    task_ids |= {e.agent_demand_id for e in executions if e.agent_demand_id}
    demands = {d.id: d for d in (await db.scalars(select(AgentDemand).where(AgentDemand.id.in_(task_ids)))).all()} if task_ids else {}

    agent_ids = {e.agent_id for e in executions if e.agent_id} | {d.target_agent_id for d in demands.values() if d.target_agent_id}
    names = dict((await db.execute(select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids)))).all()) if agent_ids else {}

    # Recording attempts, per task: done, discarded, or still unknown.
    events = (await db.scalars(
        select(AuditEvent).where(AuditEvent.entity_type == f"darckware_{kind}", AuditEvent.entity_id == item_id,
                                 AuditEvent.event_type.in_((RECORDING_EVENT, RECORDED_EVENT, DISCARDED_EVENT)))
        .order_by(AuditEvent.created_at)
    )).all()
    recorded: dict[str, dict[str, Any]] = {}
    closed: set[str] = set()
    for event in events:
        p = event.payload or {}
        if event.event_type == RECORDED_EVENT:
            recorded.setdefault(p.get("agent_demand_id"), {
                "minutes": p.get("minutes"), "mode": p.get("mode"), "at": _iso(event.created_at), "by": event.actor,
                "confirmed_by_operator": bool(p.get("confirmed_by_operator")),
            })
        if event.event_type in (RECORDED_EVENT, DISCARDED_EVENT) and p.get("attempt_id"):
            closed.add(p["attempt_id"])
    uncertain: dict[str, dict[str, Any]] = {}
    for event in events:
        p = event.payload or {}
        if event.event_type == RECORDING_EVENT and p.get("attempt_id") not in closed:
            uncertain[p.get("agent_demand_id")] = {
                "attempt_id": p.get("attempt_id"), "mode": p.get("mode"), "minutes": p.get("minutes"),
                "note": p.get("note"), "at": _iso(event.created_at), "by": event.actor,
            }

    execution_rows = []
    for e in executions:
        rs = sorted(results[e.id], key=lambda r: r.server_name)
        demand = demands.get(e.agent_demand_id) if e.agent_demand_id else None
        verdict = _verdict([r.status for r in rs])
        execution_rows.append({
            "id": str(e.id),
            "started_at": _iso(e.started_at),
            "finished_at": _iso(e.finished_at),
            "duration_seconds": int(_duration(e)) if e.finished_at else None,
            "status": e.status,
            # A run still going: the execution itself, or any machine of it.
            "in_progress": e.status == "running" or e.finished_at is None or verdict == "running",
            "verdict": verdict,
            "machines": [{"name": r.server_name, "server_id": str(r.server_id) if r.server_id else None,
                          "verdict": _verdict([r.status])} for r in rs],
            "requested_by": e.requested_by,
            "trigger": e.trigger,
            "agent_id": str(e.agent_id) if e.agent_id else None,
            "agent_name": names.get(e.agent_id),
            "script_name": e.script_name,
            "what": _what(e),
            "reason": e.reason,
            "agent_demand_id": str(e.agent_demand_id) if e.agent_demand_id else None,
            "demand_number": demand.number if demand else None,
            "_clients": {str(clients[r.server_id]) if r.server_id and clients.get(r.server_id) else None
                         for r in rs if r.status != "skipped"},
            "_interval": (e.started_at, e.finished_at),
        })

    tasks = []
    for demand in sorted(demands.values(), key=lambda d: d.created_at, reverse=True):
        mine = [row for row in execution_rows if row["agent_demand_id"] == str(demand.id)]
        # Runs where nothing ran (every machine skipped) aren't work done.
        counted = [row for row in mine if row["verdict"] != "nothing_ran"]
        finished = demand.dispatch_status in DEMAND_TERMINAL_DISPATCH_STATUSES
        in_progress = any(row["in_progress"] for row in mine)
        done = recorded.get(str(demand.id))
        pending = None if done else uncertain.get(str(demand.id))
        proposal = None
        if finished and counted and not in_progress and done is None and pending is None:
            proposal = {
                "minutes": proposed_minutes(union_seconds([row["_interval"] for row in counted])),
                "note": proposed_note(list(reversed(counted))),
                "start_time": _iso(min(row["_interval"][0] for row in counted)),
                "end_time": _iso(max(row["_interval"][1] for row in counted)),
                "execution_count": len(counted),
            }
        tasks.append({
            "demand_id": str(demand.id),
            "number": demand.number,
            "subject": demand.subject,
            "agent_id": str(demand.target_agent_id) if demand.target_agent_id else None,
            "agent_name": names.get(demand.target_agent_id),
            "dispatch_status": demand.dispatch_status,
            "status": demand.status,
            "created_at": _iso(demand.created_at),
            "finished": finished,
            "runs_in_progress": in_progress,
            "execution_ids": [row["id"] for row in counted],
            "client_ids": sorted({c or "" for row in counted for c in row["_clients"]}),
            "recorded": done,
            "uncertain": pending,
            "proposal": proposal,
        })
    for row in execution_rows:
        row.pop("_clients")
        row.pop("_interval")
    return {"executions": execution_rows, "tasks": tasks}


async def task_for_record(db: AsyncSession, kind: str, item_id: uuid.UUID, demand_id: uuid.UUID) -> dict[str, Any]:
    """The task row of `item_maintenance`, or 404 when the task doesn't serve the item."""
    view = await item_maintenance(db, kind, item_id)
    task = next((t for t in view["tasks"] if t["demand_id"] == str(demand_id)), None)
    if task is None:
        raise maintenance_error(404, "MAINTENANCE_TASK_NOT_FOUND", "This Messages task did no maintenance for this item")
    return task


async def lock_task(db: AsyncSession, demand_id: uuid.UUID) -> None:
    """Transaction advisory lock on one task's recording."""
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"{RECORDED_EVENT}:{demand_id}"})
