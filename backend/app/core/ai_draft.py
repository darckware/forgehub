"""Prompt construction and reply parsing for the "Gerar via IA" draft feature.

One icon, one dialog, one backend endpoint (api/routes/ai_draft.py) shared by
all 5 Software Factory phases (Conception, System Map, Backlog, Tasks,
Governance) -- only the `target_kind` and the prompt/schema it maps to
differ. This module never writes to the database: an agent call here always
returns a draft for human review; applying it (creating the actual System
Element / Planning Item / Task / concept fields) goes through each domain's
own existing, already-permissioned create endpoints, never a new path that
bypasses them -- see docs/... governance boundary: an agent may never
create/edit a domain entity on its own, only propose content for a human to
apply (memory: forgehub-inapp-assistant-policy).
"""
import json
import re

from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError

from app.api.schemas.ai_draft import DRAFT_SCHEMA_BY_KIND, AiDraftTargetKind


_TARGET_KIND_INSTRUCTIONS: dict[AiDraftTargetKind, str] = {
    "concept": (
        "Leia o contexto abaixo (um documento solto descrevendo uma ideia de sistema, automação ou "
        "serviço) e proponha os campos estruturados de uma Concepção de produto no ForgeHub. Responda "
        "com um bloco JSON cercado (```json ... ```) no formato:\n"
        '{"name": str, "problem_statement": str, "vision": str|null, "scope_summary": str|null, '
        '"project_description": str|null, "tech_stack": [{"layer": "frontend"|"backend"|"database"|'
        '"deploy_infra", "decision": str, "rationale": str|null}], "documentation_markdown": str|null}\n'
        "documentation_markdown deve ser um rascunho de documentação em Markdown apropriado ao tipo de "
        "iniciativa descrita no contexto -- um sistema com telas pede uma estrutura tipo PRD; uma "
        "automação ou um serviço sem interface pede gatilho, entradas/saídas, dependências e tratamento "
        "de erro em vez de telas. Inclua em tech_stack APENAS as camadas para as quais você tem uma "
        "decisão real -- omita a camada inteira do array em vez de incluí-la com decision nulo/vazio "
        "quando ela não se aplica (ex.: uma automação sem interface não precisa de entrada \"frontend\")."
    ),
    "system_elements": (
        "Leia o contexto abaixo e proponha elementos do System Map (Mapa do Sistema) do ForgeHub -- "
        "capacidades, processos, telas/rotas, APIs, entidades de domínio etc. Responda com um bloco JSON "
        "cercado no formato:\n"
        '{"elements": [{"key": str (identificador curto único dentro desta resposta), '
        '"family": "business"|"process"|"experience"|"interface"|"domain"|"application"|"data"|"runtime"|'
        '"assurance", "element_type": str (tipo compatível com a família), "name": str, '
        '"description": str|null}], "relations": [{"from": str (key), "to": str (key), '
        '"relation_type": str}]}\n'
        "Use apenas element_type reconhecidos (capability, module, persona, journey, process, "
        "process_step, use_case, application, channel, route, screen, form, report, ui_component, api, "
        "endpoint, command, query, event, webhook, integration, domain_entity, value_object, "
        "business_rule, authorization_rule, service, handler, class, method, workflow, job, datastore, "
        "schema, table, field, index, view, procedure, migration, runtime_component, queue, cache, "
        "deployment_unit, environment_target, test_scenario, metric, log_signal, alert, slo, "
        "health_check) e relation_type reconhecidos (contains, precedes, navigates_to, invokes, "
        "implements, governed_by, reads, writes, emits, consumes, depends_on, persists_as, runs_on, "
        "deployed_to, verified_by)."
    ),
    "planning_items": (
        "Leia o contexto abaixo e proponha itens de planejamento (Planning Items/Backlog) do ForgeHub -- "
        "features, bugs, melhorias etc. Responda com um bloco JSON cercado no formato:\n"
        '{"items": [{"title": str, "item_type": "feature"|"bug"|"hotfix"|"improvement"|"technical_debt"|'
        '"refactoring"|"security_fix"|"research"|"documentation", "description": str|null, '
        '"priority": "low"|"medium"|"high"|"critical"|null}]}'
    ),
    "tasks": (
        "Leia o contexto abaixo (a descrição de um item de planejamento) e quebre-o em tarefas concretas "
        "e executáveis. Para cada tarefa, sugira o papel mais adequado para executá-la. Responda com um "
        "bloco JSON cercado no formato:\n"
        '{"tasks": [{"title": str, "description": str|null, "plan_brief": str|null (o COMO/abordagem/'
        'critérios de aceite, distinto de description que é o QUE), '
        '"suggested_role": "developer"|"data_engineer"|"release_manager"|"qa"|null}]}'
    ),
    "review": (
        "Leia o contexto abaixo (o estado atual de uma fase do processo de desenvolvimento) e faça uma "
        "revisão crítica, como um revisor experiente validando se está pronto para avançar de fase. "
        "Responda com um bloco JSON cercado no formato:\n"
        '{"summary": str, "strengths": [str], "gaps": [str], "suggested_corrections": [str]}'
    ),
    "tech_stack": (
        "Antes de decidir, consulte /root/project/forgehub/help/TECH_STACK_GUIDE.md -- é "
        "o inventário real de ferramentas aprovadas pela organização para uso nos produtos, não uma "
        "sugestão genérica. Esse guia é um resumo; se o contexto exigir mais profundidade em uma "
        "camada específica, ele mesmo aponta para os documentos-fonte completos em "
        "/root/.hermes/knowledge_base/marcelo/stack/ (02-UI-DESIGN-SYSTEM-AND-TECHNOLOGY-SPEC.md, "
        "05-FRONTEND-ARCHITECTURE-AND-CODING-STANDARD.md, 06-BACKEND-ARCHITECTURE-AND-CODING-STANDARD.md, "
        "04-DATABASE-MODELING-AND-NAMING-STANDARD.md, 12-INFRASTRUCTURE-ENVIRONMENT-AND-IAC-STANDARD.md). "
        "As opções já catalogadas em <estado_atual> abaixo (se "
        "houver) são as mesmas ferramentas extraídas desses guias e já usadas em outras concepções -- "
        "prefira reutilizar exatamente o nome de uma opção do catálogo quando ela se aplicar ao "
        "contexto, em vez de reformular o mesmo item com outro texto; só proponha uma ferramenta fora do "
        "catálogo quando o guia realmente recomendar algo mais específico para este caso e nenhuma opção "
        "do catálogo cobrir essa necessidade. Leia o contexto abaixo (o problema, a visão, o escopo e/ou "
        "a descrição do projeto) e proponha a stack tecnológica -- uma decisão por camada, com a camada "
        "certa para o tipo de iniciativa (uma automação sem interface não tem entrada \"frontend\"; um "
        "serviço interno sem exposição pública pode não precisar de \"deploy_infra\" além do padrão "
        "já registrado). Responda com um bloco JSON cercado no formato:\n"
        '{"tech_stack": [{"layer": "frontend"|"backend"|"database"|"deploy_infra", "decision": str, '
        '"rationale": str}]}\n'
        "rationale deve justificar a escolha com base no guia consultado (ex.: citar o tipo de "
        "iniciativa que o guia associa àquela tecnologia), nunca uma frase genérica. Inclua APENAS as "
        "camadas para as quais você tem uma decisão real -- omita a camada inteira do array em vez de "
        "incluí-la com decision vazio quando ela não se aplica."
    ),
    "context_summary": (
        "O texto abaixo é um documento .md grande, solto, enviado pelo usuário -- grande demais para "
        "caber com conforto no campo de contexto de onde ele será reaproveitado. Produza um resumo "
        "denso e objetivo (aproximadamente 3000 a 5000 caracteres, nunca mais que 6000) que substitua "
        "o documento original como contexto de entrada de uma etapa de geração seguinte. Preserve tudo "
        "que for material para essa etapa -- decisões já tomadas, requisitos concretos, restrições, "
        "nomes próprios e termos técnicos citados -- e corte apenas repetição, preâmbulo e "
        "preenchimento. Não interprete nem estruture o conteúdo em campos (isso é trabalho de uma "
        "etapa posterior) -- apenas condense o mesmo texto solto para um tamanho menor. Responda com "
        'um bloco JSON cercado no formato:\n{"summary": str}'
    ),
}


