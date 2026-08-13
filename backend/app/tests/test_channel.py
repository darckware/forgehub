"""Tests for the ChatChannel domain (see db/models/channel.py and
api/routes/channel.py). Mirrors test_chat_groups.py's pattern: real DB, no
mocking, explicit cleanup. Agent-turn/dispatch endpoints that require a live
host-bridge call are out of scope here (no bridge process in this
environment) -- _extract_mentions is covered directly as a pure function
instead, and the rest of this file covers everything reachable without the
bridge: CRUD, project attach/detach (mutable, not creation-locked), explicit
member choice, and lightweight channel tasks."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.api.routes.channel import _extract_mentions
from app.core.security import create_access_token, hash_password
from app.db.base import AsyncSessionLocal, engine
from app.db.models.agent import Agent
from app.db.models.channel import ChatChannelMember
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.product import Product, ProductVersion
from app.db.models.user import User
from app.main import app

_STUB_AGENT_IDS: list[uuid.UUID] = []
_STUB_AGENT_SLUGS: list[str] = []
_STUB_PROJECT_ID: uuid.UUID | None = None
_STUB_PRODUCT_ID: uuid.UUID | None = None
_STUB_PRODUCT_VERSION_ID: uuid.UUID | None = None
_created_channel_ids: list[uuid.UUID] = []
_created_approval_ids: list[uuid.UUID] = []


@pytest_asyncio.fixture(scope="module")
async def db_schema():
    global _STUB_PROJECT_ID, _STUB_PRODUCT_ID, _STUB_PRODUCT_VERSION_ID

    async with AsyncSessionLocal() as session:
        agents = [
            Agent(name=f"Channel Test Agent A {uuid.uuid4()}", profile_slug=f"channel-test-a-{uuid.uuid4().hex[:8]}"),
            Agent(name=f"Channel Test Agent B {uuid.uuid4()}", profile_slug=f"channel-test-b-{uuid.uuid4().hex[:8]}"),
        ]
        for a in agents:
            session.add(a)
        await session.commit()
        for a in agents:
            _STUB_AGENT_IDS.append(a.id)
            _STUB_AGENT_SLUGS.append(a.profile_slug)

        # projects.product_version_id is a required FK -- a dedicated
        # Product+ProductVersion is created here (and torn down after),
        # same pattern as test_pipeline.py's project fixture.
        product = Product(name=f"Channel Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.commit()
        _STUB_PRODUCT_ID = product.id
        _STUB_PRODUCT_VERSION_ID = version.id

        result = await session.execute(
            text(
                "INSERT INTO company.projects (id, name, product_version_id, status) "
                "VALUES (gen_random_uuid(), :name, :product_version_id, 'planned') RETURNING id"
            ),
            {"name": f"Channel Test Project {uuid.uuid4()}", "product_version_id": _STUB_PRODUCT_VERSION_ID},
        )
        _STUB_PROJECT_ID = result.scalar_one()
        await session.commit()

    yield

    async with engine.begin() as conn:
        if _created_approval_ids:
            await conn.execute(
                text("DELETE FROM company.approvals WHERE id = ANY(:ids)"),
                {"ids": _created_approval_ids},
            )
        if _created_channel_ids:
            await conn.execute(
                text("DELETE FROM company.chat_channels WHERE id = ANY(:ids)"),
                {"ids": _created_channel_ids},
            )
        await conn.execute(text("DELETE FROM company.project_tasks WHERE planning_item_id IN (SELECT id FROM company.planning_items WHERE project_id = :id)"), {"id": _STUB_PROJECT_ID})
        await conn.execute(text("DELETE FROM company.planning_items WHERE project_id = :id"), {"id": _STUB_PROJECT_ID})
        await conn.execute(text("DELETE FROM company.projects WHERE id = :id"), {"id": _STUB_PROJECT_ID})
        await conn.execute(text("DELETE FROM company.product_versions WHERE id = :id"), {"id": _STUB_PRODUCT_VERSION_ID})
        await conn.execute(text("DELETE FROM company.products WHERE id = :id"), {"id": _STUB_PRODUCT_ID})
        await conn.execute(text("DELETE FROM company.agents WHERE id = ANY(:ids)"), {"ids": _STUB_AGENT_IDS})


@pytest_asyncio.fixture
async def client(db_schema, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def admin_client(db_schema):
    """A real User(is_admin=True) row + JWT -- unlike `client`'s
    auth_headers (subject "test-suite", no matching User row), governance
    routes resolve identity via get_actor_principal, which does a real
    User lookup. Same pattern as test_governance.py's own `client` fixture."""
    username = f"channel-test-admin-{uuid.uuid4().hex}"
    async with AsyncSessionLocal() as db:
        user = User(username=username, hashed_password=hash_password("test"), is_admin=True)
        db.add(user)
        await db.commit()
        user_id = user.id
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(username)}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        yield ac
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM company.users WHERE id = :id"), {"id": user_id})


