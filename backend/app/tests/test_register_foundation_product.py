import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import httpx

spec = importlib.util.spec_from_file_location(
    "register_foundation", Path(__file__).resolve().parents[3] / "scripts/register_foundation_product.py"
)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


@pytest.fixture
def client(auth_headers, monkeypatch):
    monkeypatch.setattr(registry, "PRODUCT", f"Foundation test {uuid4()}")
    monkeypatch.setattr(registry, "PROJECT", f"Plano test {uuid4()}")
    with httpx.Client(base_url="http://127.0.0.1:8002", headers=auth_headers) as client:
        yield client


def test_dry_run_and_idempotence(client):
    created = None
    try:
        preview = registry.register(client, dry_run=True)
        assert preview["product_id"] is None and preview["project_id"] is None
        assert not any(x["name"] == registry.PRODUCT for x in client.get("/api/v1/products").json())
        assert not any(x["name"] == registry.PROJECT for x in client.get("/api/v1/projects").json())
        created = registry.register(client)
        reused = registry.register(client)
        for entity in ("product", "version", "project"):
            assert created[entity] == "created" and reused[entity] == "reused"
            assert created[f"{entity}_id"] == reused[f"{entity}_id"]
        assert sum(x["name"] == registry.PRODUCT for x in client.get("/api/v1/products").json()) == 1
        assert sum(x["name"] == registry.PROJECT for x in client.get("/api/v1/projects").json()) == 1
        versions = client.get(f"/api/v1/products/{created['product_id']}/versions").json()
        assert sum(x["version"] == registry.VERSION for x in versions) == 1
    finally:
        if created:
            assert client.delete(f"/api/v1/projects/{created['project_id']}").status_code == 204
            assert client.delete(f"/api/v1/products/{created['product_id']}").status_code == 204


def test_duplicate_product_aborts_before_write(client, monkeypatch):
    original = client.request
    def duplicate(method, url, **kwargs):
        response = original(method, url, **kwargs)
        if method == "GET" and url == "/api/v1/products":
            monkeypatch.setattr(response, "json", lambda: [{"name": registry.PRODUCT}] * 2)
        return response
    monkeypatch.setattr(client, "request", duplicate)
    with pytest.raises(ValueError, match="duplicado"):
        registry.register(client)
    assert not any(x["name"] == registry.PROJECT for x in client.get("/api/v1/projects").json())
