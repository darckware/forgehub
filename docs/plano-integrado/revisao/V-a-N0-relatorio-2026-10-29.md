# Validação V-a (roteiro V.1–V.15) e N.0 (navegador do Workspace) — 29–30/10/2026

Escopo: tarefas **V-a** e **N.0** de [07](../07-fases-de-implementacao.md) e [11](../11-navegador-dos-agentes.md),
executadas só na área de teste, com dados fictícios. Executor: Porthus (Claude Code). Verificador: Dartan.
Esta tarefa **só valida e relata**: nenhum código foi corrigido. Cada defeito traz a correção sugerida, para
virar tarefa no projeto "Validação do Service Factory".

## Ambiente e método

| Item | Valor |
|---|---|
| Código validado | worktree `v-a-validation`, branch `docs/v-a-n0-validation`, base `origin/develop` @ `f45c400` |
| Backend | `uvicorn app.main:app` do worktree, `ENVIRONMENT=test`, `127.0.0.1:8012` (confirmado em `/proc/<pid>/environ`), sem loops de fundo |
| Frontend | vite do worktree em `127.0.0.1:5182`, `VITE_API_URL=http://127.0.0.1:8012`, proxy `/api` → 8012 (config temporária, não versionada) |
| Banco | `forgehub_test_postgres` (127.0.0.1:5439), revisão `b9e4d2a7c615` no início. Durante a validação a M0.2a entrou no develop e o banco passou a `d3f7a1c9e2b5`; o backend `f45c400` não usa essa tabela, e nenhum `alembic` foi rodado por esta tarefa |
| Seed | estava **vazio** (0 usuários) no início; aplicado `python -m app.scripts.seed_test_database` (mescla por chave primária) |
| Integrações | só o stub `forgehub_test_stubs` (`127.0.0.1:8003`) |
| Tela | Playwright headless (`playwright-core` 1.64 + `/usr/bin/google-chrome`), porque a extensão MCP do Playwright não respondeu. Logins `admin.teste` e `operador.teste` |
| Prova | `V-a-N0-2026-10-29/evidencias-api.jsonl` (156 chamadas: passo, request, status, resposta resumida; sem token nem senha), capturas `.png` na mesma pasta, queries SQL citadas abaixo |

Todos os registros criados têm prefixo `VA` (produtos, projetos, tarefas 9077/9078/9129, pipeline, documento).

**Usuário extra:** a seed tem um só admin (`admin.teste`), e a separação de funções impede quem submete de
aprovar (ver V.2). Para exercer o gate, criei o admin fictício `aprovador.va` (e-mail `.test`) e o
**desativei** no fim.

## Resumo

| Passo | Resultado | Defeitos |
|---|---|---|
| V.1 Produto interno + versão | **Passou** | D-01 (doc) |
| V.2 Concepção → submeter → decidir | **Falhou** (o gate existe, mas é contornável) | D-02, D-03 |
| V.3 Mapa do Sistema | **Passou** | — |
| V.4 Autorizar planejamento | **Passou com ressalva** | D-02, D-04 |
| V.5 Planning items, tarefas, dependências | **Passou** | — |
| V.6 Despachar a um agente | **Passou com ressalvas** | D-05, D-06, D-07 |
| V.7 Aprovação de `project_task` | **Passou com ressalvas** | D-08, D-09 |
| V.8 Documento ↔ tarefa/fase | **Passou com ressalva** | D-10, D-06 |
| V.9 Fechar versão | **Falhou** | D-11, D-12 |
| V.10 Cockpit e Telemetria | **Passou com ressalvas** | D-11 (efeito), D-05 (efeito), D-13 |
| V.11 Ticket Darckware → projeto | **Não executável ainda** | L-01 |
| V.12 Celular 390 px | **Passou com ressalvas** | D-14 |
| V.13 Pipeline e Progresso governado | **Passou com ressalvas** | D-15, D-16 |
| V.14 Plano, baseline, CR, WBS | **Falhou parcialmente** | D-17, D-18, D-19 |
| V.15 "Gerar via IA" | **Parcial**: o modelo gera rascunhos; o caminho por IA não é executável no stub | L-02 |
| N.0 Navegador do Workspace | **Não executável** no teste (stub recusa); UI com defeito | D-20, L-03, D-21 |

