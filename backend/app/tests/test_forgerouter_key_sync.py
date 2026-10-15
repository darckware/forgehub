"""ForgeRouter key sync pass (button + 15-min loop, 2026-10-14)."""
import uuid

import pytest
from sqlalchemy import delete

from app.api.routes.agent import run_forgerouter_key_sync_pass
from app.core import forgerouter_sync
from app.core.secrets import decrypt_secret, encrypt_secret
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent


@pytest.mark.asyncio
async def test_sync_refreshes_stale_copies_and_skips_retired_agents(monkeypatch):
    tag = uuid.uuid4().hex[:8]
    stale_name, retired_name = f"Stale {tag}", f"Retired {tag}"
    async with AsyncSessionLocal() as db:
        stale = Agent(name=stale_name, status="active", is_active=True, forgerouter_api_key_encrypted=encrypt_secret("old"))
        retired = Agent(name=retired_name, status="retired", is_active=True)
        db.add_all([stale, retired])
        await db.commit()
        ids = [stale.id, retired.id]

    async def registry():
        return [
            forgerouter_sync.ForgeRouterAgentKey(name=stale_name, api_key="new"),
            forgerouter_sync.ForgeRouterAgentKey(name=retired_name, api_key="should-not-land"),
        ]

    monkeypatch.setattr(forgerouter_sync, "read_forgerouter_agent_keys", registry)
    try:
        async with AsyncSessionLocal() as db:
            result = await run_forgerouter_key_sync_pass(db)
        assert retired_name.lower() in result.unmatched_forgerouter_agents
        async with AsyncSessionLocal() as db:
            assert decrypt_secret((await db.get(Agent, ids[0])).forgerouter_api_key_encrypted) == "new"
            assert (await db.get(Agent, ids[1])).forgerouter_api_key_encrypted is None
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id.in_(ids)))
            await db.commit()
