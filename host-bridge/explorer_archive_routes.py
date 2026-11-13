"""Authenticated host archive routes; the backend owns user audit events."""
import asyncio
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from explorer_archives import ArchiveError, archive_operation


class ArchiveRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=1000)
    destination: str = Field(min_length=1)


def make_archive_router(check_token):
    router = APIRouter(prefix='/v1/fs')

    async def execute(mode, payload, token):
        check_token(token)
        try:
            return await asyncio.to_thread(archive_operation, mode, payload.paths, payload.destination)
        except ArchiveError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @router.post('/compress')
    async def compress(payload: ArchiveRequest, x_bridge_token: str | None = Header(default=None)):
        return await execute('compress', payload, x_bridge_token)

    @router.post('/extract')
    async def extract(payload: ArchiveRequest, x_bridge_token: str | None = Header(default=None)):
        return await execute('extract', payload, x_bridge_token)

    return router
