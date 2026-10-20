"""Feedback routing: the outcome goes back to the channel that asked.

Messages executes everything, but until 2026-08-13 the result stayed inside
Messages -- whoever asked from the Workspace, the Assistant or Telegram
never learned their task had finished.

The rules these protect (all agreed with Marcelo):
  - only a terminal outcome is fed back ("o feedback só é enviado quando for
    concluido ou erro da task"), and "failed" counts, including a dispatch
    that never ran;
  - the channel decides the destination, and Telegram answers the chat that
    asked rather than the configured home channel;
  - an agent's request is left alone -- requires_response/reply_to_id
    already routes that answer, and delivering here too would double it;
  - delivery is idempotent, and an undelivered outcome stays findable
    instead of being lost.
"""
import uuid

import httpx
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.feedback import deliver_feedback, run_feedback_pass
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.chat import ChatMessage, ChatSession
from app.db.models.demand import AgentDemand
from app.db.models.notification import Notification


@pytest_asyncio.fixture
async def agent():
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        a = Agent(
            name=f"Feedback {suffix}", agent_type="executor",
            runtime_type="claude", profile_slug=f"fb-{suffix}",
        )
        session.add(a)
        await session.commit()
        agent_id = a.id

    yield agent_id

    async with AsyncSessionLocal() as session:
        ids = (
            await session.execute(
                select(AgentDemand.id).where(AgentDemand.target_agent_id == agent_id)
            )
        ).scalars().all()
        for did in ids:
            await session.execute(
                delete(Notification).where(Notification.event_key.like(f"demand-feedback:{did}%"))
            )
        await session.execute(delete(AgentDemand).where(AgentDemand.target_agent_id == agent_id))
        chat_ids = (
            await session.execute(select(ChatSession.id).where(ChatSession.agent_id == agent_id))
        ).scalars().all()
        if chat_ids:
            await session.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(chat_ids)))
            await session.execute(delete(ChatSession).where(ChatSession.id.in_(chat_ids)))
        await session.execute(delete(Agent).where(Agent.id == agent_id))
        await session.commit()


async def _finished(agent_id, *, channel=None, channel_ref=None,
                    status="completed", result="tudo certo", body="faz isso") -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        d = AgentDemand(
            from_agent="tester",
            from_agent_id=agent_id,
            target_agent_id=agent_id,
            subject=f"pedido {uuid.uuid4().hex[:6]}",
            body=body,
            origin_type="task",
            dispatch_status=status,
            dispatch_attempts=1,
            dispatch_result=result,
            channel=channel,
            channel_ref=channel_ref,
        )
        session.add(d)
        await session.commit()
        return d.id


async def _notifications_for(demand_id) -> list[Notification]:
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.execute(
                    select(Notification).where(
                        Notification.event_key.like(f"demand-feedback:{demand_id}%")
                    )
                )
            ).scalars().all()
        )


async def test_failed_agent_request_receives_one_linked_feedback(agent):
    demand_id = await _finished(agent, channel="agent", status="failed")
    async with AsyncSessionLocal() as session:
        item = await session.get(AgentDemand, demand_id)
        item.working_path = "/root/project/example"
        item.dispatch_error = "Execution unavailable"
        await deliver_feedback(session, item)
        await session.commit()
        await deliver_feedback(session, item)
        await session.commit()
        replies = list((await session.execute(
            select(AgentDemand).where(AgentDemand.reply_to_id == demand_id)
        )).scalars())
        assert len(replies) == 1
        assert replies[0].target_agent_id == agent
        assert replies[0].requires_response is False
        assert replies[0].scheduled_at is None
        assert replies[0].dispatch_status == "completed"
        assert "/root/project/example" in replies[0].body
        assert item.dispatch_status == "failed"
        assert item.feedback_sent_at is not None


async def test_successful_assistant_task_is_recorded_without_an_alert(agent):
    """A normal completion remains in Messages and does not ring the bell."""
    demand_id = await _finished(agent, channel="assistant")

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, d) is True
        await session.commit()

    assert await _notifications_for(demand_id) == []
    async with AsyncSessionLocal() as session:
        assert (await session.get(AgentDemand, demand_id)).feedback_sent_at is not None


async def test_workspace_feedback_returns_to_the_conversation(agent):
    async with AsyncSessionLocal() as session:
        chat = ChatSession(agent_id=agent, title="Feedback return test")
        session.add(chat)
        await session.commit()
        chat_id = chat.id

    demand_id = await _finished(agent, channel="workspace", channel_ref=str(chat_id))
    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, demand) is True
        await session.commit()

    async with AsyncSessionLocal() as session:
        replies = list((await session.execute(
            select(ChatMessage).where(ChatMessage.session_id == chat_id)
        )).scalars().all())
        assert len(replies) == 1
        assert replies[0].responding_agent_id == agent
        assert "concluída" in replies[0].content
    assert await _notifications_for(demand_id) == []


