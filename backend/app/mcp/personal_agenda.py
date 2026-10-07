"""Agenda e tarefas pessoais do Marcelo, cuidadas pela Maia (2026-10-07).

Os dados ficam na base pessoal (``marcelo/pessoal/agenda.json``, com ``AGENDA.md`` legível gerado a
cada mudança). A Maia mexe pelas ferramentas do MCP ``pessoal`` (registradas por
``personal_contacts.register``); os lembretes e o resumo diário saem pelo cron da Maia, que importa
este módulo (``lembretes_devidos``, ``resumo_do_dia``). Só biblioteca padrão.

Item: ``{id, tipo: compromisso|tarefa, titulo, quando: "AAAA-MM-DDTHH:MM" ou "AAAA-MM-DD",
lembretes: [minutos antes], local, notas, recorrencia: ""|diaria|semanal|mensal|anual,
status: pendente|concluido|cancelado, avisados: [...]}``.
"""

from __future__ import annotations

import calendar
import fcntl
import json
import os
import secrets
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE = Path(os.environ.get("FORGEHUB_PERSONAL_CONTACTS_DIR", "/root/memory/knowledge_base/marcelo/pessoal"))
TZ = ZoneInfo("America/Sao_Paulo")
TIPOS = ("compromisso", "tarefa")
RECORRENCIAS = ("", "diaria", "semanal", "mensal", "anual")
STATUS = ("pendente", "concluido", "cancelado")
HORA_TAREFA_SEM_HORARIO = 8  # tarefa só com data: lembra às 8h do dia
LEMBRETE_PADRAO = {"compromisso": [60], "tarefa": [0]}
JANELA_ATRASO = timedelta(hours=6)  # lembrete perdido (servidor parado) ainda sai até 6 h depois
_DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


class AgendaError(Exception):
    """Erro seguro para o agente."""


def _arquivo() -> Path:
    return BASE / "agenda.json"


@contextmanager
def _travado():
    """Lê e grava a agenda com trava de arquivo (MCP e cron podem mexer ao mesmo tempo)."""
    BASE.mkdir(parents=True, exist_ok=True)
    trava = BASE / ".agenda.lock"
    with open(trava, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            itens = _ler()
            yield itens
            _gravar(itens)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _ler() -> list[dict[str, Any]]:
    try:
        return json.loads(_arquivo().read_text(encoding="utf-8")).get("itens", [])
    except (OSError, ValueError):
        return []


def _gravar(itens: list[dict[str, Any]]) -> None:
    tmp = _arquivo().with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"itens": itens}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_arquivo())
    (BASE / "AGENDA.md").write_text(_markdown(itens), encoding="utf-8")


def agora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def _parse_quando(valor: str) -> str:
    """Aceita "dd/mm/aaaa HH:MM", "dd/mm/aaaa", "aaaa-mm-dd[THH:MM]" e "dd/mm HH:MM" (ano corrente)."""
    v = str(valor or "").strip().replace("h", ":").replace("  ", " ")
    formatos = ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m %H:%M", "%d/%m")
    for fmt in formatos:
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            dt = dt.replace(year=agora().year)
        return dt.strftime("%Y-%m-%dT%H:%M") if "%H" in fmt else dt.strftime("%Y-%m-%d")
    raise AgendaError("Data inválida. Use dd/mm/aaaa HH:MM (ou só dd/mm/aaaa para tarefa sem horário).")


def _momento(item: dict[str, Any]) -> datetime:
    q = item["quando"]
    if "T" in q:
        return datetime.strptime(q, "%Y-%m-%dT%H:%M")
    return datetime.strptime(q, "%Y-%m-%d").replace(hour=HORA_TAREFA_SEM_HORARIO)


def _fmt(item: dict[str, Any]) -> str:
    m = _momento(item)
    dia = f"{_DIAS[m.weekday()]} {m:%d/%m}"
    hora = f" às {m:%H:%M}" if "T" in item["quando"] else ""
    extra = f" — {item['local']}" if item.get("local") else ""
    rec = f" (repete: {item['recorrencia']})" if item.get("recorrencia") else ""
    return f"{dia}{hora}: {item['titulo']}{extra}{rec}"


def _proxima(item: dict[str, Any]) -> str:
    m = _momento(item)
    r = item.get("recorrencia")
    if r == "diaria":
        n = m + timedelta(days=1)
    elif r == "semanal":
        n = m + timedelta(weeks=1)
    elif r == "mensal":
        ano, mes = (m.year + 1, 1) if m.month == 12 else (m.year, m.month + 1)
        n = m.replace(year=ano, month=mes, day=min(m.day, calendar.monthrange(ano, mes)[1]))
    elif r == "anual":
        n = m.replace(year=m.year + 1, day=min(m.day, calendar.monthrange(m.year + 1, m.month)[1]))
    else:
        return item["quando"]
    return n.strftime("%Y-%m-%dT%H:%M") if "T" in item["quando"] else n.strftime("%Y-%m-%d")


