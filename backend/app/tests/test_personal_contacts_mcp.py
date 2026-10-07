"""MCP pessoal: só a Maia vê as ferramentas, e nada apaga histórico."""

from datetime import date

import pytest
from mcp.server.fastmcp import FastMCP

from app.mcp import personal_contacts as pc


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "BASE", tmp_path)
    return tmp_path


def test_tools_are_registered_only_for_allowed_agents(monkeypatch):
    for slug, expected in (("maia", True), ("athos", False), ("lara", False), ("", False)):
        monkeypatch.setenv("FORGEHUB_AGENT_SLUG", slug)
        monkeypatch.delenv("FORGEHUB_PERSONAL_CONTACTS_AGENTS", raising=False)
        server = FastMCP("t")
        assert pc.register(server) is expected
        names = set(server._tool_manager._tools)
        assert ("personal_contact_upsert" in names) is expected


def test_upsert_creates_row_and_profile_then_updates_without_losing_history(base):
    c = pc.upsert_contact("+55 21 99897-5416", nome="Patrícia", categoria="familia", relacao="esposa",
                          aniversario="18/05/1970", quem_e="Esposa do Marcelo.", como_tratar="Com carinho.")
    assert c["categoria"] == "familia" and c["telefone"] == "+55 21 99897-5416"
    ficha = base / "contatos" / "5521998975416.md"
    ficha.write_text(ficha.read_text() + "- **07/10/2026 18:00** · Patrícia: oi\n")

    c = pc.upsert_contact("21998975416", como_tratar="Com muito carinho.")
    assert c["nome"] == "Patrícia" and c["relacao"] == "esposa"
    assert c["como_tratar"] == "Com muito carinho." and c["quem_e"] == "Esposa do Marcelo."
    assert c["historico_recente"] == ["- **07/10/2026 18:00** · Patrícia: oi"]
    assert len(pc.list_contacts()) == 1
    assert 'aniversario: "18/05/1970"' in ficha.read_text()


def test_validation(base):
    with pytest.raises(pc.PersonalContactsError):
        pc.upsert_contact("123")
    with pytest.raises(pc.PersonalContactsError):
        pc.upsert_contact("21999990000", categoria="vizinho")
    with pytest.raises(pc.PersonalContactsError):
        pc.upsert_contact("21999990000", aniversario="maio")
    with pytest.raises(pc.PersonalContactsError):
        pc.get_contact("21999990000")


def test_upcoming_birthdays(base):
    pc.upsert_contact("21998975416", nome="Patrícia", aniversario="18/05/1970")
    pc.upsert_contact("21972311012", nome="Filha", aniversario="31/10/2022")
    proximos = pc.upcoming_birthdays(30, hoje=date(2026, 10, 7))
    assert [(p["nome"], p["faltam_dias"], p["idade"]) for p in proximos] == [("Filha", 24, 4)]


def test_free_fields_and_history(base):
    pc.upsert_contact("21998975416", nome="Patrícia", outros_dados={"profissão": "médica", "cidade": "Niterói"})
    pc.upsert_contact("21998975416", outros_dados={"cidade": "", "time": "Flamengo"})
    c = pc.add_history("21998975416", "combinamos almoço no sábado")
    assert c["outros_dados"] == {"profissão": "médica", "time": "Flamengo"}
    assert c["historico_recente"][-1].endswith("· Marcelo: combinamos almoço no sábado")
    with pytest.raises(pc.PersonalContactsError):
        pc.add_history("21900000000", "x")


def test_forgehub_catalog_has_no_personal_tools():
    from app.mcp import factory_server

    assert not any(name.startswith("personal_") for name in factory_server.mcp._tool_manager._tools)


def test_instructions_roundtrip_keeps_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "INSTRUCOES", tmp_path / "INSTRUCOES_PESSOAIS.md")
    assert pc.get_instructions() == ""
    pc.set_instructions("Tratar a Patrícia com carinho.")
    assert pc.set_instructions("Tratar a Patrícia e a Marcela com carinho.").startswith("Tratar a Patrícia e a Marcela")
    assert len(list(tmp_path.glob("*.bak"))) == 1
    with pytest.raises(pc.PersonalContactsError):
        pc.set_instructions("x" * 6001)


def _fake_send(ok=True):
    import json
    from types import SimpleNamespace

    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        out = {"success": True, "message_id": "M1"} if ok else {"error": "Chat not found"}
        return SimpleNamespace(returncode=0 if ok else 1, stdout=json.dumps(out), stderr="")

    return run, calls


def test_whatsapp_send_opens_task_and_logs_history(base, monkeypatch):
    monkeypatch.setattr(pc, "TAREFAS", base / "tarefas.json")
    monkeypatch.setattr(pc, "ENVIOS_LOG", base / "envios.jsonl")
    pc.upsert_contact("21998975416", nome="Patrícia", categoria="familia")
    run, calls = _fake_send()

    r = pc.whatsapp_send("21 99897-5416", "Oi Patrícia, aqui é a Maia.", objetivo="combinar o jantar de sábado", _runner=run)

    cmd, kwargs = calls[0]
    assert cmd[-6:] == ["send", "--to", "whatsapp:5521998975416", "--json", "--file", "-"]
    assert kwargs["input"] == "Oi Patrícia, aqui é a Maia."  # texto pelo stdin, nunca no argv
    assert r["tarefa_aberta"] and r["contato"] == "Patrícia"
    assert pc.get_tasks()["5521998975416"]["objetivo"] == "combinar o jantar de sábado"
    assert "enviado pela Maia" in pc.get_contact("21998975416")["historico_recente"][-1]
    assert pc.close_task("21998975416") and pc.get_tasks() == {}


def test_whatsapp_send_validation_and_rate_limit(base, monkeypatch):
    monkeypatch.setattr(pc, "TAREFAS", base / "tarefas.json")
    monkeypatch.setattr(pc, "ENVIOS_LOG", base / "envios.jsonl")
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
