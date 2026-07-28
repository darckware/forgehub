"""Authenticated proxy for the shared Workspace CDP browser.

The browser runs on the host so Athos and the human operator see and control
the same Chromium tab. ForgeHub credentials cross this boundary only during
the explicit login command and are neither stored nor returned by the bridge.

Automations (WebAutomationRoutine, structured CDP steps) and Macro
(MacroInstructionSet, free-text instructions run by seeding the Assistant
composer) both target exactly one of Product or StandaloneApp -- the latter
is a lightweight name+URL registration for pointing this pane at a site that
doesn't warrant full Product onboarding.
"""

import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.workspace_browser import (
    BackgroundTestAdHocIn,
    BackgroundTestDispatchIn,
    BackgroundTestToggle,
    MacroInstructionSetCreate,
    MacroInstructionSetOut,
    MacroInstructionSetUpdate,
    StandaloneAppCreate,
    StandaloneAppOut,
    StandaloneAppUpdate,
    WebAutomationTestRunOut,
    WorkspaceBrowserNavigate,
    WorkspaceBrowserPointer,
    WorkspaceBrowserScroll,
    WorkspaceBrowserStart,
    WorkspaceBrowserStateOut,
    WorkspaceBrowserText,
    WebAutomationRoutineCreate,
    WebAutomationRoutineOut,
    WebAutomationRoutineUpdate,
    WebAutomationRunOut,
)
from app.core.config import settings
from app.db.base import get_db
from app.db.models.product import Product
from app.db.models.web_automation import (
    MacroInstructionSet,
    StandaloneApp,
    WebAutomationRoutine,
    WebAutomationTestRun,
)

router = APIRouter(prefix="/api/v1/workspace-browser", tags=["workspace-browser"])


async def _bridge(method: str, path: str, payload: dict | None = None) -> WorkspaceBrowserStateOut:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{settings.CHAT_BRIDGE_URL}/v1/workspace-browser{path}",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Workspace browser unavailable: {exc}") from exc
    if response.status_code != 200:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Workspace browser error: {response.text[:500]}")
    return WorkspaceBrowserStateOut.model_validate(response.json())


@router.post("/start", response_model=WorkspaceBrowserStateOut)
async def start_browser(payload: WorkspaceBrowserStart) -> WorkspaceBrowserStateOut:
    return await _bridge("POST", "/start", payload.model_dump())


@router.get("/state", response_model=WorkspaceBrowserStateOut)
async def browser_state() -> WorkspaceBrowserStateOut:
    return await _bridge("GET", "/state")


@router.post("/navigate", response_model=WorkspaceBrowserStateOut)
async def navigate_browser(payload: WorkspaceBrowserNavigate) -> WorkspaceBrowserStateOut:
    return await _bridge("POST", "/navigate", payload.model_dump())


@router.post("/reload", response_model=WorkspaceBrowserStateOut)
async def reload_browser() -> WorkspaceBrowserStateOut:
    return await _bridge("POST", "/reload")


@router.post("/back", response_model=WorkspaceBrowserStateOut)
async def back_browser() -> WorkspaceBrowserStateOut:
    return await _bridge("POST", "/back")


@router.post("/pointer", response_model=WorkspaceBrowserStateOut)
async def pointer_browser(payload: WorkspaceBrowserPointer) -> WorkspaceBrowserStateOut:
    return await _bridge("POST", "/pointer", payload.model_dump())


@router.post("/text", response_model=WorkspaceBrowserStateOut)
async def text_browser(payload: WorkspaceBrowserText) -> WorkspaceBrowserStateOut:
    return await _bridge("POST", "/text", payload.model_dump())


@router.post("/scroll", response_model=WorkspaceBrowserStateOut)
async def scroll_browser(payload: WorkspaceBrowserScroll) -> WorkspaceBrowserStateOut:
    return await _bridge("POST", "/scroll", payload.model_dump())


@router.post("/login-forgehub", response_model=WorkspaceBrowserStateOut)
async def login_forgehub(payload: WorkspaceBrowserNavigate) -> WorkspaceBrowserStateOut:
    return await _bridge(
        "POST",
        "/login-forgehub",
        {
            "url": payload.url,
            "username": settings.DEV_USER_USERNAME,
            "password": settings.DEV_USER_PASSWORD,
        },
    )


@router.get("/standalone-apps", response_model=list[StandaloneAppOut])
async def list_standalone_apps(db: AsyncSession = Depends(get_db)) -> list[StandaloneApp]:
    return list((await db.execute(select(StandaloneApp).order_by(StandaloneApp.name))).scalars())


