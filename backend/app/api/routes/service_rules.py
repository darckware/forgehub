"""Pessoal -> Regras de atendimento: the agents' customer-service rules per channel.

Only Marcelo reads and edits them here (``personal_actor`` + owner check). Each save mirrors the text
into the agent's profile as ``ATENDIMENTO_<CANAL>.md`` (core/service_rules.py) and is audited.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.personal import OWNER, personal_actor
from app.api.schemas.service_rules import ServiceRuleHistoryOut, ServiceRuleOut, ServiceRuleUpdate
from app.core import service_rules as rules
from app.db.base import get_db
from app.db.models.personal import AgentServiceRule

router = APIRouter(prefix="/api/v1/personal/service-rules", tags=["personal"])


def _owner(actor: str = Depends(personal_actor)) -> str:
    if actor != OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Service rules are managed by Marcelo")
    return actor


def _out(agent: str, channel: str, row: AgentServiceRule | None) -> ServiceRuleOut:
    target = rules.rule_file(agent, channel)
    content = row.content if row else ""
    return ServiceRuleOut(
        agent=agent, channel=channel, file_name=target.name, file_path=target.host_path, content=content,
        content_hash=row.content_hash if row else None, chars=len(content.strip()),
        max_chars=rules.SERVICE_RULE_MAX_CHARS, updated_at=row.updated_at if row else None,
        updated_by=row.updated_by if row else None, file_state=rules.file_state(agent, channel, row))


def _pair(agent: str, channel: str) -> None:
    try:
        rules.check_pair(agent, channel)
    except rules.ServiceRuleError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("", response_model=list[ServiceRuleOut])
async def list_service_rules(actor: str = Depends(_owner), db: AsyncSession = Depends(get_db)) -> list[ServiceRuleOut]:
    return [_out(agent, channel, row) for agent, channel, row in await rules.list_rules(db)]


@router.put("/{agent}/{channel}", response_model=ServiceRuleOut)
async def update_service_rule(agent: str, channel: str, payload: ServiceRuleUpdate, actor: str = Depends(_owner),
                              db: AsyncSession = Depends(get_db)) -> ServiceRuleOut:
    _pair(agent, channel)
    try:
        result = await rules.save_rule(db, agent, channel, payload.content, actor, expected_hash=payload.expected_hash)
    except rules.ServiceRuleError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except rules.ServiceRuleConflict as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "SERVICE_RULE_CHANGED", "message": str(exc),
                                                      "current_hash": exc.current_hash}) from exc
    except rules.ServiceRuleFileError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, {"code": "SERVICE_RULE_FILE_NOT_WRITTEN",
                                                         "message": str(exc)}) from exc
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        rules.restore_file(agent, channel, result.previous_content)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, {
            "code": "SERVICE_RULE_NOT_SAVED",
            "message": "The rules were not saved; the agent's file was put back as it was."}) from exc
    await db.refresh(result.row)
    return _out(agent, channel, result.row)


@router.get("/{agent}/{channel}/history", response_model=list[ServiceRuleHistoryOut])
async def service_rule_history(agent: str, channel: str, actor: str = Depends(_owner),
                               db: AsyncSession = Depends(get_db)) -> list[ServiceRuleHistoryOut]:
    _pair(agent, channel)
    events = await rules.history(db, agent, channel)
    return [ServiceRuleHistoryOut(at=e.created_at, actor=e.actor, content_hash=(e.payload or {}).get("content_hash", ""),
                                  previous_hash=(e.payload or {}).get("previous_hash"),
                                  chars=int((e.payload or {}).get("chars") or 0)) for e in events]
