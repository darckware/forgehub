"""Workspace browser proxy contracts."""

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.config import settings
from app.db.base import AsyncSessionLocal
from app.db.models.product import Product, ProductVersion


@pytest_asyncio.fixture
async def client(auth_headers):
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


def _state(url: str = "http://127.0.0.1:5173/") -> dict:
    return {
        "running": True,
        "cdp_url": "http://127.0.0.1:9223",
        "url": url,
        "title": "ForgeHub",
        "ready_state": "complete",
        "viewport_width": 1440,
        "viewport_height": 757,
        "image_base64": "aW1hZ2U=",
        "captured_at": "2026-07-13T16:00:00",
    }


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self):
        return self._payload


class FakeBridgeClient:
    calls: list[tuple[str, str, dict | None]] = []
    # Override for GET .../test-run/{id} polling (used by the completion-pass
    # tests below) -- None means "still running", matching the real
    # host-bridge's shape while nothing has finished yet.
    get_response: dict | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def request(self, method, url, headers=None, json=None):
        self.calls.append((method, url, json))
        return FakeResponse(_state())

    async def post(self, url, headers=None, json=None):
        self.calls.append(("POST", url, json))
        if url.endswith("/workspace-browser/test-run"):
            return FakeResponse({"test_run_id": json["test_run_id"], "status": "running"})
        return FakeResponse({
            "status": "passed",
            "steps": [{"index": 1, "action": "assert_text", "status": "passed", "outcome": "asserted"}],
            "browser": _state(json["start_url"]),
        })

    async def get(self, url, headers=None, params=None):
        self.calls.append(("GET", url, params))
        return FakeResponse(
            self.get_response
            if self.get_response is not None
            else {"test_run_id": url.rsplit("/", 1)[-1], "status": "running"}
        )


async def test_browser_state_proxies_live_cdp_metadata(client: AsyncClient, monkeypatch):
    from app.api.routes import workspace_browser

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    response = await client.get("/api/v1/workspace-browser/state")

    assert response.status_code == 200, response.text
    assert response.json()["viewport_height"] == 757
    assert FakeBridgeClient.calls[0][1].endswith("/v1/workspace-browser/state")


async def test_login_credential_is_injected_server_side(client: AsyncClient, monkeypatch):
    from app.api.routes import workspace_browser

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    response = await client.post(
        "/api/v1/workspace-browser/login-forgehub",
        json={"url": "http://127.0.0.1:5173/login"},
    )

    assert response.status_code == 200, response.text
    payload = FakeBridgeClient.calls[0][2]
    assert payload == {
        "url": "http://127.0.0.1:5173/login",
        "username": settings.DEV_USER_USERNAME,
        "password": settings.DEV_USER_PASSWORD,
    }


async def test_product_web_automation_routine_crud_and_run(client: AsyncClient, monkeypatch):
    from app.api.routes import workspace_browser

    product_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        product = Product(
            id=product_id,
            name=f"Automation Product {product_id}",
            application_url="http://127.0.0.1:5173/login",
        )
        db.add(product)
        db.add(ProductVersion(product=product, version="0.1.0", status="planned"))
        await db.commit()

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)
    try:
        created = await client.post("/api/v1/workspace-browser/routines", json={
            "product_id": str(product_id),
            "name": "Login smoke test",
            "steps": [
                {"action": "type", "selector": "#username", "value": "admin"},
                {"action": "assert_text", "value": "Welcome back"},
            ],
        })
        assert created.status_code == 201, created.text
        routine_id = created.json()["id"]

        listed = await client.get(f"/api/v1/workspace-browser/routines?product_id={product_id}")
        assert listed.status_code == 200
        assert [item["name"] for item in listed.json()] == ["Login smoke test"]

        run = await client.post(f"/api/v1/workspace-browser/routines/{routine_id}:run")
        assert run.status_code == 200, run.text
        assert run.json()["status"] == "passed"
        assert FakeBridgeClient.calls[-1][2]["start_url"] == "http://127.0.0.1:5173/login"
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Product).where(Product.id == product_id))
            await db.commit()


# ---------------------------------------------------------------------------
# Background app testing (WebAutomationTestRun) -- mocked host-bridge, same
# convention as the tests above in this file (unlike test_project_mcp.py,
# which hits the real host-bridge: this domain's existing tests already
# established mocking here, so new tests follow suit rather than mixing
# conventions within one file). The real end-to-end path (isolated Chromium
# actually launching, screenshots actually written, the completion pass
# actually polling) was verified by hand against the real host-bridge while
# building this feature -- see the plan's Fase 3 verification notes.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def bg_product(client: AsyncClient):
    product_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        product = Product(
            id=product_id, name=f"BG Test Product {product_id}", application_url="http://127.0.0.1:5173/login"
        )
        db.add(product)
        db.add(ProductVersion(product=product, version="0.1.0", status="planned"))
        await db.commit()
    yield product_id
    async with AsyncSessionLocal() as db:
        await db.execute(delete(Product).where(Product.id == product_id))
        await db.commit()