def get_prompt_instructions(target_kind: AiDraftTargetKind) -> str:
    """The exact per-target_kind instruction text build_ai_draft_prompt
    embeds -- exposed read-only (GET /api/v1/ai-draft/prompt-template) so
    the "Copiar prompt" button shows the real instructions the agent
    receives, not a hand-maintained paraphrase that could drift from it
    (2026-08-16, Marcelo: "preciso copiar um prompt que informe o que é
    preciso... como fosse uma engenharia reversa")."""
    return _TARGET_KIND_INSTRUCTIONS[target_kind]


def build_ai_draft_prompt(
    *, target_kind: AiDraftTargetKind, context: str, extra_instruction: str, subject_context: str | None,
) -> str:
    extra = extra_instruction.strip() or "Nenhuma instrução adicional."
    parts = [
        "Você está ajudando a preencher um formulário no ForgeHub a partir de um contexto solto. Sua "
        "resposta é um RASCUNHO para revisão humana -- nada é aplicado automaticamente.",
        _TARGET_KIND_INSTRUCTIONS[target_kind],
        "Regras invariáveis:\n"
        "- responda APENAS com o bloco JSON cercado, sem comentário, prefácio ou explicação fora dele;\n"
        "- não invente fatos que não constem do contexto; quando faltar uma decisão material, deixe o "
        "campo null ou registre a lacuna em vez de inventar;\n"
        "- preserve nomes próprios, termos técnicos e identificadores citados no contexto.",
    ]
    if subject_context:
        parts.append(f"<estado_atual>\n{subject_context}\n</estado_atual>")
    parts.append(f"<contexto>\n{context.strip() or '(nenhum contexto adicional fornecido)'}\n</contexto>")
    parts.append(f"Instrução adicional do usuário: {extra}")
    return "\n\n".join(parts)


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def _extract_json_object(reply: str) -> dict:
    match = _JSON_BLOCK_RE.search(reply)
    raw = match.group(1) if match else reply.strip()
    # raw_decode (not json.loads) on purpose: an agent that skips the fence
    # (or adds a closing remark after it, seen in practice -- "Extra data"
    # at some late column is exactly a trailing-prose reply) still has a
    # single well-formed JSON object at the start; raw_decode parses that
    # object and simply ignores whatever follows, instead of rejecting the
    # whole reply over trailing text that was never part of the answer.
    try:
        parsed, _end = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Agent reply was not valid JSON: {exc}",
        ) from None
    if not isinstance(parsed, dict):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Agent reply's JSON was not an object")
    return parsed


def parse_ai_draft_reply(reply: str, target_kind: AiDraftTargetKind) -> dict:
    """Extracts the fenced JSON block from an agent's raw reply and validates
    it against target_kind's schema. Raises HTTPException(502) on anything
    that doesn't match -- never silently coerces malformed agent output."""
    schema: type[BaseModel] = DRAFT_SCHEMA_BY_KIND[target_kind]
    raw = _extract_json_object(reply)
    try:
        validated = schema.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Agent reply did not match the expected '{target_kind}' shape: {exc}",
        ) from None
    return validated.model_dump(by_alias=True)
