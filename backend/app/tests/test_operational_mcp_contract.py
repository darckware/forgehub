"""Offline regressions against the actual API response schemas."""
import pytest
import httpx

from app.mcp.factory_server import messages


@pytest.mark.parametrize("status", ["ok", "fail", "timeout", "error"])
async def test_auditor_reads_nested_run(monkeypatch, status):
    async def call(method, path, **kwargs):
        return [{"id": "check", "name": "ECO-001", "enabled": True,
                 "last_run": {"status": status, "created_at": "2026-10-18T22:00:00Z"}}]

    monkeypatch.setattr(messages, "_call", call)
    result = await messages.list_audit_checks()
    assert f"Status: {status}" in result
    assert "never_ran" not in result
    assert "2026-10-18" in result


async def test_auditor_distinguishes_disabled_and_missing_runs(monkeypatch):
    async def call(*args, **kwargs):
        return [{"name": "ECO-001", "enabled": False, "last_run": None},
                {"name": "ECO-002", "enabled": True, "last_run": None}]

    monkeypatch.setattr(messages, "_call", call)
    result = await messages.list_audit_checks()
    assert "disabled" in result
    assert result.count("never_ran") == 1


async def test_system_metrics_use_host_stats_without_inventing_cpu(monkeypatch):
    async def call(method, path, **kwargs):
        assert path == "/api/v1/system-stats"
        return {"memory": {"total_bytes": 8 * 1024**3, "used_bytes": 2 * 1024**3,
                           "percent_used": 25},
                "disk": {"total_bytes": 100 * 1024**3, "used_bytes": 50 * 1024**3,
                         "percent_used": 50}}

    monkeypatch.setattr(messages, "_call", call)
    result = await messages.get_system_status()
    assert "25%" in result and "50%" in result
    assert "CPU: unavailable" in result
    assert "0 cores" not in result


async def test_missing_metrics_are_unavailable_not_zero(monkeypatch):
    async def call(*args, **kwargs):
        return {"git": {}, "backups": {}}

    monkeypatch.setattr(messages, "_call", call)
    result = await messages.get_system_status()
    assert "Memory: unavailable" in result and "Disk: unavailable" in result
    assert "0.0" not in result
    assert "health cannot be inferred" in result


async def test_audit_execution_counts_actual_runs_and_exposes_failures(monkeypatch):
    async def call(method, path, **kwargs):
        assert path == "/api/v1/audit/run"
        return {"runs": [{"check_id": "a", "status": "ok"},
                         {"check_id": "b", "status": "timeout", "output": "timed out"},
                         {"check_id": "c", "status": "error", "output": "bridge error"}]}

    monkeypatch.setattr(messages, "_call", call)
    result = await messages.run_audit_checks()
    assert "1/3 passed, 2 failed" in result
    assert "timed out" in result and "bridge error" in result


@pytest.mark.parametrize("response", [{}, {"runs": []}])
async def test_empty_audit_response_never_reports_success(monkeypatch, response):
    async def call(*args, **kwargs):
        return response

    monkeypatch.setattr(messages, "_call", call)
    result = await messages.run_audit_checks()
    assert "unavailable" in result
    assert "completed" not in result


async def test_stats_bridge_auth_is_validated_and_scoped(monkeypatch):
    from app.main import app
    from app.core.config import settings
    from app.api.routes import systemstats

    monkeypatch.setattr(settings, "CHAT_BRIDGE_TOKEN", "test-stats-token")
    original_client = httpx.AsyncClient
    payload = {"memory": {"total_bytes": 100, "used_bytes": 20, "available_bytes": 80, "percent_used": 20},
               "disk": {"total_bytes": 100, "used_bytes": 40, "free_bytes": 60, "percent_used": 40},
               "network": {"interface": "eth0", "rx_bytes": 1, "tx_bytes": 2}}

    def upstream(request):
        assert request.url.path == "/v1/system-stats"
        assert request.headers["X-Bridge-Token"] == "test-stats-token"
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(systemstats.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(upstream), **kwargs))
    async with original_client(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/system-stats")).status_code == 401
        assert (await client.get("/api/v1/system-stats", headers={"X-Bridge-Token": "wrong"})).status_code == 401
        response = await client.get("/api/v1/system-stats", headers={"X-Bridge-Token": "test-stats-token"})
        assert response.status_code == 200
        assert response.json() == payload
        assert (await client.get("/api/v1/system-stats/other", headers={"X-Bridge-Token": "test-stats-token"})).status_code == 401
