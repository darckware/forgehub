"""MCP pessoal → API do módulo Pessoal: formatos de data, mapeamento de campos, erros."""
import json

import pytest

from app.mcp import personal_agenda as ag


class _Resp:
    def __init__(self, data):
        self._raw = json.dumps(data).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture()
def calls(monkeypatch):
    seen = []
    monkeypatch.setenv("FORGEHUB_AGENT_TOKEN", "agt_test")

    def fake_urlopen(req, timeout=0):
        seen.append((req.get_method(), req.full_url, json.loads(req.data) if req.data else None,
                     req.headers.get("Authorization")))
        if req.full_url.endswith("/reminders:due"):
            return _Resp({"lines": ["✅ Lembrete (agora): x"]})
        return _Resp({"id": "1"})

    monkeypatch.setattr(ag.urllib.request, "urlopen", fake_urlopen)
    return seen


def test_compromisso_vira_evento(calls):
    ag.adicionar("Dentista", "10/01/2030 15:00", local="Centro", lembretes=[1440, 60], recorrencia="mensal")
    method, url, body, auth = calls[0]
    assert method == "POST" and url.endswith("/api/v1/personal/events") and auth == "Bearer agt_test"
    assert body == {"title": "Dentista", "starts_at": "2030-01-10T15:00:00", "all_day": False, "location": "Centro",
                    "notes": None, "recurrence": "monthly", "reminders": [1440, 60]}


def test_tarefa_sem_hora_e_sem_data(calls):
    ag.adicionar("Pagar IPVA", "10/01/2030", tipo="tarefa", lista="Casa")
    ag.adicionar("Ler livro", tipo="tarefa")
    assert calls[0][2] == {"title": "Pagar IPVA", "notes": None, "recurrence": "", "list_name": "Casa",
                           "due_at": "2030-01-10T00:00:00", "due_has_time": False}
    assert "due_at" not in calls[1][2]


def test_concluir_tarefa_usa_complete_e_compromisso_cancela(calls):
    ag.atualizar("t1", "tarefa", status="concluido")
    ag.atualizar("e1", "compromisso", status="cancelado")
    assert calls[0][:2] == ("POST", ag.API + "/tasks/t1:complete")
    assert calls[1][0] == "PATCH" and calls[1][2] == {"status": "cancelled"}


def test_lembretes_e_validacao(calls):
    assert ag.lembretes_devidos() == ["✅ Lembrete (agora): x"]
    with pytest.raises(ag.AgendaError):
        ag.adicionar("x", "amanhã")
    with pytest.raises(ag.AgendaError):
        ag.adicionar("x", tipo="compromisso")
    with pytest.raises(ag.AgendaError):
        ag.adicionar("x", "10/01/2030", recorrencia="horaria")


def test_sem_credencial(monkeypatch):
    monkeypatch.delenv("FORGEHUB_AGENT_TOKEN", raising=False)
    with pytest.raises(ag.AgendaError):
        ag.lembretes_devidos()