def adicionar(titulo: str, quando: str, tipo: str = "compromisso", lembretes: list[int] | None = None,
              local: str = "", notas: str = "", recorrencia: str = "") -> dict[str, Any]:
    titulo = str(titulo or "").strip()
    if not titulo:
        raise AgendaError("Informe o título.")
    if tipo not in TIPOS:
        raise AgendaError(f"Tipo inválido: use {', '.join(TIPOS)}.")
    if recorrencia not in RECORRENCIAS:
        raise AgendaError(f"Recorrência inválida: use {', '.join(r for r in RECORRENCIAS if r)} ou vazio.")
    lem = LEMBRETE_PADRAO[tipo] if lembretes is None else sorted({int(x) for x in lembretes if 0 <= int(x) <= 10080}, reverse=True)
    item = {"id": secrets.token_hex(3), "tipo": tipo, "titulo": titulo[:300], "quando": _parse_quando(quando),
            "lembretes": lem, "local": str(local or "")[:300], "notas": str(notas or "")[:1000],
            "recorrencia": recorrencia, "status": "pendente", "avisados": [],
            "criado": agora().strftime("%Y-%m-%dT%H:%M")}
    with _travado() as itens:
        itens.append(item)
    return {**item, "resumo": _fmt(item)}


def listar(dias: int = 7, incluir_atrasadas: bool = True, status: str = "pendente") -> list[dict[str, Any]]:
    limite = agora() + timedelta(days=max(0, min(dias, 366)))
    out = []
    for it in _ler():
        if status and it.get("status") != status:
            continue
        m = _momento(it)
        if m <= limite and (incluir_atrasadas or m >= agora() - timedelta(minutes=1)):
            out.append({**it, "resumo": _fmt(it), "atrasado": m < agora() and it["tipo"] == "tarefa"})
    return sorted(out, key=lambda i: _momento(i))


def atualizar(item_id: str, **mudancas: Any) -> dict[str, Any]:
    with _travado() as itens:
        it = next((i for i in itens if i["id"] == item_id), None)
        if it is None:
            raise AgendaError(f"Item {item_id} não encontrado.")
        for chave in ("titulo", "local", "notas"):
            if mudancas.get(chave) is not None:
                it[chave] = str(mudancas[chave])[:1000]
        if mudancas.get("quando"):
            it["quando"] = _parse_quando(mudancas["quando"])
            it["avisados"] = []
        if mudancas.get("lembretes") is not None:
            it["lembretes"] = sorted({int(x) for x in mudancas["lembretes"] if 0 <= int(x) <= 10080}, reverse=True)
            it["avisados"] = []
        if mudancas.get("recorrencia") is not None:
            if mudancas["recorrencia"] not in RECORRENCIAS:
                raise AgendaError("Recorrência inválida.")
            it["recorrencia"] = mudancas["recorrencia"]
        if mudancas.get("status") is not None:
            if mudancas["status"] not in STATUS:
                raise AgendaError(f"Status inválido: use {', '.join(STATUS)}.")
            if mudancas["status"] == "concluido" and it.get("recorrencia"):
                # recorrente: concluir esta vez agenda a próxima
                it["quando"], it["avisados"], it["status"] = _proxima(it), [], "pendente"
            else:
                it["status"] = mudancas["status"]
        return {**it, "resumo": _fmt(it)}


def lembretes_devidos(momento: datetime | None = None) -> list[str]:
    """Lembretes que venceram e ainda não foram enviados; marca-os como enviados.
    Também avança itens recorrentes que já passaram."""
    momento = momento or agora()
    saida = []
    with _travado() as itens:
        for it in itens:
            if it.get("status") != "pendente":
                continue
            m = _momento(it)
            for minutos in it.get("lembretes") or []:
                chave = f"{it['quando']}|{minutos}"
                vence = m - timedelta(minutes=minutos)
                if chave in it.get("avisados", []) or not (vence <= momento <= vence + JANELA_ATRASO):
                    continue
                it.setdefault("avisados", []).append(chave)
                if minutos == 0:
                    quando = "agora"
                elif minutos < 60:
                    quando = f"em {minutos} min"
                elif minutos % 1440 == 0:
                    quando = f"em {minutos // 1440} dia(s)"
                else:
                    quando = f"em {minutos // 60}h{minutos % 60:02d}" if minutos % 60 else f"em {minutos // 60}h"
                icone = "📅" if it["tipo"] == "compromisso" else "✅"
                linha = f"{icone} Lembrete ({quando}): {_fmt(it)}"
                if it.get("notas"):
                    linha += f"\n   {it['notas']}"
                saida.append(linha)
            if it.get("recorrencia") and m + timedelta(hours=1) < momento:
                it["quando"], it["avisados"] = _proxima(it), []
    return saida


