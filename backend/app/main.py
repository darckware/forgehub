"""FastAPI application entrypoint.

Domain agents: add your router with `app.include_router(<domain>.router)`
in the marked block below. Each app/api/routes/<domain>.py module must
export a module-level `router = APIRouter(prefix="/api/v1/<resource>",
tags=[...])` — main.py never adds prefixes itself, the router owns its
full path.
"""
import asyncio
import contextlib
import logging
import hashlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.security import decode_access_token

from app.api.routes import (
    agent,
    agent_activity,
    agent_report,
    ai_draft,
    artifact,
    audit,
    auth,
    backlog,
    channel,
    chat,
    client,
    cron_scripts,
    database,
    deploy,
    demand,
    execution,
    docs,
    factory,
    forgerouter,
    foundation,
    foundation_docs,
    foundation_script,
    governance,
    governed_approval,
    hindsight,
    mcp_catalog,
    news,
    notifications,
    orchestration,
    pipeline,
    progress,
    prompt_commands,
    prompt_techniques,
    product,
    profiles,
    project,
    remote_access,
    server,
    system_control,
    system_scope,
    systemstats,
    task,
    terminal,
    tool,
    toolversions,
    users,
    vault,
    vpn,
    workspace_browser,
    workstation,
)


@contextlib.asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Initialize application state and own every background worker.

    FastAPI deprecated ``on_event`` in favor of lifespan handlers. Keeping
    startup and shutdown in one context also guarantees that every worker
    started here is cancelled when the application exits.
    """
    await _bootstrap_admin()
    await _start_background_tasks()
    try:
        yield
    finally:
        await _stop_background_tasks()


app = FastAPI(title="ForgeHub (ForgeHub) API", version="0.1.0", lifespan=_lifespan)

# Routes not covered by their own Depends(get_current_user)/get_current_admin
# -- just the login endpoint itself, which is how a client gets a token in
# the first place.
# /audit/run-internal self-guards with the shared bridge token (see audit.py).
_PUBLIC_API_PATHS = {
    "/api/v1/auth/token",
    "/api/v1/audit/run-internal",
    "/api/v1/demands/submit",
    # Nexo Remote Agent ingestion -- authenticated by its own X-Device-Token
    # header (hashed and matched against Workstation.device_token_hash, see
    # agent_report.py), never a User/Agent JWT/agt_ principal. Same "this
    # route does its own auth" trust boundary as /demands/submit above.
    "/api/v1/agent-reports",
    # An agent's own cron/loop pulling its pending mail -- see
    # demand.py's list_pending_for_agent docstring.
    "/api/v1/demands/pending",
    # The read-only counterpart: an agent listing its own messages by status
    # without consuming them (/pending is a queue) -- see list_for_agent.
    "/api/v1/demands/for-agent",
    # Any Hermes agent logging a task directly (project_id + planning item
    # auto-created) -- see task.py's submit_task docstring.
    "/api/v1/tasks/submit",
}


class RequireAuthMiddleware(BaseHTTPMiddleware):
    """Almost none of the domain routers were wired up with their own auth
    dependency (only users.py/auth.py were) -- this was fine while the app
    was only ever reached from localhost, but terminal.py's /ws is a real
    shell and /upload-to-dir writes arbitrary files, so it can't stay open
    once the Dashboard's remote-access card can tunnel this app to a public
    URL. Requiring a valid bearer token here for every /api/v1/* route
    (except login) closes that gap in one place instead of touching every
    router. WebSocket upgrades bypass HTTP middleware in Starlette entirely,
    so /api/v1/terminal/ws validates its own `token` query param instead."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/v1/") or path in _PUBLIC_API_PATHS:
            return await call_next(request)
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None
        agent_command_path = path.startswith((
            "/api/v1/governed/", "/api/v1/executions/", "/api/v1/execution-waves/",
            "/api/v1/work-packages/", "/api/v1/execution-runners", "/api/v1/pipeline-stages/",
            "/api/v1/workspace-browser/", "/api/v1/products",
            # 2026-08-05, see docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md:
            # /governance/ lets a delegated agent-orchestrator (e.g. Athos,
            # once granted an AuthorityDelegation for
            # "governance.approval.decide") decide an Approval with its own
            # agt_ credential, same as a human would via JWT; /channels/
            # lets an agent call POST /channels/{id}/tasks/propose with its
            # own credential instead of only the shared bridge token.
            "/api/v1/governance/", "/api/v1/channels/",
        )) or (path.startswith("/api/v1/projects/") and ("/progress" in path or "/execution-waves" in path))
        factory_read_path = request.method == "GET" and path.startswith((
            "/api/v1/projects",
            "/api/v1/tasks",
            "/api/v1/planning-items",
            "/api/v1/project-scopes/",
            "/api/v1/blueprint-revisions/",
        ))
        factory_task_command = request.method == "PATCH" and path.startswith("/api/v1/tasks/")
        agent_command_path = agent_command_path or factory_read_path or factory_task_command
        if token and token.startswith("agt_") and agent_command_path:
            from sqlalchemy import select
            from app.db.base import AsyncSessionLocal
            from app.db.models.agent import AgentServiceCredential
            async with AsyncSessionLocal() as db:
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                credential = (await db.execute(select(AgentServiceCredential.id).where(
                    AgentServiceCredential.token_hash == token_hash,
                    AgentServiceCredential.revoked_at.is_(None),
                ))).scalar_one_or_none()
            if credential is not None:
                return await call_next(request)
        # Same shared-bridge-token trust boundary as /api/v1/demands/submit
        # (see that route's own docstring) -- can't just add these paths to
        # _PUBLIC_API_PATHS since that set only does exact string matches
        # and these have dynamic {channel_id} segments. Two things a
        # bridge-token caller (the forgehub-messages MCP's
        # list_channel_members/propose_channel_task tools) may do: read
        # anything under /channels/ (listing channels/members is harmless,
        # same trust level as /demands/pending's read), or propose a task.
        # Writes beyond proposing a task still need a real JWT or agt_
        # credential -- this never opens the whole /channels/ prefix to
        # unauthenticated writes.
        is_channels_path = path == "/api/v1/channels" or path.startswith("/api/v1/channels/")
        channels_bridge_path = is_channels_path and (
            request.method == "GET" or path.endswith("/tasks/propose")
        )
        if channels_bridge_path:
            bridge_token = request.headers.get("x-bridge-token")
            if bridge_token and settings.CHAT_BRIDGE_TOKEN and bridge_token == settings.CHAT_BRIDGE_TOKEN:
                return await call_next(request)
        # Same trust boundary as channels_bridge_path above -- read-only,
        # non-secret roster/skills data (2026-08-06, backs the
        # forgehub-messages MCP's list_agent_skills tool: an
        # orchestrator-agent checking a colleague's skills before proposing
        # a task). Scoped narrowly to GET /agents (roster, for slug
        # resolution) and any GET path ending in /skills under /agents/
        # (covers both /agents/{id}/skills and the /agents/skills catalog)
        # -- never the whole /agents/ prefix, so routes like GET
        # /agents/{id} (decrypts the ForgeRouter key for admins) stay
        # behind their own JWT-based dependency untouched by this bypass.
        is_agents_path = path == "/api/v1/agents" or path.startswith("/api/v1/agents/")
        agents_bridge_path = is_agents_path and (
            (request.method == "GET" and (path == "/api/v1/agents" or path.endswith("/skills") or "/credentials" in path))
            or (request.method in ("POST", "DELETE") and "/credentials" in path)
            or (request.method == "POST" and path.endswith("/skills"))
            or (request.method == "DELETE" and "/skills/" in path)
        )
        if agents_bridge_path:
            bridge_token = request.headers.get("x-bridge-token")
            if bridge_token and settings.CHAT_BRIDGE_TOKEN and bridge_token == settings.CHAT_BRIDGE_TOKEN:
                return await call_next(request)
        # Same trust boundary again (2026-08-15) -- dynamic demand actions
        demands_bridge_action = path.startswith("/api/v1/demands/") and (
            path.endswith("/incubation:receive")
            or path.endswith("/incubation:drop")
            or path.endswith("/reprocess")
            or path.endswith("/agent")
            or path.endswith("/agent-archive")
        )
        if demands_bridge_action:
            bridge_token = request.headers.get("x-bridge-token")
            if bridge_token and settings.CHAT_BRIDGE_TOKEN and bridge_token == settings.CHAT_BRIDGE_TOKEN:
                return await call_next(request)

        # System operations via bridge token (system-control, backups, audit, deploy, database query)
        is_system_bridge_path = (
            path.startswith("/api/v1/system-control/")
            or path.startswith("/api/v1/deploy/")
            or path.startswith("/api/v1/backups")
            or path.startswith("/api/v1/audit/")
            or path == "/api/v1/servers"
            or path == "/api/v1/database/query"
        )
        if is_system_bridge_path:
            bridge_token = request.headers.get("x-bridge-token")
            if bridge_token and settings.CHAT_BRIDGE_TOKEN and bridge_token == settings.CHAT_BRIDGE_TOKEN:
                return await call_next(request)
        if not token or decode_access_token(token) is None:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return await call_next(request)


# Added before CORSMiddleware so CORS ends up outermost (Starlette wraps
# middleware in reverse registration order) -- otherwise a 401 from this
# middleware would reach the browser without CORS headers and fail as an
# opaque network error instead of a readable 401.
app.add_middleware(RequireAuthMiddleware)

# CORS: allow all origins/methods/headers for local dev. Tighten before
# any non-local deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)

# ---------------------------------------------------------------------------
# DOMAIN ROUTERS -- added by wiring step
# ---------------------------------------------------------------------------
app.include_router(product.router)
app.include_router(project.router)
app.include_router(pipeline.router)
app.include_router(progress.router)
app.include_router(execution.router)
app.include_router(factory.router)
app.include_router(backlog.router)
app.include_router(client.router)
app.include_router(workstation.router)
app.include_router(agent_report.router)
app.include_router(task.router)
app.include_router(task.responsibility_router)
app.include_router(agent.router)
app.include_router(agent_activity.router)
app.include_router(ai_draft.router)
app.include_router(mcp_catalog.router)
app.include_router(tool.router)
app.include_router(artifact.router)
app.include_router(audit.router)
app.include_router(governance.router)
app.include_router(governed_approval.router)
app.include_router(hindsight.router)
app.include_router(news.router)
app.include_router(foundation.router)
app.include_router(foundation_docs.router)
app.include_router(foundation_script.router)
app.include_router(chat.router)
app.include_router(channel.router)
app.include_router(terminal.router)
app.include_router(toolversions.router)
app.include_router(systemstats.router)
app.include_router(workspace_browser.router)
app.include_router(vault.router)
app.include_router(docs.router)
app.include_router(demand.router)
app.include_router(cron_scripts.router)
app.include_router(notifications.router)
app.include_router(prompt_commands.router)
app.include_router(prompt_techniques.router)
app.include_router(deploy.router)
app.include_router(database.router)
app.include_router(users.router)
app.include_router(profiles.router)
app.include_router(server.router)
app.include_router(remote_access.router)
app.include_router(system_control.router)
app.include_router(vpn.router)
app.include_router(forgerouter.router)
app.include_router(orchestration.router)
app.include_router(system_scope.router)
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# How often the background poll re-checks tool versions when sync is
# enabled. Matches Antigravity's own auto-updater cadence (it already
# re-checks itself roughly every 15 min regardless of this loop).
TOOL_VERSION_POLL_INTERVAL_SECONDS = 900

# Recovery interval for due demands. New due Messages wake the worker as soon
# as their transaction commits; this timeout catches direct database writes,
# a signal lost to restart, and future scheduled_at timestamps.
SCHEDULED_DISPATCH_POLL_INTERVAL_SECONDS = 30

# How often matured incubations are handed to their owners. The deadline
# being enforced is measured in days (INCUBATION_DEFAULT_MATURATION_DAYS),
# so a 5-minute pass is already far finer than the thing it watches.
INCUBATION_MATURATION_POLL_INTERVAL_SECONDS = 300

# How often stalled dispatches are checked against their deadline. Minutes,
# not seconds: the deadline itself is DISPATCH_TIMEOUT_MINUTES (45), so a
# 60s pass is already far finer than what it watches.
DISPATCH_TIMEOUT_POLL_INTERVAL_SECONDS = 60

# How often outcomes that still owe their channel a delivery are retried.
# The happy path delivers inline when the dispatch finishes; this only
# catches what that missed -- an app restart mid-delivery, Telegram down.
FEEDBACK_POLL_INTERVAL_SECONDS = 120

# Com que frequência turnos que passaram do prazo são fechados. O caso real é
# um restart do host-bridge: ele guarda os subprocessos em memória, então
# reiniciar perde o processo enquanto a linha ainda diz "rodando" -- e cada
# reconecte ficaria esperando um stream sem produtor.
ACTIVE_TURN_SWEEP_INTERVAL_SECONDS = 120

# How often in-flight dispatches are polled to completion. Same interval as
# the scheduled-send loop above and for the same reason: this is what turns
# a finished agent run into a reply item in the Inbox, so latency here is
# latency in an agent-to-agent conversation.
DISPATCH_COMPLETION_POLL_INTERVAL_SECONDS = 30

# How often the task-health pass scans for overdue/stalled tasks (see
# core/task_health.py). Much longer than the dispatch poll -- a missed
# deadline or a stalled execution isn't as time-sensitive as a queued
# message, and this pass walks every non-terminal task in the system.
TASK_FAILURE_POLL_INTERVAL_SECONDS = 900

# How often reported-but-unverified TaskExecutions get their evidence_ref
# checked against reality (see core/task_evidence.py). Short-ish: this is
# the gate that stops a narrated-but-not-executed claim from sitting as
# "reported" indefinitely, and it's a cheap query (filesystem/git checks
# only run for the handful of rows actually in that state).
EVIDENCE_VERIFICATION_POLL_INTERVAL_SECONDS = 120

# How often in-flight background app-test runs (mode="background") are
# polled to completion -- same role as DISPATCH_COMPLETION_POLL_INTERVAL_
# SECONDS above, for the "Background tests" tab / /testar's results.
BACKGROUND_TEST_COMPLETION_POLL_INTERVAL_SECONDS = 15

# How often terminal mail is checked against its 60-day retention window
# (DEMAND_RETENTION_DAYS). A day-granularity policy doesn't need a fast
# pass -- 6h matches the ecosystem's existing cadence for this kind of
# periodic, non-urgent maintenance sweep (e.g. the Auditor's own checks).
DEMAND_RETENTION_POLL_INTERVAL_SECONDS = 21600

# How often workstations that stopped reporting are detected and marked
# as unreachable. 5 minutes is sufficient for the 15-minute staleness
# threshold.
WORKSTATION_STALENESS_POLL_INTERVAL_SECONDS = 300

_background_tasks: list[asyncio.Task[None]] = []


async def _tool_version_poll_loop() -> None:
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                setting = await toolversions.get_or_create_sync_setting(db)
                if setting.enabled:
                    # POLL_TOOLS excludes antigravity -- its "check" is a
                    # real `agy update`, and it already self-updates on its
                    # own cadence independent of this loop.
                    await toolversions.refresh_all_tool_versions(db, tools=toolversions.POLL_TOOLS)
        except Exception:
            logger.exception("Tool version poll failed")
        await asyncio.sleep(TOOL_VERSION_POLL_INTERVAL_SECONDS)


async def _scheduled_dispatch_poll_loop() -> None:
    from app.api.routes.demand import run_scheduled_dispatch_pass
    from app.core.dispatch_signal import wait_for_scheduled_dispatch
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_scheduled_dispatch_pass(db)
        except Exception:
            logger.exception("Scheduled dispatch poll failed")
        # Normal path: a committed message wakes this immediately. Timeout is
        # deliberately retained as a database-backed recovery sweep.
        await wait_for_scheduled_dispatch(SCHEDULED_DISPATCH_POLL_INTERVAL_SECONDS)


async def _incubation_maturation_poll_loop() -> None:
    """Hands matured incubations to their owners (2026-08-13).

    Its own task rather than a branch inside the dispatch loop above, for
    the same reason _dispatch_completion_poll_loop is separate: the two fail
    independently. This one only touches ForgeHub's own database, so a
    host-bridge outage that stalls dispatching must not also stop decisions
    from being handed over.

    Minutes, not seconds: the deadline it enforces is measured in days, so
    polling faster would only add load without making anything more timely.
    """
    from app.api.routes.demand import run_incubation_maturation_pass
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_incubation_maturation_pass(db)
        except Exception:
            logger.exception("Incubation maturation poll failed")
        await asyncio.sleep(INCUBATION_MATURATION_POLL_INTERVAL_SECONDS)


async def _dispatch_completion_poll_loop() -> None:
    """Finishes dispatches whose agent run has ended -- creating the reply
    item -- without needing the message open in a reading pane. Kept as its
    own task rather than a second call inside the loop above: the two passes
    fail independently (one talks to agent CLIs through the bridge, the
    other only reads run status), and a slow dispatch shouldn't delay
    delivering a reply that's already sitting there finished."""
    from app.api.routes.demand import run_dispatch_completion_pass
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_dispatch_completion_pass(db)
        except Exception:
            logger.exception("Dispatch completion poll failed")
        await asyncio.sleep(DISPATCH_COMPLETION_POLL_INTERVAL_SECONDS)


async def _background_test_completion_poll_loop() -> None:
    """Finishes background app-test runs whose isolated CDP browser has
    ended, mirroring _dispatch_completion_poll_loop above for the same
    reason: the result must be ready in the history list whether or not
    anyone has the tab open."""
    from app.api.routes.workspace_browser import run_background_test_completion_pass
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_background_test_completion_pass(db)
        except Exception:
            logger.exception("Background test completion poll failed")
        await asyncio.sleep(BACKGROUND_TEST_COMPLETION_POLL_INTERVAL_SECONDS)


async def _task_failure_poll_loop() -> None:
    from app.core.task_health import run_task_failure_pass
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_task_failure_pass(db)
        except Exception:
            logger.exception("Task failure poll failed")
        await asyncio.sleep(TASK_FAILURE_POLL_INTERVAL_SECONDS)


async def _evidence_verification_poll_loop() -> None:
    from app.core.task_evidence import run_evidence_verification_pass
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_evidence_verification_pass(db)
        except Exception:
            logger.exception("Evidence verification poll failed")
        await asyncio.sleep(EVIDENCE_VERIFICATION_POLL_INTERVAL_SECONDS)


async def _bootstrap_admin() -> None:
    """Ensure default profiles exist and admin user is seeded."""
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.db.base import AsyncSessionLocal
    from app.db.models.profile import MODULES, Profile, ProfilePermission
    from app.db.models.user import User

    async with AsyncSessionLocal() as db:
        try:
            # -- Default profiles ------------------------------------------
            default_profiles = [
                {
                    "name": "Administrador",
                    "description": "Acesso total a todos os módulos",
                    "perms": {"can_view": True, "can_query": True, "can_write": True, "can_delete": True},
                },
                {
                    "name": "Padrão",
                    "description": "Visualização e consulta sem alterações",
                    "perms": {"can_view": True, "can_query": True, "can_write": False, "can_delete": False},
                },
            ]
            admin_profile_id = None
            for pd in default_profiles:
                res = await db.execute(select(Profile).where(Profile.name == pd["name"]))
                profile = res.scalar_one_or_none()
                if profile is None:
                    profile = Profile(name=pd["name"], description=pd["description"])
                    db.add(profile)
                    await db.flush()
                    for m in MODULES:
                        db.add(ProfilePermission(profile_id=profile.id, module=m, **pd["perms"]))
                    logger.info("Bootstrap profile created: %s", pd["name"])
                if pd["name"] == "Administrador":
                    admin_profile_id = profile.id

            # -- Admin user ------------------------------------------------
            res = await db.execute(select(User).where(User.username == settings.DEV_USER_USERNAME))
            if res.scalar_one_or_none() is None:
                db.add(User(
                    username=settings.DEV_USER_USERNAME,
                    hashed_password=hash_password(settings.DEV_USER_PASSWORD),
                    full_name="Admin",
                    is_admin=True,
                    is_active=True,
                    profile_id=admin_profile_id,
                ))
                logger.info("Bootstrap admin created: %s", settings.DEV_USER_USERNAME)

            await db.commit()
        except Exception:
            logger.exception("Bootstrap failed (tables may not exist yet)")


async def _dispatch_timeout_poll_loop() -> None:
    """Fails dispatches that never came back (2026-08-13).

    Own task, like the other passes: this one only touches our database, so
    it must keep running when the host-bridge (which the dispatch loops
    depend on) is the very thing that is down -- that outage is precisely
    when runs get stranded.
    """
    from app.api.routes.demand import run_dispatch_timeout_pass
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_dispatch_timeout_pass(db)
        except Exception:
            logger.exception("Dispatch timeout poll failed")
        await asyncio.sleep(DISPATCH_TIMEOUT_POLL_INTERVAL_SECONDS)


async def _feedback_poll_loop() -> None:
    """Delivers outcomes whose feedback never went out (2026-08-13).

    The delivery itself happens inline when a dispatch reaches a terminal
    state; this is the net under it. Driven by state (`feedback_sent_at IS
    NULL`) rather than by retrying a failed call in memory, so a delivery
    lost to a restart is still found afterwards.
    """
    from app.core.feedback import run_feedback_pass
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_feedback_pass(db)
        except Exception:
            logger.exception("Feedback poll failed")
        await asyncio.sleep(FEEDBACK_POLL_INTERVAL_SECONDS)


async def _demand_retention_poll_loop() -> None:
    """Auto-archives terminal mail past its 60-day retention window
    (2026-08-15). Own task, same reasoning as the other passes: it must
    keep running independent of whatever else is happening to the
    dispatch/host-bridge machinery, since it only ever touches our own
    database.
    """
    from app.api.routes.demand import run_demand_retention_sweep
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_demand_retention_sweep(db)
        except Exception:
            logger.exception("Demand retention sweep failed")
        await asyncio.sleep(DEMAND_RETENTION_POLL_INTERVAL_SECONDS)


async def _active_turn_sweep_loop() -> None:
    """Fecha turnos que passaram do prazo sem reportar (2026-08-13)."""
    from app.core.active_turns import sweep_stale
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await sweep_stale(db)
        except Exception:
            logger.exception("Active turn sweep failed")
        await asyncio.sleep(ACTIVE_TURN_SWEEP_INTERVAL_SECONDS)


async def _workstation_staleness_poll_loop() -> None:
    """Detects workstations that stopped reporting and raises agent_unreachable
    Irregularities. Own task like the other passes: this only touches our
    database and must keep running independent of other sweeps."""
    from app.core.workstation_staleness import run_workstation_staleness_sweep
    from app.db.base import AsyncSessionLocal

    while True:
        try:
            async with AsyncSessionLocal() as db:
                await run_workstation_staleness_sweep(db)
        except Exception:
            logger.exception("Workstation staleness poll failed")
        await asyncio.sleep(WORKSTATION_STALENESS_POLL_INTERVAL_SECONDS)


async def _start_background_tasks() -> None:
    """Start each independent maintenance loop exactly once."""
    global _background_tasks
    if _background_tasks:
        return
    from app.core.dispatch_signal import reset_scheduled_dispatch_signal

    reset_scheduled_dispatch_signal()
    workers = (
        ("tool-version-poll", _tool_version_poll_loop),
        ("scheduled-dispatch-poll", _scheduled_dispatch_poll_loop),
        ("dispatch-timeout-poll", _dispatch_timeout_poll_loop),
        ("active-turn-sweep", _active_turn_sweep_loop),
        ("feedback-poll", _feedback_poll_loop),
        ("incubation-maturation-poll", _incubation_maturation_poll_loop),
        ("dispatch-completion-poll", _dispatch_completion_poll_loop),
        ("background-test-completion-poll", _background_test_completion_poll_loop),
        ("task-failure-poll", _task_failure_poll_loop),
        ("evidence-verification-poll", _evidence_verification_poll_loop),
        ("demand-retention-poll", _demand_retention_poll_loop),
        ("workstation-staleness-poll", _workstation_staleness_poll_loop),
    )
    _background_tasks = [asyncio.create_task(worker(), name=name) for name, worker in workers]


async def _stop_background_tasks() -> None:
    """Cancel all workers and wait until their cleanup has completed."""
    global _background_tasks
    tasks, _background_tasks = _background_tasks, []
    for background_task in tasks:
        background_task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    from app.core.dispatch_signal import reset_scheduled_dispatch_signal

    reset_scheduled_dispatch_signal()
