"""Integration test: requires a disposable database explicitly supplied by the caller."""
import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateColumn

from app.api.routes.moodle_approval import router
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import get_db
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.demand import AgentDemand, DemandAttachment
from app.db.models.governance import AuditEvent
from app.db.models.moodle_approval import MoodleApproval, MoodleChallenge
from app.db.models.user import User
from test_moodle_proposal_verification import proposal


@pytest.mark.asyncio
async def test_registration_authorization_and_claim_races(tmp_path, monkeypatch):
    url = os.environ.get("MOODLE_TEST_DATABASE_URL")
    if url != "postgresql+asyncpg://postgres:isolated-test@127.0.0.1:32768/isolated":
        pytest.skip("requires explicit disposable database")
    engine = create_async_engine(url)
    models = [User, Agent, AgentServiceCredential, AgentDemand, DemandAttachment, MoodleApproval, MoodleChallenge, AuditEvent]
    async with engine.begin() as connection:
        assert (await connection.execute(text("SELECT current_database()"))).scalar_one() == "isolated"
        await connection.execute(text("DROP SCHEMA IF EXISTS company CASCADE"))
        await connection.execute(text("CREATE SCHEMA company"))
        for model in models:
            table = model.__table__
            cols = ", ".join(str(CreateColumn(c).compile(dialect=connection.dialect)) for c in table.columns)
            await connection.execute(text(f'CREATE TABLE company."{table.name}" ({cols}, PRIMARY KEY (id))'))
        await connection.execute(text("CREATE UNIQUE INDEX ON company.moodle_message_approvals (request_id)"))
        await connection.execute(text("CREATE UNIQUE INDEX ON company.moodle_message_approvals (message_id)"))
        await connection.execute(text("CREATE UNIQUE INDEX ON company.moodle_approval_challenges (secret_hash)"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    owner_id, source_id, executor_id, other_id = (uuid.uuid4() for _ in range(4))
    source_token, executor_token, other_token = ("agt_" + uuid.uuid4().hex for _ in range(3))
    password, secret = "isolated-password", "isolated-challenge"
    async with sessions() as db:
        db.add(User(id=owner_id, username="test-owner", hashed_password=hash_password(password), is_admin=True, is_active=True))
        for aid, name, token in ((source_id, "source", source_token), (executor_id, "executor", executor_token), (other_id, "other", other_token)):
            db.add(Agent(id=aid, name=name, agent_type="executor", status="active", is_active=True, profile_slug=name, runtime_type="hermes"))
            db.add(AgentServiceCredential(id=uuid.uuid4(), agent_id=aid, label="test", token_hash=hashlib.sha256(token.encode()).hexdigest()))
        db.add(MoodleChallenge(owner_id=owner_id, secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), attempts=0))
        await db.commit()
    p = proposal()
    store = tmp_path / "proposals.json"
    store.write_text(json.dumps({"proposals": {p["request_id"]: p}}))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_ENABLED", True)
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_OWNER_ID", str(owner_id))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_WORKING_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "MOODLE_APPROVAL_SOURCE_FILES", json.dumps({str(source_id): str(store)}))
    monkeypatch.setattr("app.api.routes.moodle_approval.wake_scheduled_dispatch", lambda: None)
    app = FastAPI()
    app.include_router(router)
    async def isolated_db():
        async with sessions() as db:
            yield db
    app.dependency_overrides[get_db] = isolated_db
    headers = lambda token: {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        requests = await asyncio.gather(*(client.post("/api/v1/personal/moodle-approvals/register", headers=headers(source_token), json={"request_id": p["request_id"]}) for _ in range(2)))
        assert [r.status_code for r in requests] == [201, 201]
        assert requests[0].json() == requests[1].json()
        mid = requests[0].json()["message_id"]
        owner = headers(create_access_token("test-owner"))
        listed = await client.get("/api/v1/personal/moodle-approvals", headers=owner)
        assert listed.status_code == 200 and len(listed.json()["items"]) == 1
        item = listed.json()["items"][0]
        payload = {"password": password, "telegram_challenge": secret, "executor_agent_id": str(executor_id), "instruction": "test",
            "items": [{k: item[k] for k in ("request_id", "message_id", "params_hash", "message_updated_at")}]}
        async with sessions() as db:
            db.add(MoodleChallenge(owner_id=owner_id, secret_hash=hashlib.sha256(b"expired-link").hexdigest(),
                expires_at=datetime.now(timezone.utc) - timedelta(seconds=1), attempts=0))
            await db.commit()
        expired = await client.post("/api/v1/personal/moodle-approvals/authorize", headers=owner,
            json={**payload, "telegram_challenge": "expired-link"})
        assert expired.status_code == 403
        decisions = await asyncio.gather(*(client.post("/api/v1/personal/moodle-approvals/authorize", headers=owner, json=payload) for _ in range(2)))
        assert sorted(r.status_code for r in decisions) == [200, 403]
        async with sessions() as db:
            demand = await db.get(AgentDemand, uuid.UUID(mid))
            demand.agent_run_id = "isolated-run"
            await db.commit()
        claim = {"request_id": p["request_id"], "message_id": mid, "params_hash": p["params_hash"]}
        denied = await client.post("/api/v1/personal/moodle-approvals/claim", headers=headers(other_token), json=claim)
        assert denied.status_code == 403
        async with sessions() as db:
            demand = await db.get(AgentDemand, uuid.UUID(mid))
            approved_body = demand.body
            demand.body = "altered"
            await db.commit()
        changed = await client.post("/api/v1/personal/moodle-approvals/claim", headers=headers(executor_token), json=claim)
        assert changed.status_code == 409
        async with sessions() as db:
            demand = await db.get(AgentDemand, uuid.UUID(mid))
            demand.body = approved_body
            await db.commit()
        claims = await asyncio.gather(*(client.post("/api/v1/personal/moodle-approvals/claim", headers=headers(executor_token), json=claim) for _ in range(2)))
        assert sorted(r.status_code for r in claims) == [200, 409]
        assert next(r for r in claims if r.status_code == 200).json()["params"] == p["params"]
    await engine.dispose()
