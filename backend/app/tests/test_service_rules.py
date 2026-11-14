"""Pessoal -> Regras de atendimento: one rules document per agent and channel, mirrored into the
agent's profile as ATENDIMENTO_<CANAL>.md (Marcelo, 2026-11-14)."""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core import service_rules as rules
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.personal import AgentServiceRule
from app.db.models.user import User
from app.main import app

BASE = "/api/v1/personal/service-rules"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def agent(tmp_path, monkeypatch):
    """A throwaway agent with WhatsApp and site rules, profiles under tmp_path; rows removed after."""
    slug = f"test-{uuid.uuid4().hex[:8]}"
    (tmp_path / slug).mkdir()
    monkeypatch.setattr(settings, "SERVICE_RULES_PROFILES_ROOT", str(tmp_path))
    monkeypatch.setitem(rules.SERVICE_RULE_PAIRS, slug, ("whatsapp", "site"))
    yield slug
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentServiceRule).where(AgentServiceRule.agent_slug == slug))
        for channel in ("whatsapp", "site"):
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == rules.AUDIT_ENTITY,
                                                      AuditEvent.entity_id == rules.entity_id(slug, channel)))
        await db.commit()


def _item(items, slug, channel):
    return next(i for i in items if i["agent"] == slug and i["channel"] == channel)


@pytest.mark.asyncio
async def test_save_writes_profile_file_and_audits(client, admin_headers, agent, tmp_path):
    items = (await client.get(BASE, headers=admin_headers)).json()
    empty = _item(items, agent, "whatsapp")
    assert empty["content"] == "" and empty["content_hash"] is None and empty["file_state"] == "missing"
    assert empty["file_name"] == "ATENDIMENTO_WHATSAPP.md"
    assert empty["file_path"] == f"/root/.hermes/profiles/{agent}/ATENDIMENTO_WHATSAPP.md"

    r = await client.put(f"{BASE}/{agent}/whatsapp", headers=admin_headers,
                         json={"content": "  Atenda com simpatia.\r\n", "expected_hash": None})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["content"] == "Atenda com simpatia.\n" and saved["file_state"] == "in_sync"
    assert (tmp_path / agent / "ATENDIMENTO_WHATSAPP.md").read_text() == "Atenda com simpatia.\n"
    assert oct((tmp_path / agent / "ATENDIMENTO_WHATSAPP.md").stat().st_mode & 0o777) == "0o644"
    # the site channel is independent
    assert _item((await client.get(BASE, headers=admin_headers)).json(), agent, "site")["content"] == ""

    history = (await client.get(f"{BASE}/{agent}/whatsapp/history", headers=admin_headers)).json()
    assert len(history) == 1 and history[0]["previous_hash"] is None and history[0]["chars"] == 20

    # saving the same text again changes nothing and adds no history
    r = await client.put(f"{BASE}/{agent}/whatsapp", headers=admin_headers,
                         json={"content": "Atenda com simpatia.", "expected_hash": saved["content_hash"]})
    assert r.status_code == 200
    assert len((await client.get(f"{BASE}/{agent}/whatsapp/history", headers=admin_headers)).json()) == 1


@pytest.mark.asyncio
async def test_stale_edit_is_refused(client, admin_headers, agent):
    first = (await client.put(f"{BASE}/{agent}/site", headers=admin_headers,
                              json={"content": "v1", "expected_hash": None})).json()
    second = await client.put(f"{BASE}/{agent}/site", headers=admin_headers,
                              json={"content": "v2", "expected_hash": first["content_hash"]})
    assert second.status_code == 200
    stale = await client.put(f"{BASE}/{agent}/site", headers=admin_headers,
                             json={"content": "v3", "expected_hash": first["content_hash"]})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "SERVICE_RULE_CHANGED"
    assert stale.json()["detail"]["current_hash"] == second.json()["content_hash"]


