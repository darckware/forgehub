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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.security import decode_access_token

from app.api.routes import (
    agent,
    artifact,
    audit,
    auth,
    backlog,
    chat,
    cron_scripts,
    database,
    deploy,
    demand,
    docs,
    forgerouter,
    foundation,
    foundation_docs,
    foundation_script,
    governance,
    hindsight,
    news,
    notifications,
    pipeline,
    prompt_commands,
    product,
    profiles,
    project,
    remote_access,
    server,
    system_control,
    systemstats,
    task,
    terminal,
    tool,
    toolversions,
    users,
    vault,
)

app = FastAPI(title="ForgeHub (ForgeHub) API", version="0.1.0")

# Routes not covered by their own Depends(get_current_user)/get_current_admin
# -- just the login endpoint itself, which is how a client gets a token in
# the first place.
# /audit/run-internal self-guards with the shared bridge token (see audit.py).
_PUBLIC_API_PATHS = {"/api/v1/auth/token", "/api/v1/audit/run-internal", "/api/v1/demands/submit"}


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
app.include_router(backlog.router)
app.include_router(task.router)
app.include_router(agent.router)
app.include_router(tool.router)
app.include_router(artifact.router)
app.include_router(audit.router)
app.include_router(governance.router)
app.include_router(hindsight.router)
app.include_router(news.router)
app.include_router(foundation.router)
app.include_router(foundation_docs.router)
app.include_router(foundation_script.router)
app.include_router(chat.router)
app.include_router(terminal.router)
app.include_router(toolversions.router)
app.include_router(systemstats.router)
app.include_router(vault.router)
app.include_router(docs.router)
app.include_router(demand.router)
app.include_router(cron_scripts.router)
app.include_router(notifications.router)
app.include_router(prompt_commands.router)
app.include_router(deploy.router)
app.include_router(database.router)
app.include_router(users.router)
app.include_router(profiles.router)
app.include_router(server.router)
app.include_router(remote_access.router)
app.include_router(system_control.router)
app.include_router(forgerouter.router)
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# How often the background poll re-checks tool versions when sync is
# enabled. Matches Antigravity's own auto-updater cadence (it already
# re-checks itself roughly every 15 min regardless of this loop).
TOOL_VERSION_POLL_INTERVAL_SECONDS = 900

_tool_version_poll_task: asyncio.Task | None = None


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


@app.on_event("startup")
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


@app.on_event("startup")
async def _start_tool_version_poll() -> None:
    global _tool_version_poll_task
    _tool_version_poll_task = asyncio.create_task(_tool_version_poll_loop())


@app.on_event("shutdown")
async def _stop_tool_version_poll() -> None:
    if _tool_version_poll_task is None:
        return
    _tool_version_poll_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _tool_version_poll_task