@pytest_asyncio.fixture
async def bridge_client(db_schema):
    """No JWT -- exercises the shared-bridge-token path an agent's MCP
    tool call actually uses for POST .../tasks/propose (see main.py's
    dedicated bypass for this exact path)."""
    from app.core.config import settings

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test", headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
    ) as ac:
        yield ac


async def _create_channel(client: AsyncClient, **overrides) -> dict:
    payload = {"name": f"Channel {uuid.uuid4()}", "member_agent_ids": []}
    payload.update(overrides)
    resp = await client.post("/api/v1/channels", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    _created_channel_ids.append(uuid.UUID(data["channel"]["id"]))
    return data


def test_extract_mentions_matches_longest_name_first():
    class _A:
        def __init__(self, id_, name):
            self.id, self.name = id_, name

    short = _A(uuid.uuid4(), "Ath")
    long = _A(uuid.uuid4(), "Athos")
    found = _extract_mentions("oi #Athos, tudo bem?", [short, long])
    assert [a.id for a in found] == [long.id]


def test_extract_mentions_no_match_returns_empty():
    class _A:
        def __init__(self, id_, name):
            self.id, self.name = id_, name

    found = _extract_mentions("no mentions here", [_A(uuid.uuid4(), "Athos")])
    assert found == []


async def test_create_channel_freeform_without_project(client: AsyncClient):
    result = await _create_channel(client)
    channel = result["channel"]
    assert channel["project_id"] is None
    assert result["suggested_project_members"] == []
    member_types = sorted(m["is_human"] for m in channel["members"])
    assert member_types == [False] * 0 + [True]  # exactly one human member, no agents


async def test_create_channel_with_explicit_members(client: AsyncClient):
    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])])
    channel = result["channel"]
    agent_ids_in_channel = {m["agent_id"] for m in channel["members"] if not m["is_human"]}
    assert agent_ids_in_channel == {str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])}


async def test_create_channel_with_project_suggests_but_does_not_force_members(client: AsyncClient):
    result = await _create_channel(client, project_id=str(_STUB_PROJECT_ID))
    channel = result["channel"]
    # No membership rows exist for this fresh project, so suggestions are
    # empty -- but crucially, member_agent_ids being omitted must NOT have
    # auto-populated the channel's team from the project.
    agent_members = [m for m in channel["members"] if not m["is_human"]]
    assert agent_members == []


