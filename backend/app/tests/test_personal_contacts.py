"""Personal contacts in the database (2026-10-14): record rules carried over from the Maia's file-based
module, the WhatsApp plugin's endpoints, the context pass and the capture suggestions."""
import hashlib
import json
import random
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core import forgerouter_llm
from app.core import personal_contacts as rules
from app.core.config import settings
from app.core.personal_context import parse_reply, run_personal_context_pass
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.personal import (
    PersonalCaptureSuggestion,
    PersonalContact,
    PersonalContactMessage,
    PersonalDemand,
    PersonalNote,
    PersonalTask,
)
from app.main import app

BASE = "/api/v1/personal"


def _phone() -> str:
    # 5599 + 9 digits: a DDD that the real contact list never uses.
    return "5599" + "".join(random.choice("0123456789") for _ in range(9))


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def phones():
    created: list[str] = []
    yield created
    async with AsyncSessionLocal() as db:
        ids = list((await db.execute(select(PersonalContact.id).where(PersonalContact.phone.in_(created)))).scalars())
        if ids:
            items = list((await db.execute(
                select(PersonalCaptureSuggestion.created_item_id).where(PersonalCaptureSuggestion.contact_id.in_(ids))
            )).scalars())
            items = [i for i in items if i]
            for model in (PersonalDemand, PersonalTask, PersonalNote):
                await db.execute(delete(model).where(model.id.in_(items)))
            await db.execute(delete(PersonalContact).where(PersonalContact.id.in_(ids)))
        await db.commit()


@pytest_asyncio.fixture
async def maia(monkeypatch):
    slug = f"maia-test-{uuid.uuid4().hex[:6]}"
    token = f"agt_{secrets.token_urlsafe(24)}"
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"test-contacts-{slug}", profile_slug=slug, status="active", is_active=True)
        db.add(agent)
        await db.flush()
        db.add(AgentServiceCredential(agent_id=agent.id, label="test", token_hash=hashlib.sha256(token.encode()).hexdigest()))
        await db.commit()
        agent_id = agent.id
    monkeypatch.setattr(settings, "PERSONAL_AGENT_SLUGS", slug)
    yield {"Authorization": f"Bearer {token}"}
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id == agent_id))
        await db.execute(delete(Agent).where(Agent.id == agent_id))
        await db.commit()


def test_phone_category_and_birthday_rules():
    assert rules.normalize_phone("(21) 99999-1234") == "5521999991234"
    assert rules.normalize_phone("+12025550123") == "12025550123"  # US number from a WhatsApp JID
    with pytest.raises(rules.ContactRuleError):
        rules.require_phone("1234")
    assert rules.format_phone("21999991234") == "+55 21 99999-1234"
    assert rules.normalize_category("Trabalho (SEMED)") == "trabalho_semed"
    assert rules.normalize_category("Colaboradores") == "colaboradores"
    with pytest.raises(rules.ContactRuleError):
        rules.check_birthday("3 de maio")
    assert rules.merge_other_data({"cargo": "x", "setor": "y"}, {"cargo": "", "empresa": "Acme"}) == {
        "setor": "y", "empresa": "Acme"}
    assert rules.upcoming_birthday("16/10/1990", date(2026, 10, 14), 30) == {"data": "16/10/2026", "faltam_dias": 2, "idade": 36}


def test_parse_legacy_ficha():
    ficha = """---
nome: "Ana"
telefone: "+55 21 99999-1234"
categoria: familia
relacao: "irmã"
aniversario: "03/05"
sensitivity: pessoal
---

# Ana (+55 21 99999-1234)

## Quem é

Irmã do Marcelo.

## Como tratar

(a preencher pelo Marcelo: tom, o que pode dizer, o que fazer com o recado)

## Outros dados

- **tipo:** blacklist
- **cargo:** professora

## Histórico

- **12/10/2026 10:00** · Ana: almoço domingo?
- **12/10/2026 10:05** · Marcelo: sim
- **12/10/2026 10:06** · Ana:
"""
    contact = rules.parse_ficha(ficha)
    assert contact.phone == "5521999991234" and contact.name == "Ana" and contact.category == "familia"
    assert contact.who_is == "Irmã do Marcelo." and contact.how_to_treat == ""
    assert contact.blocked is True and contact.other_data == {"cargo": "professora"}
    assert [(m.direction, m.text) for m in contact.messages] == [
        ("in", "almoço domingo?"), ("out", "sim"), ("in", rules.EMPTY_MESSAGE)]


