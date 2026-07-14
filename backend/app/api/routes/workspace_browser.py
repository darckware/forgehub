"""Authenticated proxy for the shared Workspace CDP browser.

The browser runs on the host so Athos and the human operator see and control
the same Chromium tab. ForgeHub credentials cross this boundary only during
the explicit login command and are neither stored nor returned by the bridge.
"""

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.workspace_browser import (
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
from app.db.models.web_automation import WebAutomationRoutine

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


@router.get("/routines", response_model=list[WebAutomationRoutineOut])
async def list_routines(product_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[WebAutomationRoutine]:
    return list((await db.execute(
        select(WebAutomationRoutine)
        .where(WebAutomationRoutine.product_id == product_id)
        .order_by(WebAutomationRoutine.name)
    )).scalars())


@router.post("/routines", response_model=WebAutomationRoutineOut, status_code=201)
async def create_routine(
    payload: WebAutomationRoutineCreate, db: AsyncSession = Depends(get_db)
) -> WebAutomationRoutine:
    if not await db.get(Product, payload.product_id):
        raise HTTPException(404, "Product not found")
    routine = WebAutomationRoutine(
        product_id=payload.product_id,
        name=payload.name,
        description=payload.description,
        steps=[step.model_dump(exclude_none=True) for step in payload.steps],
    )
    db.add(routine)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_web_automation_routine_product_name":
            raise HTTPException(409, "A routine with this name already exists for the product") from None
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
        if getattr(getattr(exc, "orig", None), "constraint_name", None) == "uq_web_automation_routine_product_name":
            raise HTTPException(409, "A routine with this name already exists for the product") from None
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
    product = await db.get(Product, routine.product_id)
    if not product or not product.application_url:
        raise HTTPException(409, "Product application URL is not configured")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/workspace-browser/run-routine",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"start_url": product.application_url, "steps": routine.steps},
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
