#!/usr/bin/env python3
"""Teste operacional do Agent Activity: Agentes, Banco de Dados, Projetos e Messages.

Valida que o read model e topologia do Agent Activity retrata fielmente:
1. Todos os 13 Agentes operacionais ativos no ecossistema
2. O Banco de Dados (forgehub_postgres / schema company)
3. O Projeto (Portal Web Factory) e seus vínculos
4. A comunicação entre os agentes via Messages (canal company.agent_demands)
5. As relações topológicas de persistência (Projeto -> Banco) e alocação (Agentes -> Projeto)
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.demand import DemandSubmitIn
from app.core.agent_activity import build_agent_activity
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.project import Project

PROJECT_ID = uuid.UUID("12c96e63-5d29-4f51-8817-77aa11ac26fc")  # Portal Web Factory

ROLE_BY_AGENT = {
    "athos": "coordinator",
    "daedalus": "architect",
    "atlas": "developer",
    "themis": "compliance",
    "aegis": "security_reviewer",
    "hephaestus": "data_engineer",
    "mnemosyne": "knowledge_management",
    "scriba": "documentation",
    "kairos": "planner",
    "lara": "release_manager",
    "aramis": "developer",
    "porthus": "reviewer",
    "dartan": "developer",
}

COMMUNICATION_FLOW = [
    # (from_slug, to_slug, subject, body, status, requires_response)
    (
        "athos",
        "daedalus",
        "[Portal Web] Definir arquitetura de componentes e layout da Software Factory",
        "Por favor estruture a especificação técnica e diagramas da interface para o Portal Web Factory.",
        "completed",
        True,
    ),
    (
        "daedalus",
        "athos",
        "[Portal Web] Re: Especificação de arquitetura concluída",
        "Arquitetura e divisão de componentes definidas no documento de concepção.",
        "completed",
        False,
    ),
    (
        "athos",
        "atlas",
        "[Portal Web] Implementação do backend e endpoints de catálogo",
        "Implemente os endpoints REST para sincronização de projetos e módulos no backend.",
        "completed",
        True,
    ),
    (
        "athos",
        "themis",
        "[Portal Web] Revisão de conformidade e governança de permissões",
        "Verifique as regras de isolamento de tenant e políticas de auditoria do Portal Web Factory.",
        "completed",
        True,
    ),
    (
        "themis",
        "aegis",
        "[Portal Web] Validação cruzada de segurança e tokens RBAC",
        "Encaminhando matriz de permissões para auditoria de segurança das credenciais e tokens.",
        "completed",
        False,
    ),
    (
        "athos",
        "aegis",
        "[Portal Web] Auditoria de segurança nas rotas e autenticação reCAPTCHA",
        "Execute varredura nos fluxos de autenticação e proteção contra brute-force.",
        "completed",
        True,
    ),
    (
        "athos",
        "hephaestus",
        "[Portal Web] Migração e indexação no banco de dados PostgreSQL",
        "Otimize os índices no schema company e valide a integridade referencial.",
        "completed",
        True,
    ),
    (
        "daedalus",
        "hephaestus",
        "[Portal Web] Alinhamento de modelo de dados e ERD",
        "Alinhando tabelas de catálogo com a modelagem relacional persistida no PostgreSQL.",
        "completed",
        False,
    ),
    (
        "athos",
        "mnemosyne",
        "[Portal Web] Indexação na base de conhecimento e vetores RAG",
        "Catalogar as referências arquiteturais e especificações na base de conhecimento.",
        "completed",
        True,
    ),
    (
        "athos",
        "scriba",
        "[Portal Web] Redação do manual do usuário e documentação técnica",
        "Elabore a documentação técnica de integração e o guia do operador.",
        "completed",
        True,
    ),
    (
        "athos",
        "kairos",
        "[Portal Web] Cronograma de sprints e agendamento de verificações",
        "Planeje os cron scripts de verificação periódica de integridade dos componentes.",
        "completed",
        True,
    ),
    (
        "athos",
        "lara",
        "[Portal Web] Preparação do pacote de release e checklist de deploy",
        "Prepare a esteira de build e release para a versão candidata do Portal Web Factory.",
        "completed",
        True,
    ),
    (
        "athos",
        "aramis",
        "[Portal Web] Implementação do layout responsivo e componentes React",
        "Codifique os componentes Tailwind/shadcn da interface do Portal Web Factory.",
        "completed",
        True,
    ),
    (
        "aramis",
        "porthus",
        "[Portal Web] Solicitação de code review dos componentes frontend",
        "Submetendo PR dos componentes React e hooks de estado para revisão técnica.",
        "completed",
        True,
    ),
    (
        "athos",
        "porthus",
        "[Portal Web] Code review arquitetural e validação de tipagem",
        "Revise a consistência de tipos TypeScript e contratos com as APIs.",
        "completed",
        True,
    ),
    (
        "porthus",
        "dartan",
        "[Portal Web] Diretrizes para refatoração e otimização de bundle",
        "Revisão aprovada com sugestões de modularização e lazy loading para refatorar.",
        "completed",
        False,
    ),
    (
        "athos",
        "dartan",
        "[Portal Web] Refatoração de performance e testes automatizados",
        "Aplique otimização de renderização e execute suíte de testes unitários.",
        "completed",
        True,
    ),
    (
        "dartan",
        "athos",
        "[Portal Web] Re: Testes e refatoração concluídos com 100% de sucesso",
        "Otimizações aplicadas, cobertura de testes validada e pronta para homologação.",
        "completed",
        False,
    ),
]


async def run_test():
    print("================================================================================")
    print("INICIANDO TESTE DO AGENT ACTIVITY COM TODOS OS AGENTES, PROJETOS E BANCO DE DADOS")
    print("================================================================================\n")

    async with AsyncSessionLocal() as session:
        # 1. Carregar agentes ativos
        agents_result = await session.execute(
            select(Agent).where(Agent.is_active == True).order_by(Agent.name)
        )
        active_agents = list(agents_result.scalars().all())
        agent_by_slug = {a.profile_slug: a for a in active_agents}
        agent_by_id = {a.id: a for a in active_agents}

        print(f"[1] Agentes ativos no sistema: {len(active_agents)} agentes.")
        for a in active_agents:
            print(f"    - {a.name:<12} (slug: {a.profile_slug:<12}, runtime: {a.runtime_type or 'hermes'})")
        assert len(active_agents) == 13, f"Esperado 13 agentes, encontrado {len(active_agents)}"

        # 2. Carregar projeto de teste
        project = await session.get(Project, PROJECT_ID)
        assert project is not None, f"Projeto {PROJECT_ID} não encontrado!"
        print(f"\n[2] Projeto de teste: {project.name} (ID: {project.id}, Status: {project.status})")

        # 3. Assegurar filiações (memberships) de todos os 13 agentes ao projeto
        print(f"\n[3] Configurando alocação dos agentes no projeto (company.project_agent_memberships)...")
        existing_memberships_res = await session.execute(
            select(ProjectAgentMembership).where(ProjectAgentMembership.project_id == PROJECT_ID)
        )
        existing_memberships = {m.agent_id: m for m in existing_memberships_res.scalars().all()}

        created_memberships = 0
        for agent in active_agents:
            role = ROLE_BY_AGENT.get(agent.profile_slug, "developer")
            if agent.id not in existing_memberships:
                mem = ProjectAgentMembership(
                    project_id=PROJECT_ID,
                    agent_id=agent.id,
                    role=role,
                    status="active",
                    allocation_percent=50.0,
                    can_review=True,
                    can_approve=(role == "coordinator"),
                )
                session.add(mem)
                created_memberships += 1
            else:
                existing_memberships[agent.id].status = "active"
                existing_memberships[agent.id].role = role

        await session.commit()
        print(f"    - {created_memberships} novas alocações criadas. Todos os 13 agentes alocados como membros ativos.")

        # 4. Criar a rede de comunicação completa entre todos os agentes via Messages
        print(f"\n[4] Criando rede de comunicação inter-agentes via Messages (company.agent_demands)...")
        # Limpar mensagens de teste anteriores deste projeto para resultado determinístico
        await session.execute(
            delete(AgentDemand).where(AgentDemand.project_id == PROJECT_ID)
        )
        await session.commit()

        now = datetime.now(timezone.utc)
        created_demands = []
        for from_slug, to_slug, subject, body, status, requires_response in COMMUNICATION_FLOW:
            from_agent = agent_by_slug[from_slug]
            target_agent = agent_by_slug[to_slug]

            demand = AgentDemand(
                from_agent=from_slug,
                from_agent_id=from_agent.id,
                target_agent_id=target_agent.id,
                project_id=PROJECT_ID,
                subject=subject,
                body=body,
                channel="agent",
                origin_type="task",
                status="read",
                dispatch_status=status,
                requires_response=requires_response,
                scheduled_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(demand)
            created_demands.append((demand, from_agent, target_agent))

        await session.commit()
        print(f"    - {len(created_demands)} mensagens criadas entre agentes associadas ao projeto {project.name}.")

        # 5. Chamar a agregação do Agent Activity (build_agent_activity)
        print(f"\n[5] Executando build_agent_activity (Read Model canônico)...")
        activity_view = await build_agent_activity(session, project_id=None, window_minutes=120)

        # 6. Validar Agentes no Agent Activity
        print(f"\n[6] Validação de Agentes:")
        activity_agents_by_name = {a.name: a for a in activity_view.agents}
        print(f"    - Total de agentes no Agent Activity: {len(activity_view.agents)}")
        for a in activity_view.agents:
            print(f"      * {a.name:<12} | Disponibilidade: {a.availability:<10} | Runtime: {a.runtime_type or 'hermes'}")
        assert len(activity_view.agents) == 13, f"Esperado 13 agentes, obtido {len(activity_view.agents)}"

        # 7. Validar Banco de Dados no Agent Activity
        print(f"\n[7] Validação de Recursos de Banco de Dados:")
        assert len(activity_view.resources) >= 1, "Nenhum recurso encontrado no Agent Activity!"
        db_resource = next((r for r in activity_view.resources if r.kind == "database"), None)
        assert db_resource is not None, "Recurso de banco de dados não encontrado!"
        print(f"    - Recurso DB: {db_resource.label} (key: {db_resource.key}, detail: {db_resource.detail}, status: {db_resource.status})")
        assert db_resource.status == "available"

        # 8. Validar Projetos no Agent Activity
        print(f"\n[8] Validação de Projetos:")
        activity_projects = {p.id: p for p in activity_view.projects}
        print(f"    - Total de projetos visíveis: {len(activity_view.projects)}")
        for p in activity_view.projects:
            print(f"      * {p.name} (id: {p.id}, status: {p.status})")
        assert PROJECT_ID in activity_projects, f"Projeto {PROJECT_ID} não encontrado em projects!"

        # 9. Validar Relações Topológicas (Persistência no Banco & Alocação de Agentes)
        print(f"\n[9] Validação de Relações Topológicas (Banco de Dados, Projeto e Agentes):")
        persistence_rel = next(
            (r for r in activity_view.topology_relations if r.kind == "persistence" and r.from_id == str(PROJECT_ID)),
            None,
        )
        assert persistence_rel is not None, "Relação de persistência Projeto -> Banco de Dados ausente!"
        print(f"    - Vínculo Projeto -> DB: {persistence_rel.key}")
        print(f"      * {persistence_rel.from_type}:{persistence_rel.from_id} ---> {persistence_rel.to_type}:{persistence_rel.to_id} ({persistence_rel.label})")

        membership_rels = [
            r for r in activity_view.topology_relations
            if r.kind == "membership" and r.to_id == str(PROJECT_ID)
        ]
        print(f"    - Vínculos Agentes -> Projeto: {len(membership_rels)} relações de alocação encontradas.")
        allocated_agent_ids = {r.from_id for r in membership_rels}
        for a in active_agents:
            assert str(a.id) in allocated_agent_ids, f"Agente {a.name} não vinculado ao projeto!"
            print(f"      * Agente {a.name:<12} ---> Projeto {project.name} (Allocated)")

        # 10. Validar Arestas de Mensagens (Message Edges - Comunicação no Messages)
        print(f"\n[10] Validação de Message Edges (Comunicação entre Agentes no Messages):")
        print(f"    - Total de message_edges encontradas: {len(activity_view.message_edges)}")
        participating_agents = set()
        for edge in activity_view.message_edges:
            participating_agents.add(edge.from_agent_name)
            participating_agents.add(edge.target_agent_name)
            assert edge.project_id == PROJECT_ID, f"Edge {edge.message_id} com project_id inconsistente"
            print(f"      * {edge.from_agent_name:<10} ---> {edge.target_agent_name:<10} | Assunto: {edge.subject[:45]:<45} | Status: {edge.dispatch_status}")

        print(f"\n    - Agentes participantes na comunicação das arestas: {len(participating_agents)} agentes.")
        for name in sorted(participating_agents):
            print(f"      * {name}")
        for a in active_agents:
            assert a.name in participating_agents, f"Agente {a.name} ausente da comunicação de arestas!"

        # 11. Validar Flow Items e Timeline
        print(f"\n[11] Validação de Flow Items e Timeline:")
        project_flow_items = [item for item in activity_view.flow_items if item.source_type == "agent_demand"]
        print(f"    - Flow items de Messages: {len(project_flow_items)} itens.")
        project_timeline_events = [ev for ev in activity_view.timeline if ev.source_type == "agent_demand"]
        print(f"    - Timeline events de Messages: {len(project_timeline_events)} eventos.")
        assert len(project_flow_items) == len(COMMUNICATION_FLOW)
        assert len(project_timeline_events) == len(COMMUNICATION_FLOW)

        # 12. Testar visão com filtro explícito de projeto
        print(f"\n[12] Validação do filtro com project_id explícito:")
        project_scoped_view = await build_agent_activity(session, project_id=PROJECT_ID, window_minutes=120)
        assert len(project_scoped_view.projects) == 1
        assert project_scoped_view.projects[0].id == PROJECT_ID
        assert len(project_scoped_view.message_edges) == len(COMMUNICATION_FLOW)
        print(f"    - Visão com project_id={PROJECT_ID} retornou {len(project_scoped_view.projects)} projeto e {len(project_scoped_view.message_edges)} arestas.")

    print("\n================================================================================")
    print("TODAS AS VALIDAÇÕES DO AGENT ACTIVITY PASSARAM COM 100% DE SUCESSO!")
    print("================================================================================")


if __name__ == "__main__":
    asyncio.run(run_test())
