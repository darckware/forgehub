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
PROPOSAL_ID = str(uuid.uuid4())
LEAD_ID = str(uuid.uuid4())
CONTRACT_ID = str(uuid.uuid4())

CYCLE_REPORT = {
    "client": {"id": CLIENT_ID, "company_name": "ACME", "contact_name": "Ana Souza", "email": "ana@acme.com.br"},
    "cycle": {"start": "2026-09-05", "end": "2026-10-05", "billing_cycle_day": 5},
    "support_contract": {"id": CONTRACT_ID, "plan_name": "Plano 4 Horas"},
    "hours": {"used": 5.5, "quota": 4.0, "remaining": 0.0, "extra": 1.5},
    "time_entries": [{"ticket_id": TICKET_ID, "description": "Troca do toner", "billable_hours": 1.0, "service_type": "remoto", "date": "2026-09-10"}],
    "tickets": {"opened": [], "closed": [{"title": "Impressora parada"}], "open": [{"title": "Backup lento"}]},
    "demands": {"opened": [], "closed": [], "open": []},
}
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
        self.queued: list[dict] = []
        self.report_refs: list[str | None] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        auth = request.headers.get("authorization", "")
        self.calls.append((request.method, path, body, auth))
        a = "/api/internal/agent"
        if path.startswith("/api/internal/approver/"):
            if auth != "Bearer approver-token":
                return httpx.Response(403, json={"detail": "Credencial de aprovação inválida"})
            if path.endswith("/contracts") and request.method == "POST":
                return httpx.Response(201, json={"id": CONTRACT_ID, **body})
            if path == f"/api/internal/approver/contracts/{CONTRACT_ID}":
                return httpx.Response(200, json={"id": CONTRACT_ID, **body})
            if path.endswith(f"/conversion-proposals/{PROPOSAL_ID}/approve"):
                return httpx.Response(
                    200,
                    json={
                        "proposal": {"id": PROPOSAL_ID, "status": "aprovada"},
                        "client_account_id": CLIENT_ID,
                        "contract": {"id": CONTRACT_ID, **body["overrides"]["contract"]},
                        "welcome_email_id": EMAIL_ID,
                    },
                )
            if path.endswith(f"/conversion-proposals/{PROPOSAL_ID}/reject"):
                return httpx.Response(200, json={"id": PROPOSAL_ID, "status": "rejeitada"})
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
        if path == f"{a}/outbound-emails" and request.method == "GET" and not request.url.params.get("source_ref"):
            return httpx.Response(200, json={"items": [self.email], "total": 1, "pending": {}})
        if path == f"{a}/outbound-emails" and request.method == "POST":
            if not self.recipient_ok:
                return httpx.Response(422, json={"detail": "Destinatário não vinculado"})
            self.queued.append({**body, "id": str(uuid.uuid4())})
            return httpx.Response(201, json={**self.email, **{k: body[k] for k in ("subject", "kind", "to_email")}})
        if path == f"{a}/clients/{CLIENT_ID}/cycle-report":
            self.report_refs.append(request.url.params.get("reference"))
            return httpx.Response(200, json=CYCLE_REPORT)
        if path == f"{a}/clients-with-contracts":
            return httpx.Response(200, json={"items": [{"id": CLIENT_ID, "company_name": "ACME", "billing_cycle_day": 5}]})
        if path == f"{a}/tickets/{TICKET_ID}/time-entries":
            return httpx.Response(201, json=self.ticket)
        if path == f"{a}/outbound-emails" and request.method == "GET" and request.url.params.get("source_ref"):
            hits = [e for e in self.queued if e.get("source_ref") == request.url.params["source_ref"]]
            return httpx.Response(200, json={"items": hits, "total": len(hits)})
        if path == f"{a}/leads/{LEAD_ID}/conversion-proposals":
            return httpx.Response(201, json={"id": PROPOSAL_ID, "status": "proposta", "payload": body})
        if path == f"{a}/conversion-proposals":
            return httpx.Response(
                200,
                json={"items": [{"id": PROPOSAL_ID, "proposed_by": "lara", "payload": {"company_name": "Gatling"}}]},
            )
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
        ids = [uuid.UUID(x) for x in (TICKET_ID, DEMAND_ID, EMAIL_ID, PROPOSAL_ID, CONTRACT_ID)]
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(ids)))
        await db.execute(
            delete(Notification).where(
                Notification.event_key.in_(
                    [
                        f"darckware:email:{EMAIL_ID}:v1",
                        f"darckware:ticket:{TICKET_ID}",
                        f"darckware:demand:{DEMAND_ID}",
                        f"darckware:conversion:{PROPOSAL_ID}",
                    ]
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
    assert first == 4
    assert second == 0


SUPPORT = {"contract_type": "suporte_horas", "plan_name": "Plano 8 Horas", "monthly_hours_quota": 8, "monthly_price": 900}


@pytest.mark.asyncio
async def test_contract_writes_use_approver_and_are_audited(client, darckware):
    r = await client.post(f"/api/v1/client-ops/clients/{CLIENT_ID}/contracts", json=SUPPORT)
    assert r.status_code == 201, r.text
    call = next(c for c in darckware.calls if c[1].endswith("/contracts"))
    assert call[1] == f"/api/internal/approver/clients/{CLIENT_ID}/contracts"
    assert call[3] == "Bearer approver-token"
    assert call[2]["created_by"].startswith("test-admin-")

    bad = await client.post(f"/api/v1/client-ops/clients/{CLIENT_ID}/contracts", json={**SUPPORT, "billing_cycle_day": 31})
    assert bad.status_code == 422

    patched = await client.patch(f"/api/v1/client-ops/contracts/{CONTRACT_ID}", json={"status": "encerrado"})
    assert patched.status_code == 200
    async with AsyncSessionLocal() as db:
        events = (
            await db.execute(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(CONTRACT_ID)))
        ).scalars().all()
    assert sorted(e.event_type for e in events) == ["created", "updated"]


@pytest.mark.asyncio
async def test_approve_conversion_sends_edited_data(client, darckware):
    r = await client.post(
        f"/api/v1/client-ops/conversions/{PROPOSAL_ID}:approve",
        json={"data": {"company_name": "Clube Gatling", "email": "r@g.com", "contract": {**SUPPORT, "monthly_price": 950}}},
    )
    assert r.status_code == 200, r.text
    call = next(c for c in darckware.calls if c[1].endswith("/approve"))
    assert call[3] == "Bearer approver-token"
    assert call[2]["overrides"]["contract"]["monthly_price"] == 950
    assert call[2]["overrides"]["company_name"] == "Clube Gatling"
    assert r.json()["welcome_email_id"] == EMAIL_ID


@pytest.mark.asyncio
async def test_convert_lead_proposes_then_approves(client, darckware):
    r = await client.post(
        f"/api/v1/client-ops/leads/{LEAD_ID}:convert",
        json={"data": {"contract": SUPPORT}, "notes": "Fechado em reunião"},
    )
    assert r.status_code == 200, r.text
    paths = [p for _, p, _, _ in darckware.calls]
    propose = paths.index(f"/api/internal/agent/leads/{LEAD_ID}/conversion-proposals")
    approve = paths.index(f"/api/internal/approver/conversion-proposals/{PROPOSAL_ID}/approve")
    assert propose < approve
    assert darckware.calls[propose][2]["proposed_by"].startswith("forgehub:")


@pytest.mark.asyncio
async def test_reject_conversion(client, darckware):
    r = await client.post(f"/api/v1/client-ops/conversions/{PROPOSAL_ID}:reject", json={"reason": "Ainda negociando"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejeitada"


# ---------------------------------------------------------------------------
# Onda 3 -- Software Factory per client
# ---------------------------------------------------------------------------

from app.db.models.product import Product  # noqa: E402
from app.db.models.project import Project  # noqa: E402


@pytest_asyncio.fixture
async def factory_cleanup():
    names: list[str] = []
    yield names
    async with AsyncSessionLocal() as db:
        products = (await db.execute(select(Product).where(Product.name.in_(names)))).scalars().all()
        for product in products:
            from app.db.models.product import ProductVersion

            version_ids = select(ProductVersion.id).where(ProductVersion.product_id == product.id)
            project_ids = [p.id for p in (await db.execute(select(Project).where(Project.product_version_id.in_(version_ids)))).scalars()]
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(project_ids + [product.id])))
            await db.execute(delete(Project).where(Project.id.in_(project_ids)))
            await db.delete(product)
        await db.commit()


@pytest.mark.asyncio
async def test_create_project_from_ticket(client, darckware, factory_cleanup):
    name = f"test-clientops-{uuid.uuid4().hex[:8]}"
    factory_cleanup.append(name)
    r = await client.post(
        f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:create-project",
        json={"new_product_name": name},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["product"]["darckware_client_id"] == CLIENT_ID
    assert data["product"]["darckware_client_name"] == "ACME"
    assert data["project"]["darckware_origin_type"] == "ticket"
    assert data["project"]["darckware_origin_id"] == TICKET_ID

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, uuid.UUID(data["project"]["id"]))
        assert str(project.darckware_client_id) == CLIENT_ID
        assert project.name == "Impressora parada"

    # the ticket moved to in progress with a note pointing at the project
    patch = next(c for c in darckware.calls if c[0] == "PATCH")
    assert patch[2]["status"] == "em_andamento"
    assert data["project"]["id"] in patch[2]["note"]

    again = await client.post(
        f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:create-project",
        json={"product_id": data["product"]["id"]},
    )
    assert again.status_code == 409

    factory = (await client.get(f"/api/v1/client-ops/clients/{CLIENT_ID}/factory")).json()
    assert [p["name"] for p in factory["products"]] == [name]
    assert factory["projects"][0]["id"] == data["project"]["id"]


@pytest.mark.asyncio
async def test_project_inherits_product_client(client, factory_cleanup):
    """POST /projects without a client takes the product's (Cockpit's own button)."""
    name = f"test-clientops-{uuid.uuid4().hex[:8]}"
    factory_cleanup.append(name)
    product = (
        await client.post("/api/v1/products", json={"name": name, "darckware_client_id": CLIENT_ID, "darckware_client_name": "ACME"})
    ).json()
    version_id = product["versions"][0]["id"]
    project = (await client.post("/api/v1/projects", json={"name": "Fase 2", "product_version_id": version_id})).json()
    assert project["darckware_client_id"] == CLIENT_ID


@pytest.mark.asyncio
async def test_create_project_needs_client_and_one_product_choice(client, darckware):
    no_choice = await client.post(f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:create-project", json={})
    assert no_choice.status_code == 422
    darckware.ticket = {**darckware.ticket, "client_account_id": None}
    lead_only = await client.post(
        f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:create-project", json={"new_product_name": "x"}
    )
    assert lead_only.status_code == 422
    assert "convert the lead" in lead_only.json()["detail"]


# ---------------------------------------------------------------------------
# Onda 4 -- hours and monthly report
# ---------------------------------------------------------------------------

from datetime import date  # noqa: E402

from app.core.client_monthly_report import build_report_text, run_due_reports  # noqa: E402


def test_report_text_is_client_facing():
    subject, body = build_report_text(
        CYCLE_REPORT, [{"id": "x", "name": "Portal", "status": "active", "tasks_total": 10, "tasks_done": 4}], today=date(2026, 10, 5)
    )
    assert subject == "Informe mensal Darckware — ACME (05/09/2026 a 04/10/2026)"
    partial, _ = build_report_text(CYCLE_REPORT, [], today=date(2026, 9, 20))
    assert partial.endswith("(05/09/2026 a 20/09/2026 (parcial))")
    assert body.startswith("Olá, Ana!")
    assert "Horas utilizadas: 5,5 h de 4 h" in body
    assert "Horas excedentes: 1,5 h" in body
    assert "- 10/09/2026 Troca do toner (1 h)" in body
    assert "- Impressora parada" in body and "- Backup lento" in body
    assert "- Portal: em andamento — 4 de 10 etapas concluídas" in body
    assert TICKET_ID not in body  # no internal ids


@pytest.mark.asyncio
async def test_monthly_report_is_queued_once_per_cycle(client, darckware):
    first = await client.post(f"/api/v1/client-ops/clients/{CLIENT_ID}/monthly-report", json={"reference": "2026-10-04"})
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    queued = darckware.queued[0]
    assert queued["kind"] == "informe_mensal"
    assert queued["to_email"] == "ana@acme.com.br"
    assert queued["source_ref"] == f"monthly-report:{CLIENT_ID}:2026-09-05"

    again = await client.post(f"/api/v1/client-ops/clients/{CLIENT_ID}/monthly-report", json={"reference": "2026-10-04"})
    assert again.json()["created"] is False
    assert len(darckware.queued) == 1


@pytest.mark.asyncio
async def test_run_internal_needs_bridge_token_and_picks_due_clients(darckware, monkeypatch):
    monkeypatch.setattr(settings, "CHAT_BRIDGE_TOKEN", "bridge-secret")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as anon:
        denied = await anon.post("/api/v1/client-ops/reports/run-internal")
        assert denied.status_code == 401
        ok = await anon.post("/api/v1/client-ops/reports/run-internal", headers={"X-Bridge-Token": "bridge-secret"})
        assert ok.status_code == 200, ok.text

    async with AsyncSessionLocal() as db:
        not_due = await run_due_reports(db, today=date(2026, 10, 4))
        due = await run_due_reports(db, today=date(2026, 10, 5))
    assert not_due["due"] == 0
    assert due["due"] == 1 and due["results"][0]["client"] == "ACME"
    assert darckware.report_refs[-1] == "2026-10-04"  # the cycle that just closed


@pytest.mark.asyncio
async def test_log_time_records_who(client, darckware):
    r = await client.post(
        f"/api/v1/client-ops/work-items/ticket/{TICKET_ID}:log-time",
        json={"start_time": "2026-10-04T13:00:00Z", "end_time": "2026-10-04T14:00:00Z", "description": "Visita técnica", "service_type": "presencial"},
    )
    assert r.status_code == 201, r.text
    call = next(c for c in darckware.calls if c[1].endswith("/time-entries"))
    assert call[2]["recorded_by"].startswith("forgehub:test-admin-")
    assert call[2]["service_type"] == "presencial"
