"""Agenda, tarefas e anotações do Marcelo no MCP ``pessoal`` -- dados no ForgeHub (2026-10-08).

Até 07/10 a agenda ficava em ``marcelo/pessoal/agenda.json``; agora mora no módulo Pessoal do
ForgeHub (``/api/v1/personal``, tela "Pessoal"), que o Marcelo também vê e edita. A Maia chega lá
com a própria credencial ``agt_`` (``FORGEHUB_AGENT_TOKEN``); a API só aceita os agentes de
``PERSONAL_AGENT_SLUGS`` e nunca deixa agente apagar (ela cancela ou arquiva).

Os lembretes e o resumo da manhã saem dos crons da Maia, que chamam ``lembretes_devidos`` e
``resumo_do_dia`` deste módulo (``POST /reminders:due`` e ``GET /summary``). Só biblioteca padrão.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

API = os.environ.get("FORGEHUB_API_URL", "http://localhost:8000").rstrip("/") + "/api/v1/personal"
TZ = ZoneInfo("America/Sao_Paulo")
RECORRENCIAS = {"": "", "diaria": "daily", "semanal": "weekly", "mensal": "monthly", "anual": "yearly",
                "daily": "daily", "weekly": "weekly", "monthly": "monthly", "yearly": "yearly"}
STATUS_TAREFA = {"pendente": "pending", "concluido": "done", "cancelado": "cancelled"}


class AgendaError(Exception):
    """Erro seguro para o agente."""


def _token() -> str:
    token = os.environ.get("FORGEHUB_AGENT_TOKEN", "").strip()
    if not token:
        raise AgendaError("FORGEHUB_AGENT_TOKEN ausente: a Maia precisa da credencial agt_ dela.")
    return token


def _call(method: str, path: str, body: dict | None = None, query: dict | None = None) -> Any:
    url = API + path + (f"?{urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v not in (None, '')})}" if query else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise AgendaError(f"ForgeHub recusou ({exc.code}): {detail}") from None
    except urllib.error.URLError as exc:
        raise AgendaError(f"ForgeHub indisponível: {exc.reason}") from None


def agora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None, second=0, microsecond=0)


def _parse_quando(valor: str) -> tuple[str, bool]:
    """(ISO local "AAAA-MM-DDTHH:MM:00", tem_hora). Aceita "dd/mm/aaaa HH:MM", "dd/mm/aaaa",
    "aaaa-mm-dd[THH:MM]", "dd/mm HH:MM" e "dd/mm" (ano corrente)."""
    v = str(valor or "").strip().replace("h", ":").replace("  ", " ")
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m %H:%M", "%d/%m"):
        try:
            dt = datetime.strptime(v, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            dt = dt.replace(year=agora().year)
        return dt.strftime("%Y-%m-%dT%H:%M:00"), "%H" in fmt
    raise AgendaError("Data inválida. Use dd/mm/aaaa HH:MM (ou só dd/mm/aaaa para tarefa sem horário).")


def _recorrencia(valor: str | None) -> str | None:
    if valor is None:
        return None
    if valor not in RECORRENCIAS:
        raise AgendaError("Recorrência inválida: use diaria, semanal, mensal, anual ou vazio.")
    return RECORRENCIAS[valor]


def adicionar(titulo: str, quando: str = "", tipo: str = "compromisso", lembretes: list[int] | None = None,
              local: str = "", notas: str = "", recorrencia: str = "", lista: str = "") -> dict[str, Any]:
    if not str(titulo or "").strip():
        raise AgendaError("Informe o título.")
    if tipo == "compromisso":
        if not quando:
            raise AgendaError("Compromisso precisa de data e hora.")
        inicio, tem_hora = _parse_quando(quando)
        body = {"title": titulo.strip(), "starts_at": inicio, "all_day": not tem_hora, "location": local or None,
                "notes": notas or None, "recurrence": _recorrencia(recorrencia) or ""}
        if lembretes is not None:
            body["reminders"] = lembretes
        return {"tipo": "compromisso", **_call("POST", "/events", body)}
    if tipo == "tarefa":
        body = {"title": titulo.strip(), "notes": notas or None, "recurrence": _recorrencia(recorrencia) or ""}
        if lista:
            body["list_name"] = lista
        if quando:
            body["due_at"], body["due_has_time"] = _parse_quando(quando)
        if lembretes is not None:
            body["reminders"] = lembretes
        return {"tipo": "tarefa", **_call("POST", "/tasks", body)}
    raise AgendaError("Tipo inválido: use compromisso ou tarefa.")


def listar(dias: int = 7) -> list[dict[str, Any]]:
    inicio = agora().replace(hour=0, minute=0)
    fim = inicio + timedelta(days=max(1, min(dias, 366)))
    return _call("GET", "/agenda", query={"start": inicio.strftime("%Y-%m-%dT%H:%M:00"), "end": fim.strftime("%Y-%m-%dT%H:%M:00")})


def atualizar(item_id: str, tipo: str, **mudancas: Any) -> dict[str, Any]:
    status = mudancas.pop("status", None)
    if tipo == "tarefa":
        if status == "concluido":
            return _call("POST", f"/tasks/{item_id}:complete")
        body: dict[str, Any] = {}
        if status:
            if status not in STATUS_TAREFA:
                raise AgendaError("Status inválido: pendente, concluido ou cancelado.")
            body["status"] = STATUS_TAREFA[status]
        if mudancas.get("quando"):
            body["due_at"], body["due_has_time"] = _parse_quando(mudancas["quando"])
        path = f"/tasks/{item_id}"
    elif tipo == "compromisso":
        body = {}
        if status:
            if status not in ("cancelado", "agendado"):
                raise AgendaError("Status de compromisso: cancelado ou agendado.")
            body["status"] = "cancelled" if status == "cancelado" else "scheduled"
        if mudancas.get("quando"):
            body["starts_at"], tem_hora = _parse_quando(mudancas["quando"])
            body["all_day"] = not tem_hora
        if mudancas.get("local") is not None:
            body["location"] = mudancas["local"]
        path = f"/events/{item_id}"
    else:
        raise AgendaError("Tipo inválido: use compromisso ou tarefa.")
    for chave, campo in (("titulo", "title"), ("notas", "notes"), ("lembretes", "reminders")):
        if mudancas.get(chave) is not None:
            body[campo] = mudancas[chave]
    if mudancas.get("recorrencia") is not None:
        body["recurrence"] = _recorrencia(mudancas["recorrencia"])
    return _call("PATCH", path, body)


def lembretes_devidos() -> list[str]:
    return _call("POST", "/reminders:due")["lines"]


def resumo_do_dia(dia: str = "") -> str:
    return _call("GET", "/summary", query={"day": dia})["text"]


def register(mcp) -> None:
    """Ferramentas de agenda, tarefas e anotações (chamado por personal_contacts.register)."""

    def _safe(fn, *a, **k):
        try:
            return {"success": True, "resultado": fn(*a, **k)}
        except AgendaError as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def agenda_add(titulo: str, quando: str = "", tipo: str = "compromisso",
                         lembretes_minutos: list[int] | None = None, local: str = "", notas: str = "",
                         recorrencia: str = "", lista: str = "") -> dict[str, Any]:
        """Registra um compromisso ou tarefa do Marcelo no ForgeHub (tela Pessoal). quando:
        "dd/mm/aaaa HH:MM" (tarefa pode ser só "dd/mm/aaaa", lembra às 8h, ou vazio = sem data).
        lembretes_minutos: minutos antes (padrão: 60 para compromisso, na hora para tarefa).
        recorrencia: diaria, semanal, mensal, anual ou vazio. lista (tarefa): "Pessoal", "SEMED",
        "Darckware", "Casa"... Só a pedido do Marcelo."""
        return _safe(adicionar, titulo, quando, tipo, lembretes_minutos, local, notas, recorrencia, lista)

    @mcp.tool()
    async def agenda_list(dias: int = 7) -> dict[str, Any]:
        """Compromissos e tarefas com data dos próximos `dias`, mais as tarefas atrasadas."""
        return _safe(listar, dias)

    @mcp.tool()
    async def agenda_update(item_id: str, tipo: str, titulo: str | None = None, quando: str | None = None,
                            lembretes_minutos: list[int] | None = None, local: str | None = None,
                            notas: str | None = None, recorrencia: str | None = None,
                            status: str | None = None) -> dict[str, Any]:
        """Altera um compromisso ou tarefa (tipo: compromisso|tarefa). status da tarefa: concluido
        (recorrente agenda a próxima), cancelado ou pendente; do compromisso: cancelado. Nunca apaga."""
        return _safe(atualizar, item_id, tipo, titulo=titulo, quando=quando, lembretes=lembretes_minutos,
                     local=local, notas=notas, recorrencia=recorrencia, status=status)

    @mcp.tool()
    async def agenda_day_summary(data: str = "") -> dict[str, Any]:
        """Resumo de um dia (padrão: hoje): compromissos, tarefas atrasadas e próximos 3 dias.
        data: "dd/mm/aaaa"."""
        try:
            dia = _parse_quando(data)[0][:10] if data else ""
        except AgendaError as exc:
            return {"success": False, "error": str(exc)}
        return _safe(resumo_do_dia, dia)

    @mcp.tool()
    async def tasks_list(lista: str = "", status: str = "pendente", busca: str = "") -> dict[str, Any]:
        """Tarefas do Marcelo (com ou sem data), filtrando por lista, status (pendente, concluido,
        cancelado ou "" para todas) e texto."""
        return _safe(_call, "GET", "/tasks", None,
                     {"list_name": lista, "status": STATUS_TAREFA.get(status, status), "q": busca})

    @mcp.tool()
    async def notes_add(titulo: str, conteudo: str = "", etiquetas: list[str] | None = None,
                        fixar: bool = False) -> dict[str, Any]:
        """Cria uma anotação do Marcelo (aparece na tela Pessoal → Anotações). Só a pedido dele."""
        return _safe(_call, "POST", "/notes", {"title": titulo, "content": conteudo,
                                               "tags": etiquetas or [], "pinned": fixar})

    @mcp.tool()
    async def notes_search(busca: str = "", etiqueta: str = "", arquivadas: bool = False) -> dict[str, Any]:
        """Busca anotações do Marcelo por texto ou etiqueta."""
        return _safe(_call, "GET", "/notes", None,
                     {"q": busca, "tag": etiqueta, "archived": "true" if arquivadas else "false"})

    @mcp.tool()
    async def notes_update(nota_id: str, titulo: str | None = None, conteudo: str | None = None,
                           etiquetas: list[str] | None = None, fixar: bool | None = None,
                           arquivar: bool | None = None) -> dict[str, Any]:
        """Altera uma anotação (texto, etiquetas, fixar, arquivar). Nunca apaga. Só a pedido do Marcelo."""
        body = {k: v for k, v in (("title", titulo), ("content", conteudo), ("tags", etiquetas),
                                  ("pinned", fixar), ("archived", arquivar)) if v is not None}
        return _safe(_call, "PATCH", f"/notes/{nota_id}", body)
