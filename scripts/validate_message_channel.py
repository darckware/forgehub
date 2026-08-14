#!/usr/bin/env python3
"""Validação ponta a ponta do canal de mensagens do ForgeHub (Inbox/Messages).

Roda contra um ForgeHub de verdade -- por padrão o deploy (:8000), que é a
porta que `send_agent_message.sh` usa e portanto a que precisa estar
correta para o ecossistema. Não substitui `pytest` (que cobre as regras
isoladamente, sem CLI de agente): este script exercita o canal *inteiro*,
incluindo o script compartilhado, os loops de background e execuções reais
de agente em cada runtime.

    python scripts/validate_message_channel.py                 # deploy :8000
    python scripts/validate_message_channel.py --base http://localhost:8001
    python scripts/validate_message_channel.py --skip-live     # sem despachar agentes

As mensagens sintéticas das fases de contrato são apagadas no fim; a thread
de dispatch ao vivo é mantida de propósito, para inspeção na UI.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO, ".env")
SEND_SCRIPT = "/root/.hermes/profiles/athos/scripts/send_agent_message.sh"
INBOX_SCRIPT = "/root/.hermes/profiles/athos/scripts/check_agent_inbox.sh"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def env(key: str) -> str:
    for line in open(ENV_PATH, encoding="utf-8"):
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"{key} ausente em {ENV_PATH}")


class Runner:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.token = env("CHAT_BRIDGE_TOKEN")
        self.jwt = self._login()
        self.results: list[tuple[str, str, bool, str]] = []
        self.created: list[str] = []
        self.phase = ""

    # ---------------------------------------------------------------- infra
    def _login(self) -> str:
        data = f"username={env('DEV_USER_USERNAME')}&password={env('DEV_USER_PASSWORD')}".encode()
        req = urllib.request.Request(
            f"{self.base}/api/v1/auth/token", data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())["access_token"]

    def call(self, method, path, payload=None, *, bridge=False, jwt=True, headers=None, raw=None):
        h = dict(headers or {})
        if bridge:
            h.setdefault("X-Bridge-Token", self.token)
        if jwt and not bridge:
            h.setdefault("Authorization", f"Bearer {self.jwt}")
        body = raw
        if payload is not None:
            h.setdefault("Content-Type", "application/json")
            body = json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode()
                try:
                    return r.status, json.loads(text) if text else None
                except ValueError:
                    return r.status, text
        except urllib.error.HTTPError as e:
            text = e.read().decode()
            try:
                return e.code, json.loads(text)
            except ValueError:
                return e.code, text
        except Exception as exc:  # noqa: BLE001 - rede/timeout viram falha do caso
            return 0, str(exc)

    def check(self, case, expected, got, detail=""):
        ok = got == expected
        self.results.append((self.phase, case, ok, detail))
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FALHA{RESET}"
        extra = f" {DIM}{detail}{RESET}" if detail else ""
        print(f"  {mark} {case} {DIM}(esperado {expected}, obtido {got}){RESET}{extra}")
        return ok

    def check_true(self, case, ok, detail=""):
        self.results.append((self.phase, case, bool(ok), detail))
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FALHA{RESET}"
        extra = f" {DIM}{detail}{RESET}" if detail else ""
        print(f"  {mark} {case}{extra}")
        return bool(ok)

    def banner(self, name):
        self.phase = name
        print(f"\n{YELLOW}=== {name} ==={RESET}")

    def submit(self, track=True, **kw):
        payload = {"from_agent": "validador", "subject": f"[val] {uuid.uuid4().hex[:8]}", "body": "corpo"}
        payload.update(kw)
        status, body = self.call("POST", "/api/v1/demands/submit", payload, bridge=True)
        if track and status == 201 and isinstance(body, dict):
            self.created.append(body["id"])
        return status, body

    def sql(self, query: str) -> str:
        out = subprocess.run(
            ["psql", "-h", env("POSTGRES_HOST"), "-p", env("POSTGRES_PORT"), "-U", env("POSTGRES_USER"),
             "-d", env("POSTGRES_DB"), "-tAc", query],
            capture_output=True, text=True, env={**os.environ, "PGPASSWORD": env("POSTGRES_PASSWORD")},
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip())
        # `psql -tAc` ainda imprime a tag do comando ("INSERT 0 1") depois do
        # RETURNING -- só a primeira linha interessa.
        linhas = [l for l in out.stdout.splitlines() if l.strip()]
        return linhas[0].strip() if linhas else ""

    def agents(self) -> list[dict]:
        _, body = self.call("GET", "/api/v1/agents")
        return body if isinstance(body, list) else []

    def demand(self, demand_id: str) -> dict | None:
        """Uma mensagem específica. Passa pela lista inteira porque não
        existe GET /demands/{id} -- ver o caso E2. Se essa rota for
        adicionada, trocar por uma chamada direta."""
        _, todas = self.call("GET", "/api/v1/demands")
        if not isinstance(todas, list):
            return None
        return next((d for d in todas if d["id"] == demand_id), None)


# ==========================================================================
# Fases
# ==========================================================================


def phase_auth(r: Runner):
    r.banner("A. Autenticação e fronteira de confiança")
    s, _ = r.call("POST", "/api/v1/demands/submit", {"from_agent": "x", "subject": "x", "body": "x"}, jwt=False)
    r.check("A1 submit sem token", 401, s)
    s, _ = r.call("POST", "/api/v1/demands/submit", {"from_agent": "x", "subject": "x", "body": "x"},
                  headers={"X-Bridge-Token": "token-errado"}, jwt=False)
    r.check("A2 submit com bridge token inválido", 401, s)
    s, b = r.submit(subject="[val] A3 token válido")
    r.check("A3 submit com bridge token válido", 201, s)
    s, _ = r.call("GET", "/api/v1/demands", jwt=False)
    r.check("A4 listar sem JWT", 401, s)
    s, _ = r.call("GET", "/api/v1/demands/pending?agent=atlas", headers={"X-Bridge-Token": "errado"}, jwt=False)
    r.check("A5 pending com bridge token inválido", 401, s)
    s, _ = r.call("GET", "/api/v1/demands")
    r.check("A6 listar com JWT", 200, s)


def phase_payload(r: Runner):
    r.banner("B. Validação de payload")
    r.check("B1 subject vazio", 422, r.submit(subject="")[0])
    s, _ = r.call("POST", "/api/v1/demands/submit", {"from_agent": "x", "subject": "y"}, bridge=True)
    r.check("B2 body ausente", 422, s)
    r.check("B3 from_agent vazio", 422, r.submit(from_agent="")[0])
    r.check("B4 subject acima de 255 caracteres", 422, r.submit(subject="x" * 256)[0])
    r.check("B5 from_agent acima de 50 caracteres", 422, r.submit(from_agent="x" * 51)[0])
    r.check("B6 status fora do enum", 422, r.submit(status="inexistente")[0])
    r.check("B7 origin_type fora do enum", 422, r.submit(origin_type="lixo", origin_number=1)[0])
    # "demand" foi aposentado como Tipo (2026-07-28) -- só existe numa
    # mensagem de retorno gerada pelo backend, nunca submetido diretamente.
    r.check("B8 origin_type=demand é rejeitado (aposentado)", 422,
            r.submit(origin_type="demand")[0])
    s, b = r.submit(subject="[val] B9 sem tipo")
    if r.check("B9 origin_type omitido", 201, s):
        r.check_true("B9b default é incubation (campo obrigatório)", b.get("origin_type") == "incubation")


def phase_refs(r: Runner, agents: dict[str, dict]):
    r.banner("C. Resolução de referências")
    s, b = r.submit(subject="[val] C1 slug válido", target_agent_slug="atlas")
    ok = r.check("C1 target_agent_slug de agente registrado", 201, s)
    if ok:
        r.check_true("C1b target_agent_id resolvido", b.get("target_agent_id") == agents["Atlas"]["id"])
    r.check("C2 target_agent_slug inexistente", 404, r.submit(target_agent_slug="nao-existe")[0])
    r.check("C3 target_agent_id inexistente", 404, r.submit(target_agent_id=str(uuid.uuid4()))[0])
    r.check("C4 project_id inexistente", 404, r.submit(project_id=str(uuid.uuid4()))[0])

    r.check("C7 origin_type=task com número inexistente", 404,
            r.submit(origin_type="task", origin_number=99999999)[0])
    # Task sempre precisa de agente (2026-07-27) -- sem um, é rebaixada a
    # Backlog em vez de rejeitada (não perde o item, garante que não roda).
    s, b = r.submit(subject="[val] C8 task sem agente vira incubation", origin_type="task")
    if r.check("C8 origin_type=task sem agente", 201, s):
        r.check_true("C8b rebaixa para incubation", b.get("origin_type") == "incubation")
        r.check_true("C8c origin_id fica nulo", b.get("origin_id") is None)
    s, b = r.submit(subject="[val] C8d categoria sem vínculo, com agente",
                     origin_type="task", target_agent_slug="atlas",
                     from_agent_id=agents["Athos"]["id"])
    if r.check("C8d origin_type=task sem número, com To e From", 201, s):
        r.check_true("C8e continua task", b.get("origin_type") == "task")
        r.check_true("C8f origin_id fica nulo mesmo assim", b.get("origin_id") is None)
    # Regra 2026-07-28 (Marcelo: "se o agente não tem (to), não tem
    # retorno. Preciso ter agente (from) no tipo task. Isso é regra") --
    # To sem From registrado rebaixa igual a To ausente (C8).
    s, b = r.submit(subject="[val] C8g task com To mas sem From registrado",
                     origin_type="task", target_agent_slug="atlas")
    if r.check("C8g origin_type=task com To, sem From registrado", 201, s):
        r.check_true("C8h rebaixa para incubation", b.get("origin_type") == "incubation")
        r.check_true("C8i mantém o target_agent_id", b.get("target_agent_id") == agents["Atlas"]["id"])

    s, b = r.submit(subject="[val] C9 remetente por slug", from_agent="atlas")
    if r.check("C9 from_agent com slug registrado", 201, s):
        r.check_true("C9b from_agent_id auto-resolvido", b.get("from_agent_id") == agents["Atlas"]["id"],
                     "" if b.get("from_agent_id") else "não resolveu")
    s, b = r.submit(subject="[val] C10 remetente humano", from_agent="marcelo")
    if r.check("C10 from_agent não registrado (humano)", 201, s):
        r.check_true("C10b from_agent_id fica nulo, sem erro", b.get("from_agent_id") is None)

    # Cobertura do buraco conhecido: agentes sem profile_slug no banco.
    sem_slug = [a["name"] for a in agents.values() if not a.get("profile_slug")]
    if sem_slug:
        alvo = sem_slug[0].lower()
        s, _ = r.submit(target_agent_slug=alvo)
        r.check(f"C11 target_agent_slug de agente sem profile_slug ({alvo})", 201, s,
                f"sem profile_slug no banco: {', '.join(sem_slug)}")
    else:
        r.check_true("C11 todo agente registrado tem profile_slug", True)


def phase_rules(r: Runner, agents: dict[str, dict]):
    r.banner("D. Regras de negócio")
    r.check("D1 scheduled_at sem destinatário", 400,
            r.submit(scheduled_at="2030-01-01T00:00:00Z")[0])
    futuro = (datetime.now(timezone.utc) + timedelta(days=3650)).strftime("%Y-%m-%dT%H:%M:%SZ")
    s, b = r.submit(subject="[val] D2 agendada", target_agent_slug="atlas", scheduled_at=futuro)
    if r.check("D2 scheduled_at com destinatário", 201, s):
        r.check_true("D2b fica sem despachar até a hora marcada", b.get("dispatch_status") is None)
    s, b = r.submit(subject="[val] D3 arquivada na criação", status="archived")
    if r.check("D3 status=archived na criação", 201, s):
        r.check_true("D3b nasce arquivada", b.get("status") == "archived", str(b.get("status")))
    s, b = r.submit(subject="[val] D4 retorno sem remetente", from_agent="marcelo", requires_response=True)
    if r.check("D4 requires_response sem agente remetente", 201, s):
        r.check_true("D4b marcada, mas sem ninguém para relay",
                     b.get("requires_response") is True and b.get("from_agent_id") is None)


def phase_crud(r: Runner, agents: dict[str, dict]):
    r.banner("E. CRUD e edição")
    s, b = r.submit(subject="[val] E antes", body="corpo antes")
    if not r.check("E1 criar", 201, s):
        return
    did = b["id"]
    # Lacuna conhecida: o recurso só expõe GET na coleção. Quem quer o
    # estado de UMA mensagem (um agente conferindo o próprio dispatch, por
    # exemplo) precisa baixar a lista inteira.
    r.check("E2 ler uma mensagem por id (GET /demands/{id})", 200,
            r.call("GET", f"/api/v1/demands/{did}")[0], "rota não existe: só PATCH e DELETE")
    r.check_true("E2b contorno pela coleção funciona", r.demand(did) is not None)
    s, upd = r.call("PATCH", f"/api/v1/demands/{did}", {"subject": "[val] E depois", "body": "corpo depois"})
    if r.check("E3 editar assunto e corpo", 200, s):
        r.check_true("E3b alterações persistiram",
                     upd.get("subject") == "[val] E depois" and upd.get("body") == "corpo depois")
    s, upd = r.call("PATCH", f"/api/v1/demands/{did}", {"status": "read"})
    r.check("E4 mudar status", 200, s)
    s, _ = r.call("PATCH", f"/api/v1/demands/{did}", {"target_agent_id": str(uuid.uuid4())})
    r.check("E5 apontar para agente inexistente", 404, s)
    s, upd = r.call("PATCH", f"/api/v1/demands/{did}", {"target_agent_id": agents["Atlas"]["id"]})
    r.check("E6 atribuir destinatário sem despachar", 200, s,
            f"dispatch_status={upd.get('dispatch_status') if isinstance(upd, dict) else '?'}")
    r.check("E7 apagar", 204, r.call("DELETE", f"/api/v1/demands/{did}")[0])
    r.check_true("E8 some da coleção depois de apagar", r.demand(did) is None)
    if did in r.created:
        r.created.remove(did)


def phase_attachments(r: Runner):
    r.banner("F. Anexos")
    s, b = r.submit(subject="[val] F anexos")
    if not r.check("F1 criar mensagem para anexar", 201, s):
        return
    did = b["id"]
    boundary = "----validacao" + uuid.uuid4().hex
    conteudo = b"linha de teste do validador\n"
    corpo = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"validacao.txt\"\r\n"
        f"Content-Type: text/plain\r\n\r\n".encode() + conteudo + f"\r\n--{boundary}--\r\n".encode()
    )
    s, att = r.call("POST", f"/api/v1/demands/{did}/attachments", raw=corpo,
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    if not r.check("F2 enviar anexo", 201, s, str(att)[:120] if s != 201 else ""):
        return
    aid = att["id"]
    s, _ = r.call("GET", f"/api/v1/demands/{did}")
    s2, down = r.call("GET", f"/api/v1/demands/{did}/attachments/{aid}/download")
    r.check("F3 baixar anexo", 200, s2)
    r.check_true("F3b conteúdo íntegro", isinstance(down, str) and "linha de teste" in down)
    r.check("F4 remover anexo", 204, r.call("DELETE", f"/api/v1/demands/{did}/attachments/{aid}")[0])


def phase_groups(r: Runner):
    r.banner("G. Pastas de arquivamento")
    nome = f"val-{uuid.uuid4().hex[:6]}"
    s, g = r.call("POST", "/api/v1/demands/groups", {"name": nome})
    if not r.check("G1 criar pasta", 201, s, str(g)[:120] if s != 201 else ""):
        return
    gid = g["id"]
    s, b = r.submit(subject="[val] G mover para pasta")
    if s == 201:
        s2, moved = r.call("PATCH", f"/api/v1/demands/{b['id']}", {"group_id": gid})
        if r.check("G2 mover mensagem para a pasta", 200, s2):
            r.check_true("G2b arquiva ao mover", moved.get("status") == "archived",
                         f"status={moved.get('status')}")
    r.check("G3 apagar pasta", 204, r.call("DELETE", f"/api/v1/demands/groups/{gid}")[0])


def phase_pull(r: Runner):
    r.banner("H. Fila de leitura do próprio agente (pull = ack)")
    s, b = r.submit(subject="[val] H fila do agente", target_agent_slug="scriba")
    if not r.check("H1 endereçar mensagem ao agente", 201, s):
        return
    s, pend = r.call("GET", "/api/v1/demands/pending?agent=scriba", bridge=True, jwt=False)
    if r.check("H2 agente puxa a própria caixa", 200, s):
        r.check_true("H2b a mensagem endereçada veio na fila",
                     any(d["id"] == b["id"] for d in pend), f"{len(pend)} na fila")
    s, pend2 = r.call("GET", "/api/v1/demands/pending?agent=scriba", bridge=True, jwt=False)
    if r.check("H3 segunda leitura", 200, s):
        r.check_true("H3b puxar é o ack: não volta duas vezes",
                     not any(d["id"] == b["id"] for d in pend2), f"{len(pend2)} na fila")
    s, _ = r.call("GET", "/api/v1/demands/pending?agent=nao-existe", bridge=True, jwt=False)
    r.check("H4 fila de agente inexistente", 404, s)

    out = subprocess.run(["bash", INBOX_SCRIPT, "scriba", "--json"], capture_output=True, text=True, timeout=60)
    r.check_true("H5 check_agent_inbox.sh executa", out.returncode == 0, out.stderr.strip()[:120])


def phase_for_agent(r: Runner):
    r.banner("L. Listagem por status sem consumir (/for-agent)")
    s, msg = r.submit(subject="[val] L listagem por status", target_agent_slug="scriba")
    if not r.check("L1 mensagem endereçada criada", 201, s):
        return
    base = "/api/v1/demands/for-agent?agent=scriba"

    s, todas = r.call("GET", base, bridge=True, jwt=False)
    if r.check("L2 lista as próprias mensagens", 200, s):
        r.check_true("L2b a mensagem nova aparece",
                     any(d["id"] == msg["id"] for d in todas), f"{len(todas)} listadas")

    # A garantia que separa isto de /pending: listar não faz o ack.
    s, pend = r.call("GET", "/api/v1/demands/pending?agent=scriba", bridge=True, jwt=False)
    if r.check("L3 fila ainda entrega a mensagem", 200, s):
        r.check_true("L3b listar não consumiu a fila",
                     any(d["id"] == msg["id"] for d in pend), f"{len(pend)} na fila")

    s, nunca = r.call("GET", f"{base}&dispatch_status=none", bridge=True, jwt=False)
    if r.check("L4 filtro dispatch_status=none", 200, s):
        r.check_true("L4b só traz não despachadas",
                     all(d["dispatch_status"] is None for d in nunca), f"{len(nunca)} itens")

    s, entrada = r.call("GET", f"{base}&direction=incoming", bridge=True, jwt=False)
    if r.check("L5 filtro direction=incoming", 200, s):
        r.check_true("L5b todas endereçadas ao agente",
                     all(d["target_agent_id"] for d in entrada), f"{len(entrada)} itens")

    s, um = r.call("GET", f"{base}&number={msg['number']}", bridge=True, jwt=False)
    if r.check("L6 busca por número", 200, s):
        r.check_true("L6b traz exatamente a mensagem pedida",
                     len(um) == 1 and um[0]["id"] == msg["id"], f"{len(um)} itens")

    s, _ = r.call("GET", f"{base}&status_filter=inexistente", bridge=True, jwt=False)
    r.check("L7 status inválido rejeitado", 400, s)
    s, _ = r.call("GET", f"{base}&dispatch_status=inexistente", bridge=True, jwt=False)
    r.check("L8 dispatch_status inválido rejeitado", 400, s)
    s, _ = r.call("GET", f"{base}&direction=lateral", bridge=True, jwt=False)
    r.check("L9 direction inválida rejeitada", 400, s)
    s, _ = r.call("GET", "/api/v1/demands/for-agent?agent=nao-existe", bridge=True, jwt=False)
    r.check("L10 agente inexistente", 404, s)
    s, _ = r.call("GET", base, bridge=False, jwt=False)
    r.check("L11 exige bridge token", 401, s)


def phase_script(r: Runner, agents: dict[str, dict]):
    r.banner("I. Script compartilhado send_agent_message.sh")
    corpo = f"/tmp/val-corpo-{uuid.uuid4().hex[:6]}.md"
    with open(corpo, "w", encoding="utf-8") as f:
        f.write("Corpo de validação do canal. Nenhuma ação necessária.\n")

    def run(*args, expect_ok=True):
        out = subprocess.run(["bash", SEND_SCRIPT, *args], capture_output=True, text=True, timeout=120)
        payload = None
        if out.returncode == 0:
            try:
                payload = json.loads(out.stdout)
                r.created.append(payload["id"])
            except (ValueError, KeyError):
                payload = None
        return out, payload

    out, b = run("validador", "[val] I1 nota simples", corpo)
    if r.check_true("I1 nota simples", out.returncode == 0 and b is not None, out.stderr.strip()[:140]):
        r.check_true("I1b nasce sem destinatário e sem retorno",
                     b.get("target_agent_id") is None and b.get("requires_response") is False)

    # "athos" (não "validador") -- Tipo=task exige um remetente registrado
    # desde 2026-07-28 (Marcelo: "Preciso ter agente (from) no tipo task.
    # Isso é regra"); "validador" nunca resolve a um Agent de verdade.
    out, b = run("athos", "[val] I2 endereçada com retorno", corpo, "--to", "atlas", "--requires-response")
    if r.check_true("I2 --to + --requires-response", out.returncode == 0 and b is not None,
                    out.stderr.strip()[:140]):
        r.check_true("I2b destinatário resolvido", b.get("target_agent_id") == agents["Atlas"]["id"])
        r.check_true("I2c retorno marcado", b.get("requires_response") is True)
        r.check_true("I2d agenda para agora (dispatch automático)", b.get("scheduled_at") is not None)
        r.check_true("I2e Tipo=task por padrão", b.get("origin_type") == "task")

    futuro = (datetime.now(timezone.utc) + timedelta(days=3650)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out, b3 = run("validador", "[val] I4 agendada", corpo, "--to", "atlas", "--scheduled-at", futuro)
    if r.check_true("I4 --scheduled-at adia o disparo", out.returncode == 0 and b3 is not None,
                    out.stderr.strip()[:140]):
        r.check_true("I4b não despacha agora", b3.get("dispatch_status") is None)

    out, _ = run("validador", "[val] I5", corpo, "--origin-task", "99999999")
    r.check_true("I5 --origin-task com número inexistente falha", out.returncode != 0,
                 out.stdout.strip()[:100] or out.stderr.strip()[:100])
    out, _ = run("validador", "[val] I6", corpo, "--opcao-inventada")
    r.check_true("I6 opção desconhecida falha", out.returncode != 0)
    out = subprocess.run(["bash", SEND_SCRIPT, "validador"], capture_output=True, text=True, timeout=60)
    r.check_true("I7 argumentos insuficientes falham com uso", out.returncode != 0 and "uso:" in out.stderr)

    sem_slug = [a["name"].lower() for a in agents.values() if not a.get("profile_slug")]
    if sem_slug:
        out, _ = run("validador", "[val] I8", corpo, "--to", sem_slug[0])
        r.check_true(f"I8 --to {sem_slug[0]} (agente sem profile_slug)", out.returncode == 0,
                     f"sem profile_slug: {', '.join(sem_slug)}")
    os.unlink(corpo)


def phase_dispatch_failure(r: Runner, agents: dict[str, dict]):
    r.banner("K. Falha de dispatch fica visível")
    # Backlog sem remetente registrado nem chega a ser tentado pelo loop
    # (_assert_dispatchable / run_scheduled_dispatch_pass's query) -- estes
    # dois casos precisam de Tipo=task com um remetente real para de fato
    # alcançar o caminho de falha "agente sem runtime_type" que testam,
    # em vez de serem descartados antes por outra regra (2026-07-28, mesma
    # causa corrigida em test_demand_dispatch.py).
    remetente = agents["Athos"]
    nome = f"Validador Sem Runtime {uuid.uuid4().hex[:6]}"
    aid = r.sql(
        "insert into company.agents "
        "(id, name, agent_type, status, is_active, telegram_required, has_profile, created_at, updated_at) "
        f"values (gen_random_uuid(), '{nome}', 'executor', 'active', true, false, false, now(), now()) "
        "returning id"
    )
    try:
        s, b = r.submit(subject="[val] K dispatch impossível",
                         origin_type="task", from_agent_id=remetente["id"])
        if s != 201:
            r.check_true("K setup", False, "não criou a mensagem")
            return
        did = b["id"]
        s, _ = r.call("POST", f"/api/v1/demands/{did}/dispatch", {"target_agent_id": aid})
        r.check("K1 dispatch manual em agente sem runtime_type", 409, s)

        agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        s, b2 = r.submit(subject="[val] K2 agendada para agente impossível",
                         origin_type="task", from_agent_id=remetente["id"],
                         target_agent_id=aid, scheduled_at=agora)
        if s != 201:
            r.check_true("K2 setup", False, str(b2)[:120])
            return
        did2 = b2["id"]
        deadline = time.time() + 120
        estado = None
        while time.time() < deadline:
            cur = r.demand(did2)
            estado = cur.get("dispatch_status") if cur else None
            if estado == "failed":
                break
            time.sleep(5)
        r.check_true("K2 loop agendado marca 'failed' em vez de tentar para sempre",
                     estado == "failed", f"dispatch_status={estado}")
        notif = r.sql(f"select count(*) from company.notifications where event_key = 'demand-dispatch-failed:{did2}'")
        r.check_true("K3 falha permanente gera notificação no sino", notif == "1", f"notificações={notif}")
        r.sql(f"delete from company.notifications where event_key = 'demand-dispatch-failed:{did2}'")
    finally:
        r.sql(f"delete from company.agent_demands where target_agent_id = '{aid}'")
        r.sql(f"delete from company.agents where id = '{aid}'")


def phase_live(r: Runner, agents: dict[str, dict]):
    r.banner("J. Dispatch real e relay de Retorno (um agente por runtime)")
    alvos, vistos = [], set()
    for nome in ("Atlas", "Aramis", "Dartan", "Vector", "Porthus"):
        a = agents.get(nome)
        if a and a.get("runtime_type") and a["runtime_type"] not in vistos:
            vistos.add(a["runtime_type"])
            alvos.append(a)
    remetente = agents["Athos"]
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    enviados = []
    for a in alvos:
        payload = {
            "from_agent": "athos", "from_agent_id": remetente["id"], "target_agent_id": a["id"],
            "origin_type": "task", "requires_response": True, "scheduled_at": agora,
            "subject": f"[val] ciclo automático → {a['name']}",
            "body": "Responda apenas com a palavra: recebido. Não crie nem altere nenhum arquivo.",
        }
        s, b = r.call("POST", "/api/v1/demands/submit", payload, bridge=True)
        if s == 201:
            enviados.append((a, b))
            print(f"  {DIM}enviada #{b['number']} → {a['name']} ({a['runtime_type']}){RESET}")
        else:
            r.check_true(f"J {a['name']} ({a['runtime_type']}) enviada", False, str(b)[:140])

    print(f"  {DIM}a partir daqui nenhuma chamada de dispatch/dispatch-status é feita — "
          f"só os loops de background{RESET}")
    deadline = time.time() + 600
    pendentes = {b["id"] for _, b in enviados}
    finais: dict[str, dict] = {}
    while pendentes and time.time() < deadline:
        time.sleep(15)
        _, todas = r.call("GET", "/api/v1/demands")
        por_id = {d["id"]: d for d in todas} if isinstance(todas, list) else {}
        for did in list(pendentes):
            cur = por_id.get(did)
            if cur and cur.get("dispatch_status") in ("completed", "failed"):
                finais[did] = cur
                pendentes.discard(did)

    _, todas = r.call("GET", "/api/v1/demands")
    respostas = {d.get("reply_to_id"): d for d in todas if d.get("reply_to_id")}
    for a, b in enviados:
        cur = finais.get(b["id"])
        rt = a["runtime_type"]
        if cur is None:
            r.check_true(f"J {a['name']} ({rt}) executou sem intervenção", False, "não finalizou em 10 min")
            continue
        r.check_true(f"J {a['name']} ({rt}) despachada e finalizada pelos loops",
                     cur.get("dispatch_status") == "completed", f"dispatch_status={cur.get('dispatch_status')}")
        r.check_true(f"J {a['name']} ({rt}) carimbou a execução",
                     cur.get("task_execution_at") is not None)
        # "Processamento" -- o resultado sempre fica gravado na própria
        # mensagem original, independente de requires_response (2026-07-28).
        r.check_true(f"J {a['name']} ({rt}) gravou dispatch_result na própria mensagem",
                     bool(cur.get("dispatch_result")))
        # requires_response=True nesta rodada -- também deve existir uma
        # mensagem de retorno real, separada.
        resp = respostas.get(b["id"])
        r.check_true(f"J {a['name']} ({rt}) gerou mensagem de retorno (requires_response=true)", resp is not None)
        if resp is not None:
            r.check_true(f"J {a['name']} ({rt}) retorno é Tipo=task",
                         resp.get("origin_type") == "task", f"origin_type={resp.get('origin_type')}")
            r.check_true(f"J {a['name']} ({rt}) retorno devolvido ao remetente",
                         resp.get("target_agent_id") == remetente["id"],
                         f"target={resp.get('target_agent_id')}")
            r.check_true(f"J {a['name']} ({rt}) retorno não pede retorno de volta (sem loop)",
                         resp.get("requires_response") is False)
            r.check_true(f"J {a['name']} ({rt}) resposta é texto limpo (sem JSON cru)",
                         not (resp.get("body") or "").lstrip().startswith(("{", "[")),
                         (resp.get("body") or "")[:60].replace("\n", " "))
            iguais = [d for d in todas if d.get("reply_to_id") == b["id"]]
            r.check_true(f"J {a['name']} ({rt}) resposta única (sem duplicata de pollers)",
                         len(iguais) == 1, f"{len(iguais)} respostas")


def phase_regression() -> tuple[bool, str]:
    print(f"\n{YELLOW}=== M. Suíte de regressão (pytest) ==={RESET}")
    out = subprocess.run(
        ["bash", "-lc", "cd /root/project/forgehub/backend && source .venv/bin/activate && pytest -q 2>&1 | tail -3"],
        capture_output=True, text=True, timeout=1800,
    )
    linha = [l for l in out.stdout.strip().splitlines() if "passed" in l or "failed" in l]
    resumo = linha[-1].strip() if linha else out.stdout.strip()[-200:]
    ok = "failed" not in resumo and "error" not in resumo.lower()
    mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FALHA{RESET}"
    print(f"  {mark} M1 pytest {DIM}{resumo}{RESET}")
    return ok, resumo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--skip-live", action="store_true", help="pula a fase J (execuções reais de agente)")
    ap.add_argument("--skip-pytest", action="store_true")
    args = ap.parse_args()

    r = Runner(args.base)
    print(f"{YELLOW}Validação do canal de mensagens — {r.base}{RESET}")
    lista = r.agents()
    if not lista:
        raise SystemExit("Não consegui listar agentes — abortando.")
    agents = {a["name"]: a for a in lista}
    print(f"{DIM}{len(agents)} agentes registrados{RESET}")

    phase_auth(r)
    phase_payload(r)
    phase_refs(r, agents)
    phase_rules(r, agents)
    phase_crud(r, agents)
    phase_attachments(r)
    phase_groups(r)
    phase_pull(r)
    phase_for_agent(r)
    phase_script(r, agents)
    phase_dispatch_failure(r, agents)
    if not args.skip_live:
        phase_live(r, agents)

    print(f"\n{DIM}limpando {len(r.created)} mensagens sintéticas...{RESET}")
    for did in r.created:
        r.call("DELETE", f"/api/v1/demands/{did}")

    pytest_ok = True
    if not args.skip_pytest:
        pytest_ok, _ = phase_regression()

    print(f"\n{YELLOW}=== Resumo ==={RESET}")
    por_fase: dict[str, list[bool]] = {}
    for fase, _, ok, _ in r.results:
        por_fase.setdefault(fase, []).append(ok)
    for fase, oks in por_fase.items():
        falhas = oks.count(False)
        cor = GREEN if falhas == 0 else RED
        print(f"  {cor}{len(oks) - falhas}/{len(oks)}{RESET}  {fase}")
    falhas = [(f, c, d) for f, c, ok, d in r.results if not ok]
    total = len(r.results)
    print(f"\n{GREEN if not falhas and pytest_ok else RED}{total - len(falhas)}/{total} casos{RESET}"
          f" + pytest {'ok' if pytest_ok else 'com falha'}")
    if falhas:
        print(f"\n{RED}Falhas:{RESET}")
        for f, c, d in falhas:
            print(f"  - [{f}] {c}{(' — ' + d) if d else ''}")
    sys.exit(1 if falhas or not pytest_ok else 0)


if __name__ == "__main__":
    main()
