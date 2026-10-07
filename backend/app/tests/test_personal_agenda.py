"""Agenda da Maia: lembretes na hora certa, uma vez só, e recorrência."""

from datetime import date, datetime

import pytest

from app.mcp import personal_agenda as ag


@pytest.fixture()
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(ag, "BASE", tmp_path)
    monkeypatch.setattr(ag, "agora", lambda: datetime(2026, 10, 7, 9, 0))
    return tmp_path


def test_compromisso_lembra_uma_vez_no_horario(base):
    item = ag.adicionar("Dentista", "07/10/2026 15:00", lembretes=[60, 0], local="Centro")
    assert item["quando"] == "2026-10-07T15:00"
    assert ag.lembretes_devidos(datetime(2026, 10, 7, 13, 59)) == []
    primeiro = ag.lembretes_devidos(datetime(2026, 10, 7, 14, 0))
    assert len(primeiro) == 1 and "em 1h" in primeiro[0] and "Dentista — Centro" in primeiro[0]
    assert ag.lembretes_devidos(datetime(2026, 10, 7, 14, 1)) == []  # não repete
    assert "agora" in ag.lembretes_devidos(datetime(2026, 10, 7, 15, 0))[0]
    assert (base / "AGENDA.md").exists()


def test_tarefa_sem_horario_lembra_as_8h_e_aparece_atrasada(base):
    ag.adicionar("Pagar IPVA", "06/10/2026", tipo="tarefa")
    resumo = ag.resumo_do_dia(date(2026, 10, 7))
    assert "Tarefas atrasadas:\n- terça 06/10: Pagar IPVA" in resumo


def test_recorrente_concluida_vai_para_a_proxima(base):
    item = ag.adicionar("Condomínio", "10/10/2026", tipo="tarefa", recorrencia="mensal")
    novo = ag.atualizar(item["id"], status="concluido")
    assert novo["quando"] == "2026-11-10" and novo["status"] == "pendente"


def test_validacao(base):
    with pytest.raises(ag.AgendaError):
        ag.adicionar("", "07/10/2026")
    with pytest.raises(ag.AgendaError):
        ag.adicionar("x", "amanhã")
    with pytest.raises(ag.AgendaError):
        ag.adicionar("x", "07/10/2026", tipo="festa")
