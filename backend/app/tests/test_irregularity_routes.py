"""Irregularity list/resolve route tests -- real DB, no mocking."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation
from app.db.models.user import User
from app.main import app


async def _user_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        assert user is not None
        return create_access_token(user.username)


@pytest.mark.asyncio
async def test_list_and_resolve_irregularity():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id, os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.flush()
        irregularity = Irregularity(
            workstation_id=workstation.id, rule_key="backup_stale", severity="warning",
            detail="test", detected_at=datetime.now(timezone.utc),
        )
        db.add(irregularity)
        await db.commit()
        irregularity_id, client_id = irregularity.id, client.id

    try:
        token = await _user_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            list_resp = await http.get("/api/v1/irregularities", params={"status_filter": "open"})
            assert list_resp.status_code == 200
            assert any(i["id"] == str(irregularity_id) for i in list_resp.json())

            resolve_resp = await http.patch(
                f"/api/v1/irregularities/{irregularity_id}",
                json={"status": "resolved"},
                headers=headers,
            )
            assert resolve_resp.status_code == 200
            body = resolve_resp.json()
            assert body["status"] == "resolved"
            assert body["resolved_at"] is not None
            assert body["resolved_by_user_id"] is not None
    finally:
        async with AsyncSessionLocal() as db:
            client = await db.get(Client, client_id)
            await db.delete(client)
            await db.commit()
