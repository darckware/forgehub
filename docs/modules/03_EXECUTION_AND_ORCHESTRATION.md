# Módulo 03 — Execução e Orquestração via CLI

## Status de implementação

- Baseline funcional: **implementada**.
- Tasks: `RUN-01` a `RUN-10`, **completed**.
- Execution Release: `ER-RUN-01`, **liberada pelo usuário e implementada em 2026-07-13**.
- Escopo de interface: componentes de Execution, Task e Pipeline dentro do grupo **Planning**.
- Dependências externas propostas: backend de orquestração e `host-bridge`/adapters Claude, Codex e Agy. Nenhum processo CLI pode ser iniciado por consequência apenas desta documentação.

## 1. Objetivo

Consumir somente Tasks `ready`, selecionar um responsável/produtor e um runtime elegível, emitir Work Package, executar Claude/Codex/Agy de forma durável, coletar evidência e encaminhar o resultado para revisão independente.

```text
ExecutionWave active + Task ready
  -> scheduler
  -> Assignment
  -> WorkPackage revision
  -> lease
  -> claude | codex | agy
  -> Result + evidence
  -> deterministic verification
  -> reviewer
  -> verified ou nova execução
```

## 2. Identidade versus runtime

- Agent/SubAgent: responsável lógico, skills, credencial, custo e histórico.
- ProjectMembership: autorização no Project.
- TaskAssignment: responsabilidade concreta.
- RuntimeProfile: CLI/modelo/routing/capabilities/budget.
- CLI adapter: processo executável no host.
- TaskExecution: tentativa real e imutável.

Nunca usar `Agent = Claude/Codex/Agy`. O mesmo Agent pode possuir profiles de CLIs diferentes; a execução registra qual foi usada.

## 3. Runtimes

Valores-alvo: `claude|codex|agy`. Entrada legada `antigravity` é normalizada para `agy` na API e migrada no banco quando seguro.

### Adapter registry definido em código/config protegida

| Runtime | Executable | Capabilities mínimas |
|---|---|---|
| claude | adapter Claude CLI | non-interactive prompt, workspace, result capture |
| codex | adapter Codex CLI | non-interactive task, workspace, result capture |
| agy | adapter Agy CLI | non-interactive task, workspace, result capture |

O banco armazena profile e parâmetros permitidos, nunca executable/argv arbitrário. Adapter valida versão mínima e health antes de ficar elegível.

## 4. Entidades-alvo

### Runtime profile

Ampliar profile com `adapter_version`, `capabilities`, `min_cli_version`, `context_limit`, `supports_resume`, mantendo model/routing/budget.

### `execution_work_packages`

`id`, `task_id`, `assignment_id`, `execution_wave_id`, `baseline_id`, `revision`, `contract_version`, `payload`, `payload_hash`, `idempotency_key`, `status`, `issued_at`, `expires_at`.

- status `draft|validated|issued|superseded|expired|cancelled`.
- payload imutável após `issued`.

### `execution_leases`

`id`, `work_package_id`, `runner_id`, `status`, `leased_at`, `expires_at`, `heartbeat_at`, `released_at`.

- status `claimed|running|expired|released|cancelled`.
- um lease ativo por WorkPackage/Task salvo policy paralela explícita.

### TaskExecution

Alvo: assignment/work package obrigatórios para dispatch automatizado, unique `(task_id, attempt_number)`, runtime, adapter/session/PID refs, start/finish, exit code, result status, cost/usage, summary e evidence manifest.

Execution status: `pending|running|completed|verified|failed|blocked|cancelled|stale`.

### `execution_events`

