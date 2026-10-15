"""MCP da Maia: grupos do WhatsApp — leitura e envio só com o código do Marcelo."""
import json
import re
from types import SimpleNamespace

import pytest

from app.mcp import personal_groups as pg

CHAT = "120363000000000001@g.us"


@pytest.fixture()
def base(tmp_path, monkeypatch):
    grupos = tmp_path / "whatsapp" / "grupos"
    grupos.mkdir(parents=True)
    (tmp_path / ".env").write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_HOME_CHANNEL=42\n")
    monkeypatch.setattr(pg, "PROFILE", tmp_path)
    monkeypatch.setattr(pg, "GRUPOS", grupos)
    monkeypatch.setattr(pg, "RASCUNHOS", grupos / "_rascunhos.json")
    monkeypatch.setattr(pg, "ENVIOS_LOG", grupos / "_envios.jsonl")
    (grupos / "_grupos.json").write_text(json.dumps({CHAT: {"nome": "Família Ferreira"},
                                                     "2@g.us": {"nome": "Condomínio"}}))
    (grupos / "120363000000000001.jsonl").write_text(
        json.dumps({"ts": 1000.0, "quando": "12/10/2026 10:00", "chat": CHAT, "autor": "Ana", "texto": "almoço domingo?"}) + "\n")
    return grupos


def _fake_urlopen(store):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def urlopen(req, timeout=0):
        from urllib.parse import parse_qs
        store.append((req.full_url, {k: v[0] for k, v in parse_qs(req.data.decode()).items()}))
        return Resp()
    return urlopen


def _runner(calls, ok=True):
    def run(cmd, input=None, **_):
        calls.append((cmd, input))
        return SimpleNamespace(returncode=0 if ok else 1, stdout=json.dumps({"success": ok, "message_id": "m1"}), stderr="")
    return run


def test_list_and_read_groups(base):
    grupos = pg.list_groups(agora=1000.0 + 60)
    assert grupos[0] == {"grupo": "Família Ferreira", "id": CHAT, "status": "active", "mensagens_24h": 1, "ultima_mensagem": "12/10/2026 10:00"}
    msgs = pg.group_messages("família", horas=24, agora=1000.0 + 60)
    assert msgs["mensagens"] == [{"quando": "12/10/2026 10:00", "autor": "Ana", "texto": "almoço domingo?"}]


def test_sync_is_read_only_and_reports_bridge_limitation(base, monkeypatch):
    before = (base / "_grupos.json").read_text()
    monkeypatch.setattr(pg, "_bridge_group_catalog", lambda: None)
    resultado = pg.sync_groups(agora=1000.0 + 60, dry_run=True)
    assert resultado["descobertos"] == 2
    assert resultado["complete"] is False
    assert resultado["status_bridge"] == "sem_catalogo_read_only"
    assert {grupo["id"] for grupo in resultado["grupos"]} == {CHAT, "2@g.us"}
    assert (base / "_grupos.json").read_text() == before


def test_sync_merges_observed_group_without_network_or_send(base, monkeypatch):
    novo = "120363999999999999@g.us"
    (base / "120363999999999999.jsonl").write_text(json.dumps({
        "ts": 1100.0, "chat": novo, "grupo": "Grupo Novo", "texto": "olá"
    }) + "\n")
    monkeypatch.setattr(pg, "_bridge_group_catalog", lambda: None)
    resultado = pg.sync_groups(agora=1200.0)
    assert resultado["alterado"] is True
    salvo = json.loads((base / "_grupos.json").read_text())
    assert salvo[novo]["nome"] == "Grupo Novo"
    assert salvo[novo]["id"] == novo
    assert salvo[novo]["status"] == "active"


def test_resolve_rejects_unknown_and_ambiguous(base):
    with pytest.raises(pg.GroupError):
        pg.resolve_group("trabalho")
    with pytest.raises(pg.GroupError):
        pg.resolve_group("i")  # casa com os dois nomes


def test_draft_sends_code_only_to_telegram_api_and_stores_hash(base):
    enviados = []
    r = pg.draft("Família", "Chego às 13h", agora=5000.0, _urlopen=_fake_urlopen(enviados))
    url, dados = enviados[0]
    assert url == "https://api.telegram.org/bottok/sendMessage" and dados["chat_id"] == "42"
    codigo = re.search(r"autorizo \w+ (\d{6})", dados["text"]).group(1)
    assert "Chego às 13h" in dados["text"] and codigo not in json.dumps(r)
    salvo = json.loads(pg.RASCUNHOS.read_text())[r["rascunho"]]
    assert codigo not in json.dumps(salvo) and salvo["chat"] == CHAT


def _preparar(base):
    enviados = []
    r = pg.draft("Família", "Chego às 13h", agora=5000.0, _urlopen=_fake_urlopen(enviados))
    return r["rascunho"], re.search(r"autorizo \w+ (\d{6})", enviados[0][1]["text"]).group(1)


def test_send_with_right_code_sends_exact_text_once(base):
    rid, codigo = _preparar(base)
    calls = []
    out = pg.send(rid, codigo, agora=5100.0, _runner=_runner(calls))
    assert out["enviado_para_grupo"] == "Família Ferreira"
    assert calls[0][0][-5:] == ["--to", f"whatsapp:{CHAT}", "--json", "--file", "-"] and calls[0][1] == "Chego às 13h"
    with pytest.raises(pg.GroupError, match="já usado"):
        pg.send(rid, codigo, agora=5200.0, _runner=_runner(calls))
    assert len(calls) == 1


def test_wrong_code_never_sends_and_locks_after_three(base):
    rid, codigo = _preparar(base)
    calls = []
    for _ in range(3):
        with pytest.raises(pg.GroupError, match="não confere"):
            pg.send(rid, "000000" if codigo != "000000" else "111111", agora=5100.0, _runner=_runner(calls))
    with pytest.raises(pg.GroupError, match="vezes demais"):
        pg.send(rid, codigo, agora=5100.0, _runner=_runner(calls))
    assert calls == []


def test_expired_authorization_is_refused(base):
    rid, codigo = _preparar(base)
    with pytest.raises(pg.GroupError, match="expirou"):
        pg.send(rid, codigo, agora=5000.0 + pg.VALIDADE_S + 1, _runner=_runner([]))


def test_tampered_text_is_refused(base):
    rid, codigo = _preparar(base)
    dados = json.loads(pg.RASCUNHOS.read_text())
    dados[rid]["texto"] = "outro texto"
    pg.RASCUNHOS.write_text(json.dumps(dados))
    calls = []
    with pytest.raises(pg.GroupError, match="alterado"):
        pg.send(rid, codigo, agora=5100.0, _runner=_runner(calls))
    assert calls == []


def test_draft_without_telegram_bot_is_not_created(base):
    (pg.PROFILE / ".env").write_text("")
    with pytest.raises(pg.GroupError, match="não configurado"):
        pg.draft("Família", "oi", agora=5000.0, _urlopen=_fake_urlopen([]))
    assert not pg.RASCUNHOS.exists()
