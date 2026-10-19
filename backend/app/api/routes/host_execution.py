"""Command executions on machines – Remote Access phase 4
(docs/architecture/REMOTE_MAINTENANCE_PLAN.md). Admin-only: this runs
arbitrary commands as the machine's login.

Endpoints:
  POST /api/v1/host-executions                 – run a command on machines/groups
  GET  /api/v1/host-executions                 – recent executions with counts
  GET  /api/v1/host-executions/{id}            – one execution, result per machine
  POST /api/v1/host-executions/{id}:follow-up  – run another command on the
                                                 machines that failed
  POST /api/v1/host-executions/{id}:cancel     – machines not started yet are skipped

Machines are checked before anything runs; one that can't take the command is
recorded as "skipped" with the reason, never silently dropped: parked in
ForgeHub, no login yet, OS incompatible with the shell, or already running
another command (one execution per machine at a time).
"""
import json
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.host_execution import (
    MAX_TARGETS,
    AgentExecutionCreate,
    AgentMachineOut,
    AgentScriptOut,
    HostExecutionCounts,
    HostExecutionCreate,
    HostExecutionDetail,
    HostExecutionFollowUp,
    HostExecutionResultOut,
    HostExecutionSummary,
)
from app.core import host_exec_runner
from app.core.host_scripts import ScriptError, compatible, render_script, resolve_values, shell_for
from app.core.deps import ActorPrincipal, authorize_action, get_actor_principal, get_current_admin
from app.core.secret_masking import mask_secrets
from app.core.forgevault import machine_secret_name, vault_reveal_name, vault_store
from app.db.base import get_db
from app.db.models.governance import AuditEvent
from app.db.models.agent import Agent
from app.db.models.host_execution import HostExecution, HostExecutionResult
from app.db.models.host_script import HostScript
from app.db.models.server import HostGroup, HostGroupMember, Server
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/host-executions", tags=["remote-access"])

ACTIVE_RESULT_STATUSES = ("pending", "running")


async def busy_server_ids(db: AsyncSession) -> set[uuid.UUID]:
    """Machines with a command queued or running right now. Shared with the
    readiness endpoint, which reports them as "busy"."""
    rows = await db.execute(
        select(HostExecutionResult.server_id).where(
            # Not filtered by the execution's status: a cancelled execution can
            # still have one machine finishing its command.
            HostExecutionResult.status.in_(ACTIVE_RESULT_STATUSES),
            HostExecutionResult.server_id.is_not(None),
        )
    )
    return set(rows.scalars())


def skip_reason(
    server: Server, shell: str, busy: set[uuid.UUID], platform: str | None = None, shell_agnostic: bool = False,
    login_given: bool = False,
) -> str | None:
    if not server.access_enabled:
        return "Access is turned off in ForgeHub"
    if not server.remote_user and not login_given:
        return "No login set for this machine yet"
    if not server.ip_address:
        return "Waiting for the machine to join the tailnet"
    if shell_agnostic:
        pass  # the executor picks the right shell per machine
    elif platform is not None:
        if not compatible(platform, server.os_family):
            return f"This script is for {platform.capitalize()} machines"
    elif shell == "powershell" and server.os_family != "windows":
        return "PowerShell runs only on Windows machines"
    elif shell == "sh" and server.os_family == "windows":
        return "sh does not run on Windows machines"
    if server.id in busy:
        return "Already running another command"
    return None


def _counts_and_verdict(statuses: list[str]) -> tuple[HostExecutionCounts, str]:
    counts = HostExecutionCounts(total=len(statuses))
    for s in statuses:
        setattr(counts, s, getattr(counts, s) + 1)
    if counts.pending or counts.running:
        verdict = "running"
    elif counts.failed:
        verdict = "failed"
    elif counts.succeeded:
        verdict = "succeeded"
    else:
        verdict = "nothing_ran"
    return counts, verdict