async def test_get_update_delete_channel(admin_client: AsyncClient):
    """Marcelo is admin -- authorize_action's "admin" bypass keeps
    update/delete working with zero delegation setup, same as before the
    "channel.manage" gate was added (2026-08-06)."""
    result = await _create_channel(admin_client)
    channel_id = result["channel"]["id"]

    get_resp = await admin_client.get(f"/api/v1/channels/{channel_id}")
    assert get_resp.status_code == 200

    patch_resp = await admin_client.patch(
        f"/api/v1/channels/{channel_id}", json={"name": "Renamed", "archived": True}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Renamed"
    assert patch_resp.json()["archived"] is True

    delete_resp = await admin_client.delete(f"/api/v1/channels/{channel_id}")
    assert delete_resp.status_code == 204
    _created_channel_ids.remove(uuid.UUID(channel_id))

    missing_resp = await admin_client.get(f"/api/v1/channels/{channel_id}")
    assert missing_resp.status_code == 404


async def test_clear_channel_messages_wipes_transcript_and_agent_sessions(admin_client: AsyncClient, monkeypatch):
    """The lighter "start this room over" action next to full delete
    (2026-08-06, Marcelo: "adicione um icone de limpeza do chat") -- wipes
    every message but keeps the channel/membership/tasks, and resets each
    member's hermes_session_id so a stale bridge session can't keep
    referencing a transcript the UI no longer shows."""
    from app.api.routes import channel as channel_routes

    async def fake_bridge_text(profile, message, hermes_session_id):
        return {"reply": "ok", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_call_bridge_text", fake_bridge_text)

    result = await _create_channel(admin_client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]
    member_id = result["channel"]["members"][0]["id"]

    async with AsyncSessionLocal() as db:
        member = await db.get(ChatChannelMember, uuid.UUID(member_id))
        member.hermes_session_id = "fake-bridge-session"
        await db.commit()

    # No mention -- broadcasts to the single agent member (2026-08-06,
    # "#all seja opcional"), so this also produces a real agent turn/reply.
    post_resp = await admin_client.post(f"/api/v1/channels/{channel_id}/messages", json={"content": "hello"})
    assert post_resp.status_code == 200
    assert len(post_resp.json()) == 2

    list_resp = await admin_client.get(f"/api/v1/channels/{channel_id}/messages")
    assert len(list_resp.json()) == 2

    clear_resp = await admin_client.delete(f"/api/v1/channels/{channel_id}/messages")
    assert clear_resp.status_code == 204

    list_resp = await admin_client.get(f"/api/v1/channels/{channel_id}/messages")
    assert list_resp.json() == []

    get_resp = await admin_client.get(f"/api/v1/channels/{channel_id}")
    assert get_resp.json()["members"][0]["hermes_session_id"] is None


async def test_attach_and_detach_project_is_mutable_after_creation(client: AsyncClient):
    result = await _create_channel(client)
    channel_id = result["channel"]["id"]
    assert result["channel"]["project_id"] is None

    attach_resp = await client.post(f"/api/v1/channels/{channel_id}/project", json={"project_id": str(_STUB_PROJECT_ID)})
    assert attach_resp.status_code == 200
    assert attach_resp.json()["project_id"] == str(_STUB_PROJECT_ID)

    detach_resp = await client.delete(f"/api/v1/channels/{channel_id}/project")
    assert detach_resp.status_code == 200
    assert detach_resp.json()["project_id"] is None


async def test_add_and_remove_member(admin_client: AsyncClient):
    """Marcelo is admin -- authorize_action's "admin" bypass keeps this
    working with zero delegation setup, same as before "channel.member.
    manage" was added (2026-08-05)."""
    result = await _create_channel(admin_client)
    channel_id = result["channel"]["id"]

    add_resp = await admin_client.post(
        f"/api/v1/channels/{channel_id}/members", json={"agent_id": str(_STUB_AGENT_IDS[0])}
    )
    assert add_resp.status_code == 201
    member_id = add_resp.json()["id"]

    dup_resp = await admin_client.post(
        f"/api/v1/channels/{channel_id}/members", json={"agent_id": str(_STUB_AGENT_IDS[0])}
    )
    assert dup_resp.status_code == 400

    remove_resp = await admin_client.delete(f"/api/v1/channels/{channel_id}/members/{member_id}")
    assert remove_resp.status_code == 204


async def test_cannot_remove_human_member(admin_client: AsyncClient):
    result = await _create_channel(admin_client)
    channel_id = result["channel"]["id"]
    human_member = next(m for m in result["channel"]["members"] if m["is_human"])

    resp = await admin_client.delete(f"/api/v1/channels/{channel_id}/members/{human_member['id']}")
    assert resp.status_code == 400


async def test_delegated_agent_can_add_member(admin_client: AsyncClient):
    """The concrete "orquestrador adiciona agentes que não foram colocados
    no canal" flow (2026-08-05): no delegation -> 403; once granted
    "channel.member.manage", the agent's own agt_ credential can add a
    member exactly like Marcelo via the UI."""
    result = await _create_channel(admin_client, member_agent_ids=[str(_STUB_AGENT_IDS[1])])
    channel_id = result["channel"]["id"]
    orchestrator_agent_id = _STUB_AGENT_IDS[1]

    cred_resp = await admin_client.post(
        "/api/v1/governed/agent-credentials",
        json={"agent_id": str(orchestrator_agent_id), "label": "orchestrator-add-member-test"},
    )
    assert cred_resp.status_code == 201, cred_resp.text
    agent_token = cred_resp.json()["token"]
    credential_id = cred_resp.json()["credential_id"]
    agent_headers = {"Authorization": f"Bearer {agent_token}"}

    transport = ASGITransport(app=app)
    delegation_id = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test", headers=agent_headers) as agent_client:
            denied = await agent_client.post(
                f"/api/v1/channels/{channel_id}/members", json={"agent_id": str(_STUB_AGENT_IDS[0])}
            )
            assert denied.status_code == 403

            delegation_resp = await admin_client.post(
                "/api/v1/governed/authority-delegations",
                json={
                    "grantee_agent_id": str(orchestrator_agent_id),
                    "allowed_actions": ["channel.member.manage"],
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                },
            )
            assert delegation_resp.status_code == 201, delegation_resp.text
            delegation_id = delegation_resp.json()["id"]

            allowed = await agent_client.post(
                f"/api/v1/channels/{channel_id}/members", json={"agent_id": str(_STUB_AGENT_IDS[0])}
            )
            assert allowed.status_code == 201, allowed.text
    finally:
        if delegation_id:
            await admin_client.post(f"/api/v1/governed/authority-delegations/{delegation_id}:revoke")
        await admin_client.post(f"/api/v1/governed/agent-credentials/{credential_id}:revoke")


async def test_post_message_without_mention_wakes_every_agent_member(client: AsyncClient, monkeypatch):
    """2026-08-06, Marcelo: "quando não especificar o agente a mensagem é
    para todos e #all seja opcional" -- a message that names no agent at
    all is a broadcast, same as an explicit #all, not a no-op."""
    from app.api.routes import channel as channel_routes

    async def fake_bridge_text(profile, message, hermes_session_id):
        return {"reply": f"ok from {profile}", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_call_bridge_text", fake_bridge_text)

    result = await _create_channel(
        client, member_agent_ids=[str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])]
    )
    channel_id = result["channel"]["id"]

    resp = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"content": "just an idea, no one mentioned"}
    )
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) == 3  # human + both agents
    assert messages[0]["author_type"] == "human"
    agent_ids_replied = {m["author_agent_id"] for m in messages if m["author_type"] == "agent"}
    assert agent_ids_replied == {str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])}

    list_resp = await client.get(f"/api/v1/channels/{channel_id}/messages")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 3