Achados de ambiente: A-01 a A-03, no fim.

---

## V.1 — Produto interno e versão

**Feito:** `POST /api/v1/products` sem cliente; leitura das versões; tentativa de duplicar o nome; tentativa de
apagar a única versão; `GET /factory/cockpit`; captura da árvore no Cockpit (aba Telemetria).

**Prova:**
- `POST /products {"name":"VA Produto Interno Fictício"}` → 201, `darckware_client_id: null`, com versão `0.1.0 / planned` criada junto
- `POST /products` com `initial_version 1.0.0` → 201, versão 1.0.0
- mesmo nome → 409 `A product with this name already exists`
- `DELETE /products/versions/{única}` → 422 `Cannot delete the only remaining version of a product`
- cockpit: `('VA Produto Interno Fictício', 0 projetos, client None)`; captura `V1-cockpit-arvore.png` (produto sem selo de cliente, "Nenhum projeto ainda")

**Resultado: passou.**

**D-01 (documentação):** o `CLAUDE.md` diz que o Cockpit "carries the registration of both" (novo produto/novo
projeto). O `pages/cockpit/index.tsx` atual não tem nenhum botão de criação. Produto se cria pela Concepção
("+ Novo produto") ou por `/products` (escondida do menu). Também não há um rótulo "Interno" na árvore: só falta
o selo do cliente (isso é a B.3). **Correção:** atualizar o `CLAUDE.md`, ou recolocar as ações no Cockpit.

## V.2 — Concepção → submeter → decidir

**Feito:** `POST /conception/ideas` (produto "VA Ideia Fictícia Sigma"); submeter com o mapa vazio; submeter com
o mapa válido; decisão direta antiga; decisão governada como operador, como o próprio solicitante e como um
segundo admin; repetição idempotente.

**Prova:**
- `:submit` com o mapa vazio → 422 `System Map validation failed` (`empty_blueprint`)
- `:submit` com o mapa válido → 200, conceito `in_review`, pedido `d40302e4…` em `/governed/approval-requests` (`pending`)
- `POST /product-concepts/{id}:decide` → 409 `Direct decisions are disabled`
- `:decide` governado como `operador.teste` → 403 `Permission denied: governance.approval.decide`
- como `admin.teste` (o solicitante) → 403 `separation_of_duties_violation`
- como `aprovador.va` → 200; repetido com a mesma `idempotency_key` → 200 com a mesma decisão `096591b1…`
- conceito `approved`, revisão do mapa `approved`

**Resultado: falhou.** O gate de decisão funciona (permissão, separação de funções, idempotência), mas
**não protege nada**: antes de submeter e de aprovar, `POST :authorize-delivery-planning` sobre o conceito
**ainda em `draft`** respondeu 200 e criou a versão 1.0.0, o projeto "VA Sigma Web", 1 item de escopo e a tarefa 9009.

