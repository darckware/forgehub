Versão: 1.0.0  
Data: 2026-11-03  
Fonte canônica: /root/.hermes/foundation/52_policies/MISSION_CONVENTION_M0.md  
Testado por: backend/app/tests/test_mission_rehearsal_m0.py

> Rascunho: o ensaio indicado cobre apenas a criação e os vínculos; o percurso completo ainda não foi verificado.

# Roteiro de missão M0

Consulte a fonte canônica para as regras de papéis, delegação, substituição, evidência, documentos e aceite. Este roteiro descreve as chamadas; ele não substitui a convenção. Cada agente usa seu próprio `agt_`: credencial ausente ou inválida é bloqueio. Não use credencial emprestada nem token do bridge.

Nas escritas com `idempotency_key`, gere uma chave de 1 a 150 caracteres por intenção. `IDEMPOTENCY_KEY_REUSED` significa que a mesma chave foi usada com outro conteúdo: confira o estado e use uma nova chave para uma nova intenção. Em `DELEGATION_REQUIRED`, obtenha a delegação indicada para o escopo; não contorne a recusa. `MISSION_TOOLS_DISABLED` exige habilitação pelo operador. Após `UPSTREAM_UNCERTAIN`, consulte o estado ou repita a mesma chave, sem iniciar outra operação.

## Coordenador

1. `create_internal_project(product_version_id, name, idempotency_key)` cria a missão; requer `mission.manage` no produto. `PROJECT_NAME_EXISTS_IN_VERSION`: reutilize o projeto indicado; `PRODUCT_VERSION_NOT_FOUND`: confira a versão; `PATH_NOT_ABSOLUTE`: corrija `working_directory_path`, se informado.
2. `manage_project_members(project_id, operations, idempotency_key)` requer `mission.manage` no projeto e vínculo de coordenador. Cada operação exige `op` e `agent_id`; adição exige `role`. Em `MEMBER_RULE_VIOLATION`, corrija as violações listadas, inclusive `can_approve` ou runtime incompatível; `LAST_COORDINATOR` impede remover o coordenador; `NOT_PROJECT_COORDINATOR` exige o coordenador autorizado. A operação é atômica.
3. Registre o plano, ambiente, revisões por camada, itens e disposições; avance P1–P7 em ordem até `baseline` por `planning:advance` (`to`, `reason`, `idempotency_key`). Os registros de planejamento usam as rotas da missão, pois não há ferramentas MCP equivalentes neste recorte. O coordenador precisa de `mission.orchestrate` para avançar; o autor do plano precisa de `mission.plan.submit`, e revisores de `mission.plan.review`. `PLANNING_STAGE_OUT_OF_ORDER`: siga a ordem; `PLANNING_EXIT_CONDITIONS_UNMET`: resolva os itens em `unmet`; `ROW_VERSION_CONFLICT`: releia antes de editar. A baseline P8 depende da decisão de Marcelo.
4. `submit_project_plan(project_id, task_ids, idempotency_key)` requer `mission.plan.submit`. `PLANNING_PIPELINE_UNFINISHED`: complete P1–P7; `PLAN_CHECKS_FAILED`: corrija os checks; `PLAN_ALREADY_PENDING`: consulte a solicitação existente; `PLAN_DIFFERS_FROM_REVIEWED_VERSION`: submeta a versão revisada; `CHANGE_REQUEST_REQUIRED`: siga o processo de mudança após a baseline. A chamada não aprova.
5. `add_task_dependency(task_id, depends_on_task_id, idempotency_key)` requer `planning.execution.manage`; o único tipo aceito é `finish_to_start`. `TASK_IN_BASELINE`: solicite mudança; `DEPENDENCY_ALREADY_EXISTS`: use a dependência existente; `DEPENDENCY_TYPE_NOT_SUPPORTED`: corrija o tipo; `TASK_NOT_FOUND`: confira o escopo.
6. `assign_task(project_id, task_id, agent_id, reason, idempotency_key)` requer `planning.execution.manage`; reatribuição também requer `mission.orchestrate`. `ASSIGNEE_NOT_ELIGIBLE`: escolha membro ativo com papel executor; `ASSIGNEE_IS_REVIEWER`: escolha outro agente; `TASK_RUN_IN_FLIGHT`: reconcilie a execução antes de reatribuir.
7. `dispatch_task(task_id, idempotency_key)` requer `planning.execution.manage`. `TASK_NOT_ASSIGNED`: atribua primeiro; `CONTEXT_TOO_LARGE`: divida a tarefa; `task_run_in_flight`/`TASK_RUN_IN_FLIGHT`: aguarde ou reconcilie a execução existente; `UPSTREAM_UNCERTAIN`: reconcilie sem novo despacho.
8. Após verificação da execução, `request_task_review(project_id, task_id, execution_id, reviewer_agent_id, idempotency_key)` requer `mission.orchestrate`. `EXECUTION_NOT_VERIFIED`: aguarde verificação; `REVIEWER_NOT_ELIGIBLE`: escolha revisor independente e habilitado; `REVIEW_ALREADY_OPEN`: acompanhe a revisão existente.
9. Se necessário, `return_task_for_correction(project_id, task_id, execution_id, reason, idempotency_key)` requer `mission.orchestrate`. `EXECUTOR_CANNOT_RETURN`: o coordenador deve fazer a devolução; `EXECUTION_NOT_FOUND`: confira a execução. Despache novamente apenas depois da correção apropriada.