async def _summaries(db: AsyncSession, executions: list[HostExecution]) -> list[HostExecutionSummary]:
    ids = [e.id for e in executions]
    statuses: dict[uuid.UUID, list[str]] = {i: [] for i in ids}
    if ids:
        rows = await db.execute(
            select(HostExecutionResult.execution_id, HostExecutionResult.status).where(
                HostExecutionResult.execution_id.in_(ids)
            )
        )
        for execution_id, result_status in rows.all():
            statuses[execution_id].append(result_status)
    agent_ids = {e.agent_id for e in executions if e.agent_id}
    names = {}
    if agent_ids:
        names = dict((await db.execute(select(Agent.id, Agent.name).where(Agent.id.in_(agent_ids)))).all())
    out = []
    for execution in executions:
        summary = HostExecutionSummary.model_validate(execution)
        summary.counts, summary.verdict = _counts_and_verdict(statuses[execution.id])
        summary.agent_name = names.get(execution.agent_id)
        out.append(summary)
    return out


async def _detail(db: AsyncSession, execution: HostExecution) -> HostExecutionDetail:
    results = list(
        (
            await db.execute(
                select(HostExecutionResult)
                .where(HostExecutionResult.execution_id == execution.id)
                .order_by(HostExecutionResult.server_name)
            )
        ).scalars()
    )
    follow_ups = list(
        (
            await db.execute(
                select(HostExecution.id)
                .where(HostExecution.parent_execution_id == execution.id)
                .order_by(HostExecution.started_at)
            )
        ).scalars()
    )
    detail = HostExecutionDetail.model_validate(execution)
    if execution.agent_id:
        agent = await db.get(Agent, execution.agent_id)
        detail.agent_name = agent.name if agent else None
    detail.results = [HostExecutionResultOut.model_validate(r) for r in results]
    detail.counts, detail.verdict = _counts_and_verdict([r.status for r in results])
    detail.follow_up_ids = follow_ups
    return detail


async def launch_execution(
    db: AsyncSession,
    *,
    servers: list[Server],
    command: str,
    shell: str,
    timeout_seconds: int,
    actor: str,
    target_summary: str,
    parent_execution_id: uuid.UUID | None = None,
    secrets: list[str] | None = None,
    trigger: str = "manual",
    agent_id: uuid.UUID | None = None,
    schedule_id: uuid.UUID | None = None,
    script: HostScript | None = None,
    retry_until=None,
    on_success=None,
    values_for_hook: dict | None = None,
    executor=None,
    script_label: str | None = None,
    shell_agnostic: bool = False,
    login_given: bool = False,
    reason: str | None = None,
    darckware_item: tuple[str, str] | None = None,
) -> HostExecution:
    """Creates the execution + one result per machine (skipped ones already
    closed with their reason), audits it and starts the background run.
    Phase 3's preparation/rotation will call this with `secrets` so the
    passwords it generates are masked everywhere."""
    busy = await busy_server_ids(db)
    now = datetime.now(timezone.utc)
    masked = mask_secrets(command, secrets or []) or ""
    execution = HostExecution(
        parent_execution_id=parent_execution_id,
        shell=shell,
        command=masked,
        timeout_seconds=timeout_seconds,
        status="running",
        requested_by=actor,
        target_summary=target_summary[:500],
        started_at=now,
        trigger=trigger,
        agent_id=agent_id,
        schedule_id=schedule_id,
        script_id=script.id if script else None,
        script_version=script.current_version if script else None,
        script_name=script.name if script else script_label,
        retry_until=retry_until,
        reason=reason,
        darckware_item_kind=darckware_item[0] if darckware_item else None,
        darckware_item_id=darckware_item[1] if darckware_item else None,
    )
    db.add(execution)
    await db.flush()
    for server in servers:
        reason = skip_reason(server, shell, busy, script.platform if script else None, shell_agnostic, login_given)
        db.add(
            HostExecutionResult(
                execution_id=execution.id,
                server_id=server.id,
                server_name=server.name,
                status="skipped" if reason else "pending",
                skip_reason=reason,
                finished_at=now if reason else None,
            )
        )
    db.add(
        AuditEvent(
            entity_type="host_execution",
            entity_id=execution.id,
            event_type="started",
            actor=actor,
            payload={
                "shell": shell,
                "command": masked,
                "machines": [str(s.id) for s in servers],
                "parent_execution_id": str(parent_execution_id) if parent_execution_id else None,
                "trigger": trigger,
                "agent_id": str(agent_id) if agent_id else None,
                "script": f"{script.name} v{script.current_version}" if script else None,
                "reason": reason,
                "darckware_item": f"{darckware_item[0]}:{darckware_item[1]}" if darckware_item else None,
            },
        )
    )
    await db.commit()
    await db.refresh(execution)
    if on_success is None and script is not None:
        on_success = system_script_hook(script, values_for_hook)
    host_exec_runner.start_execution(
        execution.id, shell, command, timeout_seconds, secrets, retry_until, on_success, executor
    )
    return execution


