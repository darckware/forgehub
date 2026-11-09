"""Exercise the mission version selector's real routing without a database connection."""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.routes.product import router
from app.db.base import get_db


@pytest.mark.asyncio
async def test_mission_version_selector_reaches_static_collection():
    class Database:
        async def execute(self, statement):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    async def inert_db():
        yield Database()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = inert_db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/products/versions")
    assert response.status_code == 200, response.text
    assert response.json() == []