async def test_background_test_toggle_requires_url(client: AsyncClient):
    """A routine can't even be *created* without a resolvable start URL
    (create_routine already calls _resolve_start_url) -- so the only way to
    reach the toggle's own 409 guard is a routine whose product later lost
    its application_url, not a product with none from the start."""
    product_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        product = Product(
            id=product_id, name=f"Losing URL Product {product_id}", application_url="http://127.0.0.1:5173/login"
        )
        db.add(product)
        db.add(ProductVersion(product=product, version="0.1.0", status="planned"))
        await db.commit()
    try:
        created = await client.post(
            "/api/v1/workspace-browser/routines",
            json={"product_id": str(product_id), "name": "Losing URL Routine", "steps": [{"action": "wait", "wait_ms": 100}]},
        )
        assert created.status_code == 201, created.text
        routine_id = created.json()["id"]

        async with AsyncSessionLocal() as db:
            product = await db.get(Product, product_id)
            product.application_url = None
            await db.commit()

        resp = await client.put(f"/api/v1/workspace-browser/routines/{routine_id}/background-test", json={"enabled": True})
        assert resp.status_code == 409
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Product).where(Product.id == product_id))
            await db.commit()


async def test_toggle_and_run_background_mode(client: AsyncClient, bg_product, monkeypatch):
    from app.api.routes import workspace_browser

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    created = await client.post(
        "/api/v1/workspace-browser/routines",
        json={"product_id": str(bg_product), "name": "BG Routine", "steps": [{"action": "wait", "wait_ms": 100}]},
    )
    routine_id = created.json()["id"]

    toggle = await client.put(f"/api/v1/workspace-browser/routines/{routine_id}/background-test", json={"enabled": True})
    assert toggle.status_code == 200, toggle.text
    assert toggle.json()["background_test_enabled"] is True

    run = await client.post(f"/api/v1/workspace-browser/routines/{routine_id}:run-background", json={"mode": "background"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["mode"] == "background"
    assert body["status"] == "running"
    assert body["bridge_run_id"] is not None
    assert body["triggered_by"] == "slash_command"
    assert FakeBridgeClient.calls[-1][1].endswith("/workspace-browser/test-run")


async def test_run_background_visible_mode_is_synchronous(client: AsyncClient, bg_product, monkeypatch):
    from app.api.routes import workspace_browser

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    created = await client.post(
        "/api/v1/workspace-browser/routines",
        json={"product_id": str(bg_product), "name": "Visible Routine", "steps": [{"action": "wait", "wait_ms": 100}]},
    )
    routine_id = created.json()["id"]

    run = await client.post(f"/api/v1/workspace-browser/routines/{routine_id}:run-background", json={"mode": "visible"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["mode"] == "visible"
    assert body["status"] == "passed"  # finished synchronously, unlike mode=background
    assert body["bridge_run_id"] is None
    # Delegated to /run-routine, never /test-run.
    assert FakeBridgeClient.calls[-1][1].endswith("/workspace-browser/run-routine")


async def test_ad_hoc_background_test_has_no_routine(client: AsyncClient, bg_product, monkeypatch):
    from app.api.routes import workspace_browser

    FakeBridgeClient.calls = []
    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    resp = await client.post(
        "/api/v1/workspace-browser/background-test",
        json={"product_id": str(bg_product), "steps": [{"action": "wait", "wait_ms": 100}], "mode": "background"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["routine_id"] is None
    assert body["triggered_by"] == "mcp_tool"
    assert body["status"] == "running"


async def test_ad_hoc_background_test_requires_exactly_one_target(client: AsyncClient, bg_product):
    resp = await client.post(
        "/api/v1/workspace-browser/background-test",
        json={"steps": [{"action": "wait", "wait_ms": 100}]},
    )
    assert resp.status_code == 422  # neither product_id nor standalone_app_id


async def test_test_runs_history_filters_by_product(client: AsyncClient, bg_product, monkeypatch):
    from app.api.routes import workspace_browser

    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    await client.post(
        "/api/v1/workspace-browser/background-test",
        json={"product_id": str(bg_product), "steps": [{"action": "wait", "wait_ms": 100}], "mode": "background"},
    )

    listed = await client.get(f"/api/v1/workspace-browser/test-runs?product_id={bg_product}")
    assert listed.status_code == 200
    runs = listed.json()
    assert len(runs) == 1
    assert runs[0]["product_id"] == str(bg_product)

    detail = await client.get(f"/api/v1/workspace-browser/test-runs/{runs[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == runs[0]["id"]


async def test_completion_pass_finishes_background_run(client: AsyncClient, bg_product, monkeypatch):
    from app.api.routes import workspace_browser
    from app.db.base import AsyncSessionLocal as SessionLocal

    monkeypatch.setattr(workspace_browser.httpx, "AsyncClient", FakeBridgeClient)

    dispatched = await client.post(
        "/api/v1/workspace-browser/background-test",
        json={"product_id": str(bg_product), "steps": [{"action": "wait", "wait_ms": 100}], "mode": "background"},
    )
    run_id = dispatched.json()["id"]
    assert dispatched.json()["status"] == "running"

    # Simulate the isolated browser having finished, then run the same pass
    # main.py's poll loop calls periodically.
    FakeBridgeClient.get_response = {
        "test_run_id": run_id, "status": "passed", "steps": [], "report": "PASSED -- 1 step(s) executed",
        "screenshot_paths": ["/root/.forgehub/test-runs/x/step-1.jpg"], "error": None,
    }
    try:
        async with SessionLocal() as db:
            await workspace_browser.run_background_test_completion_pass(db)
    finally:
        FakeBridgeClient.get_response = None

    detail = await client.get(f"/api/v1/workspace-browser/test-runs/{run_id}")
    assert detail.json()["status"] == "passed"
    assert detail.json()["report"] == "PASSED -- 1 step(s) executed"
    assert detail.json()["screenshot_paths"] == ["/root/.forgehub/test-runs/x/step-1.jpg"]
