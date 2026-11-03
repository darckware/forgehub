"""Ferramentas de contatos pessoais da Maia dentro do MCP ForgeHub.

Desde 14/10/2026 os contatos, o histórico de cada conversa (com o contexto de cada mensagem), as
sugestões de demanda/tarefa/anotação e as regras de atendimento moram no ForgeHub
(``/api/v1/personal``, tela "Pessoal" → Contatos e Maia). Antes ficavam em
``knowledge_base/marcelo/pessoal`` (``CONTATOS.md`` + ``contatos/<telefone>.md``) e em
``whatsapp/INSTRUCOES_PESSOAIS.md``; esses arquivos foram importados e não são mais escritos.

A Maia chega lá com a própria credencial ``agt_`` (``FORGEHUB_AGENT_TOKEN``), e as ferramentas só são
registradas para os agentes em ``FORGEHUB_PERSONAL_CONTACTS_AGENTS`` (padrão: ``maia``), conferido
pelo ``FORGEHUB_AGENT_SLUG`` do perfil que abriu o MCP. Nomes, parâmetros e campos de resposta são os
mesmos de antes; nenhuma ferramenta apaga contato nem histórico. O envio pelo WhatsApp e as tarefas de
conversa continuam no próprio perfil da Maia (``hermes -p maia send`` e ``whatsapp/tarefas.json``).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

API = os.environ.get("FORGEHUB_API_URL", "http://localhost:8000").rstrip("/") + "/api/v1/personal"
TAREFAS = Path(os.environ.get(
    "PERSONAL_WHATSAPP_TASKS", "/root/.hermes/profiles/maia/whatsapp/tarefas.json"))
ENVIOS_LOG = Path(os.environ.get(
    "PERSONAL_WHATSAPP_SENDS", "/root/.hermes/profiles/maia/whatsapp/envios.jsonl"))
HERMES_BIN = os.environ.get("HERMES_BIN", "/usr/local/bin/hermes")
ENVIOS_POR_HORA = 30
TAREFA_HORAS = 48
TZ = ZoneInfo("America/Sao_Paulo")
_TIPOS = {"demanda": "demand", "tarefa": "task", "anotacao": "note", "anotação": "note",
          "demand": "demand", "task": "task", "note": "note"}
_TIPOS_PT = {"demand": "demanda", "task": "tarefa", "note": "anotacao"}


class PersonalContactsError(Exception):
    """Erro seguro para o agente que chamou."""


def allowed_agent(slug: str | None = None) -> bool:
    slug = (slug if slug is not None else os.environ.get("FORGEHUB_AGENT_SLUG", "")).strip().lower()
    allowed = {
        s.strip().lower()
        for s in os.environ.get("FORGEHUB_PERSONAL_CONTACTS_AGENTS", "maia").split(",")
        if s.strip()
    }
    return bool(slug) and slug in allowed


def _token() -> str:
    token = os.environ.get("FORGEHUB_AGENT_TOKEN", "").strip()
    if not token:
        raise PersonalContactsError("FORGEHUB_AGENT_TOKEN ausente: a Maia precisa da credencial agt_ dela.")
    return token


def _call(method: str, path: str, body: dict | None = None, query: dict | None = None) -> Any:
    clean = {k: v for k, v in (query or {}).items() if v not in (None, "")}
    url = API + path + (f"?{urllib.parse.urlencode(clean)}" if clean else "")
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw).get("detail", raw)
        except ValueError:
            detail = raw
        if isinstance(detail, list):  # validação do FastAPI
            detail = "; ".join(str(d.get("msg", d)) for d in detail)
        raise PersonalContactsError(str(detail)[:300]) from None
    except urllib.error.URLError as exc:
        raise PersonalContactsError(f"ForgeHub indisponível: {exc.reason}") from None


def digitos(valor: str) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _tel_completo(telefone: str) -> str:
    t = digitos(telefone)
    if len(t) in (10, 11):  # DDD + número, sem o 55
        t = "55" + t
    if not (12 <= len(t) <= 15):
        raise PersonalContactsError("Telefone inválido: informe com DDD (ex.: +55 21 99999-9999).")
    return t


def formata_tel(tel: str) -> str:
    t = digitos(tel)
    if len(t) in (10, 11):
        t = "55" + t
    if len(t) == 13 and t.startswith("55"):
        return f"+55 {t[2:4]} {t[4:9]}-{t[9:]}"
    if len(t) == 12 and t.startswith("55"):
        return f"+55 {t[2:4]} {t[4:8]}-{t[8:]}"
    return f"+{t}" if t else ""


def _local(iso: str | None) -> str:
    if not iso:
        return ""
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d/%m/%Y %H:%M")


def _contato(c: dict[str, Any]) -> dict[str, Any]:
    """O formato que a Maia já conhece (o da antiga linha de CONTATOS.md + ficha)."""
    return {
        "nome": c["name"], "telefone": c["phone_display"] or formata_tel(c["phone"]), "categoria": c["category"],
        "relacao": c["relation"], "aniversario": c["birthday"], "observacoes": c["observations"],
        "ultimo_contato": _local(c.get("last_contact_at")), "bloqueado": c["blocked"],
        "sugestoes_pendentes": c.get("pending_suggestions", 0),
    }


def _linha_historico(m: dict[str, Any]) -> str:
    linha = f"- **{_local(m['at'])}** · {m['author'] or m['direction']}: {m['text']}"
    return linha + (f" [contexto: {m['context']}]" if m.get("context") else "")


def list_categories() -> list[str]:
    return _call("GET", "/contact-categories")


def create_category(nome: str) -> list[str]:
    return _call("POST", "/contact-categories", {"name": nome})


def list_contacts(categoria: str | None = None) -> list[dict[str, Any]]:
    return [_contato(c) for c in _call("GET", "/contacts", query={"category": categoria})]


def get_contact(telefone: str, ultimos: int = 20) -> dict[str, Any]:
    tel = _tel_completo(telefone)
    c = _call("GET", f"/contacts/{tel}")
    mensagens = _call("GET", f"/contacts/{tel}/messages", query={"limit": ultimos})
    return {
        **_contato(c),
        "quem_e": c["who_is"], "como_tratar": c["how_to_treat"], "outros_dados": c["other_data"],
        "historico_recente": [_linha_historico(m) for m in reversed(mensagens)],
        "mensagens": [{"id":m["id"],"quando":m["at"],"autor":m["author"],"texto":m["text"]} for m in reversed(mensagens)],
    }


def upsert_contact(
    telefone: str,
    nome: str | None = None,
    categoria: str | None = None,
    relacao: str | None = None,
    aniversario: str | None = None,
    observacoes: str | None = None,
    quem_e: str | None = None,
    como_tratar: str | None = None,
    outros_dados: dict[str, Any] | None = None,
    bloqueado: bool | None = None,
) -> dict[str, Any]:
    tel = _tel_completo(telefone)
    corpo = {"name": nome, "category": categoria, "relation": relacao, "birthday": aniversario,
             "observations": observacoes, "who_is": quem_e, "how_to_treat": como_tratar, "other_data": outros_dados,
             "blocked": bloqueado}
    _call("PUT", f"/contacts/{tel}", {k: v for k, v in corpo.items() if v is not None})
    return get_contact(tel, ultimos=5)


def append_observation(telefone: str, texto: str) -> dict[str, Any]:
    texto = str(texto or "").strip()
    if not texto:
        raise PersonalContactsError("Informe a observação a acrescentar.")
    tel = _tel_completo(telefone)
    _call("POST", f"/contacts/{tel}:append-observation", {"text": texto})
    return get_contact(tel, ultimos=5)


def change_phone(telefone_atual: str, telefone_novo: str) -> dict[str, Any]:
    novo = _tel_completo(telefone_novo)
    _call("POST", f"/contacts/{_tel_completo(telefone_atual)}:change-phone", {"phone": novo})
    return get_contact(novo)


_CAMPOS_UPSERT = {"nome": "name", "categoria": "category", "relacao": "relation", "aniversario": "birthday",
                  "observacoes": "observations", "quem_e": "who_is", "como_tratar": "how_to_treat",
                  "outros_dados": "other_data", "bloqueado": "blocked"}


def upsert_many(contatos: list[dict[str, Any]]) -> dict[str, Any]:
    if not contatos:
        raise PersonalContactsError("Informe ao menos um contato.")
    if len(contatos) > 100:
        raise PersonalContactsError("No máximo 100 contatos por vez.")
    itens = []
    for item in contatos:
        item = dict(item or {})
        corpo = {"phone": str(item.get("telefone", "") or "")}
        corpo.update({en: item[pt] for pt, en in _CAMPOS_UPSERT.items() if item.get(pt) is not None})
        itens.append(corpo)
    resultado = _call("POST", "/contacts:upsert-many", {"contacts": itens})
    return {
        "gravados": [{"telefone": formata_tel(s["phone"]), "nome": s["name"], "categoria": s["category"]}
                     for s in resultado["saved"]],
        "erros": [{"telefone": e["phone"], "erro": e["error"]} for e in resultado["errors"]],
    }


def add_history(telefone: str, texto: str, autor: str = "Marcelo") -> dict[str, Any]:
    if not str(texto or "").strip():
        raise PersonalContactsError("Informe o texto a registrar.")
    tel = _tel_completo(telefone)
    _call("POST", f"/contacts/{tel}/messages",
          {"text": texto.strip(), "direction": "note", "author": (autor or "Marcelo").strip(), "source": "telegram"})
    return get_contact(tel, ultimos=5)


def _envios_na_ultima_hora() -> int:
    import time

    try:
        linhas = ENVIOS_LOG.read_text(encoding="utf-8").splitlines()[-200:]
    except OSError:
        return 0
    limite = time.time() - 3600
    return sum(1 for l in linhas if l.strip() and json.loads(l).get("ts", 0) >= limite)


def whatsapp_send(telefone: str, texto: str, objetivo: str = "", _runner=None) -> dict[str, Any]:
    """Envia pelo WhatsApp pessoal do Marcelo (`hermes -p maia send`) e, com ``objetivo``, abre uma
    tarefa: as respostas daquela pessoa passam a ser tratadas dentro desse objetivo."""
    import subprocess
    import time

    texto = str(texto or "").strip()
    if not texto:
        raise PersonalContactsError("Informe o texto da mensagem.")
    if len(texto) > 4000:
        raise PersonalContactsError("Mensagem longa demais (máximo 4000 caracteres).")
    tel = _tel_completo(telefone)
    if _envios_na_ultima_hora() >= ENVIOS_POR_HORA:
        raise PersonalContactsError(f"Limite de {ENVIOS_POR_HORA} envios por hora atingido; tente mais tarde.")
    run = _runner or subprocess.run
    proc = run([HERMES_BIN, "-p", "maia", "send", "--to", f"whatsapp:{tel}", "--json", "--file", "-"],
               input=texto, capture_output=True, text=True, timeout=90)
    try:
        resultado = json.loads(proc.stdout or "{}")
    except ValueError:
        resultado = {}
    if proc.returncode != 0 or not resultado.get("success"):
        raise PersonalContactsError(f"O WhatsApp não aceitou o envio: {resultado.get('error') or proc.stderr[-300:] or 'erro'}")

    ENVIOS_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ENVIOS_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.time(), "telefone": tel, "objetivo": objetivo[:500]}, ensure_ascii=False) + "\n")
    if objetivo.strip():
        tarefas = get_tasks()
        tarefas[tel] = {"objetivo": objetivo.strip()[:1500], "criada": datetime.now(TZ).strftime("%d/%m/%Y %H:%M"),
                        "expira_ts": time.time() + TAREFA_HORAS * 3600}
        TAREFAS.write_text(json.dumps(tarefas, ensure_ascii=False, indent=1), encoding="utf-8")
    nota = f"[enviado pela Maia a pedido do Marcelo] {texto}" + (f" (objetivo: {objetivo.strip()})" if objetivo.strip() else "")
    contato = None
    try:  # o envio já aconteceu: registrar no histórico nunca o desfaz
        contato = _call("POST", "/whatsapp/messages", {"phone": tel, "text": nota, "direction": "out", "author": "Maia"})
        contato = _call("GET", f"/contacts/{tel}")
    except PersonalContactsError:
        pass
    return {"enviado_para": formata_tel(tel), "contato": (contato or {}).get("name") or None,
            "tarefa_aberta": bool(objetivo.strip()), "message_id": resultado.get("message_id")}


def get_tasks() -> dict[str, Any]:
    import time

    try:
        tarefas = json.loads(TAREFAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in tarefas.items() if v.get("expira_ts", 0) > time.time()}


def close_task(telefone: str) -> bool:
    tel = _tel_completo(telefone)
    tarefas = get_tasks()
    existia = tarefas.pop(tel, None) is not None
    TAREFAS.parent.mkdir(parents=True, exist_ok=True)
    TAREFAS.write_text(json.dumps(tarefas, ensure_ascii=False, indent=1), encoding="utf-8")
    return existia


def get_instructions() -> str:
    return _call("GET", "/assistant-settings")["instructions"]


def set_instructions(texto: str) -> str:
    """Substitui as regras de atendimento (lidas pelo plugin a cada mensagem)."""
    texto = str(texto or "").strip()
    if len(texto) > 6000:
        raise PersonalContactsError("Instruções longas demais (máximo 6000 caracteres).")
    return _call("PUT", "/assistant-settings", {"instructions": texto})["instructions"]


def upcoming_birthdays(dias: int = 30) -> list[dict[str, Any]]:
    return _call("GET", "/birthdays", query={"days": dias})


def list_suggestions(telefone: str = "") -> list[dict[str, Any]]:
    itens = _call("GET", "/suggestions", query={"status": "pending",
                                                  "contact_phone": _tel_completo(telefone) if telefone else None})
    return [{"id": s["id"], "tipo": _TIPOS_PT.get(s["kind"], s["kind"]), "titulo": s["title"], "detalhes": s["details"],
             "contato": s.get("contact_name") or (formata_tel(s["contact_phone"]) if s.get("contact_phone") else ''),
             "telefone": formata_tel(s["contact_phone"]) if s.get("contact_phone") else '',
             "origem": 'grupo' if s.get('source_kind') == 'group' else 'contato',
             "grupo": s.get('group_name') or '', "grupo_id": s.get('group_id'),
             "autor": s.get('source_author') or s.get('source_author_id') or s.get('contact_name') or '',
             "mensagem_ref": s.get('source_message_ref'), "mensagem_id": s.get('message_id')}
            for s in itens]


def accept_suggestion(sugestao_id: str, tipo: str = "", titulo: str = "", detalhes: str | None = None) -> dict[str, Any]:
    corpo: dict[str, Any] = {}
    if tipo:
        if tipo.strip().lower() not in _TIPOS:
            raise PersonalContactsError("tipo deve ser demanda, tarefa ou anotacao.")
        corpo["kind"] = _TIPOS[tipo.strip().lower()]
    if titulo.strip():
        corpo["title"] = titulo.strip()
    if detalhes is not None:
        corpo["details"] = detalhes
    s = _call("POST", f"/suggestions/{sugestao_id}:accept", corpo)
    return {"criado": _TIPOS_PT.get(s["kind"], s["kind"]), "titulo": s["title"], "item_id": s["created_item_id"]}


def dismiss_suggestion(sugestao_id: str) -> dict[str, Any]:
    _call("POST", f"/suggestions/{sugestao_id}:dismiss")
    return {"descartada": True}


def _register_sibling(mcp, nome: str) -> None:
    """Módulo irmão deste arquivo (personal_agenda.py, personal_groups.py): carregado pelo caminho para
    funcionar tanto como pacote (testes) quanto como script (`uv run`)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(nome, Path(__file__).with_name(f"{nome}.py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    if nome == 'personal_groups':
        def group_api(method, path, body=None):
            try:
                return _call(method, path, body)
            except PersonalContactsError as exc:
                raise modulo.GroupError(str(exc)) from exc
        modulo.register(mcp, api_call=group_api)
    else:
        modulo.register(mcp)


def _safe(fn, *args, chave: str | None = None, **kwargs) -> dict[str, Any]:
    try:
        resultado = fn(*args, **kwargs)
    except PersonalContactsError as exc:
        return {"success": False, "error": str(exc)}
    if chave is None:
        return {"success": True, **resultado}
    return {"success": True, chave: resultado}


def register(mcp) -> bool:
    """Registra as ferramentas só para os agentes autorizados (padrão: Maia)."""
    if not allowed_agent():
        return False

    @mcp.tool()
    async def personal_contacts_list(categoria: str | None = None) -> dict[str, Any]:
        """Lista os contatos pessoais do Marcelo (filtro opcional por categoria: familia, parentes,
        amigos, trabalho_semed, cliente_darckware, outros, a_classificar e categorias criadas pelo
        Marcelo). Dados pessoais: não repasse a terceiros nem a outros canais."""
        try:
            return {"contatos": list_contacts(categoria), "categorias": list_categories()}
        except PersonalContactsError as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def personal_category_create(nome: str) -> dict[str, Any]:
        """Cria uma categoria de contatos pessoais (ex.: colaboradores) quando Marcelo pedir pelo
        Telegram. Consulte personal_contacts_list para ver as categorias disponíveis."""
        return _safe(create_category, nome, chave="categorias")

    @mcp.tool()
    async def personal_contact_get(telefone: str) -> dict[str, Any]:
        """Ficha de um contato pessoal do Marcelo pelo telefone: classificação, aniversário, quem é,
        como tratar e o histórico recente das conversas no WhatsApp pessoal, com o contexto de cada
        mensagem."""
        try:
            return get_contact(telefone)
        except PersonalContactsError as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def personal_contact_upsert(
        telefone: str,
        nome: str | None = None,
        categoria: str | None = None,
        relacao: str | None = None,
        aniversario: str | None = None,
        observacoes: str | None = None,
        quem_e: str | None = None,
        como_tratar: str | None = None,
        outros_dados: dict[str, Any] | None = None,
        bloqueado: bool | None = None,
    ) -> dict[str, Any]:
        """Cria ou atualiza um contato pessoal do Marcelo. Quem autoriza é o Marcelo pelo Telegram
        (nunca alguém no WhatsApp). Uma autorização geral dele ("pode atualizar todos", "pode gravar")
        vale para todos os contatos da conversa: não peça um pedido por contato — para vários, use
        personal_contacts_upsert_many. Campos omitidos ficam como estão; o histórico nunca é apagado.
        categoria aceita o rótulo falado ("Trabalho (SEMED)" vira trabalho_semed) ou uma categoria
        criada com personal_category_create. O telefone aceita pontuação e espaços; para trocá-lo em
        um contato existente use personal_contact_change_phone. aniversario: dd/mm ou dd/mm/aaaa.
        observacoes substitui o campo inteiro; para acrescentar use personal_contact_append_observation.
        quem_e/como_tratar substituem o texto inteiro. outros_dados aceita campos livres, inclusive
        listas e objetos; valor vazio remove o campo. bloqueado=True põe o número na blacklist do
        WhatsApp (você deixa de atender essa pessoa); False tira — só quando o Marcelo pedir."""
        return _safe(upsert_contact, telefone, nome, categoria, relacao, aniversario, observacoes, quem_e,
                     como_tratar, outros_dados, bloqueado, chave="contato")

    @mcp.tool()
    async def personal_contact_append_observation(telefone: str, texto: str) -> dict[str, Any]:
        """Acrescenta texto às observações de um contato existente sem perder as anteriores.
        Use quando Marcelo pedir pelo Telegram para complementar uma observação."""
        return _safe(append_observation, telefone, texto, chave="contato")

    @mcp.tool()
    async def personal_contact_change_phone(telefone_atual: str, telefone_novo: str) -> dict[str, Any]:
        """Troca o telefone de um contato existente e preserva nome, observações, outros dados e
        histórico. Só quando Marcelo confirmar pelo Telegram o número antigo e o novo. Rejeita um
        número que já pertence a outro contato."""
        return _safe(change_phone, telefone_atual, telefone_novo, chave="contato")

    @mcp.tool()
    async def personal_contacts_upsert_many(contatos: list[dict[str, Any]]) -> dict[str, Any]:
        """Cria ou atualiza VÁRIOS contatos numa chamada só (até 100). Cada item: {"telefone": ...,
        e os mesmos campos de personal_contact_upsert: nome, categoria, relacao, aniversario,
        observacoes, quem_e, como_tratar, outros_dados}. Use quando o Marcelo pedir pelo Telegram para
        cadastrar/atualizar uma lista ou disser "pode atualizar todos" — uma autorização geral basta,
        não peça confirmação contato por contato. Depois diga o que gravou e o que deu erro."""
        return _safe(upsert_many, contatos)

    @mcp.tool()
    async def personal_contact_add_history(telefone: str, texto: str, autor: str = "Marcelo") -> dict[str, Any]:
        """Registra no histórico de um contato algo que o Marcelo contou sobre a pessoa ou sobre uma
        conversa (ex.: "combinamos almoço no sábado"), para não perder o contexto. Só a pedido do
        Marcelo pelo Telegram. Nunca reescreve registros anteriores."""
        return _safe(add_history, telefone, texto, autor, chave="contato")

    @mcp.tool()
    async def personal_instructions_get() -> dict[str, Any]:
        """Regras de atendimento do Marcelo para o WhatsApp pessoal (texto atual, também editável na
        tela Pessoal → Maia do ForgeHub)."""
        try:
            return {"instrucoes": get_instructions()}
        except PersonalContactsError as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def personal_instructions_update(texto: str) -> dict[str, Any]:
        """Substitui as regras de atendimento pelo texto completo informado — só quando o Marcelo pedir
        pelo Telegram. Leia antes com personal_instructions_get e mantenha o que ele não pediu para
        mudar. Vale a partir da próxima mensagem."""
        return _safe(set_instructions, texto, chave="instrucoes")

    @mcp.tool()
    async def personal_demands_list(status: str = 'aberta') -> dict[str, Any]:
        """Consulta Pessoal → Demandas, com origem contato/grupo, solicitante, status, datas, agente que cadastrou e agente que deu baixa. status: aberta ou concluida. Consulte antes de cadastrar para evitar duplicidades."""
        states = {'aberta': 'open', 'concluida': 'done', 'concluída': 'done', 'open': 'open', 'done': 'done'}
        if status not in states:
            return {'success': False, 'error': 'status deve ser aberta ou concluida'}
        try:
            return {'success': True, 'demandas': _call('GET', '/demands', query={'status': states[status]})}
        except PersonalContactsError as exc:
            return {'success': False, 'error': str(exc)}

    @mcp.tool()
    async def personal_demand_set_status(demanda_id: str, status: str) -> dict[str, Any]:
        """Dá baixa/conclui ou reabre demanda real de Pessoal → Demandas, SOMENTE a pedido de Marcelo pelo Telegram. status: concluida ou aberta. A API registra data e agente autenticado da baixa; não aceita agente inventado. Repetir o mesmo status preserva a data. Não significa baixar arquivo nem executar a demanda."""
        import uuid
        states = {'aberta': 'open', 'concluida': 'done', 'concluída': 'done', 'open': 'open', 'done': 'done'}
        try:
            demand_id = str(uuid.UUID(demanda_id))
        except ValueError:
            return {'success': False, 'error': 'Use o UUID real da demanda'}
        if status not in states:
            return {'success': False, 'error': 'status deve ser aberta ou concluida'}
        try:
            return {'success': True, 'demanda': _call('PATCH', f'/demands/{demand_id}', {'status': states[status]})}
        except PersonalContactsError as exc:
            return {'success': False, 'error': str(exc)}

    @mcp.tool()
    async def personal_demand_from_contact(telefone: str, titulo: str, detalhes: str = '', mensagem_id: str = '', item_key: str = 'principal') -> dict[str, Any]:
        """Cadastra DIRETAMENTE em Pessoal → Demandas um pedido de contato, a pedido de Marcelo pelo Telegram. Não cria sugestão. Salva origem=contato e nome/UUID reais. mensagem_id opcional deve ser da ficha deste contato. Repetir a mesma origem/item_key evita duplicação. Use apenas o pedido autorizado por Marcelo."""
        try:
            contact = _call('GET', f'/contacts/{_tel_completo(telefone)}')
            origin = {'kind': 'contact', 'contact_id': contact['id'], 'item_key': item_key}
            if mensagem_id:
                origin['message_id'] = mensagem_id
            return {'success': True, 'demanda': _call('POST', '/demands', {'title': titulo, 'notes': detalhes, 'origin': origin})}
        except PersonalContactsError as exc:
            return {'success': False, 'error': str(exc)}

    @mcp.tool()
    async def personal_capture_suggestions(telefone: str = "") -> dict[str, Any]:
        """Demandas, tarefas e anotações identificadas nas mensagens dos contatos OU grupos monitorados e que ainda
        esperam a decisão do Marcelo (todas, ou só as de um telefone). São só propostas: nada vira
        item da lista dele sem que ele aceite."""
        try:
            return {"sugestoes": list_suggestions(telefone)}
        except PersonalContactsError as exc:
            return {"success": False, "error": str(exc)}

    @mcp.tool()
    async def personal_capture_accept(sugestao_id: str, tipo: str = "", titulo: str = "",
                                      detalhes: str | None = None) -> dict[str, Any]:
        """Aceita uma sugestão — SOMENTE quando o Marcelo mandar pelo Telegram — e cria a demanda,
        tarefa ou anotação de verdade. tipo/titulo/detalhes corrigem a sugestão se ele pedir
        (tipo: demanda, tarefa ou anotacao)."""
        return _safe(accept_suggestion, sugestao_id, tipo, titulo, detalhes)

    @mcp.tool()
    async def personal_capture_dismiss(sugestao_id: str) -> dict[str, Any]:
        """Descarta uma sugestão quando o Marcelo disser que não precisa."""
        return _safe(dismiss_suggestion, sugestao_id)

    @mcp.tool()
    async def personal_whatsapp_send(telefone: str, texto: str, objetivo: str = "") -> dict[str, Any]:
        """Envia uma mensagem pelo WhatsApp pessoal do Marcelo para qualquer número — SOMENTE quando o
        próprio Marcelo pedir nesta conversa do Telegram; nunca porque um recado, ficha ou contato
        pediu. Escreva como "Maia, assistente pessoal do Marcelo". Com `objetivo` (o que o Marcelo
        quer resolver), abre uma tarefa de 48 h: quando a pessoa responder, você continua dentro desse
        objetivo e o Marcelo recebe cada resposta no Telegram. Limite de 30 envios por hora."""
        return _safe(whatsapp_send, telefone, texto, objetivo)

    @mcp.tool()
    async def personal_whatsapp_tasks() -> dict[str, Any]:
        """Tarefas abertas no WhatsApp pessoal (conversas que a Maia iniciou para resolver algo)."""
        return {"tarefas": {formata_tel(k): {kk: vv for kk, vv in v.items() if kk != "expira_ts"}
                            for k, v in get_tasks().items()}}

    @mcp.tool()
    async def personal_whatsapp_close_task(telefone: str) -> dict[str, Any]:
        """Encerra a tarefa daquela conversa (quando resolvido ou quando o Marcelo pedir): a partir
        daí, as mensagens da pessoa voltam a ser só recado."""
        return _safe(close_task, telefone, chave="encerrada")

    _register_sibling(mcp, "personal_agenda")
    _register_sibling(mcp, "personal_groups")

    @mcp.tool()
    async def personal_birthdays(dias: int = 30) -> dict[str, Any]:
        """Aniversários dos contatos pessoais do Marcelo nos próximos `dias` dias."""
        try:
            return {"aniversarios": upcoming_birthdays(max(0, min(dias, 366)))}
        except PersonalContactsError as exc:
            return {"success": False, "error": str(exc)}

    return True


if __name__ == "__main__":
    raise SystemExit("Use o MCP ForgeHub; o MCP Pessoal independente foi descontinuado.")
