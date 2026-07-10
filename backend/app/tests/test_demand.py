"""Tests for the agent-demand inbox: CRUD, the project-scoped conversion
targets added for the "console de desenvolvimento" inbox redesign
(planning_item / project_doc / quick_task), and attachments.

DB strategy: tables come from Alembic migrations; each test creates its
own rows (UUID-suffixed) directly via the session or through the API, and
removes them in a finally block -- same pattern as test_notifications.py /
test_backlog.py.

Filesystem note: project_doc/quick_task write a doc under DOCS_ROOT
("/docs" in the real containers, bind-mounted to /root/docs) and
attachments write under the same mount. That mount doesn't exist on the
host running pytest directly, so these tests monkeypatch both
conversions.DOCS_ROOT and the demand route's DOCS_ROOT to a tmp_path
instead of touching the real filesystem root.
"""
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.backlog import PlanningItem
from app.db.models.demand import AgentDemand, DemandAttachment, DemandGroup
from app.db.models.notification import Notification
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.task import ProjectTask


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token('test-demand')}"}


@pytest_asyncio.fixture
async def client():
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=_auth_headers()) as ac:
        yield ac


@pytest_asyncio.fixture
async def project_id():
    async with AsyncSessionLocal() as session:
        product = Product(name=f"Demand Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.flush()
        project = Project(name=f"Demand Test Project {uuid.uuid4()}", product_version_id=version.id)
        session.add(project)
        await session.commit()
        pid, vid, prodid = project.id, version.id, product.id

    yield pid

    async with AsyncSessionLocal() as session:
        await session.execute(delete(PlanningItem).where(PlanningItem.project_id == pid))
        await session.execute(delete(Project).where(Project.id == pid))
        await session.execute(delete(ProductVersion).where(ProductVersion.id == vid))
        await session.execute(delete(Product).where(Product.id == prodid))
        await session.commit()


async def _create_demand(client: AsyncClient, **overrides) -> dict:
    payload = {
        "from_agent": "test-suite",
        "subject": f"Test demand {uuid.uuid4().hex[:8]}",
        "body": "# Procedimento\n\nConteúdo de teste em markdown.",
        **overrides,
    }
    resp = await client.post("/api/v1/demands", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _delete_demand(demand_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(AgentDemand).where(AgentDemand.id == uuid.UUID(demand_id)))
        # Not a real FK (Notification is a generic cross-domain record, see
        # its model docstring) -- clean it up explicitly by event_key.
        await session.execute(delete(Notification).where(Notification.event_key == f"demand:{demand_id}"))
        await session.commit()


async def test_create_and_list_demand(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        assert demand["status"] == "new"
        assert demand["attachments"] == []

        resp = await client.get("/api/v1/demands")
        assert resp.status_code == 200
        assert any(d["id"] == demand["id"] for d in resp.json())
    finally:
        await _delete_demand(demand["id"])


async def test_create_demand_raises_system_notification(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            notif = (
                await session.execute(
                    select(Notification).where(Notification.event_key == f"demand:{demand['id']}")
                )
            ).scalar_one_or_none()
            assert notif is not None
            assert notif.source == "system"
            assert notif.read_at is None
            assert demand["subject"] in notif.title

        resp = await client.get("/api/v1/notifications")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert any(n["id"] == str(notif.id) for n in body["notifications"])
    finally:
        await _delete_demand(demand["id"])


async def test_convert_to_planning_item_requires_project_id(client: AsyncClient):
    demand = await _create_demand(client)
    try:
        resp = await client.post(f"/api/v1/demands/{demand['id']}/convert", json={"target": "planning_item"})
        assert resp.status_code == 400
    finally:
        await _delete_demand(demand["id"])


async def test_convert_to_planning_item(client: AsyncClient, project_id):
    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/convert",
            json={"target": "planning_item", "project_id": str(project_id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity_type"] == "planning_item"
        assert body["entity_id"] is not None

        async with AsyncSessionLocal() as session:
            item = await session.get(PlanningItem, uuid.UUID(body["entity_id"]))
            assert item is not None
            assert item.item_type == "documentation"
            assert item.project_id == project_id

        resp = await client.get("/api/v1/demands")
        mine = next(d for d in resp.json() if d["id"] == demand["id"])
        assert mine["status"] == "converted"
        assert mine["converted_entity_type"] == "planning_item"
    finally:
        await _delete_demand(demand["id"])


async def test_convert_to_quick_task_creates_planning_item_and_task(client: AsyncClient, project_id):
    demand = await _create_demand(client)
    planning_item_id = None
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/convert",
            json={"target": "quick_task", "project_id": str(project_id), "item_type": "improvement"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity_type"] == "quick_task"
        task_id = uuid.UUID(body["entity_id"])

        async with AsyncSessionLocal() as session:
            task = await session.get(ProjectTask, task_id)
            assert task is not None
            assert task.planning_item_id is not None
            planning_item_id = task.planning_item_id
            item = await session.get(PlanningItem, planning_item_id)
            assert item is not None
            assert item.item_type == "improvement"
            assert item.project_id == project_id
    finally:
        await _delete_demand(demand["id"])
        # The task must go before the project_id fixture's teardown deletes
        # its planning_item (FK), so it's cleaned up here explicitly.
        if planning_item_id is not None:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(ProjectTask).where(ProjectTask.planning_item_id == planning_item_id)
                )
                await session.commit()


async def test_convert_to_project_doc(client: AsyncClient, project_id, monkeypatch, tmp_path):
    from app.core import conversions

    monkeypatch.setattr(conversions, "DOCS_ROOT", tmp_path)

    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/convert",
            json={"target": "project_doc", "project_id": str(project_id)},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity_type"] == "project_doc"
        written = tmp_path / body["reference"]
        assert written.is_file()
        assert "Procedimento" in written.read_text(encoding="utf-8")

        from app.db.models.doc_link import DocLink
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            link = (
                await session.execute(
                    select(DocLink).where(
                        DocLink.entity_type == "project", DocLink.entity_id == project_id
                    )
                )
            ).scalar_one_or_none()
            assert link is not None
            assert link.doc_path == body["reference"]
            await session.delete(link)
            await session.commit()
    finally:
        await _delete_demand(demand["id"])


async def test_convert_to_doc_in_area(client: AsyncClient, monkeypatch, tmp_path):
    """area_id routes the write through resolve_area_root (HOST_ROOT +
    the área's host_path) instead of the fixed DOCS_ROOT."""
    from app.core import conversions
    from app.db.models.docs_area import DocsArea

    monkeypatch.setattr(conversions, "HOST_ROOT", tmp_path)

    async with AsyncSessionLocal() as session:
        area = DocsArea(name=f"Test Area {uuid.uuid4().hex[:8]}", host_path="")
        session.add(area)
        await session.commit()
        await session.refresh(area)
        area_id = area.id

    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/convert",
            json={"target": "doc", "path": "minha-area/nota.md", "area_id": str(area_id)},
        )
        assert resp.status_code == 200, resp.text
        assert (tmp_path / "minha-area" / "nota.md").is_file()
    finally:
        await _delete_demand(demand["id"])
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DocsArea).where(DocsArea.id == area_id))
            await session.commit()


async def test_convert_to_doc_copies_attachments(client: AsyncClient, monkeypatch, tmp_path):
    """Converting to Documento with an attachment must land the attachment
    file next to the note, not just write the markdown body."""
    from app.api.routes import demand as demand_routes
    from app.core import conversions

    monkeypatch.setattr(demand_routes, "DOCS_ROOT", tmp_path)
    monkeypatch.setattr(conversions, "DOCS_ROOT", tmp_path)

    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/attachments",
            files={"file": ("checklist.pdf", b"%PDF-fake-bytes", "application/pdf")},
        )
        assert resp.status_code == 201, resp.text

        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/convert",
            json={"target": "doc", "path": "procedimentos/meu-doc.md"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["reference"] == "procedimentos/meu-doc.md"
        assert (tmp_path / "procedimentos" / "meu-doc.md").is_file()

        copied = tmp_path / "procedimentos" / "checklist.pdf"
        assert copied.is_file()
        assert copied.read_bytes() == b"%PDF-fake-bytes"
    finally:
        await _delete_demand(demand["id"])


async def test_notify_telegram_proxies_to_bridge(client: AsyncClient, monkeypatch):
    """Doesn't hit the real host-bridge (no host-bridge running against
    this test DB, and a real send would spam Telegram on every test run)
    -- verifies the route builds the right payload and passes the bridge's
    response through, using a fake httpx module scoped to demand.py's own
    `httpx` name (patching httpx.AsyncClient globally would also intercept
    the test client fixture's own ASGI-transport requests above)."""
    from app.api.routes import demand as demand_routes

    calls: dict = {}

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"success": True, "note": "Sent to telegram home channel"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None, **kwargs):
            calls["url"] = url
            calls["json"] = json
            return FakeResponse()

    class FakeHttpx:
        AsyncClient = FakeAsyncClient

    monkeypatch.setattr(demand_routes, "httpx", FakeHttpx())

    demand = await _create_demand(client, subject="Alerta de teste", body="conteúdo importante")
    try:
        resp = await client.post(f"/api/v1/demands/{demand['id']}/notify-telegram")
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True
        assert calls["url"].endswith("/v1/messages/send")
        assert calls["json"]["target"] == "telegram"
        assert "Alerta de teste" in calls["json"]["message"]
        assert "conteúdo importante" in calls["json"]["message"]
    finally:
        await _delete_demand(demand["id"])


async def test_update_demand_status_only(client: AsyncClient):
    """Regression: DemandUpdateIn.status became optional (exclude_unset,
    for the group_id-only PATCH the Inbox's drag-and-drop needs) -- a
    plain {"status": "archived"} PATCH must still work exactly as before,
    without touching group_id."""
    demand = await _create_demand(client)
    try:
        resp = await client.patch(f"/api/v1/demands/{demand['id']}", json={"status": "archived"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "archived"
        assert body["group_id"] is None
    finally:
        await _delete_demand(demand["id"])


async def test_patch_demand_group_id_forces_archived(client: AsyncClient):
    """Sending group_id alone (no explicit status) is the drag-and-drop
    case: filing a demand into an Arquivados subfolder must archive it."""
    resp = await client.post("/api/v1/demands/groups", json={"name": f"Tema {uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    group_id = resp.json()["id"]

    demand = await _create_demand(client)
    try:
        resp = await client.patch(f"/api/v1/demands/{demand['id']}", json={"group_id": group_id})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "archived"
        assert body["group_id"] == group_id

        # Moving back to Entrada: group_id: null, explicit status.
        resp = await client.patch(
            f"/api/v1/demands/{demand['id']}", json={"group_id": None, "status": "read"}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "read"
        assert body["group_id"] is None
    finally:
        await _delete_demand(demand["id"])
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DemandGroup).where(DemandGroup.id == uuid.UUID(group_id)))
            await session.commit()


async def test_demand_group_nesting_and_cycle_prevention(client: AsyncClient):
    resp = await client.post("/api/v1/demands/groups", json={"name": f"Root {uuid.uuid4().hex[:8]}"})
    assert resp.status_code == 201, resp.text
    root_id = resp.json()["id"]

    resp = await client.post(
        "/api/v1/demands/groups", json={"name": f"Child {uuid.uuid4().hex[:8]}", "parent_id": root_id}
    )
    assert resp.status_code == 201, resp.text
    child = resp.json()
    assert child["parent_id"] == root_id

    try:
        # Moving root under its own child would create a cycle -- rejected.
        resp = await client.patch(f"/api/v1/demands/groups/{root_id}", json={"parent_id": child["id"]})
        assert resp.status_code == 400, resp.text

        # Renaming without touching parent_id leaves it alone.
        resp = await client.patch(f"/api/v1/demands/groups/{child['id']}", json={"name": "Renamed"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["parent_id"] == root_id
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DemandGroup).where(DemandGroup.id == uuid.UUID(root_id)))
            await session.commit()


async def test_delete_demand_group_cascades_subfolders_and_unsets_demands():
    """Deleting a folder deletes its subfolders (parent_id ondelete=CASCADE)
    but only unsets group_id on demands filed under it (ondelete=SET NULL)
    -- the demand itself must survive, just falls back to the Arquivados
    root."""
    async with AsyncSessionLocal() as session:
        root = DemandGroup(name=f"Root {uuid.uuid4().hex[:8]}")
        session.add(root)
        await session.flush()
        child = DemandGroup(name=f"Child {uuid.uuid4().hex[:8]}", parent_id=root.id)
        session.add(child)
        demand = AgentDemand(
            from_agent="test-suite",
            subject=f"Cascade test {uuid.uuid4().hex[:8]}",
            body="body",
            status="archived",
            group_id=root.id,
        )
        session.add(demand)
        await session.commit()
        root_id, child_id, demand_id = root.id, child.id, demand.id

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(DemandGroup).where(DemandGroup.id == root_id))
            await session.commit()

        async with AsyncSessionLocal() as session:
            assert await session.get(DemandGroup, root_id) is None
            assert await session.get(DemandGroup, child_id) is None
            survivor = await session.get(AgentDemand, demand_id)
            assert survivor is not None
            assert survivor.group_id is None
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(AgentDemand).where(AgentDemand.id == demand_id))
            await session.commit()


async def test_attachment_upload_download_delete(client: AsyncClient, monkeypatch, tmp_path):
    from app.api.routes import demand as demand_routes

    monkeypatch.setattr(demand_routes, "DOCS_ROOT", tmp_path)

    demand = await _create_demand(client)
    try:
        resp = await client.post(
            f"/api/v1/demands/{demand['id']}/attachments",
            files={"file": ("procedimento.md", b"# ola\nconteudo", "text/markdown")},
        )
        assert resp.status_code == 201, resp.text
        attachment = resp.json()
        assert attachment["filename"] == "procedimento.md"
        assert attachment["size_bytes"] == len(b"# ola\nconteudo")

        resp = await client.get(f"/api/v1/demands/{demand['id']}/attachments/{attachment['id']}/download")
        assert resp.status_code == 200
        assert resp.content == b"# ola\nconteudo"

        resp = await client.get("/api/v1/demands")
        mine = next(d for d in resp.json() if d["id"] == demand["id"])
        assert len(mine["attachments"]) == 1

        resp = await client.delete(f"/api/v1/demands/{demand['id']}/attachments/{attachment['id']}")
        assert resp.status_code == 204

        async with AsyncSessionLocal() as session:
            remaining = await session.get(DemandAttachment, uuid.UUID(attachment["id"]))
            assert remaining is None
    finally:
        await _delete_demand(demand["id"])