@pytest.mark.asyncio
async def test_upsert_list_get_and_validation(client, admin_headers, phones):
    phone = _phone()
    phones.append(phone)
    r = await client.put(f"{BASE}/contacts/{phone}", headers=admin_headers, json={
        "name": "Teste Contato", "category": "Amigo", "birthday": "03/05", "other_data": {"cargo": "x"}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["category"] == "amigos" and body["phone_display"].startswith("+55 99")

    bad = await client.put(f"{BASE}/contacts/{phone}", headers=admin_headers, json={"category": "inexistente"})
    assert bad.status_code == 422
    bad = await client.put(f"{BASE}/contacts/{phone}", headers=admin_headers, json={"birthday": "maio"})
    assert bad.status_code == 422

    r = await client.put(f"{BASE}/contacts/{phone}", headers=admin_headers, json={"other_data": {"cargo": "", "setor": "TI"}})
    assert r.json()["other_data"] == {"setor": "TI"} and r.json()["name"] == "Teste Contato"

    listed = (await client.get(f"{BASE}/contacts", headers=admin_headers, params={"q": "Teste Contato"})).json()
    assert phone in {c["phone"] for c in listed}

    r = await client.post(f"{BASE}/contacts/{phone}:append-observation", headers=admin_headers, json={"text": "gosta de café"})
    r = await client.post(f"{BASE}/contacts/{phone}:append-observation", headers=admin_headers, json={"text": "mora no Rio"})
    assert r.json()["observations"] == "gosta de café; mora no Rio"


@pytest.mark.asyncio
async def test_change_phone_moves_history_and_refuses_taken_number(client, admin_headers, phones):
    a, b, c = _phone(), _phone(), _phone()
    phones.extend([a, b, c])
    for p in (a, b):
        await client.put(f"{BASE}/contacts/{p}", headers=admin_headers, json={"name": p})
    await client.post(f"{BASE}/contacts/{a}/messages", headers=admin_headers, json={"text": "nota", "direction": "note"})
    taken = await client.post(f"{BASE}/contacts/{a}:change-phone", headers=admin_headers, json={"phone": b})
    assert taken.status_code == 409
    moved = await client.post(f"{BASE}/contacts/{a}:change-phone", headers=admin_headers, json={"phone": c})
    assert moved.json()["phone"] == c and moved.json()["message_count"] == 1
    assert (await client.get(f"{BASE}/contacts/{a}", headers=admin_headers)).status_code == 404


@pytest.mark.asyncio
async def test_plugin_records_messages_and_reads_context(client, maia, phones):
    phone = _phone()
    phones.append(phone)
    first = await client.post(f"{BASE}/whatsapp/messages", headers=maia, json={"phone": phone, "text": "oi, é a Ana"})
    assert first.status_code == 201, first.text
    assert first.json()["context_status"] == "pending" and first.json()["author"] == "contato"
    out = await client.post(f"{BASE}/whatsapp/messages", headers=maia, json={"phone": phone, "text": "oi Ana", "direction": "out"})
    assert out.json()["context_status"] == "skipped" and out.json()["author"] == "Marcelo"

    ctx = (await client.get(f"{BASE}/whatsapp/context/{phone}", headers=maia)).json()
    assert ctx["contact"]["category"] == "a_classificar" and ctx["contact"]["last_contact_at"]
    assert "oi, é a Ana" in ctx["context_text"] and ctx["blocked"] is False
    assert isinstance(ctx["instructions"], str)

    unknown = (await client.get(f"{BASE}/whatsapp/context/{_phone()}", headers=maia)).json()
    assert unknown["contact"] is None

    # Deleting a contact is Marcelo's only.
    assert (await client.delete(f"{BASE}/contacts/{phone}", headers=maia)).status_code == 403


@pytest.mark.asyncio
async def test_context_pass_and_suggestions(client, admin_headers, maia, phones, monkeypatch):
    phone, blocked = _phone(), _phone()
    phones.extend([phone, blocked])
    await client.put(f"{BASE}/contacts/{phone}", headers=admin_headers, json={"name": "Ana", "category": "familia"})
    await client.put(f"{BASE}/contacts/{blocked}", headers=admin_headers, json={"blocked": True})
    msg = (await client.post(f"{BASE}/whatsapp/messages", headers=maia,
                             json={"phone": phone, "text": "Me manda o boleto da escola até sexta?"})).json()
    spam = (await client.post(f"{BASE}/whatsapp/messages", headers=maia, json={"phone": blocked, "text": "promoção"})).json()

    prompts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompts.append(body["messages"][1]["content"])
        reply = {"contexto": "Ana pede o boleto da escola até sexta.",
                 "sugestoes": [{"tipo": "tarefa", "titulo": "Enviar boleto da escola para Ana", "detalhes": "até sexta"},
                               {"tipo": "invalido", "titulo": "x"}]}
        return httpx.Response(200, json={"choices": [{"message": {"content": "```json\n" + json.dumps(reply) + "\n```"}}]})

    async def fake_key(_db, _slug):
        return "k"

    monkeypatch.setattr(forgerouter_llm, "transport", httpx.MockTransport(handler))
    monkeypatch.setattr(forgerouter_llm, "agent_api_key", fake_key)
    async with AsyncSessionLocal() as db:
        # Other pending rows may exist in the shared DB; run until ours are handled.
        for _ in range(20):
            done = await db.get(PersonalContactMessage, uuid.UUID(msg["id"]))
            await db.refresh(done)
            skipped = await db.get(PersonalContactMessage, uuid.UUID(spam["id"]))
            await db.refresh(skipped)
            if done.context_status != "pending" and skipped.context_status != "pending":
                break
            await run_personal_context_pass(db)
    assert done.context_status == "done" and done.context == "Ana pede o boleto da escola até sexta."
    assert skipped.context_status == "skipped"
    assert any("<mensagem>" in p and "boleto" in p for p in prompts)
    assert not any("promoção" in p for p in prompts)

    pending = (await client.get(f"{BASE}/suggestions", headers=admin_headers, params={"contact_phone": phone})).json()
    assert [(s["kind"], s["title"]) for s in pending] == [("task", "Enviar boleto da escola para Ana")]
    accepted = await client.post(f"{BASE}/suggestions/{pending[0]['id']}:accept", headers=admin_headers, json={})
    assert accepted.status_code == 200, accepted.text
    async with AsyncSessionLocal() as db:
        task = await db.get(PersonalTask, uuid.UUID(accepted.json()["created_item_id"]))
    assert task.title == "Enviar boleto da escola para Ana" and "Capturado do WhatsApp — Ana" in task.notes
    again = await client.post(f"{BASE}/suggestions/{pending[0]['id']}:dismiss", headers=admin_headers)
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_accept_as_note_and_dismiss(client, admin_headers, phones):
    phone = _phone()
    phones.append(phone)
    contact = (await client.put(f"{BASE}/contacts/{phone}", headers=admin_headers, json={"name": "Bia"})).json()
    async with AsyncSessionLocal() as db:
        a = PersonalCaptureSuggestion(contact_id=uuid.UUID(contact["id"]), kind="task", title="Guardar endereço")
        b = PersonalCaptureSuggestion(contact_id=uuid.UUID(contact["id"]), kind="demand", title="Reforma")
        db.add_all([a, b])
        await db.commit()
        a_id, b_id = a.id, b.id
    r = await client.post(f"{BASE}/suggestions/{a_id}:accept", headers=admin_headers,
                          json={"kind": "note", "details": "Rua X, 10"})
    assert r.json()["kind"] == "note"
    async with AsyncSessionLocal() as db:
        note = await db.get(PersonalNote, uuid.UUID(r.json()["created_item_id"]))
    assert note.tags == ["whatsapp"] and note.content.startswith("Rua X, 10")
    r = await client.post(f"{BASE}/suggestions/{b_id}:dismiss", headers=admin_headers)
    assert r.json()["status"] == "dismissed" and r.json()["created_item_id"] is None


def test_parse_reply_rejects_wrong_shape():
    with pytest.raises(ValueError):
        parse_reply('["só uma lista"]')
    context, suggestions = parse_reply('{"contexto": "ok", "sugestoes": []}')
    assert context == "ok" and suggestions == []


@pytest.mark.asyncio
async def test_assistant_settings_and_state(client, admin_headers, tmp_path, monkeypatch):
    original = (await client.get(f"{BASE}/assistant-settings", headers=admin_headers)).json()
    try:
        r = await client.put(f"{BASE}/assistant-settings", headers=admin_headers, json={"wait_minutes": 7})
        assert r.json()["wait_minutes"] == 7 and r.json()["instructions"] == original["instructions"]
        assert (await client.put(f"{BASE}/assistant-settings", headers=admin_headers, json={"wait_minutes": 999})).status_code == 422
    finally:
        await client.put(f"{BASE}/assistant-settings", headers=admin_headers, json={"wait_minutes": original["wait_minutes"]})

    future = (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()
    (tmp_path / "pausas.json").write_text(json.dumps({"5599000000001@s.whatsapp.net": future, "5599000000002@s.whatsapp.net": 1.0}))
    (tmp_path / "tarefas.json").write_text(json.dumps({"5599000000003": {"objetivo": "confirmar", "criada": "x", "expira_ts": future}}))
    monkeypatch.setattr(settings, "PERSONAL_WHATSAPP_STATE_DIR", str(tmp_path))
    state = (await client.get(f"{BASE}/assistant-state", headers=admin_headers)).json()
    assert [p["phone"] for p in state["paused"]] == ["5599000000001"]
    assert [t["goal"] for t in state["open_tasks"]] == ["confirmar"]