**D-02 (gate da concepção contornável):** `backend/app/api/routes/system_scope.py:1189-1197`
(`authorize_delivery_planning`). Três verificações foram removidas no commit `c664761` (31/08, "enable project
creation ... in Step 5"): `concept.status != "approved"`, `revision.status != "approved"` e
`approved_concept_request(db, concept, target_hash)`. A rota ao lado, `create_project_scope` (`:1395`), ainda
exige mapa aprovado, então o comportamento está incoerente.
**Correção:** restaurar as três verificações (409) e cobrir com teste. Se a etapa 5 da tela precisa criar
projeto sem aprovação, isso pede decisão explícita do Marcelo e um caminho próprio, rastreado como exceção.

**D-03 (seed sem aprovador):** a seed T.2 tem um admin e um operador sem `governance.approval.decide`.
Nenhum gate governado se fecha só com a seed. **Correção:** acrescentar um segundo admin fictício (ou dar ao
operador uma delegação de teste) em `app/scripts/seed_test_database.py`.

## V.3 — Mapa do Sistema

**Feito:** 9 elementos, um de cada família; um elemento com família e tipo trocados; um ciclo `precedes`;
validação; remoção do ciclo; nova validação.

**Prova:**
- `business/table` → 422 `table does not belong to business`, recusado já na escrita
- dois `precedes` opostos → `:validate` 200 `{"valid": false, "issues": [{"code": "cyclic_precedes"}]}`
- mapa vazio → `empty_blueprint` + 9 avisos `uncovered_family`
- sem o ciclo → `{"valid": true, "issues": []}`

**Resultado: passou.**

## V.4 — Autorizar planejamento da entrega

**Feito:** `:authorize-delivery-planning` versão 1.0.0 com `web_app` e `api_service`, ambos com
`responsible_agent_id` = Vega Teste, depois da aprovação.

**Prova** (SQL em `company.projects`/`project_agent_memberships`/`project_tasks`/`task_assignments`):

| Projeto | Membro | Tarefas | Atribuídas |
|---|---|---|---|
| VA Sigma API | `developer` Vega Teste | 9010–9012 | Vega Teste, com `membership_id` |
| VA Sigma Web | — | 9009 | nenhuma |

**Resultado: passou com ressalva.** Na chamada nova o projeto, o membro e as tarefas saem com responsável. O
projeto Web tinha sido criado antes, sem responsável (pelo D-02).

**D-04:** reautorizar um projeto que já existe ignora `responsible_agent_id`: não cria membro nem atribuição,
e a resposta diz `tasks_created: 0` sem aviso. Fica em `system_scope.py:1270-1300`, no ramo idempotente por
`(version, solution_type)`. **Correção:** no reuso, criar o membro e atribuir as tarefas sem responsável, ou
recusar com 409 explicando.

## V.5 — Planejamento: itens, tarefas e dependências

**Prova:**
- `POST /planning-items` → 201; tarefas A (9077) e B (9078), ambas atribuídas a Vega Teste
- dependência B→A → 201; A→B → 409 `This dependency would create a cycle between tasks`
- `POST /tasks/{B}/dispatch` → **409** `Task has unfinished dependencies...` com `blocking: [{task_number: 9077, status: "assigned"}]`

**Resultado: passou.**

## V.6 — Despachar a um agente

**Feito:** despacho de A. O stub simula o runner e devolve `STATUS: DONE` na hora. A finalização foi
disparada por `GET /demands/{id}/dispatch-status`, o mesmo caminho do painel de leitura. Não rodei
`run_dispatch_completion_pass`, porque ele varre todas as mensagens do banco compartilhado.

**Prova:**
- 1ª tentativa (com o token errado, ver A-01) → 409 `Agent runner rejected the request...`; mensagem #349 `failed`
- 2ª tentativa → 200; mensagem #353, `channel: factory`, `working_path` = pasta fictícia do projeto, `agent_run_id ee79fd62…`
- `dispatch-status` → `completed`; `dispatch_result` termina em `STATUS: DONE`; execução 2 → **`reported`**
- o stub não devolve linha `EVIDENCE:`, então declarei `evidence_ref = db:project:<id>` (PATCH) e rodei a verificação **só dessa execução** (`scratchpad/va/verify_one.py`, mesmo código de `run_evidence_verification_pass`, filtrado pelo id) → **`verified`**
- auditoria: um único `execution_auto_verified` (`a980b513…`) nos últimos 5 minutos
- stub: `agent_run.start claude stubbed test` e `agent_run.get stubbed`

**Resultado: passou com ressalvas.** O fluxo mensagem → execução → `STATUS: DONE` → `reported` → evidência
verificada funciona. Com o stub, porém, a evidência precisa ser declarada à mão.

**D-05 (execução órfã):** quando o runner recusa o despacho, a `TaskExecution` criada em
`backend/app/api/routes/task.py:1084` fica em **`running` para sempre**: a tentativa 1 da tarefa 9077 aparece "Em
execução" na tela (`V8-tarefa-docs.png`) e conta como "em andamento" na telemetria. No `except
AgentRunDispatchError` (`task.py:1131-1132`) só se levanta o 409, e `_fail_dispatch` (`demand.py:1682`) não
toca na execução ligada. **Correção:** ao falhar o despacho, marcar a execução `failed` com `finished_at` e o
motivo (em `_fail_dispatch` quando houver `task_execution_id`, que cobre os outros caminhos também), com teste.

**D-06 (tela de tarefa):** o card "Execuções da tarefa" (`frontend/src/pages/task/[id].tsx:397-399`) lê
`task.executions`, mas `GET /tasks/{id}` não devolve esse campo. O card sempre diz "Nenhuma execução
registrada", enquanto o bloco de cima mostra as tentativas 1 e 2. **Correção:** usar o hook
`useTaskExecutions` (`hooks/useTask.ts:329`).

**D-07 (observação, não é falha no teste):** todo despacho independente (`from_agent="forgehub"`) chama
`_send_notice` (`demand.py:1464`) → `/v1/messages/send` com `target: "telegram"`. No teste o stub registrou 2
`message.send.telegram stubbed` (A e C) e nada saiu. Em produção, cada tarefa despachada avisa no Telegram. É
para confirmar com o Marcelo que esse aviso é desejado, tendo em vista a I.13 (silêncio noturno).

## V.7 — Aprovação de `project_task`

**Prova:**
- caso de falha: Approval para B (ainda bloqueada por A), aprovada por `aprovador.va` → 200 `approved`; B continua `assigned`; notificação `warning`, `event_key approval-dispatch-failed:76eee830…`, "Dispatch it manually once resolved"
- caso de sucesso: tarefa C (9129, Lyra Teste) aprovada → C `in_progress`, execução `running` → `dispatch-status` `completed` (mensagem `d4d14945…`)
- `operador.teste` decidindo → 403

**Resultado: passou com ressalvas.**

**D-08 (Approval antiga sem separação de funções):** `admin.teste` criou e **aprovou a própria** Approval
(tarefa D) → 200, e a aprovação dispara despacho automático. O caminho governado recusaria isso
(`separation_of_duties_violation`), mas `POST /governance/approvals/{id}/approve` (`governance.py:116-131`,
`_decide_approval`) não confere quem pediu. **Correção:** recusar a decisão quando
`principal == approval.requested_by` (ou passar `project_task` pelo `governed_approval`), com teste.

**D-09 (cosmético):** o título da notificação inclui o `dict` Python cru do 409 (`governance.py:191`, `{exc.detail}`).
**Correção:** formatar `message` + números das tarefas que bloqueiam.

## V.8 — Documento ligado à tarefa e à fase

**Feito:** documento fictício `concepts/va-ideia-fict-cia-sigma/VA-V8-documento.md` (escrito pela rota de
documentos da concepção) ligado à tarefa A, ao pipeline do projeto e ao planning item.

**Prova:**
- 3 × `POST /docs/links` → 201; duplicado → 409; arquivo inexistente → 404; `../../etc/passwd` → 400 `Invalid path`
- lado do documento: `GET /docs/links?path=…` → `[pipeline, planning_item, task]` com rótulos
- lado da entidade: `GET /docs/links/by-entity?entity_type=task…` → o documento
- tela: `V8-tarefa-docs.png` ("Documentos de Contexto (1)") e `V8-planning-docs.png`

**Resultado: passou com ressalva.**

**D-10:** não existe ligação a **fase/estágio**. `DOC_LINK_ENTITY_TYPES` (`db/models/doc_link.py:16-24`) não tem
`pipeline_stage` (422 ao tentar). Liguei ao pipeline inteiro. O card da tarefa também diz "vinculados como
contexto para **este projeto**". **Correção:** acrescentar `pipeline_stage` (migration do CHECK e
`_ENTITY_LABEL_SOURCE`) e ajustar o texto por tipo de entidade. Isso também é pré-requisito da D.2.

## V.9 — Fechar versão

**Prova:**
- `POST /products/versions/{1.0.0}:publish` → **409** `This version has unfinished tasks...`, com 8 tarefas bloqueando (correto)
- `PUT /products/versions/{1.0.0} {"status":"published"}` → **200 `published`**, com as 8 tarefas abertas
- depois de publicada: `PUT /planning-items/{id}` → 409 `planning is locked`; `POST .../screens` → 409 `scope/screens/planning are locked`; `PUT` na versão → 422
- **mas** `POST /planning-items` → 201 e `POST /tasks` → 201 (tarefa 9245) no projeto da versão publicada

**Resultado: falhou.**

**D-11 (publicação contornável):** `update_product_version` (`backend/app/api/routes/product.py:630-650`) aceita
`status="published"`. O `CLAUDE.md` diz que publicar é uma ação dedicada e não um PUT. A versão de teste ficou
publicada com tarefas abertas, e isso é irreversível (o PUT recusa mudar uma versão publicada). **Correção:**
no PUT, recusar `status == "published"` (422 "use :publish").

**D-12 (trava incompleta):** a trava `_assert_version_editable` cobre a edição de planning item e de tela, mas
não `create_planning_item` (`backlog.py:81`) nem `create_task` (`task.py:311`), e provavelmente nem atribuição
ou dependência. **Correção:** aplicar a mesma checagem nas criações do projeto da versão publicada, com teste
por rota.

## V.10 — Cockpit e Telemetria

**Prova** (`GET /factory/cockpit`, `GET /factory/agent-telemetry`, após `actual_cost = 1.25` na execução verificada):
- VA Sigma API: concepção `approved`, designer `in_progress` ("map: approved / scope: draft"), planejamento 5 itens, execução 0/8, `total_cost 1.25`, `team_size 1`, pipeline "VA Pipeline Sigma API"
- VA Sigma Web: `total_cost 0.0`, `team_size 0` (consequência do D-02/D-04)
- Vega Teste: 2 execuções (1 com sucesso, 1 "other" = a órfã do D-05), `total_cost 1.25`, `dispatch_total 3`, `dispatch_success_rate 0.5`; Lyra Teste: 1 execução e 1 despacho
- agentes sem execução não aparecem (correto)

**Resultado: passou com ressalvas.** O custo por projeto e por agente bate com o que foi gravado.

- A fase "quality" aparece **`approved` / `published`** com 8 tarefas abertas. É efeito do D-11; o Cockpit
  apenas reflete o estado.
- **D-13:** `dispatch_total` conta a mensagem #350 "Checagem de #349", criada automaticamente na falha e nunca
  despachada. **Correção:** contar só linhas com `dispatch_status` preenchido (`factory.py`, agregação de
  `AgentDemand`).

## V.11 — Ticket Darckware → "Criar projeto"

**Prova:**
- `GET /client-ops/work-items` → `{"items": [], "total": 0}`
- `POST /client-ops/work-items/ticket/<uuid fictício>:create-project` → 404 `darckware_rejected: not found in the test stub`
- `GET /client-ops/clients` → os 2 clientes fictícios

**Resultado: não executável ainda.**

**L-01:** o stub (`app/tests/fixtures/integration_stub.py:333-420`) simula clientes e e-mails, mas não tem
tickets nem demandas. Qualquer `GET` com id devolve 404. **Correção (T.3/T.5):** incluir no stub um ticket e uma
demanda fixos, ligados ao "Cliente Fictício Alfa", e aceitar `PATCH`/nota de status para eles. Só então rodar
V.11, incluindo a idempotência (2º `create-project` → 409).

## V.12 — Celular (390 px)

**Feito:** 8 telas a 390×844 (mobile, toque) e 1440: Cockpit, Concepção, Mapa do Sistema, Backlog, Tarefas, Detalhe da
tarefa, Projeto, Governança. Medida: `scrollWidth` contra `clientWidth`.

**Prova:** todas `scrollWidth = clientWidth = 390`, sem rolagem lateral (capturas `V12-390-*.png`). Nenhuma
requisição saiu de `127.0.0.1`.

**Resultado: passou com ressalvas.**

**D-14 (cosmético):** no Cockpit, os três filtros (cliente, produto, projeto) ficam numa linha e cortam os
rótulos ("Todos os c…", "Todos os P…"). No detalhe da tarefa, o selo "Em Andamento" encosta na borda direita.
**Correção:** `max-md:flex-col` / `grid-cols-1` nos filtros (`pages/cockpit/index.tsx`) e `flex-wrap` no
cabeçalho da tarefa.

## V.13 — Pipeline do projeto e Progresso governado

**Feito:** pipeline com o estágio "Especificação" (artefato obrigatório `spec_document` + gate de aprovação) e
"Implementação" dependente dele.

**Prova:**
- `PATCH stage {status: completed}` → 409 `Use POST /api/v1/pipeline-stages/{id}:evaluate-completion and :complete`
- avançar "Implementação" → 409 `dependency stage 'Especificação' has not completed`
- `:evaluate-completion` → `not_ready` (artefato e gate pendentes)
- `PATCH required-artifact {is_fulfilled: true}` **sem `artifact_id`** → 200, mas a avaliação continua `not_ready` (correto: exige `artifact_id`)
- gate aprovado **pelo operador** com `approved_by: "qualquer-nome"` → 200
- artefato **de outro tipo** (`test_report`, sem ligação ao estágio) ligado ao requisito `spec_document` → `ready` → `:complete` → 200 `completed` com checkpoint; depois disso "Implementação" avança

**Resultado: passou com ressalvas.** O estágio não conclui sem artefato. Pela pergunta do roteiro, o
**Progresso não é redundante:** desde o PATCH recusado, ele é o único caminho de conclusão. A R.3 deve
oficializar isso (fundir as telas), não aposentar o Progresso.

**D-15 (gate sem identidade):** `PATCH /pipelines/gates/{id}` (`pipeline.py:819-820`, `update_stage_gate`) aceita qualquer
usuário com acesso de escrita e grava `approved_by` como texto livre, sem principal e sem separação de funções.
**Correção:** exigir `governance.approval.decide`, gravar o principal autenticado e auditar.

**D-16 (artefato sem validação):** `update_stage_required_artifact` (`pipeline.py:761-774`) aceita qualquer
`artifact_id`, sem conferir `artifact_type`, a ligação ao estágio/projeto nem o estado (o artefato estava `draft`).
**Correção:** validar o tipo e o projeto, e exigir uma versão aprovada/final quando o requisito for obrigatório.

## V.14 — Plano, baseline, change request e WBS

**Prova:** (projeto "VA Projeto Plano", no produto interno)
- baseline de plano em `draft` → 422 `Only an approved plan can be baselined`
- plano aprovado → baseline 201 com `scope/cost/end_date` congelados
- `PATCH` no plano depois da baseline → 422 `register a ChangeRequest instead` (**congela, correto**)
- CR sem nenhuma marca de impacto → 422
- CR `affects_scope + adds_features`, `cost_delta 20` → 201 `pending`
- **`operador.teste`** `PATCH {status: approved}` → 200 `approved`
- `PATCH {status: applied}` → 200 `applied`; plano e baseline **inalterados** (`scope_summary "Escopo A"`, custo 100)
- WBS: Módulo → Componente (filho); depois `PATCH` Módulo com `parent = Componente` → 200, gerando **ciclo** na árvore

**Resultado: falhou parcialmente.** A baseline congela, mas o change request não altera nada com aprovação.

- **D-17:** `update_change_request` (`backend/app/api/routes/project.py:514-571`) muda `status` sem permissão de
  decisão nem separação de funções, aceita `applied` direto de `pending` e, ao aprovar ou aplicar, não cria a
  nova versão do plano nem a baseline. **Correção:** uma ação `:decide` governada (aprovar/rejeitar) e uma
  `:apply` que gera o plano revisado + nova baseline com os deltas; máquina de estados
  `pending → approved|rejected → applied`.
- **D-18:** `update_structure_node` (`project.py:641`) aceita um `parent_node_id` que cria ciclo. **Correção:**
  subir pelos ancestrais antes de gravar (409).
- **D-19:** mudar o `status` de um CR não deixa `AuditEvent` (não encontrei gravação no handler). **Correção:**
  auditar a decisão junto com a D-17.

## V.15 — "Gerar via IA" nas fases

**Prova:**
- `POST /ai-draft/stream` (`target_kind: concept`) para Orion (hermes) e para Vega (claude) → SSE `event: error` `forgehub test stub: host-bridge /v1/chat is not simulated`, seguido de `event: done`; nada gravado. O stub registrou `chat refused test` 2×.
- `POST /product-concepts/{id}:generate-artifacts` → 4 artefatos (PRD, SPEC-TECNOLOGIA, SCREEN-TEMPLATES, DESIGN-SYSTEM), todos `draft`, `requires_approval: true`, versão 1 `draft`

**Resultado: parcial.** A geração por modelo cria rascunhos que exigem aprovação (nunca são aplicados direto),
e a rota de rascunho por IA não grava nada. O caminho por IA de verdade **não é executável** no teste.

**L-02:** o stub não simula `/v1/chat`. **Correção (T.3):** um `/v1/chat` simulado com resposta fixa (JSON do
`target_kind`), sem rodar agente. Depois, validar que a tela mostra o rascunho e só aplica pelo botão do domínio.

---

## N.0 — Navegador atual do Workspace

| Item | Feito | Prova | Resultado |
|---|---|---|---|
| Ligar | `POST /workspace-browser/start {url: http://127.0.0.1:4174/}` | 502 `host-bridge /v1/workspace-browser/start is not simulated` | Não executável |
| Estado | `GET /workspace-browser/state` | 502, idem | Não executável |
| Navegar | `POST /workspace-browser/navigate` | 502, idem | Não executável |
| Uma rotina | app avulso "VA App de teste" (201) + rotina com 2 passos (201) → `:run` | 502 `run-routine is not simulated`; **nenhum registro de execução** | Não executável; ver D-21 |
| Teste em segundo plano | `PUT .../background-test {enabled: true}` (200), `:run-background`, e `POST /background-test` (ad hoc) | 200/201 com `WebAutomationTestRun` `status: error` e o motivo em `error`; `GET /test-runs` lista os dois | O registro funciona; o teste não roda |
| Tela | Workspace → "Abrir navegador interno" (`N0-workspace-navegador.png`) | Fica em "Iniciando navegador compartilhado…" para sempre; rodapé `Request to /api/v1/workspace-browser/state failed with status 502` | Falhou (D-20) |

**L-03 (por que não executável):** o navegador é um Chromium no host, servido pelo host-bridge de produção
(CDP 9223). Por regra, o ambiente de teste não alcança o bridge, e o stub recusa `/v1/workspace-browser/*`. Para
validar de verdade, é preciso um navegador **de teste** (o "modo TESTE" do doc 11 §2.1): um Chromium em contêiner
na `forgehub_test_network`, atrás do stub ou de um bridge de teste, alcançando só `forgehub_test_frontend`.
Essa é a primeira tarefa da Fase N.

**D-20 (laço de reinício na tela):** com o `/start` falhando, o `useEffect` de
`frontend/src/components/WebAppPane.tsx:158-163` chama `start.mutate` de novo a cada renderização (a identidade
de `start` e de `state` muda a cada falha). **Medido: 240 `POST /start` em cerca de 11 s** por aba aberta (468
`workspace-browser/start` no log do stub, nas duas capturas). Em produção, com o bridge fora, isso martela o
bridge. **Correção:** não repetir com `start.isError`; tentar de novo só por ação do usuário ou com backoff, e
mostrar o erro no lugar do spinner.

**D-21 (rotina visível sem histórico):** uma falha de `:run` (modo visível) responde 502 e não grava
`WebAutomationTestRun`, enquanto o modo de segundo plano grava. O comentário da rota (`workspace_browser.py`,
seção "Background app testing") promete histórico unificado. **Correção:** registrar também o desfecho do
modo visível.

**Observação para a Fase N:** a rotina aceitou `url` `http://127.0.0.1:4174/...` sem nenhuma lista de domínios.
Isso é esperado no modo teste, mas o modo internet (doc 11 §2.3) vai precisar da allowlist por tarefa.

---

## Achados de ambiente (área de teste)

- **A-01 (tokens do worktree):** `test-env/init-env.sh` no worktree gera `CHAT_BRIDGE_TOKEN`,
  `DARCKWARE_*`, `FORGEROUTER_TEST_API_KEY`, `JWT_SECRET` e afins **novos**. Os contêineres de teste e o stub
  em execução usam os do checkout principal, então o backend do worktree recebe 401 do stub
  (`auth=rejected`), e o primeiro despacho falhou como "Agent runner rejected" (#349). Corrigi copiando essas 7
  chaves do `test-env/.env.test` do checkout, sem exibir valores. **Correção:** documentar no `CLAUDE.md` (e
  nas regras comuns dos agentes) que um worktree deve reaproveitar o `.env.test` do checkout, ou fazer o
  `init-env.sh` aceitar um `.env.test` de referência.
- **A-02 (proxy do vite aponta para a produção):** `frontend/vite.config.ts` tem o proxy `/api` fixo em
  `http://127.0.0.1:8000`, o **backend de produção**. O `dev.sh` só sobrescreve `VITE_API_URL`. Qualquer chamada
  same-origin que não passe por `lib/api.ts` (há `location.origin` em `TerminalPane`, `ChatPane`, `useChat`,
  `useChannel`, `useAgentActivityStreamViewModel`, `useAiDraft`, entre outros) iria para a produção a partir de
  um vite "de teste". Nesta validação usei uma config temporária com o proxy em 8012. **Correção:** o proxy deve
  ler `VITE_API_URL` (ou uma variável própria), com default na porta do `dev.sh` e nunca na 8000.
- **A-03:** o banco de teste estava sem seed no início (alguém resetou sem `--seed`). O primeiro `vite` desta
  validação reotimizou o cache compartilhado `frontend/node_modules/.vite` do checkout principal, antes de eu
  mover o cache para o scratchpad; é só cache e não tem efeito funcional. As rotas de documentos escrevem em
  `/docs` do host (diretório avulso, o mesmo que o pytest no host usa); o único arquivo novo é
  `/docs/concepts/va-ideia-fict-cia-sigma/` (documento V.8 + os 4 artefatos do V.15).

## Prova de produção intacta

- **Nenhuma conexão à 5433.** Um monitor (`scratchpad/va-netmon.sh`) amostrou, a cada 2 s, das 02:35 às 07:38
  UTC, `ss -tnp state connected '( dport = :5433 )'` para **todos** os processos do host:
  `va-net5433.log` ficou **vazio (0 linhas)**. No mesmo intervalo, o contador paralelo de conexões à 5439
  registrou conexões ativas (1 a 14) em 978 das 8.264 amostras, o que mostra que o monitor capturava tráfego. No fim, as
  conexões estabelecidas do PID do backend eram só `127.0.0.1:5439` (5).
- O backend foi iniciado com `ENVIRONMENT=test` (lido em `/proc/<pid>/environ`), o que aciona o guard
  `UnsafeDatabaseTargetError` antes de criar o engine. Nenhum `alembic` foi rodado. Não usei `.env`, os
  contêineres `forgehub-backend`/`forgehub-frontend`, o host-bridge real, `docker compose` nem `reset.sh`.

## Prova de nenhum envio externo

- `GET http://127.0.0.1:8003/_stub/calls?since=2026-10-30T02:31:48Z` → **594 chamadas, todas para o stub**
  (resumo em `V-a-N0-2026-10-29/stub-resumo.txt`). Os envios foram 2 `message.send.telegram` com desfecho
  `stubbed` (nada é enviado) e 2 `messages/send` com `auth=rejected` (token antigo, A-01). Não houve e-mail
  (`email.queue` ausente). O Darckware recebeu só leituras (`get.clients`, `get.tickets`, `get.demands`), e a
  ForgeRouter, nenhuma chamada. O stub é compartilhado, então parte das 594 vem de testes de outros agentes no
  mesmo intervalo, mas todas pararam no stub.
- Navegador: em todas as execuções de captura, a lista de requisições fora de `127.0.0.1`/`localhost` ficou
  **vazia** (`externalRequests: []`).
- Nenhuma mensagem foi enviada pelo Messages a agente real: as mensagens #349, #350, #353 e a da tarefa C
  existem só no banco de teste, e os agentes são os fictícios da seed.

## O que não foi verificado

- V.11 e o caminho por IA da V.15 (falta simulação no stub: L-01, L-02); o navegador em execução real (L-03).
- O fluxo "PARTIAL/BLOCKED → failed" do despacho, porque o stub só devolve `DONE`.
- A suíte de testes não foi rodada: esta tarefa só valida, sem mudar código.
- O Dartan revisa o relatório.

## Limpeza

Backend 8012, vite 5182 e o monitor foram encerrados (só os PIDs iniciados aqui). Os arquivos temporários do
worktree (`vite.va.config.ts`, link `node_modules`) foram removidos. As linhas `VA*` ficam no banco de teste como
evidência. `aprovador.va` foi desativado. A versão 1.0.0 de "VA Ideia Fictícia Sigma" ficou publicada pelo D-11,
e isso é irreversível pela API.
