"""Tailnet policy: HuJSON parsing, the server->client SSH analysis (with the
real 2026-10-16 policy that blocked every station) and the record routes."""
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.api.routes import vpn as vpn_routes
from app.core.tailnet_policy import PolicyParseError, analyze_policy, parse_hujson
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.vpn import TailnetPolicyVersion

REAL = (Path(__file__).parent / "fixtures" / "tailnet_policy_2026_10_16.hujson").read_text()
FIX = '''
        {
            "src": ["tag:darckware-infra"],
            "dst": ["tag:semed-srv", "tag:semed-users", "tag:gatling-srv", "tag:gatling-users"],
            "ip":  ["tcp:22"],
        },
'''


def test_hujson_comments_trailing_commas_and_strings():
    data = parse_hujson('{ // c\n "a": "http://x // not a comment", /* b */ "b": [1, 2,], }')
    assert data == {"a": "http://x // not a comment", "b": [1, 2]}
    with pytest.raises(PolicyParseError):
        parse_hujson('{"a": }')


def test_real_policy_gives_the_server_no_ssh_anywhere():
    analysis = analyze_policy(parse_hujson(REAL))
    assert analysis.style == "grants"
    assert analysis.client_tags == ["tag:gatling-srv", "tag:gatling-users", "tag:semed-srv", "tag:semed-users"]
    assert analysis.tags_with_ssh == []
    assert analysis.missing_ssh == analysis.client_tags
    assert '"ip":  ["tcp:22"]' in analysis.snippet


def test_suggested_grant_fixes_it():
    fixed = REAL.replace('    "grants": [\n', '    "grants": [\n' + FIX, 1)
    analysis = analyze_policy(parse_hujson(fixed))
    assert analysis.missing_ssh == [] and analysis.snippet is None


@pytest.mark.parametrize("rule, ok", [
    ({"src": ["tag:darckware-infra"], "dst": ["*"], "ip": ["*"]}, True),
    ({"src": ["tag:darckware-infra"], "dst": ["tag:x"], "ip": ["tcp:20-25"]}, True),
    ({"src": ["tag:darckware-infra"], "dst": ["tag:x"], "ip": ["udp:22"]}, False),
    ({"src": ["tag:darckware-infra"], "dst": ["tag:x"], "ip": ["tcp:3389"]}, False),
    ({"src": ["tag:other"], "dst": ["tag:x"], "ip": ["*"]}, False),
])
def test_grant_port_matching(rule, ok):
    policy = {"tagOwners": {"tag:x": [], "tag:darckware-infra": []}, "grants": [rule]}
    assert (analyze_policy(policy).missing_ssh == []) is ok


def test_legacy_acls_style():
    policy = {
        "tagOwners": {"tag:x": [], "tag:y": [], "tag:darckware-infra": []},
        "acls": [{"action": "accept", "src": ["tag:darckware-infra"], "dst": ["tag:x:22,80"]}],
    }
    analysis = analyze_policy(policy)
    assert analysis.missing_ssh == ["tag:y"] and '"tag:y:22"' in analysis.snippet


@pytest_asyncio.fixture
async def client(admin_headers):
    app = FastAPI()
    app.include_router(vpn_routes.router)
    created: list[uuid.UUID] = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=admin_headers) as ac:
        yield ac, created
    async with AsyncSessionLocal() as db:
        if created:
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(created)))
            await db.execute(delete(TailnetPolicyVersion).where(TailnetPolicyVersion.id.in_(created)))
            await db.commit()


@pytest.mark.asyncio
async def test_record_and_read_back_policy(client):
    ac, created = client
    bad = await ac.post("/api/v1/vpn/policy", json={"content": "{ not json"})
    assert bad.status_code == 422

    saved = await ac.post("/api/v1/vpn/policy", json={"content": REAL, "note": "teste"})
    assert saved.status_code == 201, saved.text
    body = saved.json()
    created.append(uuid.UUID(body["id"]))
    assert body["analysis"]["missing_ssh"] and body["content"] == REAL

    state = (await ac.get("/api/v1/vpn/policy")).json()
    assert state["current"]["id"] == body["id"]
    assert any(v["id"] == body["id"] for v in state["versions"])
    one = await ac.get(f"/api/v1/vpn/policy?version_id={body['id']}")
    assert one.json()["current"]["note"] == "teste"
    assert (await ac.get(f"/api/v1/vpn/policy?version_id={uuid.uuid4()}")).status_code == 404
