# 03 — Produtos, projetos e entrega

Base: `main` em `43a6a7f`. Não confunda os contratos atuais com o ciclo de release
proposto nos documentos de módulos.

## Produto e versão

| ID | Estado | Regra de negócio | Fonte de enforcement e cobertura |
|---|---|---|---|
| DEL-001 | IMPLEMENTADA | Nome de produto é único; um produto mantém ao menos uma versão. Não apague sua última versão. | `backend/app/db/models/product.py:44,55,109`; `backend/app/api/routes/product.py` (`create_product`, `delete_version`); `docs/reference/BUSINESS_RULES.md:9` |
| DEL-002 | IMPLEMENTADA | Versão publicada não é editada diretamente. Correção posterior é modelada como nova versão/fluxo patch ou hotfix, mas esse tratamento é convenção, não gate automático. | `backend/app/api/routes/product.py` (`update_version`); `docs/reference/BUSINESS_RULES.md:9` |
| DEL-003 | IMPLEMENTADA | Produto, módulo, versão e release têm estados distintos; use os estados definidos no modelo e nas rotas em vez de inventar um status de tela. | `backend/app/db/models/product.py:44-52,95,109,136`; `backend/app/api/schemas/product.py` |

## Mapa, escopo, plano e mudança

| ID | Estado | Regra de negócio | Fonte de enforcement e cobertura |
|---|---|---|---|
| DEL-004 | IMPLEMENTADA | Item de escopo pertence ao produto e à revisão aprovada do System Map; somente escopo em rascunho aceita inclusão; item deve existir no mapa-base e não pode ser duplicado. | `backend/app/api/routes/system_scope.py:1389,1429`; `backend/app/tests/test_system_scope.py:88` |
| DEL-005 | IMPLEMENTADA | Baseline de plano só nasce de plano aprovado. Depois do baseline, não altere escopo, cronograma ou custo diretamente: abra Change Request. | `backend/app/api/routes/project.py:306,390`; `backend/app/tests/test_project.py:170,204` |
| DEL-006 | IMPLEMENTADA | Change Request precisa declarar ao menos um tipo de impacto e congela seu conteúdo após decisão. | `backend/app/api/routes/project.py:464,546`; `backend/app/db/models/project.py:329`; `backend/app/tests/test_project.py` |
| DEL-007 | GAP | **A aprovação de plano de projeto comum não é igual à aprovação de plano de Missão.** A rota comum `approve_project_plan` altera o estado sem dependência de aprovação governada; projeto de Missão é recusado nessa rota e precisa do fluxo de Missão. Não descreva todos os planos como igualmente aprovados por governança. | `backend/app/api/routes/project.py:337,353`; `backend/app/tests/test_project.py:225`; Missões: `backend/app/api/routes/mission_plan.py:91,115` |

## Pipeline, tarefa e evidência

| ID | Estado | Regra de negócio | Fonte de enforcement e cobertura |
|---|---|---|---|
| DEL-008 | IMPLEMENTADA | Projeto pode ter no máximo um pipeline ativo. Uma etapa deve respeitar dependências, artefatos obrigatórios e gates antes de avançar/concluir. | `backend/app/api/routes/pipeline.py` (`_deactivate_other_active_pipelines`, `_enforce_stage_advance_rules`); `docs/reference/BUSINESS_RULES.md:19` |
| DEL-009 | IMPLEMENTADA | Planning Item liga-se a projeto existente; ProjectTask liga-se a Planning Item existente. Assignment aponta para exatamente um agente ou subagente. | `backend/app/api/routes/backlog.py`; `backend/app/api/routes/task.py`; `backend/app/api/schemas/task.py`; `docs/reference/BUSINESS_RULES.md:73` |
| DEL-010 | IMPLEMENTADA | Status de tarefa é um conjunto fechado no modelo. `done` é trabalho concluído com evidência; `deployed` é liberação para produção, estado separado. `assigned` e `in_progress` são efeitos de atribuição/execução, não sinônimos de aceite. | `backend/app/db/models/task.py:37,44,155`; migration `3d0bb9a16778`; `docs/reference/BUSINESS_RULES.md:126` |
| DEL-011 | GAP | A lista de status em `docs/reference/BUSINESS_RULES.md` está incompleta: o modelo atual também inclui `ready` e `in_review`. Ao mudar status, confirme `TASK_STATUSES`, validators e transições; corrija a documentação de referência junto com a implementação. | `backend/app/db/models/task.py:44`; conflito em `docs/reference/BUSINESS_RULES.md:132` |
| DEL-012 | IMPLEMENTADA | Tarefa dependente só pode iniciar/concluir quando predecessoras estiverem `done` ou `deployed`; cancelada, falha ou apenas reportada não satisfaz dependência. Grafos não podem ter ciclos. | `backend/app/core/task_dependencies.py`; `backend/app/api/routes/task.py`; `backend/app/tests/test_task.py` e `test_demand_management.py` |
| DEL-013 | IMPLEMENTADA | Execução verificada/concluída requer referência de evidência. Transições de conclusão de tarefa e execução, aprovação/rejeição de artefato e conclusão de etapa geram AuditEvent. | `backend/app/api/schemas/task.py`; `backend/app/api/routes/task.py`, `pipeline.py`, `artifact.py`; `docs/reference/BUSINESS_RULES.md:41,73,85` |
| DEL-014 | IMPLEMENTADA | Artefato pode ser independente; links a etapa ou execução, se fornecidos, precisam existir. Recurso marcado `is_locked` não aceita mutação até desbloqueio explícito. Esse lock é regra do ForgeHub, não permissão de filesystem. | `backend/app/api/routes/artifact.py` (`_validate_artifact_links`, `_assert_not_locked`); `backend/app/api/routes/project.py` (`_assert_node_not_locked`); `docs/reference/BUSINESS_RULES.md:97,105` |

