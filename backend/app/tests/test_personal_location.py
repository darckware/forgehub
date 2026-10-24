"""Pessoal: one current GPS location (no history) and the Maia's daily summaries."""
import hashlib
import secrets
import uuid
from datetime import date

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes import personal as personal_routes
from app.core.config import settings
from app.core.weather import WeatherError
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.personal import PersonalDailySummary, PersonalLocation
from app.main import app

BASE = "/api/v1/personal"
# Far from any real day the Maia could save a summary on while the suite runs.
DAY = date(2031, 3, 10)
_FIELDS = ("latitude", "longitude", "accuracy_m", "city", "state", "source", "shared_at")


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def cleanup(monkeypatch):
    """The current location is Marcelo's real one (the database is shared with production):
    keep it and put it back. Summaries live in 2031 and are deleted. No network geocoding."""
    async def fake_geocode(latitude, longitude):
        return ("Niterói", "RJ") if latitude < -22.85 else (None, None)

    monkeypatch.setattr(personal_routes, "reverse_geocode", fake_geocode)
    async with AsyncSessionLocal() as db:
        real = (await db.execute(select(PersonalLocation))).scalar_one_or_none()
        saved = {key: getattr(real, key) for key in _FIELDS} if real else None
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(delete(PersonalDailySummary).where(
            PersonalDailySummary.day.between(date(2031, 1, 1), date(2031, 12, 31))))
        await db.execute(delete(PersonalLocation))
        if saved:
            db.add(PersonalLocation(**saved))
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


async def test_location_is_one_current_row_replaced_on_each_share(client, admin_headers, agent_headers, cleanup):
    headers, _ = agent_headers
    r = await client.put(f"{BASE}/location", headers=headers,
                         json={"latitude": -22.88, "longitude": -43.1, "source": "whatsapp"})
    assert r.status_code == 200, r.text
    assert (r.json()["city"], r.json()["state"], r.json()["source"]) == ("Niterói", "RJ", "whatsapp")

    # Marcelo's browser fix: always "browser", whatever the payload says; no geocode is fine.
    r = await client.put(f"{BASE}/location", headers=admin_headers,
                         json={"latitude": -20.0, "longitude": -40.0, "accuracy_m": 12.5, "source": "telegram"})
    assert r.status_code == 200, r.text
    assert (r.json()["source"], r.json()["accuracy_m"], r.json()["city"]) == ("browser", 12.5, None)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(PersonalLocation))).scalars().all()
    assert [(row.latitude, row.longitude) for row in rows] == [(-20.0, -40.0)]

    r = await client.get(f"{BASE}/location", headers=admin_headers)
    assert r.json()["latitude"] == -20.0


async def test_rejects_impossible_coordinates(client, admin_headers, cleanup):
    r = await client.put(f"{BASE}/location", headers=admin_headers, json={"latitude": 123.0, "longitude": 0})
    assert r.status_code == 422


async def test_daily_summary_saved_once_per_day_with_the_location_used(client, admin_headers, agent_headers, cleanup):
    headers, slug = agent_headers
    await client.put(f"{BASE}/location", headers=headers, json={"latitude": -22.88, "longitude": -43.1})

    r = await client.put(f"{BASE}/daily-summaries/{DAY.isoformat()}", headers=headers, json={"content": "Bom dia!"})
    assert r.status_code == 200, r.text
    first = r.json()
    assert (first["location_city"], first["location_state"], first["created_by"]) == ("Niterói", "RJ", slug)

    r = await client.put(f"{BASE}/daily-summaries/{DAY.isoformat()}", headers=headers, json={"content": "Bom dia, Marcelo!"})
    assert r.json()["id"] == first["id"] and r.json()["content"] == "Bom dia, Marcelo!"

    r = await client.get(f"{BASE}/daily-summaries", headers=admin_headers,
                         params={"start": "2031-03-01", "end": "2031-03-31"})
    assert [s["content"] for s in r.json()] == ["Bom dia, Marcelo!"]

    r = await client.put(f"{BASE}/daily-summaries/{DAY.isoformat()}", headers=headers, json={"content": ""})
    assert r.status_code == 422


async def test_summary_weather_uses_the_current_location(client, admin_headers, cleanup, monkeypatch):
    seen = []

    async def fake_weather(day, location=None):
        seen.append(location.city if location else None)
        raise WeatherError("not needed here")  # the summary treats weather as optional

    monkeypatch.setattr(settings, "WEATHER_ENABLED", True)
    monkeypatch.setattr(personal_routes, "get_weather", fake_weather)
    r = await client.put(f"{BASE}/location", headers=admin_headers, json={"latitude": -22.88, "longitude": -43.1})
    assert r.status_code == 200, r.text

    r = await client.get(f"{BASE}/summary", headers=admin_headers, params={"day": "2031-03-10"})
    assert r.status_code == 200, r.text
    assert seen == ["Niterói"]