async def test_posting_a_mention_wakes_that_agent_with_shared_context(client: AsyncClient, monkeypatch):
    """Regression test (2026-08-06, Marcelo: "enviei a mensagem e não foi
    feito nada. Não apareceu ele trabalhando"): _build_shared_context used
    to build its member-name list as a generator expression with `await`
    inside `", ".join(...)` -- that's an async-generator expression (PEP
    530), which str.join() can't consume ("can only join an iterable").
    Every single mention-triggered turn raised here, always before ever
    reaching the bridge -- invisible because the old exception handling in
    stream_channel_message only caught httpx.HTTPError, so the TypeError
    escaped uncaught and the SSE connection just died with nothing sent.
    This exercises the same _build_shared_context call via the
    non-streaming POST /messages route, which would have caught it."""
    from app.api.routes import channel as channel_routes

    async def fake_bridge_text(profile, message, hermes_session_id):
        # Confirms _build_shared_context actually ran and produced real
        # content instead of raising before the bridge was ever called.
        assert "Membros:" in message
        return {"reply": "ok, testado", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_call_bridge_text", fake_bridge_text)

    async with AsyncSessionLocal() as db:
        agent = await db.get(Agent, _STUB_AGENT_IDS[0])
        agent_name = agent.name

    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]

    resp = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"content": f"#{agent_name} oi, tudo bem?"}
    )
    assert resp.status_code == 200, resp.text
    messages = resp.json()
    assert len(messages) == 2
    assert messages[0]["author_type"] == "human"
    assert messages[1]["author_type"] == "agent"
    assert messages[1]["content"] == "ok, testado"
    assert messages[1]["author_agent_id"] == str(_STUB_AGENT_IDS[0])


async def test_improve_prompt_requires_orchestrator(client: AsyncClient):
    """2026-08-06, Marcelo: "preciso que o próprio orquestrador me ajude a
    criar o texto" -- there's nothing to call if the channel has no
    orchestrator designated yet."""
    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]

    # Raised before StreamingResponse is even constructed -- a plain 400,
    # not an SSE event: error (that framing only applies once the stream
    # has actually started, i.e. after the orchestrator precondition).
    async with client.stream(
        "GET",
        f"/api/v1/channels/{channel_id}/improve-prompt/stream",
        params={"draft": "oi", "instruction": "mais formal"},
    ) as resp:
        assert resp.status_code == 400
        body = "".join([chunk async for chunk in resp.aiter_text()])
    assert "orchestrator" in body.lower()


async def test_improve_prompt_rewrites_via_orchestrator(client: AsyncClient, monkeypatch):
    """Confirming only replaces the compose draft -- never a real channel
    turn: no ChatChannelMessage is created, and the bridge call always
    starts fresh (hermes_session_id=None) so it can't interfere with the
    orchestrator's own conversational continuity in the room."""
    from app.api.routes import channel as channel_routes

    async def fake_bridge_text(profile, message, hermes_session_id):
        assert hermes_session_id is None
        assert "instrução de melhoria" in message.lower()
        return {"reply": "Texto melhorado.", "session_id": "unused"}

    monkeypatch.setattr(channel_routes, "_call_bridge_text", fake_bridge_text)

    result = await _create_channel(
        client,
        member_agent_ids=[str(_STUB_AGENT_IDS[0])],
        orchestrator_agent_id=str(_STUB_AGENT_IDS[0]),
    )
    channel_id = result["channel"]["id"]

    async with client.stream(
        "GET",
        f"/api/v1/channels/{channel_id}/improve-prompt/stream",
        params={"draft": "oi pessoal", "instruction": "deixar mais formal"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join([chunk async for chunk in resp.aiter_text()])
    assert '"improved_text": "Texto melhorado."' in body

    list_resp = await client.get(f"/api/v1/channels/{channel_id}/messages")
    assert list_resp.json() == []  # never became a real channel message


async def test_mention_all_wakes_every_agent_member(client: AsyncClient, monkeypatch):
    """2026-08-06, Marcelo: "como enviar a mensagem para todos os agentes,
    quando envio o comando sem informar o agente não [funciona]" -- #all
    is a deliberate broadcast, distinct from any real agent name, and
    wakes every current agent member instead of requiring one #Name per
    agent."""
    from app.api.routes import channel as channel_routes

    async def fake_bridge_text(profile, message, hermes_session_id):
        return {"reply": f"ok from {profile}", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_call_bridge_text", fake_bridge_text)

    result = await _create_channel(
        client, member_agent_ids=[str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])]
    )
    channel_id = result["channel"]["id"]

    resp = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"content": "#all bom dia, equipe"}
    )
    assert resp.status_code == 200, resp.text
    messages = resp.json()
    assert len(messages) == 3  # human + both agents
    agent_ids_replied = {m["author_agent_id"] for m in messages if m["author_type"] == "agent"}
    assert agent_ids_replied == {str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])}


