"""Chat prompt commands CRUD.

These are ForgeHub-level reusable Markdown prompts shown in the chat slash
picker beside Hermes-native slash commands. They expand into composer text;
they are not forwarded to Hermes's slash-command dispatcher.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.prompt_command import (
    PromptCommandCreate,
    PromptCommandOut,
    PromptCommandUpdate,
)
from app.db.base import get_db
from app.db.models.prompt_command import PromptCommand

router = APIRouter(prefix="/api/v1/prompt-commands", tags=["prompt-commands"])


def _to_out(command: PromptCommand) -> PromptCommandOut:
    return PromptCommandOut(
        id=str(command.id),
        name=command.name,
        description=command.description,
        prompt=command.prompt,
        created_at=command.created_at,
        updated_at=command.updated_at,
    )


async def _commit_or_name_conflict(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Command name already exists") from exc


@router.get("", response_model=list[PromptCommandOut])
async def list_prompt_commands(db: AsyncSession = Depends(get_db)) -> list[PromptCommandOut]:
    rows = (
        await db.execute(select(PromptCommand).order_by(PromptCommand.name))
    ).scalars().all()
    return [_to_out(row) for row in rows]


@router.post("", response_model=PromptCommandOut, status_code=status.HTTP_201_CREATED)
async def create_prompt_command(
    payload: PromptCommandCreate,
    db: AsyncSession = Depends(get_db),
) -> PromptCommandOut:
    command = PromptCommand(
        id=uuid.uuid4(),
        name=payload.name,
        description=payload.description,
        prompt=payload.prompt,
    )
    db.add(command)
    await _commit_or_name_conflict(db)
    await db.refresh(command)
    return _to_out(command)


@router.put("/{command_id}", response_model=PromptCommandOut)
async def update_prompt_command(
    command_id: uuid.UUID,
    payload: PromptCommandUpdate,
    db: AsyncSession = Depends(get_db),
) -> PromptCommandOut:
    command = await db.get(PromptCommand, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    command.name = payload.name
    command.description = payload.description
    command.prompt = payload.prompt
    await _commit_or_name_conflict(db)
    await db.refresh(command)
    return _to_out(command)


@router.delete("/{command_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt_command(
    command_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    command = await db.get(PromptCommand, command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    await db.delete(command)
    await db.commit()