Append-only: `execution_id`, sequence, event_type, occurred_at, payload, idempotency_key`. Tipos: claimed, started, heartbeat, progress, output, completed, failed, blocked, cancelled, reconciled.

### `execution_results`

`execution_id` unique, `contract_version`, `result_payload`, `result_hash`, `received_at`, `is_stale`, `validation_errors`.

## 5. Scheduler

Input: Tasks ready de waves ativas. Filtros obrigatórios:

1. mesma baseline/Project/Stage;
2. dependências satisfeitas;
3. membership ativa e papel permitido;
4. skills/proficiência;
5. track/stage/module/path/risk authorization;
6. runtime permitido e adapter saudável;
7. capacidade/WIP/budget;
8. separation of duties;
9. locks/conflitos;
10. auto-dispatch permitido pela Policy/delegação.

Ranking posterior: skill affinity, carga, continuidade, custo e histórico. Ranking nunca contorna filtros.

## 6. Commands

| Command | Resultado |
|---|---|
| `ComputeEligibleExecutors` | candidatos + reasons excluídos |
| `AssignTask` | Assignment ativa e Task assigned |
| `BuildWorkPackage` | draft com snapshot/revisions |
| `ValidateWorkPackage` | preflight persistido |
| `IssueWorkPackage` | package imutável/validated |
| `ClaimExecutionLease` | lease + Execution pending/running |
| `RecordExecutionEvent` | evento idempotente/heartbeat |
| `SubmitExecutionResult` | result validado, Execution completed/failed/blocked |
| `MarkResultStale` | preserva result sem aplicá-lo |
| `CancelExecution` | cancel request + adapter termination workflow |
| `ReconcileRunner` | compara banco/PID/CLI e recupera estado |
| `RequestRework` | feedback + nova attempt/package; Task volta ao trabalho |

## 7. Runner durável

- Runner possui identidade/heartbeat persistidos.
- Busca leases emitíveis ou recebe dispatch por fila.
- Canonicaliza workspace e aplica allowed/denied paths.
- Materializa WorkPackage em diretório temporário seguro.
- Inicia adapter com argv fixo e ambiente sanitizado.
- Persiste PID/session antes de considerar running.
- Faz stream truncado/segmentado de output; conteúdo completo vai para evidence storage quando permitido.
- Captura exit code/result; publica via outbox idempotente.
- No restart, reconcilia leases running com processos/sessões.

## 8. Resultado obrigatório

```yaml
contract_version: forge-engineering-result/v1
work_package_id: <uuid>
execution_id: <uuid>
status: completed | failed | blocked
summary: <text>
changed_files: []
artifacts: [{path, type, hash}]
verification: [{command_id, status, exit_code, evidence_ref}]
decisions_proposed: []
scope_impacts_discovered: []
residual_risks: []
follow_up_items: []
```

Descoberta de impacto não autoriza ampliar escopo; gera bloqueio/proposta de Planning Item ou Change Request.

## 9. Producer/reviewer

- Reviewer é outra membership quando Policy exigir.
- Reviewer recebe package/result/diff/evidence, não contexto conversacional privado do produtor.
- Feedback é estruturado por critério/scope item.
- Aprovado muda Execution `completed -> verified`.
- Changes requested cria nova execução; não reabre a anterior.
- Max iteration/budget encerra auto-loop e escala.

## 10. APIs-alvo

- `GET /api/v1/tasks/{id}/eligible-executors`
- `POST /api/v1/tasks/{id}:assign`
- `POST /api/v1/tasks/{id}/work-packages`
- `POST /api/v1/work-packages/{id}:validate|:issue|:cancel`
- `POST /api/v1/work-packages/{id}:claim`
- `POST /api/v1/executions/{id}/events`
- `POST /api/v1/executions/{id}/result`
- `POST /api/v1/executions/{id}:cancel|:reconcile|:request-rework`
- `GET /api/v1/runners` e health/capabilities.

## 11. Interface

- Task readiness/assignment/runtime card.
- Work Package viewer com revisions e constraints.
- Live execution timeline/output seguro.
- Cancellation/reconciliation controls.
- Result/evidence/review compare.
- Loop iteration, cost and limits.

## 12. Segurança

- sem shell command livre;
- executable/argv permitidos pelo adapter;
- workspace/path traversal bloqueados;
- secrets write-only via ambiente protegido;
- output redaction e size limits;
- tool/network capabilities explícitas;
- subprocess com usuário/limites adequados;
- aprovação para ação destrutiva/externa conforme Policy.

## 13. Critérios de aceite

1. Somente Task ready de wave ativa pode gerar package.
2. Claude, Codex e Agy executam o mesmo contrato e resultado.
3. Runtime inválido/indisponível torna candidato inelegível.
4. Nenhum payload controla executable shell arbitrário.
5. Retry não duplica Execution/Event/Result.
6. Runner reiniciado reconcilia execução sem inventar sucesso/falha.
7. Result de revision antiga fica stale.
8. Reviewer distinto e limites de loop são aplicados.
9. Outra CLI pode retomar nova tentativa usando artifacts/handoff persistidos.
10. Usuário pode pausar/cancelar e agente pode gerir dentro de delegação.

## 14. Diagnóstico do estado atual

O ForgeHub já possui um protótipo de ponta a ponta que cria `TaskExecution`, chama
`POST /v1/agent-runs` no host bridge e permite atualizar a execução e despachar
review. Ele deve ser tratado como compatibilidade transitória, não como a
implementação deste módulo, porque:

- aceita dispatch sem `ExecutionWave` ativa e sem Task `ready` rastreada à baseline;
- monta um prompt diretamente da Task, sem Work Package versionado, hash ou preflight;
- mantém processo, status e output somente na memória do `host-bridge`;
- perde a capacidade de consultar/reconciliar runs depois de reinício do bridge;
- não possui lease, heartbeat, eventos duráveis, outbox nem result contract validado;
- envia credencial ao bridge a cada dispatch e ainda usa `antigravity` como valor persistido;
- depende de refresh manual e pode concluir a execução apenas pelo exit code;
- não conecta PID/heartbeat aos checkpoints entregues por `ER-SCR-01`;
- a interface permite o botão de dispatch sem mostrar uma liberação executável vigente.

A migração deve preservar `TaskExecution` e reviews existentes. Runs legadas sem
Work Package ficam identificadas como `legacy`, continuam auditáveis e não podem
ser convertidas retroativamente em execução governada.

## 15. Recorte proposto para `ER-RUN-01`

### Dentro do Planning

- tela **Execution Release** para criar, validar, aprovar, ativar, pausar e concluir waves;
- elegibilidade determinística por Task, com motivos de bloqueio;
- viewer imutável do Work Package e suas revisões;
- timeline de processo, heartbeat, checkpoints, logs redigidos e resultado;
- controles de dispatch, pause/cancel, reconcile, retry e review;
- integração com Task, Pipeline/Stage e Project Progress já existentes.

Não será criado novo grupo na sidebar. A entrada pertence a **Planning >
Execution** e os detalhes podem ser reutilizados nas telas de Task e Pipeline.

### Dependências externas necessárias

| Componente | Motivo | Limite da alteração |
|---|---|---|
| `host-bridge/app.py` | processo real vive no host | endpoints internos fixos de claim/start/heartbeat/result/cancel/reconcile; sem shell arbitrário |
| adapters Claude/Codex/Agy | padronizar argv, health e resultado | registry em código/config protegida; payload nunca define executable |
| identidade/RBAC | distinguir usuário, Athos e runner | novas actions apenas para wave, dispatch, cancel/reconcile e leitura de output |
| Governance/Policy | aplicar autoridade, risco, WIP e separação | avaliação requerida pelos commands; sem implementar o Policy Engine geral |
| Notifications/Audit | avisar falha, stale, pausa e escalonamento | eventos best effort e AuditEvent; falha de notificação não altera o estado principal |
| secrets/runtime config | injetar credencial sem persistir em payload/log | referência protegida e ambiente sanitizado; segredo nunca integra Work Package/Event |

Essas alterações externas são parte necessária e inseparável de
`ER-RUN-01`; não autorizam mudanças funcionais em outros grupos da sidebar.

## 16. Plano executável — Tasks `planned`

| Task | Entrega | Dependências | Estado |
|---|---|---|---|
| `RUN-01` | migration e modelos de ExecutionWave, WaveTask, WorkPackage, Lease, Runner, Event e Result; backfill legado | baseline aprovada | `completed` |
| `RUN-02` | commands de wave e Planning Preflight determinístico, com idempotência e auditoria | `RUN-01` | `completed` |
| `RUN-03` | builder/validator de Work Package versionado, snapshot/hash, paths, artifacts e verificações | `RUN-01..02` | `completed` |
| `RUN-04` | runner durável no host bridge: registry fixo, processo persistido, lease, heartbeat, outbox e reconciliação | `RUN-01`, contrato `RUN-03` | `completed` |
| `RUN-05` | commands/APIs de claim, dispatch, events, result, cancel, reconcile e rework integrados ao `TaskExecution` e aos checkpoints | `RUN-02..04`, `ER-SCR-01` | `completed` |
| `RUN-06` | adapters Claude, Codex e Agy com health/version/capabilities e normalização segura `antigravity -> agy` | `RUN-04` | `completed` |
| `RUN-07` | actions, delegação limitada do Athos, service credential do runner, redaction e limites de custo/tempo/output | `RUN-02..06` | `completed` |
| `RUN-08` | verificação determinística, review independente e loop de rework limitado | `RUN-05..07` | `completed` |
| `RUN-09` | UI Planning > Execution, detalhes de Task/Pipeline e estados loading/empty/error/forbidden/stale | `RUN-02..08` | `completed` |
| `RUN-10` | testes, recovery/restart, rollout gradual, rollback, manual operacional e evidências | `RUN-01..09` | `completed` |

As Tasks foram executadas sob `ER-RUN-01`. A regra permanece válida para novas
ondas: planejamento não equivale a dispatch.

## 17. Autoridade e comportamento do Athos

Athos é o operador padrão do ForgeHub, mas não é autoridade irrestrita. Com
delegação ativa e actions compatíveis, pode preparar/preflightar waves, ativar
waves previamente aprovadas quando a Policy permitir, despachar Work Packages,
acompanhar checkpoints e pausar/reconciliar falhas. Deve escalar:

- aprovação reservada ao usuário ou ao papel humano;
- ampliação de escopo, path, budget, risco ou capacidade;
- ação destrutiva/externa, release ou deploy;
- ausência de evidência, resultado stale ou reconciliação inconclusiva;
- esgotamento de tempo, custo ou iterações.

Athos nunca transforma `completed` em `verified`, conclui Stage ou faz deploy
apenas porque o processo CLI terminou com exit code zero.

## 18. Rollout e rollback

1. aplicar migration e manter o dispatch legado bloqueado para novas execuções;
2. validar wave/preflight/package sem iniciar processo (`shadow mode`);
3. habilitar um adapter por vez em ambiente controlado, começando por Codex;
4. executar testes de restart durante run, heartbeat perdido, result duplicado,
   cancelamento e output malformado;
5. habilitar Athos somente depois de validar actions/delegação e kill switch;
6. habilitar auto-dispatch apenas por Policy explícita e com limites baixos.

Rollback desabilita novos claims/dispatches, pausa waves ativas e preserva
packages, leases, events, results e checkpoints. Execuções vivas são canceladas
ou reconciliadas por command auditável; tabelas e histórico não são apagados.

## 19. Registro da Execution Release

Identificador: `ER-RUN-01`, liberado pelo usuário.

Estado atual:

```text
baseline implementada
  + RUN-01..RUN-10 completed
  + ER-RUN-01 released
  + migrations 1a7d9e4c6b20 e 2b8e0f5d7c31 aplicadas
  + runner host forgehub-host-runner/v1 ativo
  + dispatch legado bloqueado
```

A liberação não autoriza release/deploy de produtos construídos pelas CLIs.

## 20. Evidência de implementação

- migration corrente: `2b8e0f5d7c31 (head)`;
- suíte focal de execução/orquestração/task/pipeline/autoridade: `22 passed`;
- suíte backend completa: `113 passed`; duas falhas ambientais conhecidas no browser de arquivos, porque diretórios temporários internos ao container de teste não existem no host bridge;
- Ruff nos arquivos backend alterados: aprovado;
- build de produção do frontend: aprovado, mantendo apenas o aviso existente de chunks grandes;
- backend healthy, frontend HTTP 200 e `forgehub-chat-bridge.service` ativo;
- health do runner confirmou Claude, Codex e Agy disponíveis, persistência, cancelamento e reconciliação;
- estado do runner persiste sem prompt ou credencial em `/root/.forgehub/agent-runs`;
- dispatch direto legado retorna `410`; somente wave ativa + package validado/emitido alcança o runner;
- aprovação de review promove Execution a `verified` e Task a `done`; rework cria package revision nova.