@router.post("/standalone-apps", response_model=StandaloneAppOut, status_code=201)
async def create_standalone_app(payload: StandaloneAppCreate, db: AsyncSession = Depends(get_db)) -> StandaloneApp:
    app = StandaloneApp(name=payload.name, url=payload.url)
    db.add(app)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_standalone_app_name":
            raise HTTPException(409, "A standalone app with this name already exists") from None
        raise
    await db.refresh(app)
    return app


@router.put("/standalone-apps/{app_id}", response_model=StandaloneAppOut)
async def update_standalone_app(
    app_id: uuid.UUID, payload: StandaloneAppUpdate, db: AsyncSession = Depends(get_db)
) -> StandaloneApp:
    app = await db.get(StandaloneApp, app_id)
    if not app:
        raise HTTPException(404, "Standalone app not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(app, key, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_standalone_app_name":
            raise HTTPException(409, "A standalone app with this name already exists") from None
        raise
    await db.refresh(app)
    return app


@router.delete("/standalone-apps/{app_id}", status_code=204)
async def delete_standalone_app(app_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    app = await db.get(StandaloneApp, app_id)
    if not app:
        raise HTTPException(404, "Standalone app not found")
    await db.delete(app)
    await db.commit()


def _target_filter(model, product_id: uuid.UUID | None, standalone_app_id: uuid.UUID | None):
    if (product_id is None) == (standalone_app_id is None):
        raise HTTPException(422, "Exactly one of product_id or standalone_app_id is required")
    return model.product_id == product_id if product_id else model.standalone_app_id == standalone_app_id


async def _resolve_start_url(db: AsyncSession, product_id: uuid.UUID | None, standalone_app_id: uuid.UUID | None) -> str:
    if product_id:
        product = await db.get(Product, product_id)
        # Production first, dev as the fallback: since the URL was split per
        # environment (2026-07-26) a product may have only its dev environment
        # up, and demanding the production one would leave that case with
        # nothing to open. Mirrors WebAppPane.tsx's selectProduct.
        url = product and (product.application_url or product.application_url_dev)
        if not url:
            raise HTTPException(409, "Product application URL is not configured")
        return url
    app = await db.get(StandaloneApp, standalone_app_id)
    if not app:
        raise HTTPException(404, "Standalone app not found")
    return app.url


@router.get("/routines", response_model=list[WebAutomationRoutineOut])
async def list_routines(
    product_id: uuid.UUID | None = None,
    standalone_app_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[WebAutomationRoutine]:
    return list((await db.execute(
        select(WebAutomationRoutine)
        .where(_target_filter(WebAutomationRoutine, product_id, standalone_app_id))
        .order_by(WebAutomationRoutine.name)
    )).scalars())


@router.post("/routines", response_model=WebAutomationRoutineOut, status_code=201)
async def create_routine(
    payload: WebAutomationRoutineCreate, db: AsyncSession = Depends(get_db)
) -> WebAutomationRoutine:
    await _resolve_start_url(db, payload.product_id, payload.standalone_app_id)
    routine = WebAutomationRoutine(
        product_id=payload.product_id,
        standalone_app_id=payload.standalone_app_id,
        name=payload.name,
        description=payload.description,
        steps=[step.model_dump(exclude_none=True) for step in payload.steps],
    )
    db.add(routine)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_web_automation_routine_target_name":
            raise HTTPException(409, "A routine with this name already exists for this target") from None
        raise
    await db.refresh(routine)
    return routine


@router.put("/routines/{routine_id}", response_model=WebAutomationRoutineOut)
async def update_routine(
    routine_id: uuid.UUID, payload: WebAutomationRoutineUpdate, db: AsyncSession = Depends(get_db)
) -> WebAutomationRoutine:
    routine = await db.get(WebAutomationRoutine, routine_id)
    if not routine:
        raise HTTPException(404, "Web automation routine not found")
    data = payload.model_dump(exclude_unset=True)
    if payload.steps is not None:
        data["steps"] = [step.model_dump(exclude_none=True) for step in payload.steps]
    for key, value in data.items():
        setattr(routine, key, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_web_automation_routine_target_name":
            raise HTTPException(409, "A routine with this name already exists for this target") from None
        raise
    await db.refresh(routine)
    return routine


@router.delete("/routines/{routine_id}", status_code=204)
async def delete_routine(routine_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    routine = await db.get(WebAutomationRoutine, routine_id)
    if not routine:
        raise HTTPException(404, "Web automation routine not found")
    await db.delete(routine)
    await db.commit()


@router.post("/routines/{routine_id}:run", response_model=WebAutomationRunOut)
async def run_routine(routine_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> WebAutomationRunOut:
    routine = await db.get(WebAutomationRoutine, routine_id)
    if not routine:
        raise HTTPException(404, "Web automation routine not found")
    start_url = await _resolve_start_url(db, routine.product_id, routine.standalone_app_id)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/workspace-browser/run-routine",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"start_url": start_url, "steps": routine.steps},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Workspace browser unavailable: {exc}") from exc
    if response.status_code != 200:
        raise HTTPException(502, f"Routine execution failed: {response.text[:1000]}")
    body = response.json()
    return WebAutomationRunOut(
        routine_id=routine.id,
        status=body["status"],
        steps=body["steps"],
        browser=WorkspaceBrowserStateOut.model_validate(body["browser"]),
    )


# ---------------------------------------------------------------------------
# Background app testing (WebAutomationTestRun)
#
# Two modes, chosen per dispatch, not fixed on the routine: "visible"
# delegates to run_routine above (untouched) and only records the outcome
# here for a unified history; "background" fires the host-bridge's isolated
# CDP instance fire-and-forget and is finished later by
# run_background_test_completion_pass, mirroring demand.py's
# run_dispatch_completion_pass for the same "nobody has to be watching"
# reason.
# ---------------------------------------------------------------------------


@router.put("/routines/{routine_id}/background-test", response_model=WebAutomationRoutineOut)
async def toggle_routine_background_test(
    routine_id: uuid.UUID, payload: BackgroundTestToggle, db: AsyncSession = Depends(get_db)
) -> WebAutomationRoutine:
    routine = await db.get(WebAutomationRoutine, routine_id)
    if not routine:
        raise HTTPException(404, "Web automation routine not found")
    if payload.enabled:
        # 422 without a live URL to test against -- mirrors
        # toggle_project_forgerouter's working_directory_path guard.
        await _resolve_start_url(db, routine.product_id, routine.standalone_app_id)
    routine.background_test_enabled = payload.enabled
    await db.commit()
    await db.refresh(routine)
    return routine


async def _dispatch_test_run(
    db: AsyncSession,
    *,
    routine: WebAutomationRoutine | None,
    product_id: uuid.UUID | None,
    standalone_app_id: uuid.UUID | None,
    steps: list[dict],
    mode: str,
    triggered_by: str,
) -> WebAutomationTestRun:
    start_url = await _resolve_start_url(db, product_id, standalone_app_id)
    run = WebAutomationTestRun(
        routine_id=routine.id if routine else None,
        product_id=product_id,
        standalone_app_id=standalone_app_id,
        triggered_by=triggered_by,
        mode=mode,
        status="queued",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    if mode == "visible":
        # Synchronous, same call run_routine makes -- the operator watches
        # it live in the Web App pane; this row just records the outcome
        # for the shared history once it's done.
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        await db.commit()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.CHAT_BRIDGE_URL}/v1/workspace-browser/run-routine",
                    headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                    json={"start_url": start_url, "steps": steps},
                )
            if response.status_code != 200:
                raise RuntimeError(response.text[:1000])
            body = response.json()
            run.status = "passed" if body["status"] == "passed" else "failed"
            report_lines = [f"{run.status.upper()} -- {len(body['steps'])} step(s) executed"]
            for s in body["steps"]:
                report_lines.append(f"  [{s['status']}] {s['index']}. {s['action']}: {s['outcome']}")
            run.report = "\n".join(report_lines)
        except (httpx.HTTPError, RuntimeError) as exc:
            run.status = "error"
            run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)
        return run

    # mode == "background": fire-and-forget against the isolated instance;
    # run_background_test_completion_pass finishes it later.
    bridge_run_id = str(run.id)
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/workspace-browser/test-run",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"test_run_id": bridge_run_id, "start_url": start_url, "steps": steps},
            )
        if response.status_code not in (200, 202):
            raise RuntimeError(response.text[:1000])
    except (httpx.HTTPError, RuntimeError) as exc:
        run.status = "error"
        run.error = str(exc)
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)
        return run

    run.status = "running"
    run.bridge_run_id = bridge_run_id
    run.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/routines/{routine_id}:run-background", response_model=WebAutomationTestRunOut)
async def run_routine_background_test(
    routine_id: uuid.UUID, payload: BackgroundTestDispatchIn, db: AsyncSession = Depends(get_db)
) -> WebAutomationTestRun:
    routine = await db.get(WebAutomationRoutine, routine_id)
    if not routine:
        raise HTTPException(404, "Web automation routine not found")
    return await _dispatch_test_run(
        db,
        routine=routine,
        product_id=routine.product_id,
        standalone_app_id=routine.standalone_app_id,
        steps=routine.steps,
        mode=payload.mode,
        triggered_by="slash_command",
    )


@router.post("/background-test", response_model=WebAutomationTestRunOut, status_code=201)
async def run_ad_hoc_background_test(
    payload: BackgroundTestAdHocIn, db: AsyncSession = Depends(get_db)
) -> WebAutomationTestRun:
    """No saved routine -- the MCP-tool trigger path's own inline steps.
    Always effectively `mode="background"` in practice (see the schema's
    own field comment)."""
    return await _dispatch_test_run(
        db,
        routine=None,
        product_id=payload.product_id,
        standalone_app_id=payload.standalone_app_id,
        steps=[step.model_dump(exclude_none=True) for step in payload.steps],
        mode=payload.mode,
        triggered_by="mcp_tool",
    )


@router.get("/test-runs", response_model=list[WebAutomationTestRunOut])
async def list_test_runs(
    product_id: uuid.UUID | None = None,
    standalone_app_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[WebAutomationTestRun]:
    query = select(WebAutomationTestRun).order_by(WebAutomationTestRun.created_at.desc())
    if product_id is not None:
        query = query.where(WebAutomationTestRun.product_id == product_id)
    if standalone_app_id is not None:
        query = query.where(WebAutomationTestRun.standalone_app_id == standalone_app_id)
    return list((await db.execute(query)).scalars())


@router.get("/test-runs/{test_run_id}", response_model=WebAutomationTestRunOut)
async def get_test_run(test_run_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> WebAutomationTestRun:
    run = await db.get(WebAutomationTestRun, test_run_id)
    if not run:
        raise HTTPException(404, "Test run not found")
    return run


async def run_background_test_completion_pass(db: AsyncSession) -> None:
    """Polled by main.py, mirrors demand.py's run_dispatch_completion_pass:
    finishes every mode="background" run still queued/running against the
    host-bridge's isolated instance, so a result is ready whether or not
    anyone has the history tab open. mode="visible" never appears here --
    it finishes synchronously inside _dispatch_test_run itself."""
    result = await db.execute(
        select(WebAutomationTestRun).where(
            WebAutomationTestRun.mode == "background",
            WebAutomationTestRun.status.in_(("queued", "running")),
            WebAutomationTestRun.bridge_run_id.isnot(None),
        )
    )
    for run in result.scalars().all():
        bridge_run_id = run.bridge_run_id
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{settings.CHAT_BRIDGE_URL}/v1/workspace-browser/test-run/{bridge_run_id}",
                    headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                )
            if response.status_code == 404:
                run.status = "error"
                run.error = "Host-bridge no longer has a record of this test run (bridge restarted?)"
                run.finished_at = datetime.now(timezone.utc)
                await db.commit()
                continue
            if response.status_code != 200:
                continue
            body = response.json()
        except httpx.HTTPError:
            continue
        bridge_status = body.get("status")
        if bridge_status not in ("passed", "failed", "error"):
            continue  # still running
        run.status = bridge_status
        run.report = body.get("report")
        run.screenshot_paths = body.get("screenshot_paths") or []
        run.error = body.get("error")
        run.finished_at = datetime.now(timezone.utc)
        await db.commit()


@router.get("/macros", response_model=list[MacroInstructionSetOut])
async def list_macros(
    product_id: uuid.UUID | None = None,
    standalone_app_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[MacroInstructionSet]:
    return list((await db.execute(
        select(MacroInstructionSet)
        .where(_target_filter(MacroInstructionSet, product_id, standalone_app_id))
        .order_by(MacroInstructionSet.name)
    )).scalars())


@router.post("/macros", response_model=MacroInstructionSetOut, status_code=201)
async def create_macro(payload: MacroInstructionSetCreate, db: AsyncSession = Depends(get_db)) -> MacroInstructionSet:
    await _resolve_start_url(db, payload.product_id, payload.standalone_app_id)
    macro = MacroInstructionSet(
        product_id=payload.product_id,
        standalone_app_id=payload.standalone_app_id,
        name=payload.name,
        description=payload.description,
        lines=payload.lines,
    )
    db.add(macro)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_macro_instruction_set_target_name":
            raise HTTPException(409, "A macro with this name already exists for this target") from None
        raise
    await db.refresh(macro)
    return macro


@router.put("/macros/{macro_id}", response_model=MacroInstructionSetOut)
async def update_macro(
    macro_id: uuid.UUID, payload: MacroInstructionSetUpdate, db: AsyncSession = Depends(get_db)
) -> MacroInstructionSet:
    macro = await db.get(MacroInstructionSet, macro_id)
    if not macro:
        raise HTTPException(404, "Macro not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(macro, key, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_macro_instruction_set_target_name":
            raise HTTPException(409, "A macro with this name already exists for this target") from None
        raise
    await db.refresh(macro)
    return macro


@router.delete("/macros/{macro_id}", status_code=204)
async def delete_macro(macro_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    macro = await db.get(MacroInstructionSet, macro_id)
    if not macro:
        raise HTTPException(404, "Macro not found")
    await db.delete(macro)
    await db.commit()