async def test_mentioned_agents_run_concurrently_not_sequentially(client: AsyncClient, monkeypatch):
    """2026-08-06, Marcelo: "o chat do canal deve executar vários agentes
    ao mesmo tempo... veja a execução do chat da conversations" -- each
    mentioned agent's bridge call must run in parallel (own DB session, see
    _wake_agent_turn_isolated), not one after another. Regression guard:
    asserts both bridge calls actually *start* close together, rather than
    asserting on an absolute total-wall-clock threshold -- the latter is
    flaky under real system load (this environment also runs a live dev
    stack via dev.sh against the same DB), where even genuinely concurrent
    calls can take longer in absolute terms without ever being sequential
    relative to each other."""
    import asyncio
    import time

    from app.api.routes import channel as channel_routes

    call_started_at: list[float] = []

    async def slow_bridge_text(profile, message, hermes_session_id):
        call_started_at.append(time.monotonic())
        await asyncio.sleep(0.3)
        return {"reply": f"ok from {profile}", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_call_bridge_text", slow_bridge_text)

    result = await _create_channel(
        client, member_agent_ids=[str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])]
    )
    channel_id = result["channel"]["id"]

    resp = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"content": "#all bom dia, equipe"}
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 3  # human + both agents
    assert len(call_started_at) == 2
    gap = max(call_started_at) - min(call_started_at)
    # A sequential loop would start the second call only after the first's
    # 0.3s sleep finishes -- a ~0.3s gap. Concurrent calls start together,
    # so any gap here should be negligible scheduling jitter, not ~0.3s.
    assert gap < 0.2, f"expected both bridge calls to start together, {gap:.2f}s apart"