async def test_a_failure_is_told_apart_from_a_success(agent):
    """Severity mirrors the outcome: the bell holds thousands of routine
    info rows, and an error that looks like all of them is invisible."""
    demand_id = await _finished(agent, channel="assistant", status="failed", result="")
    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        d.dispatch_error = "o agente não tem runtime configurado"
        await deliver_feedback(session, d)
        await session.commit()

    notes = await _notifications_for(demand_id)
    assert notes[0].severity == "error"
    assert "runtime" in notes[0].message


async def test_nothing_is_sent_while_still_running(agent):
    """Only terminal outcomes: a message still in flight has nothing to
    report, and reporting early would be wrong, not just noisy."""
    demand_id = await _finished(agent, channel="workspace", status="running")

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, d) is False

    assert await _notifications_for(demand_id) == []


async def test_delivery_happens_once(agent):
    """Idempotent by feedback_sent_at, so a re-run can't send the same
    outcome twice."""
    demand_id = await _finished(agent, channel="assistant")

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, d) is True
        await session.commit()
    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert d.feedback_sent_at is not None
        assert await deliver_feedback(session, d) is False

    assert await _notifications_for(demand_id) == []


async def test_an_agents_own_request_is_left_to_its_reply_path(agent):
    """requires_response/reply_to_id already routes an agent's answer back;
    delivering here too would put the same outcome in its inbox twice."""
    demand_id = await _finished(agent, channel="agent")

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, d) is False

    assert await _notifications_for(demand_id) == []


async def test_telegram_without_a_chat_does_not_create_a_success_alert(agent, monkeypatch):
    """A requested return without an address stays owed without bell noise."""
    demand_id = await _finished(
        agent,
        channel="telegram",
        channel_ref=None,
        body="Faça isso e me retorne pelo Telegram.",
    )

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, d) is False
        await session.commit()

    assert await _notifications_for(demand_id) == []
    async with AsyncSessionLocal() as session:
        assert (await session.get(AgentDemand, demand_id)).feedback_sent_at is None


async def test_telegram_answers_the_chat_that_asked(agent, monkeypatch):
    sent: dict = {}

    # Takes (db, demand) since 2026-08-13: picking the sending bot needs a
    # session to look the agent up.
    async def _fake_deliver(db, demand):
        sent["target"] = demand.channel_ref
        return True

    monkeypatch.setattr("app.core.feedback._deliver_telegram", _fake_deliver)
    demand_id = await _finished(
        agent,
        channel="telegram",
        channel_ref="-100123456",
        body="Faça isso e me responda no Telegram.",
    )

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, d) is True
        await session.commit()

    assert sent["target"] == "-100123456", "must answer the asking chat, not the home channel"
    assert await _notifications_for(demand_id) == []


async def test_telegram_metadata_alone_does_not_authorize_external_feedback(agent, monkeypatch):
    """The message text, not transport metadata alone, opts into Telegram.

    This covers stale/bad rows such as channel_ref="telegram": they finish
    without retrying an invalid external destination forever or creating a
    routine success alert.
    """
    async def _unexpected_delivery(*args, **kwargs):
        raise AssertionError("Telegram delivery must not run without an explicit request")

    monkeypatch.setattr("app.core.feedback._deliver_telegram", _unexpected_delivery)
    demand_id = await _finished(
        agent,
        channel="telegram",
        channel_ref="telegram",
        body="Registre apenas o resultado no Messages.",
    )

    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, demand) is True
        await session.commit()

    async with AsyncSessionLocal() as session:
        demand = await session.get(AgentDemand, demand_id)
        assert demand.feedback_sent_at is not None
    assert await _notifications_for(demand_id) == []


async def test_the_sweep_picks_up_what_inline_delivery_missed(agent):
    """An outcome that reached a terminal state without its feedback going
    out -- app restarted mid-delivery, channel down -- must still be found
    afterwards. That is why feedback_sent_at is a column, not a log line."""
    demand_id = await _finished(agent, channel="assistant")

    async with AsyncSessionLocal() as session:
        assert await run_feedback_pass(session) >= 1

    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert d.feedback_sent_at is not None


async def test_a_failed_delivery_does_not_poison_the_next_sweep(agent, monkeypatch):
    """Reproduces a real production stall: three terminal messages sat with
    feedback owed for days while every sweep crashed on the first one.

    The failed external return remains owed while the execution itself stays
    in Messages. Retrying it must not block later outcomes in the sweep."""
    class _DownClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **k):
            raise httpx.ConnectError("bridge down")

    monkeypatch.setattr("app.core.feedback.httpx.AsyncClient", _DownClient)

    stuck = await _finished(
        agent,
        channel="telegram",
        channel_ref="1085550644",
        status="failed",
        body="Quando terminar, responda no Telegram.",
    )
    async with AsyncSessionLocal() as session:
        await run_feedback_pass(session)

    async with AsyncSessionLocal() as session:
        assert (await session.get(AgentDemand, stuck)).feedback_sent_at is None, (
            "a send that never went out must stay visibly owed"
        )
    notes = await _notifications_for(stuck)
    assert len(notes) == 1
    assert notes[0].severity == "error"

    # The next sweep must survive the still-owed message and keep delivering
    # the ones behind it.
    reachable = await _finished(agent, channel="assistant")
    async with AsyncSessionLocal() as session:
        assert await run_feedback_pass(session) >= 1

    async with AsyncSessionLocal() as session:
        assert (await session.get(AgentDemand, reachable)).feedback_sent_at is not None
    assert len(await _notifications_for(stuck)) == 1