async def resolve_targets(
    db: AsyncSession, server_ids: list, group_ids: list
) -> tuple[list[Server], list[str]]:
    """Machines from explicit ids + group members, and the group names."""
    wanted = {uuid.UUID(str(i)) for i in server_ids}
    group_names: list[str] = []
    if group_ids:
        gids = [uuid.UUID(str(g)) for g in group_ids]
        groups = list((await db.execute(select(HostGroup).where(HostGroup.id.in_(gids)))).scalars())
        if len(groups) != len(set(gids)):
            raise HTTPException(status_code=422, detail="Unknown group")
        group_names = [g.name for g in groups]
        members = await db.execute(select(HostGroupMember.server_id).where(HostGroupMember.group_id.in_(gids)))
        wanted |= set(members.scalars())
    if len(wanted) > MAX_TARGETS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_TARGETS} machines per execution")
    servers = list((await db.execute(select(Server).where(Server.id.in_(wanted)).order_by(Server.name))).scalars())
    if len(servers) != len(wanted):
        raise HTTPException(status_code=422, detail="Unknown machine")
    return servers, group_names


_RUSTDESK_ID_RE = re.compile(r"RUSTDESK_ID=(\d{6,15})")


def system_script_hook(script: HostScript, values: dict | None):
    """What a system script records on a machine once it succeeded there:
    RustDesk install/password change -> the new permanent password and the
    RustDesk ID, on the machine's row. Never before success, so a failed
    change can't leave a password on file that the machine doesn't have."""
    if not (script.system_key or "").startswith(("rustdesk_install:", "remote_access_install:", "rustdesk_password:")):
        return None
    password = (values or {}).get("RUSTDESK_PASSWORD")
    if not password or (values or {}).get("COMPONENTES") == "somente_tailscale":
        return None

    async def record(server_id: uuid.UUID, outcome: dict) -> None:
        from app.db.base import AsyncSessionLocal

        match = _RUSTDESK_ID_RE.search(outcome.get("stdout") or "")
        async with AsyncSessionLocal() as db:
            server = await db.get(Server, server_id)
            if server is None:
                return
            server.rustdesk_password_ref = await vault_store(
                machine_secret_name(server, "RUSTDESK"), password,
                f"Senha permanente do RustDesk em {server.name} ({server.darckware_client_name or 'sem cliente'})",
            )
            server.rustdesk_password_encrypted = None
            if match:
                server.rustdesk_id = match.group(1)
            db.add(AuditEvent(entity_type="server", entity_id=server_id, event_type="rustdesk_password_recorded",
                              actor="forgehub", payload={"script": script.system_key, "rustdesk_id": server.rustdesk_id}))
            await db.commit()

    return record


async def prepare_script_run(script: HostScript, values: dict | None) -> tuple[str, str, list[str]]:
    """(rendered script, shell, secrets to mask) -- 422 on bad parameters. A
    blank `vault_secret` parameter is read from ForgeVault here, so the value
    lives only in the vault and in this one rendered command (masked)."""
    if script.archived:
        raise HTTPException(status_code=409, detail="This script is archived")
    values = dict(values or {})
    revealed: dict[str, str] = {}
    for p in script.parameters:
        if not p.get("vault_secret") or str(values.get(p["name"]) or "").strip() or p.get("default"):
            continue
        name = p["vault_secret"]
        if name not in revealed:
            revealed[name] = await vault_reveal_name(name)
        value = revealed[name]
        if field := p.get("vault_field"):
            try:
                value = json.loads(value)[field]
            except (ValueError, TypeError, KeyError) as exc:
                raise HTTPException(status_code=503, detail=f"ForgeVault: {name} has no field '{field}'") from exc
        values[p["name"]] = str(value)
    try:
        resolved, secrets = resolve_values(script.parameters, values)
    except ScriptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return render_script(script.platform, script.content, resolved), shell_for(script.platform), secrets


