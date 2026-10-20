#!/usr/bin/env python3
"""Preview or apply the explicitly approved 34-message consolidation.

Run from backend with its virtualenv. Preview is read-only. --apply uses the
same domain service as the administrative API and commits all five together.
"""
import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import func, select
from app.api.schemas.demand import DemandConsolidateIn
from app.core.demand_consolidation import consolidate_demands
from app.db.base import AsyncSessionLocal, engine
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.personal import PersonalCaptureSuggestion

GROUPS = [
    ("Operação dos agentes", "athos", [26382,28816,28818,28990,29060,29061,29065,29078,29079,29082,29084,29088,29109,29126,37595],
     "Reconhecimento das migrações do Foundation; triagem, briefings e retrospectivas; qualidade da evidência e confiabilidade das métricas.",
     "As propostas registram coleta zerada/never_ran, inventários divergentes e encerramentos sem evidência. Há falhas de rotinas e restaurações ECO-022/ECO-044; conclusão de execução não comprova entrega.",
     "Conferir o reconhecimento das migrações citadas em #26382; validar fontes de métricas e o inventário único; revisar perguntas duplicadas; definir critérios verificáveis de conclusão das rotinas.",
     "Evidências das migrações e controles; resultados reconciliados das execuções antigas; decisão sobre quais melhorias devem virar tarefas."),
    ("Infraestrutura", "hephaestus", [27024,27027,28860],
     "Cobertura de healthchecks Docker e observabilidade da limpeza diária.",
     "Os três registros são propostas históricas. Suas contagens de containers e ausência de timer foram observações na data de origem; não demonstram o estado atual.",
     "Refazer o inventário de healthchecks e o mapeamento do agendamento de limpeza; identificar responsáveis e exceções antes de propor alterações por stack. Não remover volumes ou dados persistentes.",
     "Inventário atual verificável, acesso aos manifests e decisão sobre escopo e critérios de saúde."),
    ("Backup", "hephaestus", [26996,28817,28856,29074,29075,29128],
     "Recuperar a observabilidade do backup externo e demonstrar recuperabilidade.",
     "As origens registram falhas de verificação, snapshot ausente/desatualizado e incidente de repositório restic bloqueado. A proposta de gate diário está documentada; não há prova de restauração aceita por esta consolidação.",
     "Reconciliar os runs registrados; conferir snapshot mais recente, idade e resultado da última execução; investigar o lock com evidência antes de qualquer intervenção; propor teste de leitura/restauração e critérios para normalizar o estado.",
     "Evidência do repositório e dos snapshots, investigação do lock, autorização específica para intervenções e teste de restauração."),
    ("Segurança", "aegis", [28288,28833,28842,28846,29067,29068,29069,29070,29086],
     "Consolidar os incidentes de permissões e exposição de portas e as melhorias de prova diária.",
     "Os registros descrevem o incidente SEC-2026-10-06-0600, permissões 0644 e listeners fora da allow-list. Listeners locais e regras de firewall são evidências parciais; não comprovam sozinhos exposição WAN nem remediação atual.",
     "Reconciliar as execuções incertas; revisar evidências do incidente e do ECO-047; comparar baseline aprovado, listeners, firewall e alcance externo por procedimento autorizado; definir saída reproduzível PASS/WARN/FAIL.",
     "Allow-list vigente, evidência atual de permissões e alcance, revisão independente e autorização específica antes de mudar rede ou credenciais."),
    ("Maia / WhatsApp", "maia", [37588],
     "Determinar como cadastrar e manter completo o inventário dos grupos WhatsApp da Maia.",
     "O pedido original descreve cache parcial, nomes numéricos e grupos ausentes na consulta. Existe uma execução falha registrada; esta consolidação não comprova que a descoberta/sincronização foi implementada.",
     "Reconciliar o run anterior; comparar descoberta da sessão WhatsApp, bridge/plugin e cache; preparar solução verificável para cadastro e sincronização, com tratamento de alterações de nomes e participação.",
     "Evidência do run e das capacidades da sessão, autorização de escopo e critérios de inventário completo. Não enviar mensagens nem interagir com participantes."),
]


