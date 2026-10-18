"""MCP pessoal (contatos): só a Maia vê as ferramentas, e cada uma vira a chamada certa à API do ForgeHub
com a resposta no formato que a Maia já conhece. As regras em si (telefone, categoria, histórico) são
testadas na API: test_personal_contacts.py."""

import json
from types import SimpleNamespace

import pytest
from mcp.server.fastmcp import FastMCP

from app.mcp import personal_contacts as pc

CONTACT = {
    "id": "c1", "phone": "5521998975416", "phone_display": "+55 21 99897-5416", "name": "Patrícia",
    "category": "familia", "relation": "esposa", "birthday": "18/05/1970", "observations": "",
    "who_is": "Esposa do Marcelo.", "how_to_treat": "Com carinho.", "other_data": {"cargo": "x"},
    "blocked": False, "last_contact_at": "2026-10-12T13:00:00+00:00", "pending_suggestions": 1,
}
MESSAGES = [  # mais nova primeiro, como a API devolve
    {"at": "2026-10-12T13:05:00+00:00", "author": "Marcelo", "direction": "out", "text": "sim", "context": None},
    {"at": "2026-10-12T13:00:00+00:00", "author": "Patrícia", "direction": "in", "text": "almoço domingo?",
     "context": "Confirma o almoço de domingo."},
]


@pytest.fixture()
def api(monkeypatch):
    calls: list[tuple] = []
    responses: dict[tuple[str, str], object] = {}

    def fake(method, path, body=None, query=None):
        calls.append((method, path, body, query))
        for (m, prefix), value in responses.items():
            if m == method and path.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value(body) if callable(value) else value
        raise AssertionError(f"chamada inesperada: {method} {path}")

    monkeypatch.setattr(pc, "_call", fake)
    return SimpleNamespace(calls=calls, responses=responses)


def test_tools_are_registered_only_for_allowed_agents(monkeypatch):
    for slug, expected in (("maia", True), ("athos", False), ("lara", False), ("", False)):
        monkeypatch.setenv("FORGEHUB_AGENT_SLUG", slug)
        monkeypatch.delenv("FORGEHUB_PERSONAL_CONTACTS_AGENTS", raising=False)
        server = FastMCP("t")
        assert pc.register(server) is expected
        names = set(server._tool_manager._tools)
        assert ("personal_contact_upsert" in names) is expected
        assert ("personal_capture_accept" in names) is expected
        assert ("personal_weather" in names) is expected


def test_get_contact_keeps_the_maias_format(api):
    api.responses[("GET", "/contacts/5521998975416/messages")] = MESSAGES
    api.responses[("GET", "/contacts/5521998975416")] = CONTACT
    c = pc.get_contact("21 99897-5416")
    assert c["nome"] == "Patrícia" and c["telefone"] == "+55 21 99897-5416" and c["categoria"] == "familia"
    assert c["quem_e"] == "Esposa do Marcelo." and c["outros_dados"] == {"cargo": "x"}
    assert c["ultimo_contato"] == "12/10/2026 10:00" and c["sugestoes_pendentes"] == 1
    assert c["historico_recente"] == [
        "- **12/10/2026 10:00** · Patrícia: almoço domingo? [contexto: Confirma o almoço de domingo.]",
        "- **12/10/2026 10:05** · Marcelo: sim",
    ]


def test_upsert_sends_only_given_fields(api):
    api.responses[("PUT", "/contacts/")] = CONTACT
    api.responses[("GET", "/contacts/5521998975416/messages")] = []
    api.responses[("GET", "/contacts/5521998975416")] = CONTACT
    pc.upsert_contact("+55 21 99897-5416", nome="Patrícia", categoria="Família", outros_dados={"cargo": ""}, bloqueado=False)
    method, path, body, _ = api.calls[0]
    assert (method, path) == ("PUT", "/contacts/5521998975416")
    assert body == {"name": "Patrícia", "category": "Família", "other_data": {"cargo": ""}, "blocked": False}


def test_invalid_phone_never_reaches_the_api(api):
    with pytest.raises(pc.PersonalContactsError):
        pc.upsert_contact("123", nome="x")
    assert api.calls == []


def test_errors_become_safe_tool_results(api, monkeypatch):
    api.responses[("POST", "/contacts/")] = pc.PersonalContactsError("O novo telefone já pertence a outro contato.")
    assert pc._safe(pc.change_phone, "21998975416", "21999990000", chave="contato") == {
        "success": False, "error": "O novo telefone já pertence a outro contato."}


def test_upsert_many_maps_both_ways(api):
    api.responses[("POST", "/contacts:upsert-many")] = {
        "saved": [{"phone": "5521965288603", "name": "Alan", "category": "trabalho_semed"}],
        "errors": [{"phone": "123", "error": "Telefone inválido"}],
    }
    r = pc.upsert_many([
        {"telefone": "+55 21 96528-8603", "nome": "Alan", "categoria": "Trabalho (SEMED)"},
        {"telefone": "123", "nome": "inválido"},
    ])
    assert api.calls[0][2]["contacts"][0] == {"phone": "+55 21 96528-8603", "name": "Alan", "category": "Trabalho (SEMED)"}
    assert r == {"gravados": [{"telefone": "+55 21 96528-8603", "nome": "Alan", "categoria": "trabalho_semed"}],
                 "erros": [{"telefone": "123", "erro": "Telefone inválido"}]}


