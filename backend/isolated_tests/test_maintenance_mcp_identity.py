"""Both agy registry entries must use the run file, never legacy env tokens."""
import asyncio
import httpx
import pytest
from app.mcp import factory_server


@pytest.mark.parametrize("server", [factory_server, factory_server.messages])
@pytest.mark.parametrize("credential", [None, "missing", "invalid", "valid"])
def test_maintenance_identity_has_no_legacy_fallback(tmp_path, monkeypatch, server, credential):
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_synthetic_legacy_wrong_identity")
    monkeypatch.setenv("FORGEHUB_AGENT_SLUG", "legacy-agent")
    monkeypatch.delenv("FORGEHUB_AGENT_TOKEN_FILE", raising=False)
    run_file = tmp_path / "run-credential"
    if credential is not None:
        monkeypatch.setenv("FORGEHUB_AGENT_TOKEN_FILE", str(run_file))
    if credential in {"invalid", "valid"}:
        run_file.write_text("agt_synthetic_dispatched_identity" if credential == "valid" else "invalid")
    seen = []
    def handle(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json=[])
    original = httpx.AsyncClient
    monkeypatch.setattr(server.messages.httpx if server is factory_server else server.httpx,
                        "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle)))
    if credential == "valid":
        assert asyncio.run(server.list_maintenance_machines()) == []
        assert seen == ["Bearer agt_synthetic_dispatched_identity"]
    else:
        with pytest.raises(factory_server.messages.ForgeHubError):
            asyncio.run(server.list_maintenance_machines())
        assert seen == []