def source_snapshot(row):
    return {"id": str(row.id), "number": row.number, "body_sha256": hashlib.sha256(row.body.encode()).hexdigest(),
        "run_id": row.agent_run_id, "error": row.dispatch_error, "attempts": row.dispatch_attempts}


async def run(apply, output):
    report = {"applied": apply, "groups": []}
    async with AsyncSessionLocal() as db:
        suggestions_before = await db.scalar(select(func.count()).select_from(PersonalCaptureSuggestion))
        numbers = [number for _, _, group, *_ in GROUPS for number in group]
        statement = select(AgentDemand).where(AgentDemand.number.in_(numbers)).order_by(AgentDemand.id)
        if apply:
            statement = statement.with_for_update()
        sources = list((await db.execute(statement)).scalars())
        if len(sources) != 34:
            raise RuntimeError("The approved 34-source selection no longer matches; investigate before applying")
        indexed = {row.number: row for row in sources}
        for area, owner_slug, source_numbers, objective, evidence, pending, dependencies in GROUPS:
            owner = (await db.execute(select(Agent).where(Agent.profile_slug == owner_slug, Agent.is_active.is_(True)))).scalar_one()
            rows = [indexed[number] for number in source_numbers]
            before = [source_snapshot(row) for row in rows]
            failures = sum(row.dispatch_status == "failed" for row in rows)
            incubations = sum(row.origin_type == "incubation" for row in rows)
            body = (f"## Objetivo\n{objective}\n\n## Situação comprovada\n"
                f"Seleção explícita de {len(rows)} registros: {failures} falhas e {incubations} incubações. {evidence}\n\n"
                "## Entregas parciais\nAs propostas, observações e saídas de execução registradas nas origens permanecem disponíveis nos vínculos abaixo. A preservação desses registros não certifica entrega nem resolução de incidentes.\n\n"
                f"## Pendências\n{pending}\n\n## Dependências\n{dependencies}\n\n"
                "## Próximos passos\nRevisar as evidências atuais, reconciliar os runs ainda incertos e apresentar uma decisão humana sobre escopo, prioridade e autorização. Este resumo permanece em Incubação e não autoriza execução.\n\n"
                "## Rastreabilidade\nOs registros de origem conservam conteúdo, erro, tentativas, run e anexos. Arquivamento por consolidação não significa conclusão, cancelamento do processo ou autorização de nova tentativa.")
            payload = DemandConsolidateIn(source_ids=[row.id for row in rows], subject=f"Contexto consolidado — {area}",
                body=body, owner_agent_id=owner.id, context_area=area)
            entry = {"area": area, "owner": owner_slug, "source_numbers": source_numbers,
                "subject": payload.subject, "body": body, "summary_number": None}
            if apply:
                summary = await consolidate_demands(db, payload, actor="marcelo:approved-plan:2026-10-20")
                for row, original in zip(rows, before):
                    assert source_snapshot(row) == original, f"Source evidence changed for #{row.number}"
                    assert row.status == "archived" and row.consolidated_into_id == summary.id
                assert summary.scheduled_at is None and summary.agent_run_id is None and summary.origin_type == "incubation"
                assert summary.requires_approval and summary.approval_status == "pending"
                entry.update(summary_number=summary.number, summary_id=str(summary.id))
            report["groups"].append(entry)
        assert suggestions_before == await db.scalar(select(func.count()).select_from(PersonalCaptureSuggestion))
        if apply:
            await db.commit()
        else:
            await db.rollback()
    if output:
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for group in report["groups"]:
        print(f"{group['area']}: {len(group['source_numbers'])} sources; summary {group['summary_number'] or 'preview'}")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    asyncio.run(run(args.apply, args.output))