def test_history_and_instructions(api):
    api.responses[("POST", "/contacts/5521998975416/messages")] = {}
    api.responses[("GET", "/contacts/5521998975416/messages")] = []
    api.responses[("GET", "/contacts/5521998975416")] = CONTACT
    pc.add_history("21998975416", "combinamos almoço no sábado")
    assert api.calls[0][2] == {"text": "combinamos almoço no sábado", "direction": "note", "author": "Marcelo",
                               "source": "telegram"}
    api.responses[("PUT", "/assistant-settings")] = lambda body: {"instructions": body["instructions"]}
    assert pc.set_instructions("  Seja breve.  ") == "Seja breve."
    with pytest.raises(pc.PersonalContactsError):
        pc.set_instructions("x" * 6001)


def test_suggestions(api):
    api.responses[("GET", "/suggestions")] = [{"id": "s1", "kind": "task", "title": "Enviar boleto", "details": "até sexta",
                                               "contact_name": "Ana", "contact_phone": "5521999991234"}]
    assert pc.list_suggestions() == [{"id": "s1", "tipo": "tarefa", "titulo": "Enviar boleto", "detalhes": "até sexta",
                                      "contato": "Ana", "telefone": "+55 21 99999-1234"}]
    api.responses[("POST", "/suggestions/s1:accept")] = {"kind": "note", "title": "Endereço", "created_item_id": "n1"}
    assert pc.accept_suggestion("s1", tipo="anotação", titulo="Endereço") == {"criado": "anotacao", "titulo": "Endereço", "item_id": "n1"}
    assert api.calls[-1][2] == {"kind": "note", "title": "Endereço"}
    with pytest.raises(pc.PersonalContactsError):
        pc.accept_suggestion("s1", tipo="lembrete")


def _fake_send(ok=True):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        out = {"success": True, "message_id": "M1"} if ok else {"success": False, "error": "falhou"}
        return SimpleNamespace(returncode=0 if ok else 1, stdout=json.dumps(out), stderr="")

    return run, calls


def test_whatsapp_send_opens_task_and_records_history(api, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "TAREFAS", tmp_path / "tarefas.json")
    monkeypatch.setattr(pc, "ENVIOS_LOG", tmp_path / "envios.jsonl")
    api.responses[("POST", "/whatsapp/messages")] = {}
    api.responses[("GET", "/contacts/5521998975416")] = CONTACT
    run, calls = _fake_send()

    r = pc.whatsapp_send("21 99897-5416", "Oi Patrícia, aqui é a Maia.", objetivo="combinar o jantar de sábado", _runner=run)

    cmd, kwargs = calls[0]
    assert cmd[-6:] == ["send", "--to", "whatsapp:5521998975416", "--json", "--file", "-"]
    assert kwargs["input"] == "Oi Patrícia, aqui é a Maia."  # texto pelo stdin, nunca no argv
    assert r["tarefa_aberta"] and r["contato"] == "Patrícia"
    recorded = api.calls[0][2]
    assert recorded["direction"] == "out" and recorded["author"] == "Maia" and "enviado pela Maia" in recorded["text"]
    assert pc.get_tasks()["5521998975416"]["objetivo"] == "combinar o jantar de sábado"
    assert pc.close_task("21998975416") and pc.get_tasks() == {}


def test_whatsapp_send_survives_forgehub_being_down(api, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "TAREFAS", tmp_path / "tarefas.json")
    monkeypatch.setattr(pc, "ENVIOS_LOG", tmp_path / "envios.jsonl")
    api.responses[("POST", "/whatsapp/messages")] = pc.PersonalContactsError("ForgeHub indisponível")
    run, _ = _fake_send()
    assert pc.whatsapp_send("21999990000", "oi", _runner=run)["enviado_para"] == "+55 21 99999-0000"


def test_whatsapp_send_validation_and_rate_limit(api, tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "TAREFAS", tmp_path / "tarefas.json")
    monkeypatch.setattr(pc, "ENVIOS_LOG", tmp_path / "envios.jsonl")
    api.responses[("POST", "/whatsapp/messages")] = {}
    api.responses[("GET", "/contacts/")] = CONTACT
    run, _ = _fake_send()
    with pytest.raises(pc.PersonalContactsError):
        pc.whatsapp_send("123", "oi", _runner=run)
    with pytest.raises(pc.PersonalContactsError):
        pc.whatsapp_send("21999990000", "", _runner=run)
    bad, _ = _fake_send(ok=False)
    with pytest.raises(pc.PersonalContactsError):
        pc.whatsapp_send("21999990000", "oi", _runner=bad)
    monkeypatch.setattr(pc, "ENVIOS_POR_HORA", 2)
    pc.whatsapp_send("21999990000", "um", _runner=run)
    pc.whatsapp_send("21999990000", "dois", _runner=run)
    with pytest.raises(pc.PersonalContactsError):
        pc.whatsapp_send("21999990000", "três", _runner=run)
