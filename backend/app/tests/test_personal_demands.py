"""Personal demands grouped by user-defined types (the Pessoal screen's Demandas tab, 2026-10-14)."""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.base import AsyncSessionLocal
from app.db.models.personal import PersonalDemand, PersonalDemandType
from app.main import app

BASE = "/api/v1/personal"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def created():
    ids: dict[str, list] = {"demand": [], "type": []}
    yield ids
    async with AsyncSessionLocal() as db:
        if ids["demand"]:
            await db.execute(delete(PersonalDemand).where(PersonalDemand.id.in_(ids["demand"])))
        if ids["type"]:
            await db.execute(delete(PersonalDemandType).where(PersonalDemandType.id.in_(ids["type"])))
        await db.commit()


@pytest.mark.asyncio
async def test_types_are_unique_tags_and_removing_one_keeps_its_demands(client, admin_headers, created):
    name = f"Casa-{uuid.uuid4().hex[:6]}"
    r = await client.post(f"{BASE}/demand-types", headers=admin_headers, json={"name": f"  {name} "})
    assert r.status_code == 201, r.text
    kind = r.json()
    created["type"].append(uuid.UUID(kind["id"]))
    assert kind["name"] == name
    clash = await client.post(f"{BASE}/demand-types", headers=admin_headers, json={"name": name.upper()})
    assert clash.status_code == 409

    r = await client.post(f"{BASE}/demands", headers=admin_headers, json={"title": "Trocar a torneira", "type_id": kind["id"]})
    assert r.status_code == 201, r.text
    demand = r.json()
    created["demand"].append(uuid.UUID(demand["id"]))
    assert demand["type_id"] == kind["id"] and demand["status"] == "open"

    bad = await client.post(f"{BASE}/demands", headers=admin_headers, json={"title": "x", "type_id": str(uuid.uuid4())})
    assert bad.status_code == 422

    assert (await client.delete(f"{BASE}/demand-types/{kind['id']}", headers=admin_headers)).status_code == 204
    listed = (await client.get(f"{BASE}/demands", headers=admin_headers)).json()
    mine = next(d for d in listed if d["id"] == demand["id"])
    assert mine["type_id"] is None


@pytest.mark.asyncio
async def test_complete_reopen_and_bulk_delete(client, admin_headers, created):
    ids = []
    for title in ("Um", "Dois", "Três"):
        r = await client.post(f"{BASE}/demands", headers=admin_headers, json={"title": title})
        ids.append(r.json()["id"])
        created["demand"].append(uuid.UUID(r.json()["id"]))

    r = await client.patch(f"{BASE}/demands/{ids[0]}", headers=admin_headers, json={"status": "done"})
    assert r.json()["completed_at"] is not None
    open_ids = {d["id"] for d in (await client.get(f"{BASE}/demands", headers=admin_headers)).json()}
    assert ids[0] not in open_ids and ids[1] in open_ids
    r = await client.patch(f"{BASE}/demands/{ids[0]}", headers=admin_headers, json={"status": "open"})
    assert r.json()["completed_at"] is None

    r = await client.post(f"{BASE}/demands:delete", headers=admin_headers, json={"ids": ids[:2]})
    assert r.status_code == 204
    left = {d["id"] for d in (await client.get(f"{BASE}/demands", headers=admin_headers, params={"status": ""})).json()}
    assert ids[0] not in left and ids[1] not in left and ids[2] in left