async def test_telegram_answers_through_the_receiving_agents_bot(agent, monkeypatch):
    """Every agent has its own Telegram bot, so the answer has to go out
    through the bot of the agent that received the request -- otherwise it
    arrives from an agent that never ran the work. The chat id can't
    disambiguate: it is the same value across every profile."""
    sent: dict = {}

    class _FakeResponse:
        def raise_for_status(self): pass

    class _FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            assert headers == {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
            sent.update(json or {})
            return _FakeResponse()

    monkeypatch.setattr("app.core.feedback.httpx.AsyncClient", _FakeClient)

    async with AsyncSessionLocal() as session:
        a = await session.get(Agent, agent)
        a.telegram_account = "HermesTestbot"
        a.profile_slug = f"prof-{uuid.uuid4().hex[:6]}"
        await session.commit()
        slug = a.profile_slug

    demand_id = await _finished(
        agent,
        channel="telegram",
        channel_ref="1085550644",
        body="Quando terminar, responda no Telegram.",
    )
    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        assert await deliver_feedback(session, d) is True
        await session.commit()

    assert sent["target"] == "telegram:1085550644", "must answer the asking chat"
    assert sent["profile"] == slug, "must send through the receiving agent's own bot"


async def test_an_agent_without_a_telegram_bot_sends_no_profile(agent, monkeypatch):
    """Porthus, Aramis and Dartan have no bot. Naming a profile that has none
    would 404 at the bridge; omitting it fails visibly instead of silently
    answering as somebody else."""
    sent: dict = {}

    class _FakeResponse:
        def raise_for_status(self): pass

    class _FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None, headers=None):
            assert headers == {"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN}
            sent.update(json or {})
            return _FakeResponse()

    monkeypatch.setattr("app.core.feedback.httpx.AsyncClient", _FakeClient)

    async with AsyncSessionLocal() as session:
        a = await session.get(Agent, agent)
        a.telegram_account = None
        await session.commit()

    demand_id = await _finished(
        agent,
        channel="telegram",
        channel_ref="1085550644",
        body="Quando terminar, responda no Telegram.",
    )
    async with AsyncSessionLocal() as session:
        d = await session.get(AgentDemand, demand_id)
        await deliver_feedback(session, d)
        await session.commit()

    assert "profile" not in sent


def test_asking_for_telegram_in_the_body_is_recognised():
    """A request can ask for its answer on Telegram in plain words
    (2026-08-13, Marcelo: "eu também posso solicitar um retorno também pelo
    telegram no corpo da tarefa") -- the system reads that instead of relying
    on the agent to interpret it."""
    from app.core.feedback import wants_telegram_reply

    for text in (
        "Liste /root/ e me responda no telegram",
        "Retorne pelo Telegram quando terminar",
        "me avise pelo Telegram assim que rodar",
        "Telegram: manda a resposta lá",
    ):
        assert wants_telegram_reply(text), text


def test_merely_mentioning_telegram_does_not_hijack_the_reply():
    """Deliberately narrow: a request *about* Telegram is not a request to be
    answered *on* Telegram. Being missed is recoverable (the in-app
    notification still happens); being wrong sends someone's output to a chat
    that never asked for it."""
    from app.core.feedback import wants_telegram_reply

    for text in (
        "Analise o código do bot do telegram",
        "Corrija o envio de mensagens do gateway",
        "Responda o mais rápido possível",
        "Não me responda no Telegram; registre somente no Messages.",
        "Sem retorno pelo Telegram.",
        "",
        None,
    ):
        assert not wants_telegram_reply(text), text


def test_telegram_bot_name_resolves_to_the_target_profiles_home_chat(monkeypatch):
    """Bot usernames are convenient logical ids, but Telegram needs chat_id."""
    from app.api.routes.demand import _resolve_telegram_channel_ref

    target = Agent(
        name="Atlas",
        agent_type="executor",
        profile_slug="atlas",
        telegram_account="HermesAtlas2bot",
    )
    monkeypatch.setattr(
        "app.api.routes.demand._telegram_home_chat", lambda agent: "1085550644"
    )

    for alias in (None, "telegram", "Atlas", "atlas", "HermesAtlas2bot", "@HermesAtlas2bot"):
        assert _resolve_telegram_channel_ref(target, alias) == "1085550644"

    assert _resolve_telegram_channel_ref(target, "-100123456:42") == "-100123456:42"
    assert _resolve_telegram_channel_ref(target, "@public_channel") == "@public_channel"