## Executor

1. `get_my_mission_role(project_id)` e `list_my_tasks()` consultam o próprio papel e tarefas com o `agt_`; não exigem delegação de escrita. `PROJECT_NOT_FOUND`: confira o vínculo ativo e o projeto; `INVALID_STATE_FILTER`: use `open`, `all` ou um status válido.
2. `report_task_execution(task_id, status, summary, evidence, idempotency_key)` requer `mission.execution.report`. Use `reported`, `failed` ou `blocked`; `verified` é recusado pela própria ferramenta. `NOT_EXECUTOR`: relate somente a tarefa atribuída; `EVIDENCE_INVALID` ou `EVIDENCE_OUT_OF_SCOPE`: corrija a referência; `EXECUTION_CLOSED`: consulte a execução atual. `COMPLETION_NO_INDEPENDENT_REVIEW`: obtenha revisão independente; `COMPLETION_EVIDENCE_INVALID`: forneça evidência verificável; `COMPLETION_NOT_INTEGRATED`: aguarde integração do commit na `develop`. Relatar não conclui a tarefa.

## Revisor e verificador

O revisor recebe `request_task_review` e decide com a própria credencial pela rota de revisão, com `status` e parecer (`feedback`); não há ferramenta MCP de decisão de revisão neste recorte. O verificador registra P7 em `plan-verifications`, com `project_plan_id`, `sampled_item_ids` e `result`, usando `mission.plan.review`. `REVIEWER_IS_PLANNER`: escolha outro verificador; `SAMPLE_TOO_SMALL` ou `SAMPLE_ITEM_INVALID`: corrija a amostra; `APPLICATION_VERIFICATION_DISCREPANCIES`: resolva as divergências e verifique novamente. A revisão da própria execução é recusada: escolha outro revisor.

## Documentação

`attach_project_document(project_id, entity_type, entity_id, doc_path, idempotency_key)` exige vínculo ativo; BRIEF e dossiê exigem papel `documentation`. `DOC_PATH_NOT_ALLOWED`: use caminho relativo em `missions/<slug>/`, sem `..`; `DOC_FILE_NOT_FOUND`: crie o arquivo; `DOCUMENTATION_ROLE_REQUIRED`: use o agente de documentação; `ENTITY_NOT_IN_PROJECT`: confira a entidade. Para versionar o artefato, informe `register_artifact=true`; o conteúdo é identificado por sha256.

## Atos reservados ao Marcelo

Marcelo aprova a baseline, decide a transição `planning → ready`, aceita a missão e toma as decisões dos itens de revisão sinalizados. Use seu login de administrador, nunca token de agente.