def darckware_item_of(kind: str | None, item_id: str | None) -> tuple[str, str] | None:
    """The client ticket/demand an execution serves: both or neither."""
    if bool(kind) != bool(item_id):
        raise HTTPException(status_code=422, detail="Inform both the Darckware item kind and its id")
    return (kind, item_id.strip()) if kind and item_id else None


def login_executor(shell: str, command: str, timeout: int, user: str, password: str):
    """Runs on each machine with ForgeHub's own login when it works there (the
    SSH probe said "active"), and with the login typed for this run on a
    machine ForgeHub has no access to yet (Marcelo, 2026-10-19: "caso não tenha
    login, precisa ser informado"). The typed password lives only in this
    closure -- never stored, masked in the output."""
    from app.api.routes.server import _ssh_probe_cache

    async def run(server: Server) -> dict:
        statuses = _ssh_probe_cache.get("statuses") or {}
        if server.remote_user and statuses.get(str(server.id)) == "active":
            return await host_exec_runner.call_bridge_exec(server, shell, command, timeout)
        return await host_exec_runner.call_bridge_exec_as(
            host=server.ip_address, user=user, port=server.ssh_port or 22, key_path=None, password=password,
            shell=shell, script=command, timeout_seconds=timeout,
        )

    return run


@router.post("", response_model=HostExecutionDetail, status_code=status.HTTP_201_CREATED)
async def create_execution(
    payload: HostExecutionCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    servers, group_names = await resolve_targets(db, payload.server_ids, payload.group_ids)
    if not servers:
        raise HTTPException(status_code=422, detail="Pick at least one machine or a group with machines")
    script = None
    secrets: list[str] = []
    if payload.script_id:
        script = await db.get(HostScript, payload.script_id)
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")
        command, shell, secrets = await prepare_script_run(script, payload.parameter_values)
        timeout = payload.timeout_seconds if "timeout_seconds" in payload.model_fields_set else script.timeout_seconds
    else:
        if not payload.command or not payload.shell:
            raise HTTPException(status_code=422, detail="Pick a script or write a command")
        command, shell, timeout = payload.command, payload.shell, payload.timeout_seconds

    item = darckware_item_of(payload.darckware_item_kind, payload.darckware_item_id)
    login = None
    if payload.login_user or payload.login_password:
        if not (payload.login_user and payload.login_password):
            raise HTTPException(status_code=422, detail="Inform both the login and the password")
        login = (payload.login_user.strip(), payload.login_password)

    loose = len(payload.server_ids)
    parts = [*group_names]
    if loose:
        parts.append(servers[0].name if len(servers) == 1 else f"{loose} machine(s)")
    execution = await launch_execution(
        db,
        servers=servers,
        command=command,
        shell=shell,
        timeout_seconds=timeout,
        actor=admin.username,
        target_summary=" + ".join(parts),
        secrets=[*secrets, payload.login_password] if login else secrets,
        script=script,
        values_for_hook=payload.parameter_values,
        executor=login_executor(shell, command, timeout, login[0], login[1]) if login else None,
        login_given=bool(login),
        reason=(payload.reason or "").strip() or None,
        darckware_item=item,
    )
    if login:
        db.add(AuditEvent(entity_type="host_execution", entity_id=execution.id, event_type="typed_login_used",
                          actor=admin.username, payload={"login": login[0]}))
        await db.commit()
    return await _detail(db, execution)


# --- Agents (MCP) -----------------------------------------------------------
# 2026-10-19 (Marcelo approved): agents maintain machines through ForgeHub with
# their own agt_ credential, so every run is recorded as theirs -- one machine
# account (`darckware`), who did what kept here. Deny by default: the agent
# needs an active AuthorityDelegation for AGENT_ACTION, and the script's risk
# must fit the delegation's max_risk. Library scripts only, machines with
# ForgeHub's own login only (no typed passwords), and always a reason.
AGENT_ACTION = "remote_access.execute"
_RISK_FOR_DELEGATION = {"read": "low", "change": "medium", "destructive": "high"}


async def _agent_readiness(db: AsyncSession) -> dict[uuid.UUID, tuple[bool, str]]:
    from app.api.routes.server import get_readiness

    result = await get_readiness(refresh=False, db=db, _user=None)
    return {e.server_id: (e.readiness == "ready", e.status) for e in result.entries}


@router.get("/agent/machines", response_model=list[AgentMachineOut])
async def agent_list_machines(
    db: AsyncSession = Depends(get_db), principal: ActorPrincipal = Depends(get_actor_principal)
):
    """The machines an agent may maintain, with whether a script can run now."""
    await authorize_action(db, principal, AGENT_ACTION)
    readiness = await _agent_readiness(db)
    servers = (await db.execute(select(Server).where(Server.access_enabled.is_(True)).order_by(Server.name))).scalars()
    return [
        AgentMachineOut(
            id=s.id, name=s.name, kind=s.kind, os_family=s.os_family, darckware_client_name=s.darckware_client_name,
            location=s.location, runnable=readiness.get(s.id, (False, "unknown"))[0],
            status=readiness.get(s.id, (False, "unknown"))[1],
        )
        for s in servers
    ]


@router.get("/agent/scripts", response_model=list[AgentScriptOut])
async def agent_list_scripts(
    db: AsyncSession = Depends(get_db), principal: ActorPrincipal = Depends(get_actor_principal)
):
    await authorize_action(db, principal, AGENT_ACTION)
    from app.db.models.host_script import HostScriptCategory

    labels = dict((await db.execute(select(HostScriptCategory.id, HostScriptCategory.label))).all())
    scripts = (await db.execute(select(HostScript).where(HostScript.archived.is_(False)).order_by(HostScript.name))).scalars()
    return [
        AgentScriptOut(id=s.id, name=s.name, category=labels.get(s.category_id), platform=s.platform, risk=s.risk,
                       description=s.description,
                       # Defaults stay server-side: they can be infrastructure values.
                       parameters=[{k: v for k, v in p.items() if k != "default"} | {"has_default": bool(p.get("default"))}
                                   for p in s.parameters])
        for s in scripts
    ]


@router.post("/agent", response_model=HostExecutionDetail, status_code=status.HTTP_201_CREATED)
async def agent_create_execution(
    payload: AgentExecutionCreate,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    script = await db.get(HostScript, payload.script_id)
    if not script or script.archived:
        raise HTTPException(status_code=404, detail="Script not found")
    await authorize_action(db, principal, AGENT_ACTION, action_risk=_RISK_FOR_DELEGATION.get(script.risk, "high"))
    servers, _ = await resolve_targets(db, payload.server_ids, [])
    readiness = await _agent_readiness(db)
    blocked = [s.name for s in servers if not readiness.get(s.id, (False, ""))[0]]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail=f"ForgeHub has no working login on: {', '.join(blocked)} (a person must configure access first)",
        )
    item = darckware_item_of(payload.darckware_item_kind, payload.darckware_item_id)
    command, shell, secrets = await prepare_script_run(script, payload.parameter_values)
    agent = await db.get(Agent, principal.principal_id) if principal.principal_type == "agent" else None
    execution = await launch_execution(
        db,
        servers=servers,
        command=command,
        shell=shell,
        timeout_seconds=script.timeout_seconds,
        actor=principal.display_name,
        target_summary=servers[0].name if len(servers) == 1 else f"{len(servers)} machine(s)",
        secrets=secrets,
        trigger="agent" if agent else "manual",
        agent_id=agent.id if agent else None,
        script=script,
        values_for_hook=payload.parameter_values,
        reason=payload.reason.strip(),
        darckware_item=item,
    )
    return await _detail(db, execution)


@router.get("/agent/{execution_id}", response_model=HostExecutionDetail)
async def agent_get_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    principal: ActorPrincipal = Depends(get_actor_principal),
):
    """An agent reads back only the runs it asked for."""
    await authorize_action(db, principal, AGENT_ACTION)
    execution = await db.get(HostExecution, execution_id)
    if not execution or (principal.principal_type == "agent" and execution.agent_id != principal.principal_id):
        raise HTTPException(status_code=404, detail="Execution not found")
    return await _detail(db, execution)


