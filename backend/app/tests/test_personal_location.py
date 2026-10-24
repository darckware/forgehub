"""Pessoal location: one row per day, source follows the caller, the summary's weather uses it."""
import hashlib
import secrets
import uuid
from datetime import date

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import personal as personal_routes
from app.core.config import settings
from app.core.weather import WeatherError
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.personal import PersonalLocation
from app.main import app

BASE = "/api/v1/personal"
# Far from any real day the Maia could send while the suite runs (one row per day).
DAY = date(2031, 3, 10)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def cleanup():
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(PersonalLocation).where(PersonalLocation.day.between(date(2031, 1, 1), date(2031, 12, 31))))
        await db.commit()


@pytest_asyncio.fixture
async def agent_headers(monkeypatch):
    slug = f"test-loc-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(settings, "PERSONAL_AGENT_SLUGS", slug)
    token = f"agt_{secrets.token_urlsafe(24)}"
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"test-personal-{uuid.uuid4().hex[:8]}", profile_slug=slug, status="active", is_active=True)
        db.add(agent)
        await db.flush()
        db.add(AgentServiceCredential(agent_id=agent.id, label="test", token_hash=hashlib.sha256(token.encode()).hexdigest()))
        await db.commit()
        agent_id = agent.id
    yield {"Authorization": f"Bearer {token}"}, slug
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id == agent_id))
        await db.execute(delete(Agent).where(Agent.id == agent_id))
        await db.commit()


def _body(day: date, city: str, lat: float = -23.55, lon: float = -46.63) -> dict:
    return {"day": day.isoformat(), "city": city, "state": "SP", "latitude": lat, "longitude": lon}


async def test_one_location_per_day_replaced_by_a_second_send(client, admin_headers, cleanup):
    r = await client.post(f"{BASE}/locations", headers=admin_headers, json={**_body(DAY, "São Paulo"), "notes": "viagem"})
    assert r.status_code == 201, r.text
    first = r.json()
    assert (first["source"], first["created_by"], first["country"]) == ("manual", "marcelo", "Brasil")

    r = await client.post(f"{BASE}/locations", headers=admin_headers, json=_body(DAY, "Campinas", -22.9, -47.06))
    assert r.status_code == 200, r.text
    assert r.json()["id"] == first["id"] and r.json()["city"] == "Campinas"

    r = await client.get(f"{BASE}/locations", headers=admin_headers,
                         params={"start": "2031-03-01", "end": "2031-03-31"})
    assert [loc["city"] for loc in r.json()] == ["Campinas"]


async def test_agent_sends_but_only_marcelo_corrects(client, admin_headers, agent_headers, cleanup):
    headers, slug = agent_headers
    r = await client.post(f"{BASE}/locations", headers=headers, json=_body(DAY, "Niterói", -22.88, -43.1))
    assert r.status_code == 201, r.text
    assert (r.json()["source"], r.json()["created_by"]) == ("maia", slug)

    r = await client.patch(f"{BASE}/locations/{DAY.isoformat()}", headers=headers, json={"city": "Rio"})
    assert r.status_code == 403

    r = await client.patch(f"{BASE}/locations/{DAY.isoformat()}", headers=admin_headers, json={"city": "Rio de Janeiro"})
    assert r.status_code == 200, r.text
    assert (r.json()["city"], r.json()["source"]) == ("Rio de Janeiro", "manual")


async def test_rejects_impossible_coordinates(client, admin_headers, cleanup):
    r = await client.post(f"{BASE}/locations", headers=admin_headers, json=_body(DAY, "Lugar nenhum", lat=123.0))
    assert r.status_code == 422


async def test_summary_weather_uses_latest_location_within_seven_days(client, admin_headers, cleanup, monkeypatch):
    seen = []

    async def fake_weather(day, location=None):
        seen.append(location.city if location else None)
        raise WeatherError("not needed here")  # the summary treats weather as optional

    monkeypatch.setattr(settings, "WEATHER_ENABLED", True)
    monkeypatch.setattr(personal_routes, "get_weather", fake_weather)
    r = await client.post(f"{BASE}/locations", headers=admin_headers, json=_body(DAY, "São Paulo"))
    assert r.status_code == 201, r.text

    for day in ("2031-03-10", "2031-03-16", "2031-03-17"):
        r = await client.get(f"{BASE}/summary", headers=admin_headers, params={"day": day})
        assert r.status_code == 200, r.text
    # Same day and six days later use it; on the seventh it has expired (default city).
    assert seen == ["São Paulo", "São Paulo", None]
