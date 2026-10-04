"""client_ops proxy domain (Darckware CRM), with Darckware mocked.

Darckware is replaced by an in-memory `httpx.MockTransport`; ForgeHub's own
side effects (AuditEvent, Notification) hit the real database and are
removed by the ids this test generated.
"""
import json
import uuid

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.api.routes.client_ops import run_client_ops_notification_pass
from app.core import darckware_client
from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.governance import AuditEvent
from app.db.models.notification import Notification
from app.main import app

CLIENT_ID = str(uuid.uuid4())
TICKET_ID = str(uuid.uuid4())
DEMAND_ID = str(uuid.uuid4())
EMAIL_ID = str(uuid.uuid4())
HASH = "a" * 64


class FakeDarckware:
    """Just enough of Darckware's internal API to drive the routes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict | None, str]] = []
        self.ticket = {
            "id": TICKET_ID,
            "client_account_id": CLIENT_ID,
            "company_name": "ACME",
            "title": "Impressora parada",
            "description": "Não imprime",
            "type": "manutencao",
            "category": "suporte_ti",
            "priority": "media",
            "status": "aberto",
            "requester_name": "Ana",
            "requester_email": "ana@acme.com.br",
            "total_billable_hours": 0,
            "created_at": "2026-10-04T10:00:00+00:00",
            "updated_at": "2026-10-04T10:00:00+00:00",
            "comments": [],
            "time_entries": [],
        }
        self.demand = {
            "id": DEMAND_ID,
            "title": "Novo relatório",
            "status": "aguardando_cliente",
            "priority": "alta",
            "category": "dados_relatorios",
            "client_account_id": CLIENT_ID,
            "source_channel": "email",
            "created_at": "2026-10-03T10:00:00+00:00",
            "updated_at": "2026-10-03T10:00:00+00:00",
        }
        self.email = {
            "id": EMAIL_ID,
            "status": "aguardando_aprovacao",
            "kind": "pendencia",
            "to_email": "ana@acme.com.br",
            "subject": "Precisamos do acesso",
            "body_text": "Olá",
            "version": 1,
            "body_hash": HASH,
        }
        self.fail_patch = False
        self.recipient_ok = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        auth = request.headers.get("authorization", "")
        self.calls.append((request.method, path, body, auth))
        a = "/api/internal/agent"
        if path.startswith("/api/internal/approver/"):
            if auth != "Bearer approver-token":
                return httpx.Response(403, json={"detail": "Credencial de aprovação inválida"})
            if body["version"] != self.email["version"]:
                return httpx.Response(409, json={"detail": "O texto mudou"})
            return httpx.Response(200, json={**self.email, "status": "aprovado"})
        if path == f"{a}/clients":
            return httpx.Response(200, json={"items": [{"id": CLIENT_ID, "company_name": "ACME"}], "total": 1})
        if path == f"{a}/tickets" and request.method == "GET":
            wanted = request.url.params.get("status")
            items = [self.ticket] if not wanted or self.ticket["status"] in wanted.split(",") else []
            return httpx.Response(200, json={"items": items, "total": len(items)})
        if path == f"{a}/tickets/{TICKET_ID}" and request.method == "GET":
            return httpx.Response(200, json=self.ticket)
        if path == f"{a}/tickets/{TICKET_ID}" and request.method == "PATCH":
            if self.fail_patch:
                return httpx.Response(500, text="boom")
            self.ticket = {**self.ticket, "status": body["status"]}
            return httpx.Response(200, json=self.ticket)
        if path == f"{a}/demands" and request.method == "GET":
            return httpx.Response(200, json={"items": [self.demand], "total": 1})
        if path == f"{a}/outbound-emails" and request.method == "GET":
            return httpx.Response(200, json={"items": [self.email], "total": 1, "pending": {}})
        if path == f"{a}/outbound-emails" and request.method == "POST":
            if not self.recipient_ok:
                return httpx.Response(422, json={"detail": "Destinatário não vinculado"})
            return httpx.Response(201, json={**self.email, **{k: body[k] for k in ("subject", "kind", "to_email")}})
        if path == f"{a}/outbound-emails/{EMAIL_ID}/cancel":
            return httpx.Response(200, json={**self.email, "status": "cancelado"})
        return httpx.Response(404, json={"detail": f"unmocked {request.method} {path}"})


@pytest.fixture
def darckware(monkeypatch):
    fake = FakeDarckware()
    monkeypatch.setattr(darckware_client, "transport", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(settings, "DARCKWARE_API_URL", "http://darckware.test")
    monkeypatch.setattr(settings, "DARCKWARE_AGENT_TOKEN", "agent-token")
    monkeypatch.setattr(settings, "DARCKWARE_APPROVER_TOKEN", "approver-token")
    return fake


@pytest_asyncio.fixture
async def client(admin_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=admin_headers) as ac:
        yield ac
    async with AsyncSessionLocal() as db:
        ids = [uuid.UUID(x) for x in (TICKET_ID, DEMAND_ID, EMAIL_ID)]
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
        await db.execute(
            delete(Notification).where(
                Notification.event_key.in_(
                    [f"darckware:email:{EMAIL_ID}:v1", f"darckware:ticket:{TICKET_ID}", f"darckware:demand:{DEMAND_ID}"]
                )
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_not_configured_is_503(client, monkeypatch):
    monkeypatch.setattr(settings, "DARCKWARE_AGENT_TOKEN", "")
    r = await client.get("/api/v1/client-ops/work-items")
    assert r.status_code == 503
    status_resp = await client.get("/api/v1/client-ops/status")
    assert status_resp.json()["configured"] is False


@pytest.mark.asyncio
async def test_requires_admin(darckware):
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {create_access_token(f'not-an-admin-{uuid.uuid4().hex}')}"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=headers) as ac:
        r = await ac.get("/api/v1/client-ops/work-items")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_unified_work_items(client, darckware):
    r = await client.get("/api/v1/client-ops/work-items")
    assert r.status_code == 200, r.text
    data = r.json()
    by_kind = {i["kind"]: i for i in data["items"]}
    assert by_kind["ticket"]["tipo"] == "servico"
    assert by_kind["ticket"]["stage"] == "novo"
    assert by_kind["demand"]["tipo"] == "desenvolvimento"
    assert by_kind["demand"]["stage"] == "aguardando_cliente"
    assert by_kind["demand"]["company_name"] == "ACME"
    assert data["by_stage"]["novo"] == 1

    waiting = await client.get("/api/v1/client-ops/work-items?stage=aguardando_cliente")
    assert [i["kind"] for i in waiting.json()["items"]] == ["demand"]


@pytest.mark.asyncio
async def test_wait_customer_queues_email_then_changes_status(client, darckware):
    r = await client.post(
        f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:wait-customer",
        json={"note": "Sem acesso", "email": {"subject": "Precisamos do acesso", "body_text": "Pode liberar?"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "aguardando_cliente"
    assert r.json()["queued_email"]["kind"] == "pendencia"

    methods = [(m, p) for m, p, _, _ in darckware.calls]
    post_idx = methods.index(("POST", "/api/internal/agent/outbound-emails"))
    patch_idx = methods.index(("PATCH", f"/api/internal/agent/tickets/{TICKET_ID}"))
    assert post_idx < patch_idx
    email_body = darckware.calls[post_idx][2]
    assert email_body["to_email"] == "ana@acme.com.br"
    assert email_body["ticket_id"] == TICKET_ID

    async with AsyncSessionLocal() as db:
        events = (
            await db.execute(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(TICKET_ID)))
        ).scalars().all()
    assert [e.event_type for e in events] == ["wait-customer"]
    assert events[0].entity_type == "darckware_ticket"


@pytest.mark.asyncio
async def test_failed_status_change_cancels_queued_email(client, darckware):
    darckware.fail_patch = True
    r = await client.post(
        f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:resolve",
        json={"resolution": "Trocado o toner", "email": {"subject": "Resolvido", "body_text": "Feito"}},
    )
    assert r.status_code == 502
    assert ("POST", f"/api/internal/agent/outbound-emails/{EMAIL_ID}/cancel") in [
        (m, p) for m, p, _, _ in darckware.calls
    ]


@pytest.mark.asyncio
async def test_refused_recipient_blocks_the_action(client, darckware):
    darckware.recipient_ok = False
    r = await client.post(
        f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:wait-customer",
        json={"email": {"subject": "x", "body_text": "y", "to_email": "estranho@x.com"}},
    )
    assert r.status_code == 422
    assert not any(m == "PATCH" for m, *_ in darckware.calls)


@pytest.mark.asyncio
async def test_approve_uses_approver_credential(client, darckware):
    r = await client.post(f"/api/v1/client-ops/emails/{EMAIL_ID}:approve", json={"version": 1, "body_hash": HASH})
    assert r.status_code == 200, r.text
    approve_call = next(c for c in darckware.calls if c[1].endswith("/approve"))
    assert approve_call[1] == f"/api/internal/approver/outbound-emails/{EMAIL_ID}/approve"
    assert approve_call[3] == "Bearer approver-token"
    assert approve_call[2]["approved_by"].startswith("test-admin-")

    stale = await client.post(f"/api/v1/client-ops/emails/{EMAIL_ID}:approve", json={"version": 9, "body_hash": HASH})
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_darckware_down_is_502(client, monkeypatch, darckware):
    def boom(request):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(darckware_client, "transport", httpx.MockTransport(boom))
    r = await client.get("/api/v1/client-ops/emails")
    assert r.status_code == 502
    assert "unreachable" in r.json()["detail"]


@pytest.mark.asyncio
async def test_notification_pass_is_deduplicated(client, darckware):
    darckware.demand = {**darckware.demand, "status": "aberta"}
    async with AsyncSessionLocal() as db:
        first = await run_client_ops_notification_pass(db)
        second = await run_client_ops_notification_pass(db)
    assert first == 3
    assert second == 0
