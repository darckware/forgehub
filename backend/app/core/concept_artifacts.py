"""Deterministic Markdown generators for the documents Conception can
produce once a concept is approved -- PRD, Tech Spec, Screen Templates and
a Design System note -- per the organization's documentation governance
standard (required metadata header + fixed sections per document type).

Pure functions: no I/O, no DB session, so the API route that calls them
only has to write the returned string to disk and register an Artifact
version pointing at it (see api/routes/system_scope.py's
`generate_concept_artifacts`).
"""
from datetime import date
from typing import Any

TECH_STACK_LAYER_LABELS = {
    "frontend": "Frontend",
    "backend": "Backend",
    "database": "Banco de dados",
    "deploy_infra": "Deploy / infraestrutura",
}
SCREEN_SPEC_FIELD_LABELS = {
    "objective": "Objetivo",
    "authorized_users": "Usuários autorizados",
    "required_data": "Dados necessários",
    "actions": "Ações",
    "validation_rules": "Regras de validação",
    "states": "Estados obrigatórios",
}


def _header(title: str, file_name: str, owner: str) -> str:
    today = date.today().isoformat()
    return (
        f"# {title}\n\n"
        f"**Arquivo:** `{file_name}`  \n"
        f"**Versão:** 0.1  \n"
        f"**Status:** Draft  \n"
        f"**Classificação:** Uso interno  \n"
        f"**Responsável:** {owner}  \n"
        f"**Última atualização:** {today}  \n\n"
        "> Gerado automaticamente a partir da Concepção -- revisar e aprovar antes de considerar vigente.\n\n"
        "---\n"
    )


def build_prd_markdown(
    product_name: str, problem_statement: str, vision: str | None,
    scope_summary: str | None, functionality_names: list[str], owner: str,
) -> str:
    scope = scope_summary.strip() if scope_summary and scope_summary.strip() else (
        "\n".join(f"- {name}" for name in functionality_names)
        if functionality_names else "_(nenhuma funcionalidade modelada ainda no diagrama)_"
    )
    return "\n\n".join([
        _header(f"PRD — {product_name}", "PRD.md", owner),
        "## Problema\n\n" + (problem_statement or "_(não informado)_"),
        "## Objetivo de negócio / visão\n\n" + (vision or "_(não informado)_"),
        "## Usuários\n\n_(a detalhar na revisão)_",
        "## Valor\n\n_(a detalhar na revisão)_",
        "## Escopo\n\n" + scope,
        "## Fora de escopo\n\n_(a detalhar na revisão)_",
        "## Métricas de sucesso\n\n_(a detalhar na revisão)_",
        "## Restrições\n\n_(a detalhar na revisão)_",
        "## Riscos\n\n_(a detalhar na revisão)_",
        "## Critérios de aceite\n\n_(a detalhar na revisão)_",
    ]) + "\n"


def build_tech_spec_markdown(product_name: str, tech_stack_decisions: list[dict[str, Any]], owner: str) -> str:
    sections = [_header(f"Spec de Tecnologia — {product_name}", "SPEC-TECNOLOGIA.md", owner)]
    by_layer = {item.get("layer"): item for item in (tech_stack_decisions or [])}
    for layer, label in TECH_STACK_LAYER_LABELS.items():
        decision = by_layer.get(layer)
        body = "_(não definido na concepção)_"
        if decision and decision.get("decision"):
            body = f"**Decisão:** {decision['decision']}"
            if decision.get("rationale"):
                body += f"\n\n**Justificativa:** {decision['rationale']}"
        sections.append(f"## {label}\n\n{body}")
    return "\n\n".join(sections) + "\n"


def build_screen_templates_markdown(product_name: str, screens: list[dict[str, Any]], owner: str) -> str:
    sections = [_header(f"Templates de Tela — {product_name}", "SCREEN-TEMPLATES.md", owner)]
    if not screens:
        sections.append("_(nenhuma tela modelada na visão \"Telas e Navegação\" do diagrama ainda)_")
        return "\n\n".join(sections) + "\n"
    for screen in screens:
        spec = screen.get("screen_spec") or {}
        field_lines = [
            f"**{label}:** {spec.get(field) or '_(a detalhar)_'}"
            for field, label in SCREEN_SPEC_FIELD_LABELS.items()
        ]
        sections.append(f"## {screen['name']}\n\n" + "\n\n".join(field_lines))
    return "\n\n".join(sections) + "\n"


def build_design_system_markdown(product_name: str, frontend_decision: str | None, owner: str) -> str:
    return "\n\n".join([
        _header(f"Design System — {product_name}", "DESIGN-SYSTEM.md", owner),
        "## Stack de UI escolhida\n\n" + (frontend_decision or "_(nenhuma decisão de frontend registrada na concepção)_"),
        "## Fonte canônica de tokens e catálogo de componentes\n\n"
        "Seguir `02-UI-DESIGN-SYSTEM-AND-TECHNOLOGY-SPEC.md` (tokens semânticos, catálogo de componentes "
        "obrigatório, estados de tela) -- este documento não reinventa tokens, apenas registra a escolha "
        "de stack e um checklist inicial de conformidade.",
        "## Checklist inicial\n\n"
        "- [ ] Tokens de cor/tipografia/espaçamento aplicados\n"
        "- [ ] Catálogo base de componentes confirmado (Button, FormField, Dialog, DataGrid, EmptyState, ErrorState)\n"
        "- [ ] Estados obrigatórios de tela cobertos (Loading/Empty/Error/Offline/Permission denied/Not found/Success)",
    ]) + "\n"


__all__ = [
    "build_prd_markdown", "build_tech_spec_markdown",
    "build_screen_templates_markdown", "build_design_system_markdown",
]