@pytest.mark.asyncio
async def test_size_empty_and_unknown_pair(client, admin_headers, agent):
    too_big = "x" * (rules.SERVICE_RULE_MAX_CHARS + 1)
    assert (await client.put(f"{BASE}/{agent}/whatsapp", headers=admin_headers,
                             json={"content": too_big, "expected_hash": None})).status_code == 422
    assert (await client.put(f"{BASE}/{agent}/whatsapp", headers=admin_headers,
                             json={"content": "   ", "expected_hash": None})).status_code == 422
    assert (await client.put(f"{BASE}/{agent}/email", headers=admin_headers,
                             json={"content": "x", "expected_hash": None})).status_code == 404
    assert (await client.get(f"{BASE}/nobody/whatsapp/history", headers=admin_headers)).status_code == 404


@pytest.mark.asyncio
async def test_unwritable_profile_saves_nothing(client, admin_headers, agent, tmp_path):
    (tmp_path / agent).rmdir()
    r = await client.put(f"{BASE}/{agent}/whatsapp", headers=admin_headers,
                         json={"content": "regras", "expected_hash": None})
    assert r.status_code == 502 and r.json()["detail"]["code"] == "SERVICE_RULE_FILE_NOT_WRITTEN"
    item = _item((await client.get(BASE, headers=admin_headers)).json(), agent, "whatsapp")
    assert item["content_hash"] is None and item["file_state"] == "unknown"


@pytest.mark.asyncio
async def test_file_edited_outside_forgehub_reads_as_differs(client, admin_headers, agent, tmp_path):
    await client.put(f"{BASE}/{agent}/whatsapp", headers=admin_headers, json={"content": "a", "expected_hash": None})
    (tmp_path / agent / "ATENDIMENTO_WHATSAPP.md").write_text("editado à mão\n")
    assert _item((await client.get(BASE, headers=admin_headers)).json(), agent, "whatsapp")["file_state"] == "differs"


@pytest.mark.asyncio
async def test_only_marcelo_manages_rules(client):
    username = f"test-op-{uuid.uuid4().hex[:8]}"
    async with AsyncSessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(uuid.uuid4().hex), is_admin=False))
        await db.commit()
    try:
        headers = {"Authorization": f"Bearer {create_access_token(username)}"}
        assert (await client.get(BASE, headers=headers)).status_code == 403
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.username == username))
            await db.commit()


@pytest.mark.asyncio
async def test_maia_assistant_settings_reads_and_writes_the_whatsapp_rule(client, admin_headers, tmp_path, monkeypatch):
    (tmp_path / "maia").mkdir()
    monkeypatch.setattr(settings, "SERVICE_RULES_PROFILES_ROOT", str(tmp_path))
    async with AsyncSessionLocal() as db:
        previous = await rules.get_rule(db, "maia", "whatsapp")
        backup = (previous.content, previous.content_hash, previous.updated_by) if previous else None
    try:
        r = await client.put("/api/v1/personal/assistant-settings", headers=admin_headers,
                             json={"instructions": "Regras da Maia de teste"})
        assert r.status_code == 200 and r.json()["instructions"] == "Regras da Maia de teste\n"
        assert (tmp_path / "maia" / "ATENDIMENTO_WHATSAPP.md").read_text() == "Regras da Maia de teste\n"
        got = (await client.get("/api/v1/personal/assistant-settings", headers=admin_headers)).json()
        assert got["instructions"] == "Regras da Maia de teste\n"
        item = _item((await client.get(BASE, headers=admin_headers)).json(), "maia", "whatsapp")
        assert item["file_state"] == "in_sync"
    finally:
        async with AsyncSessionLocal() as db:
            row = await rules.get_rule(db, "maia", "whatsapp")
            if backup is None and row is not None:
                await db.delete(row)
            elif row is not None:
                row.content, row.content_hash, row.updated_by = backup
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == rules.AUDIT_ENTITY,
                                                      AuditEvent.entity_id == rules.entity_id("maia", "whatsapp"),
                                                      AuditEvent.payload["content_hash"].astext == rules.content_hash("Regras da Maia de teste\n")))
            await db.commit()
