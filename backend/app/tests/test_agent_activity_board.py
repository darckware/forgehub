"""A.1 (Plano Integrado): the Agent Activity board lists every eligible agent.

Eligible = the registry says the agent is in service (`is_active` and
`status == "active"`). External runtimes (claude/codex/agy) are on the board
even when Messages runs nothing for them -- `idle`, with no telemetry invented
--, inactive/retired agents never are, and nothing counts agents by a fixed
number: a newly registered agent appears with no code change. Each row carries
its Telegram channel and gateway health; an unreachable host-bridge reads
`unknown`, never a failure.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import and_, delete, select

from app.core import agent_activity_alerts, agent_activity_stream
from app.core.agent_activity import build_agent_activity
from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand


@pytest.fixture(autouse=True)
def _no_optional_sources(monkeypatch):
    async def no_forgerouter():
        return None

    monkeypatch.setattr(agent_activity_stream, "_cached_forgerouter_usage", no_forgerouter)
    # The gateway read is cached for every poll; each test starts without a cached verdict.
    agent_activity_alerts._cache.clear()
    yield
    agent_activity_alerts._cache.clear()


def _bridge_unreachable(monkeypatch):
    # A closed local port: the real reader runs and fails to connect.
    monkeypatch.setattr(settings, "CHAT_BRIDGE_URL", "http://127.0.0.1:9")


async def _make_agents(suffix: str, home: str) -> dict[str, uuid.UUID]:
    async with AsyncSessionLocal() as db:
        rows = {
            "external": Agent(name=f"Board External {suffix}", runtime_type="agy",
                              profile_slug=f"board-ext-{suffix}"),
            "hermes": Agent(name=f"Board Hermes {suffix}", runtime_type="hermes",
                            profile_slug=f"board-hermes-{suffix}", home_path=home),
            "inactive": Agent(name=f"Board Inactive {suffix}", runtime_type="codex",
                              profile_slug=f"board-off-{suffix}", is_active=False, status="inactive"),
            "retired": Agent(name=f"Board Retired {suffix}", runtime_type="hermes",
                             profile_slug=f"board-retired-{suffix}", status="retired"),
        }
        db.add_all(rows.values())
        await db.commit()
        return {key: agent.id for key, agent in rows.items()}


async def _drop_agents(ids: dict[str, uuid.UUID]) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentDemand).where(AgentDemand.target_agent_id.in_(ids.values())))
        await db.execute(delete(Agent).where(Agent.id.in_(ids.values())))
        await db.commit()


@pytest.fixture
def telegram_home(tmp_path):
    """A fictitious profile home whose .env has a Telegram channel configured."""
    (tmp_path / ".env").write_text(
        "TELEGRAM_BOT_TOKEN=fictitious-test-token\nTELEGRAM_HOME_CHANNEL=-1000000000001\n",
        encoding="utf-8",
    )
    return str(tmp_path)


@pytest.mark.asyncio
async def test_board_lists_eligible_agents_with_idle_externals(monkeypatch, telegram_home):
    _bridge_unreachable(monkeypatch)
    suffix = uuid.uuid4().hex[:8]
    ids = await _make_agents(suffix, telegram_home)
    try:
        eligible_query = select(Agent.id).where(and_(Agent.is_active.is_(True), Agent.status == "active"))
        async with AsyncSessionLocal() as db:
            before = set((await db.execute(eligible_query)).scalars())
            snapshot = await agent_activity_stream.build_live_snapshot(db)
            view = await build_agent_activity(db, project_id=None, window_minutes=60)
            after = set((await db.execute(eligible_query)).scalars())

        snapshot_ids = {item.agent_id for item in snapshot.agents}
        board_ids = {agent.id for agent in view.agents}
        # Every eligible agent of the current registry, no more and no fewer. The test
        # database is shared, so an agent another test adds/removes meanwhile may go either way.
        for ids_seen in (snapshot_ids, board_ids):
            assert before & after <= ids_seen <= before | after
        assert len(before & after) <= snapshot.pulse.agents_total <= len(before | after)

        # External with nothing dispatched: present and idle, no telemetry invented.
        assert ids["external"] in snapshot_ids and ids["external"] in board_ids
        external_live = next(i.live for i in snapshot.agents if i.agent_id == ids["external"])
        assert external_live is not None and external_live.state == "idle"
        assert external_live.source == "messages"
        assert external_live.turns_last_hour == 0 and external_live.tools_last_hour == 0
        assert external_live.last_event_at is None  # never dispatched: no "last seen" made up

        # A new agent appears with no code change.
        assert ids["hermes"] in snapshot_ids and ids["hermes"] in board_ids
        # Inactive and retired agents never do.
        for key in ("inactive", "retired"):
            assert ids[key] not in snapshot_ids and ids[key] not in board_ids
    finally:
        await _drop_agents(ids)


@pytest.mark.asyncio
async def test_external_idle_since_its_last_finished_dispatch(monkeypatch, telegram_home):
    _bridge_unreachable(monkeypatch)
    suffix = uuid.uuid4().hex[:8]
    ids = await _make_agents(suffix, telegram_home)
    try:
        async with AsyncSessionLocal() as db:
            finished = AgentDemand(
                from_agent="board-test", from_agent_id=ids["hermes"], target_agent_id=ids["external"],
                subject="done", body="x", origin_type="task", dispatch_status="completed",
                dispatched_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
            )
            queued = AgentDemand(
                from_agent="board-test", from_agent_id=ids["hermes"], target_agent_id=ids["external"],
                subject="queued", body="x", origin_type="task",
            )
            db.add_all([finished, queued])
            await db.commit()
        async with AsyncSessionLocal() as db:
            snapshot = await agent_activity_stream.build_live_snapshot(db)
        live = next(i.live for i in snapshot.agents if i.agent_id == ids["external"])
        assert live.state == "idle" and live.source == "messages"
        assert live.last_event_at is not None  # the real end of its last Messages run
        assert live.pending_count == 1
    finally:
        await _drop_agents(ids)


@pytest.mark.asyncio
async def test_channel_health_is_unknown_when_the_bridge_is_unreachable(monkeypatch, telegram_home):
    _bridge_unreachable(monkeypatch)
    suffix = uuid.uuid4().hex[:8]
    ids = await _make_agents(suffix, telegram_home)
    try:
        async with AsyncSessionLocal() as db:
            view = await build_agent_activity(db, project_id=None, window_minutes=60)
        by_id = {agent.id: agent for agent in view.agents}
        hermes = by_id[ids["hermes"]].channel_health
        assert hermes.telegram == "unknown" and hermes.gateway == "unknown"
        external = by_id[ids["external"]].channel_health
        # No Telegram configured and no gateway: not applicable, never "offline".
        assert external.telegram == "not_applicable" and external.gateway == "not_applicable"
    finally:
        await _drop_agents(ids)


@pytest.mark.asyncio
async def test_channel_health_reads_the_gateway_state(monkeypatch, telegram_home):
    from app.core import agent_telegram

    suffix = uuid.uuid4().hex[:8]

    async def gateway_up():
        return agent_telegram.GatewayHealth(
            alive=True, telegram_states={f"board-hermes-{suffix}": "fatal"}, error=None
        )

    monkeypatch.setattr(agent_telegram, "read_gateway_health", gateway_up)
    ids = await _make_agents(suffix, telegram_home)
    try:
        async with AsyncSessionLocal() as db:
            view = await build_agent_activity(db, project_id=None, window_minutes=60)
        hermes = next(a for a in view.agents if a.id == ids["hermes"]).channel_health
        assert hermes.gateway == "ok" and hermes.telegram == "not_running"
    finally:
        await _drop_agents(ids)