async def test_stream_channel_message_emits_agent_started_before_replies(client: AsyncClient, monkeypatch):
    """Exercises the actual SSE endpoint the Channels UI uses
    (useStreamChannelMessage), not just the plain POST route the other
    tests above proxy through. 2026-08-06, Marcelo: "precisa ver a
    quantidade de processos em paralelo... com o detalhamento de cada
    agente" -- the frontend needs an `agent_started` event per mentioned
    agent, up front, before their (possibly slow, concurrent) replies
    arrive, so it can render a live "N agentes trabalhando" strip."""
    from app.api.routes import channel as channel_routes

    async def fake_bridge_stream(bridge_params):
        yield {"done": True, "reply": f"ok from {bridge_params['profile']}", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_iter_bridge_stream", fake_bridge_stream)

    result = await _create_channel(
        client, member_agent_ids=[str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])]
    )
    channel_id = result["channel"]["id"]

    async with client.stream(
        "GET",
        f"/api/v1/channels/{channel_id}/messages/stream",
        params={"content": "#all bom dia, equipe"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join([chunk async for chunk in resp.aiter_text()])

    assert body.count("event: agent_started") == 2
    # Both agent_started events precede any agent reply data -- they're
    # fired up front, all at once, before the concurrent bridge calls even
    # start (see stream_channel_message).
    last_started_at = body.rindex("event: agent_started")
    assert body.index('"ok from') > last_started_at
    assert body.count('"ok from') == 2  # one reply per agent
    assert "event: done" in body


async def test_stream_channel_message_relays_tool_steps_live(client: AsyncClient, monkeypatch):
    """2026-08-06, Marcelo: "traz o passo a passo de ferramentas em tempo
    real também" -- tool_start/tool_complete events from the bridge's
    /v1/chat/stream must reach the browser as `agent_step` SSE events
    while the turn is still in flight, not just the final persisted
    message once it's done."""
    from app.api.routes import channel as channel_routes

    async def fake_bridge_stream(bridge_params):
        yield {"tool_start": {"tool_id": "t1", "name": "Read", "context": "Reading file.py"}}
        yield {"tool_complete": {"tool_id": "t1", "name": "Read", "summary": "Read file.py"}}
        yield {"done": True, "reply": f"ok from {bridge_params['profile']}", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_iter_bridge_stream", fake_bridge_stream)

    async with AsyncSessionLocal() as db:
        agent = await db.get(Agent, _STUB_AGENT_IDS[0])
        agent_name = agent.name

    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]

    async with client.stream(
        "GET",
        f"/api/v1/channels/{channel_id}/messages/stream",
        params={"content": f"#{agent_name} oi"},
    ) as resp:
        assert resp.status_code == 200
        body = "".join([chunk async for chunk in resp.aiter_text()])

    assert body.count("event: agent_step") == 2
    assert '"tool_id": "t1"' in body
    assert '"name": "Read"' in body
    assert '"done": false' in body  # tool_start
    assert '"done": true' in body  # tool_complete
    assert '"summary": "Read file.py"' in body
    # The step events precede the final reply -- live, not after the fact.
    last_step_at = body.rindex("event: agent_step")
    assert body.index('"ok from') > last_step_at
    assert "event: done" in body


async def test_onboarding_note_only_on_first_turn(client: AsyncClient, monkeypatch):
    """2026-08-06, Marcelo: "cada agente quando iniciar no grupo precisa
    receber uma mensagem informando que ele está dentro do contexto de um
    grupo de trabalho... para ele poder saber como interagir no ambiente."
    Fires once (member.hermes_session_id is the gate -- see
    _wake_agent_turn): the first mention gets the onboarding note
    prepended, a second mention of the same agent in the same channel
    does not repeat it."""
    from app.api.routes import channel as channel_routes

    seen_messages: list[str] = []

    async def fake_bridge_text(profile, message, hermes_session_id):
        seen_messages.append(message)
        return {"reply": "ok", "session_id": "fake-session"}

    monkeypatch.setattr(channel_routes, "_call_bridge_text", fake_bridge_text)

    async with AsyncSessionLocal() as db:
        agent = await db.get(Agent, _STUB_AGENT_IDS[0])
        agent_name = agent.name

    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]

    first = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"content": f"#{agent_name} primeira mensagem"}
    )
    assert first.status_code == 200, first.text
    assert "Contexto interno" in seen_messages[0]
    assert "cumprimente" in seen_messages[0]

    second = await client.post(
        f"/api/v1/channels/{channel_id}/messages", json={"content": f"#{agent_name} segunda mensagem"}
    )
    assert second.status_code == 200, second.text
    assert "Contexto interno" not in seen_messages[1]