## Release e deploy: limite do que está implementado

| ID | Estado | Regra de negócio | Fonte de enforcement e cobertura |
|---|---|---|---|
| DEL-015 | IMPLEMENTADA | Gate de etapa e artefatos obrigatórios são condições de conclusão no pipeline atual; não substitua essas verificações por status visual ou texto de agente. | `backend/app/api/routes/pipeline.py`; `docs/reference/BUSINESS_RULES.md:19` |
| DEL-016 | GAP | A API de Deploy atual administra containers, imagens, volumes, redes e registro de instalações sincronizado com Docker. Isso não comprova um lifecycle completo de release de produto com canary, blue/green e rollback automático. O ciclo mais rico em `docs/modules/05_RELEASE_OPERATIONS_MAINTENANCE.md` é alvo documental; não o apresente como feature ativa sem achar implementação atual. | `backend/app/db/models/deploy.py:11`; `backend/app/api/routes/deploy.py:74,242,397`; testes `backend/app/tests/test_deploy.py:68,158`; alvo em `docs/modules/05_RELEASE_OPERATIONS_MAINTENANCE.md:7,35`; conflito em `docs/reference/TECHNOLOGY.md:32` |
| DEL-017 | GAP | `ProductVersion`/`Release` existentes pertencem a produtos cadastrados. Não os use como controle da versão do próprio ForgeHub. A tela `Controle do Sistema > Releases`, entidade/API própria e histórico tipado ainda são proposta e não comportamento atual; o changelog atual não deve inventar releases passadas. | `backend/app/db/models/product.py:109,137`; `backend/app/api/routes/product.py:897`; contrato proposto em `docs/superpowers/specs/2026-11-14-forgehub-release-control-design.md` |

## Instruções para agentes

- Antes de mudar escopo aprovado, plano, tarefa, artefato ou pipeline, siga a regra de
  baseline/Change Request adequada ao tipo de projeto. Verifique se é projeto comum
  ou Missão: a aprovação não tem o mesmo enforcement nos dois fluxos (DEL-007).
- Não converta falha de processo, execução limpa ou mensagem `completed` em aceite da
  tarefa. Validação, aceite (`done`) e deploy (`deployed`) são transições distintas.
- Ao alterar status, artefato ou release, atualize migrations/validators/rotas/testes
  que aplicam o gate e esta documentação; preserve o histórico de auditoria.
- Não implemente canary, blue/green, rollback ou aprovação de release por inferência
  de um documento-alvo. Primeiro confirme contrato atual e decisão autorizada.

## Fontes de contexto

- [Business Rules anterior](../reference/BUSINESS_RULES.md) — regras de produto,
  pipeline, planejamento, execution, governança e rastreabilidade; tem a divergência
  DEL-011.
- [Arquitetura de Planning e Delivery](../architecture/PLANNING_DELIVERY_ARCHITECTURE.md)
  — mistura arquitetura-alvo e trechos marcados como implementados; confirme cada
  comportamento no código antes de chamar de vigente.
- [Docs de módulos](../modules/README.md) — contratos de destino; não provam deploy.