def resumo_do_dia(dia: date | None = None) -> str:
    """Texto-base do resumo diário (o cron da Maia transforma em mensagem)."""
    dia = dia or agora().date()
    hoje, atrasadas, proximos = [], [], []
    for it in _ler():
        if it.get("status") != "pendente":
            continue
        m = _momento(it)
        if m.date() == dia:
            hoje.append(it)
        elif m.date() < dia and it["tipo"] == "tarefa":
            atrasadas.append(it)
        elif dia < m.date() <= dia + timedelta(days=3):
            proximos.append(it)
    linhas = [f"Agenda de {_DIAS[dia.weekday()]}, {dia:%d/%m/%Y}."]
    for titulo, grupo in (("Hoje", hoje), ("Tarefas atrasadas", atrasadas), ("Próximos 3 dias", proximos)):
        linhas.append(f"{titulo}:")
        linhas += [f"- {_fmt(i)}" for i in sorted(grupo, key=_momento)] or ["- nada"]
    return "\n".join(linhas)


def _markdown(itens: list[dict[str, Any]]) -> str:
    pend = sorted((i for i in itens if i.get("status") == "pendente"), key=_momento)
    feitos = [i for i in itens if i.get("status") != "pendente"][-30:]
    linhas = ["---", "title: Agenda e tarefas do Marcelo", "sensitivity: pessoal", "owner: marcelo",
              "maintained_by: maia", "---", "", "# Agenda e tarefas", "",
              "Gerado automaticamente a partir de `agenda.json` — peça mudanças à Maia pelo Telegram.", "",
              "## Pendentes", ""]
    linhas += [f"- [{i['tipo']}] {_fmt(i)} `({i['id']})`" for i in pend] or ["- nada"]
    linhas += ["", "## Concluídos e cancelados (recentes)", ""]
    linhas += [f"- ~~{_fmt(i)}~~ — {i['status']}" for i in feitos] or ["- nada"]
    return "\n".join(linhas) + "\n"


def register(mcp) -> None:
    """Ferramentas de agenda no MCP pessoal (chamado por personal_contacts.register)."""

    @mcp.tool()
    async def agenda_add(titulo: str, quando: str, tipo: str = "compromisso", lembretes_minutos: list[int] | None = None,
                         local: str = "", notas: str = "", recorrencia: str = "") -> dict[str, Any]:
        """Registra um compromisso ou tarefa do Marcelo. quando: "dd/mm/aaaa HH:MM" (ou "dd/mm/aaaa"
        para tarefa sem horário; lembra às 8h). lembretes_minutos: minutos antes (padrão: 60 para
        compromisso, na hora para tarefa; ex.: [1440, 60] = um dia antes e uma hora antes).
        recorrencia: "", "diaria", "semanal", "mensal" ou "anual". Só a pedido do Marcelo."""
        try:
            return {"success": True, "item": adicionar(titulo, quando, tipo, lembretes_minutos, local, notas, recorrencia)}
        except (AgendaError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def agenda_list(dias: int = 7, incluir_atrasadas: bool = True, status: str = "pendente") -> dict[str, Any]:
        """Compromissos e tarefas dos próximos `dias` (com tarefas atrasadas). status: pendente,
        concluido, cancelado ou "" para todos."""
        return {"itens": listar(dias, incluir_atrasadas, status), "agora": agora().strftime("%d/%m/%Y %H:%M")}

    @mcp.tool()
    async def agenda_update(item_id: str, titulo: str | None = None, quando: str | None = None,
                            lembretes_minutos: list[int] | None = None, local: str | None = None,
                            notas: str | None = None, recorrencia: str | None = None,
                            status: str | None = None) -> dict[str, Any]:
        """Altera um item (remarcar, mudar lembretes...). status: "concluido" (recorrente: agenda a
        próxima vez) ou "cancelado". Campos omitidos ficam como estão. Só a pedido do Marcelo."""
        try:
            return {"success": True, "item": atualizar(item_id, titulo=titulo, quando=quando, lembretes=lembretes_minutos,
                                                       local=local, notas=notas, recorrencia=recorrencia, status=status)}
        except (AgendaError, ValueError) as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def agenda_day_summary(data: str = "") -> dict[str, Any]:
        """Resumo de um dia (padrão: hoje): compromissos, tarefas atrasadas e próximos 3 dias.
        data: "dd/mm/aaaa"."""
        try:
            dia = datetime.strptime(_parse_quando(data), "%Y-%m-%d").date() if data else None
        except (AgendaError, ValueError) as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "resumo": resumo_do_dia(dia)}