async def test_channel_task_lifecycle_without_project_stays_lightweight(client: AsyncClient):
    result = await _create_channel(client)
    channel_id = result["channel"]["id"]

    create_resp = await client.post(f"/api/v1/channels/{channel_id}/tasks", json={"title": "Investigar algo"})
    assert create_resp.status_code == 201
    task = create_resp.json()
    assert task["project_task_id"] is None
    assert task["status"] == "todo"

    patch_resp = await client.patch(
        f"/api/v1/channels/{channel_id}/tasks/{task['id']}", json={"status": "doing"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "doing"

    promote_resp = await client.post(f"/api/v1/channels/{channel_id}/tasks/{task['id']}:promote")
    assert promote_resp.status_code == 400  # no project attached yet


async def test_channel_task_promotes_to_real_project_task(client: AsyncClient):
    result = await _create_channel(client, project_id=str(_STUB_PROJECT_ID))
    channel_id = result["channel"]["id"]

    create_resp = await client.post(f"/api/v1/channels/{channel_id}/tasks", json={"title": "Tarefa promovivel"})
    assert create_resp.status_code == 201
    task = create_resp.json()
    assert task["project_task_id"] is None

    promote_resp = await client.post(f"/api/v1/channels/{channel_id}/tasks/{task['id']}:promote")
    assert promote_resp.status_code == 200
    promoted = promote_resp.json()
    assert promoted["project_task_id"] is not None

    second_promote = await client.post(f"/api/v1/channels/{channel_id}/tasks/{task['id']}:promote")
    assert second_promote.status_code == 400


# --------------------------------------------------------------------------
# Agent function (role) + delegation-needs-approval (2026-08-05, see
# docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md)
# --------------------------------------------------------------------------


async def test_member_role_is_prefilled_from_agent_default_role(client: AsyncClient):
    set_role_resp = await client.patch(f"/api/v1/agents/{_STUB_AGENT_IDS[0]}", json={"default_role": "qa"})
    assert set_role_resp.status_code == 200, set_role_resp.text

    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    member = next(m for m in result["channel"]["members"] if not m["is_human"])
    assert member["role"] == "qa"


async def test_updating_channel_role_syncs_project_membership(admin_client: AsyncClient):
    """2026-08-06, Marcelo: "eu acho que é a mesma coisa função no canal e
    projeto" -- setting a member's channel role, when the channel has a
    project attached, upserts a matching ProjectAgentMembership so the two
    views don't visibly diverge, without deleting/merging the underlying
    concepts (see _sync_project_membership_role's docstring: the
    membership row still gates real task-assignment eligibility
    elsewhere)."""
    result = await _create_channel(
        admin_client, project_id=str(_STUB_PROJECT_ID), member_agent_ids=[str(_STUB_AGENT_IDS[0])]
    )
    channel_id = result["channel"]["id"]
    member = next(m for m in result["channel"]["members"] if not m["is_human"])

    async with AsyncSessionLocal() as db:
        pre_existing = (await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == _STUB_PROJECT_ID,
            ProjectAgentMembership.agent_id == _STUB_AGENT_IDS[0],
        ))).scalar_one_or_none()
        assert pre_existing is None

    resp = await admin_client.patch(
        f"/api/v1/channels/{channel_id}/members/{member['id']}", json={"role": "designer"}
    )
    assert resp.status_code == 200

    async with AsyncSessionLocal() as db:
        membership = (await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == _STUB_PROJECT_ID,
            ProjectAgentMembership.agent_id == _STUB_AGENT_IDS[0],
        ))).scalar_one()
        assert membership.role == "designer"

    # Changing it again updates the same row, never duplicates it.
    resp2 = await admin_client.patch(
        f"/api/v1/channels/{channel_id}/members/{member['id']}", json={"role": "qa"}
    )
    assert resp2.status_code == 200

    async with AsyncSessionLocal() as db:
        rows = list((await db.execute(select(ProjectAgentMembership).where(
            ProjectAgentMembership.project_id == _STUB_PROJECT_ID,
            ProjectAgentMembership.agent_id == _STUB_AGENT_IDS[0],
        ))).scalars())
        assert len(rows) == 1
        assert rows[0].role == "qa"


async def test_orchestrator_can_edit_member_role(admin_client: AsyncClient):
    """Marcelo is admin -- authorize_action's "admin" bypass means this
    keeps working with zero delegation setup, same as before the
    "channel.member.role.assign" gate was added (2026-08-05)."""
    result = await _create_channel(admin_client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]
    member = next(m for m in result["channel"]["members"] if not m["is_human"])

    resp = await admin_client.patch(
        f"/api/v1/channels/{channel_id}/members/{member['id']}", json={"role": "documentation"}
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "documentation"

    invalid_resp = await admin_client.patch(
        f"/api/v1/channels/{channel_id}/members/{member['id']}", json={"role": "not-a-real-role"}
    )
    assert invalid_resp.status_code == 400


async def test_delegated_agent_can_edit_member_role(admin_client: AsyncClient, bridge_client: AsyncClient):
    """The concrete "Athos as orchestrator" flow (2026-08-05, Marcelo:
    "posso mandar o pedir para o agente orquestrador alterar os roles dos
    agentes"): an agent with no delegation gets 403; once granted an
    AuthorityDelegation for "channel.member.role.assign", its own agt_
    credential can PATCH a member's role exactly like Marcelo via the UI --
    same governed-authority mechanism already used for
    "governance.approval.decide", not a new channel-specific permission."""
    result = await _create_channel(admin_client, member_agent_ids=[str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])])
    channel_id = result["channel"]["id"]
    member = next(m for m in result["channel"]["members"] if not m["is_human"])
    orchestrator_agent_id = _STUB_AGENT_IDS[1]

    cred_resp = await admin_client.post(
        "/api/v1/governed/agent-credentials",
        json={"agent_id": str(orchestrator_agent_id), "label": "orchestrator-role-edit-test"},
    )
    assert cred_resp.status_code == 201, cred_resp.text
    agent_token = cred_resp.json()["token"]
    credential_id = cred_resp.json()["credential_id"]
    agent_headers = {"Authorization": f"Bearer {agent_token}"}

    transport = ASGITransport(app=app)
    delegation_id = None
    try:
        async with AsyncClient(transport=transport, base_url="http://test", headers=agent_headers) as agent_client:
            denied = await agent_client.patch(
                f"/api/v1/channels/{channel_id}/members/{member['id']}", json={"role": "qa"}
            )
            assert denied.status_code == 403

            delegation_resp = await admin_client.post(
                "/api/v1/governed/authority-delegations",
                json={
                    "grantee_agent_id": str(orchestrator_agent_id),
                    "allowed_actions": ["channel.member.role.assign"],
                    "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                },
            )
            assert delegation_resp.status_code == 201, delegation_resp.text
            delegation_id = delegation_resp.json()["id"]

            allowed = await agent_client.patch(
                f"/api/v1/channels/{channel_id}/members/{member['id']}", json={"role": "qa"}
            )
            assert allowed.status_code == 200, allowed.text
            assert allowed.json()["role"] == "qa"
    finally:
        if delegation_id:
            await admin_client.post(f"/api/v1/governed/authority-delegations/{delegation_id}:revoke")
        await admin_client.post(f"/api/v1/governed/agent-credentials/{credential_id}:revoke")


async def test_propose_self_assignment_within_own_role_needs_no_approval(client: AsyncClient, bridge_client: AsyncClient):
    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]
    member = next(m for m in result["channel"]["members"] if not m["is_human"])
    await client.patch(f"/api/v1/channels/{channel_id}/members/{member['id']}", json={"role": "qa"})

    resp = await bridge_client.post(
        f"/api/v1/channels/{channel_id}/tasks/propose",
        json={
            "acting_agent_slug": _STUB_AGENT_SLUGS[0],
            "title": "Testar o próprio módulo",
            "assignee_agent_slug": _STUB_AGENT_SLUGS[0],
            "role_required": "qa",
        },
    )
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["approval_id"] is None
    assert task["approval_status"] is None
    assert task["created_by_agent_id"] == str(_STUB_AGENT_IDS[0])


