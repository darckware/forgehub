import asyncio
import json

import pytest

from app.mcp import personal_agenda as ag


class _Resp:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_local_holiday_is_all_day_without_reminders_and_carries_scope(monkeypatch):
    calls = []
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_test")

    def fake_urlopen(req, timeout=0):
        calls.append((req.get_method(), req.full_url, json.loads(req.data) if req.data else None))
        return _Resp([] if req.get_method() == "GET" else {"id": "holiday-1"})

    monkeypatch.setattr(ag.urllib.request, "urlopen", fake_urlopen)

    result = ag.adicionar_feriado_local("São Sebastião", "20/01/2030", "municipal")

    assert result["tipo"] == "feriado_local"
    assert calls[0][0] == "GET" and calls[0][1].endswith("/events?start=2030-01-20T00%3A00%3A00&end=2030-01-21T00%3A00%3A00")
    method, url, body = calls[1]
    assert method == "POST" and url.endswith("/events")
    assert body["title"] == "Feriado municipal: São Sebastião"
    assert body["starts_at"] == "2030-01-20T00:00:00"
    assert body["all_day"] is True
    assert body["reminders"] == []
    assert body["recurrence"] == ""
    assert "Rio de Janeiro (RJ)" in body["location"]
    assert "municipal" in body["notes"].lower()


def test_local_holiday_is_idempotent_for_same_title_and_date(monkeypatch):
    calls = []
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_test")

    def fake_urlopen(req, timeout=0):
        calls.append(req.get_method())
        return _Resp([{"id": "holiday-existing", "title": "Feriado estadual: São Jorge",
                       "starts_at": "2030-04-23T00:00:00", "all_day": True}])

    monkeypatch.setattr(ag.urllib.request, "urlopen", fake_urlopen)

    result = ag.adicionar_feriado_local("São Jorge", "23/04/2030", "estadual")

    assert result["ja_existia"] is True
    assert result["id"] == "holiday-existing"
    assert calls == ["GET"]


@pytest.mark.parametrize("scope", ["nacional", "regional", "municipalidade"])
def test_local_holiday_rejects_non_local_scope(monkeypatch, scope):
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_test")

    with pytest.raises(ag.AgendaError, match="estadual ou municipal"):
        ag.adicionar_feriado_local("Data", "20/01/2030", scope)


def test_local_holiday_rejects_invalid_date(monkeypatch):
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_test")

    with pytest.raises(ag.AgendaError, match="dd/mm/aaaa"):
        ag.adicionar_feriado_local("Data", "amanhã", "municipal")


def test_mcp_registers_local_holiday_tool(monkeypatch):
    class FakeMcp:
        tools = {}

        def tool(self):
            def register(fn):
                self.tools[fn.__name__] = fn
                return fn
            return register

    monkeypatch.setattr(ag, "adicionar_feriado_local", lambda *args: {"nome": args[0], "scope": args[2]})
    mcp = FakeMcp()

    ag.register(mcp)
    result = asyncio.run(mcp.tools["agenda_add_local_holiday"]("São Sebastião", "20/01/2030", "municipal"))

    assert result == {"success": True, "resultado": {"nome": "São Sebastião", "scope": "municipal"}}