@router.get("", response_model=list[HostExecutionSummary])
async def list_executions(
    limit: int = Query(default=30, ge=1, le=200),
    server_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    requested_by: str | None = None,
    trigger: str | None = Query(default=None, pattern="^(manual|schedule|agent)$"),
    script_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Execution log. Filters: by machine, by agent (decision 7 -- what each
    agent ran, where, with what result), by person, by origin, by script."""
    await host_exec_runner.recover_interrupted_executions()
    query = select(HostExecution).order_by(HostExecution.started_at.desc()).limit(limit)
    if server_id is not None:
        query = query.where(
            HostExecution.id.in_(
                select(HostExecutionResult.execution_id).where(HostExecutionResult.server_id == server_id)
            )
        )
    if agent_id is not None:
        query = query.where(HostExecution.agent_id == agent_id)
    if requested_by:
        query = query.where(HostExecution.requested_by == requested_by)
    if trigger:
        query = query.where(HostExecution.trigger == trigger)
    if script_id is not None:
        query = query.where(HostExecution.script_id == script_id)
    executions = list((await db.execute(query)).scalars())
    return await _summaries(db, executions)


@router.get("/{execution_id}", response_model=HostExecutionDetail)
async def get_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    execution = await db.get(HostExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return await _detail(db, execution)


@router.post("/{execution_id}:follow-up", response_model=HostExecutionDetail, status_code=status.HTTP_201_CREATED)
async def follow_up_execution(
    execution_id: uuid.UUID,
    payload: HostExecutionFollowUp,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    parent = await db.get(HostExecution, execution_id)
    if not parent:
        raise HTTPException(status_code=404, detail="Execution not found")
    failed_ids = set(
        (
            await db.execute(
                select(HostExecutionResult.server_id).where(
                    HostExecutionResult.execution_id == execution_id,
                    HostExecutionResult.status == "failed",
                    HostExecutionResult.server_id.is_not(None),
                )
            )
        ).scalars()
    )
    if not failed_ids:
        raise HTTPException(status_code=409, detail="No machine failed in this execution")
    servers = list((await db.execute(select(Server).where(Server.id.in_(failed_ids)).order_by(Server.name))).scalars())
    script = None
    secrets: list[str] = []
    if payload.script_id:
        script = await db.get(HostScript, payload.script_id)
        if not script:
            raise HTTPException(status_code=404, detail="Script not found")
        command, shell, secrets = await prepare_script_run(script, payload.parameter_values)
        timeout = payload.timeout_seconds if "timeout_seconds" in payload.model_fields_set else script.timeout_seconds
    else:
        if not payload.command or not payload.shell:
            raise HTTPException(status_code=422, detail="Pick a script or write a command")
        command, shell, timeout = payload.command, payload.shell, payload.timeout_seconds
    execution = await launch_execution(
        db,
        servers=servers,
        command=command,
        shell=shell,
        timeout_seconds=timeout,
        actor=admin.username,
        target_summary=f"{len(servers)} failed machine(s) of {parent.target_summary or 'previous run'}",
        parent_execution_id=parent.id,
        secrets=secrets,
        script=script,
        values_for_hook=payload.parameter_values,
    )
    return await _detail(db, execution)


@router.post("/{execution_id}:cancel", response_model=HostExecutionDetail)
async def cancel_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Machines that haven't started are skipped; one already running is left
    to finish (or time out) -- killing a half-applied change midway is worse
    than letting it end and reporting what it did."""
    execution = await db.get(HostExecution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    if execution.status != "running":
        raise HTTPException(status_code=409, detail="Execution is not running")
    execution.status = "cancelled"
    now = datetime.now(timezone.utc)
    pending = await db.execute(
        select(HostExecutionResult).where(
            HostExecutionResult.execution_id == execution_id, HostExecutionResult.status == "pending"
        )
    )
    for result in pending.scalars():
        result.status, result.skip_reason, result.finished_at = "skipped", "Cancelled before it started", now
    db.add(
        AuditEvent(
            entity_type="host_execution", entity_id=execution.id, event_type="cancelled",
            actor=admin.username, payload=None,
        )
    )
    await db.commit()
    await db.refresh(execution)
    return await _detail(db, execution)