async def test_propose_delegation_to_another_agent_always_needs_approval(
    client: AsyncClient, bridge_client: AsyncClient, admin_client: AsyncClient
):
    result = await _create_channel(
        client, member_agent_ids=[str(_STUB_AGENT_IDS[0]), str(_STUB_AGENT_IDS[1])]
    )
    channel_id = result["channel"]["id"]

    resp = await bridge_client.post(
        f"/api/v1/channels/{channel_id}/tasks/propose",
        json={
            "acting_agent_slug": _STUB_AGENT_SLUGS[0],
            "title": "Escreva a documentação disso",
            "assignee_agent_slug": _STUB_AGENT_SLUGS[1],
        },
    )
    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["approval_id"] is not None
    assert task["approval_status"] == "pending"
    _created_approval_ids.append(uuid.UUID(task["approval_id"]))

    # Marcelo (JWT, admin) decides via the *existing* Governance route --
    # no channel-specific decision endpoint was built, by design.
    decide_resp = await admin_client.post(
        f"/api/v1/governance/approvals/{task['approval_id']}/approve", json={"decided_by": "Marcelo"}
    )
    assert decide_resp.status_code == 200, decide_resp.text
    assert decide_resp.json()["status"] == "approved"

    tasks_resp = await client.get(f"/api/v1/channels/{channel_id}/tasks")
    assert tasks_resp.status_code == 200
    updated_task = next(t for t in tasks_resp.json() if t["id"] == task["id"])
    assert updated_task["approval_status"] == "approved"

    # The channel got a system narration message when the Approval was decided.
    messages_resp = await client.get(f"/api/v1/channels/{channel_id}/messages")
    system_messages = [m for m in messages_resp.json() if m["author_type"] == "system"]
    assert any("aprovado" in m["content"].lower() or "approved" in m["content"].lower() for m in system_messages)


async def test_propose_rejects_acting_agent_not_a_channel_member(client: AsyncClient, bridge_client: AsyncClient):
    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[1])])
    channel_id = result["channel"]["id"]

    resp = await bridge_client.post(
        f"/api/v1/channels/{channel_id}/tasks/propose",
        json={
            "acting_agent_slug": _STUB_AGENT_SLUGS[0],  # not a member of this channel
            "title": "Não deveria conseguir propor isso",
            "assignee_agent_slug": _STUB_AGENT_SLUGS[1],
        },
    )
    assert resp.status_code == 403


async def test_propose_task_requires_bridge_token(client: AsyncClient):
    result = await _create_channel(client, member_agent_ids=[str(_STUB_AGENT_IDS[0])])
    channel_id = result["channel"]["id"]

    # `client` carries a real JWT but no X-Bridge-Token -- this path is
    # bridge-token-gated (main.py's dedicated bypass), not JWT-open.
    resp = await client.post(
        f"/api/v1/channels/{channel_id}/tasks/propose",
        json={
            "acting_agent_slug": _STUB_AGENT_SLUGS[0],
            "title": "Sem bridge token",
            "assignee_agent_slug": _STUB_AGENT_SLUGS[0],
        },
        headers={"Authorization": ""},
    )
    assert resp.status_code == 401
