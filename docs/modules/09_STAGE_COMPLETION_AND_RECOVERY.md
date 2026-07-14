# Módulo 09 — Controle de Conclusão, Checkpoint e Retomada

## 1. Estado e autoridade

- Necessidade registrada pelo usuário em 2026-07-13.
- Planejamento técnico: **baseline aprovada pelo usuário em 2026-07-13**.
- Tasks: `SCR-01` a `SCR-09`, **completed**.
- Execution Release: `ER-SCR-01`, **liberada pelo usuário e implementada em 2026-07-13**.
- Escopo publicado: checkpoints, avaliação/conclusão de Stage, recuperação, projeção/timeline, UI Planning, notificações e integração mínima do Athos.

## 2. Objetivo

Permitir que usuário, Athos ou outra LLM respondam sem depender da conversa anterior:

1. qual macrofluxo, Stage, Task e execução estão ativos;
2. qual foi o último passo concluído e confirmado;
3. qual passo estava em andamento quando houve interrupção;
4. se houve bloqueio, falha, pausa, timeout ou perda de comunicação;
5. quais evidências já são válidas e não precisam ser refeitas;
6. qual é o ponto seguro e autorizado de retomada;
7. quais precondições ainda impedem a conclusão da etapa.

```text
Project/Macroflow
  → PipelineStage
      → WorkPackage/TaskExecution
          → checkpoint append-only
          → evidências confirmadas
          → interrupção/bloqueio
          → reconciliation
          → resume instruction
      → completion assessment
      → StageCompletion command
```

## 3. Correção conceitual

Um campo `status=completed` não é controle de conclusão suficiente. A conclusão precisa ser **derivada e comprovável**:

```text
concluído = precondições satisfeitas
          + trabalho terminal
          + verificações obrigatórias aprovadas
          + artifacts/evidências vigentes
          + approvals/gates satisfeitos
          + checkpoint final persistido
```

O sistema deve manter duas visões distintas:

- **estado atual calculado**, rápido para a interface;
- **histórico append-only de checkpoints e avaliações**, usado para auditoria e recuperação.

Percentual de progresso nunca deve ser digitado livremente pelo agente. Ele é calculado a partir de requisitos ponderados e confirmados; quando não houver base suficiente, a interface mostra estado/contagem, não uma precisão inventada.

## 4. Granularidades controladas

| Nível | Pergunta respondida | Registro autoritativo |
|---|---|---|
| Macrofluxo | em qual das três fases o produto está? | projeção dos Stages e gates do Product/Project |
| Pipeline Stage | a etapa pode ser declarada concluída? | `StageCompletionAssessment` |
| Task/Work Package | qual unidade ainda falta? | state machine + assignment/review |
| TaskExecution | qual tentativa rodou/parou? | lease, heartbeat, exit/result e checkpoints |
| Passo interno | qual foi o último ponto confirmado? | `ProgressCheckpoint` append-only |
| Integração externa | o efeito ocorreu realmente? | receipt/idempotency key + reconciliation |

A UI pode apresentar uma linha do tempo única, mas não deve misturar essas máquinas de estado em um único campo.

## 5. Contratos de dados propostos

### 5.1 `progress_checkpoints`

```text
id UUID
project_id UUID
pipeline_stage_id UUID?
task_id UUID?
task_execution_id UUID?
sequence integer
checkpoint_type started | progress | evidence | blocked | failed | paused |
                heartbeat_lost | reconciled | resumed | completed
step_key string
step_label string
state_snapshot JSONB
completed_requirement_keys JSONB
evidence_refs JSONB
last_confirmed_at timestamptz
resume_from_step_key string?
blocker_code string?
error_code string?
message text?
actor_type user | agent | system
actor_id UUID?
idempotency_key string
created_at timestamptz
unique(task_execution_id, sequence)
unique(idempotency_key)
```

Checkpoint é append-only. Correção cria novo registro `reconciled`; não altera o evento antigo.

### 5.2 `stage_completion_assessments`

```text
id UUID
pipeline_stage_id UUID
stage_revision integer
baseline_id UUID?
policy_version_id UUID?
input_hash string
result ready | not_ready | stale
requirement_results JSONB
missing_requirements JSONB
blocking_reasons JSONB
evidence_refs JSONB
evaluator_version string
evaluated_at timestamptz
```

Mesmos inputs, revisões e policy version devem produzir o mesmo resultado/hash.

### 5.3 Projeção `stage_progress`

Read model reconstruível contendo:

```text
stage_id, effective_status, requirement_total, requirement_completed
active_task_count, blocked_task_count, failed_execution_count
last_checkpoint_id, last_confirmed_at, current_step, stopped_reason
resume_from, owner, runtime, lease_expires_at, heartbeat_state
completion_assessment_id, updated_at
```

A projeção pode ser recalculada; checkpoints, decisões e evidências não podem ser descartados.

## 6. Estados de interrupção

| Condição | Estado exibido | Retomada |
|---|---|---|
| dependência/requisito ausente | `blocked` | resolver blocker e emitir `resumed` |
| comando/teste terminou com erro | `failed` na execução | nova tentativa a partir do último checkpoint seguro |
| usuário/Athos pausou | `paused` | exige autoridade para retomar |
| heartbeat expirou | `unknown/reconciling` | consultar processo/adapter antes de declarar falha |
| runner reiniciou | `recovering` | restaurar outbox, lease e checkpoint persistidos |
| resultado chegou para revisão antiga | `stale` | preservar resultado; não avançar Stage |
| integração externa sem confirmação | `reconciling` | consultar receipt usando idempotency key |

Ausência de heartbeat não equivale automaticamente a falha. O reconciliador deve primeiro verificar PID/session/adapter e efeitos externos.

## 7. Commands e APIs-alvo

| Command | API-alvo | Regra principal |
|---|---|---|
| `RecordProgressCheckpoint` | `POST /api/v1/executions/{id}/checkpoints` | runtime/ator autorizado e sequência idempotente |
| `ReportExecutionBlocker` | `POST /api/v1/executions/{id}:block` | blocker estruturado e ação segura |
| `PauseExecution` | `POST /api/v1/executions/{id}:pause` | preserva processo/evidência e bloqueia avanço |
| `ReconcileExecution` | `POST /api/v1/executions/{id}:reconcile` | confirma estado real antes da retomada |
| `ResumeExecution` | `POST /api/v1/executions/{id}:resume` | usa checkpoint seguro e nova lease/attempt quando necessário |
| `EvaluateStageCompletion` | `POST /api/v1/pipeline-stages/{id}:evaluate-completion` | resultado determinístico e versionado |
| `CompleteStage` | `POST /api/v1/pipeline-stages/{id}:complete` | somente assessment `ready` vigente |
| `GetProjectProgress` | `GET /api/v1/projects/{id}/progress` | read model calculado com ponto de parada |
| `GetProgressTimeline` | `GET /api/v1/projects/{id}/progress-timeline` | checkpoints, decisões e transições ordenadas |

PATCH genérico de status não pode concluir uma etapa nem apagar o motivo de parada.

## 8. Interface no grupo Planning

### 8.1 Pipeline/Project Progress

Adicionar aos detalhes de Project/Pipeline:

- linha das etapas do início ao deploy;
- estado atual e requisitos concluídos/pendentes por etapa;
- última confirmação, ator, runtime e horário;
- “Parou em” com step, Task/Execution e motivo;
- evidências já aceitas;
- primeira ação segura para retomar;
- botões governados `Pausar`, `Reconciliar`, `Retomar` e `Avaliar conclusão`;
- timeline de checkpoints e decisões sem sobrescrever histórico.

### 8.2 Regra visual

Cada Stage deve distinguir pelo menos:

```text
não iniciado | pronto | em andamento | aguardando revisão
bloqueado | falhou | pausado | reconciliando | concluído
```

O card de erro precisa exibir código, mensagem, última etapa confirmada, impacto, evidência e autoridade necessária — não apenas “falhou”.

## 9. Relação com o Athos e as CLIs

- Athos monitora a projeção, aponta interrupções e recomenda a próxima ação elegível;
- somente autoridade válida pode pausar, retomar, cancelar ou aceitar override;
- Claude/Codex/Agy registram checkpoint pelo adapter, não alteram Stage diretamente;
- uma nova LLM recebe o Work Package, último checkpoint confirmado, evidências, blocker e resume instruction;
- retomada cria nova tentativa quando a anterior terminou ou perdeu lease; histórico não é reutilizado como se fosse a mesma execução;
- o ForgeHub é o ledger autoritativo; checkpoint local do ForgeFlow é reconciliado, não copiado cegamente.

## 10. Necessidades externas ao grupo Planning

| Componente | Necessidade | Por que é externa |
|---|---|---|
| Runtime/host bridge | PID, session, heartbeat, outbox e reconcile dos adapters | executa fora das telas Planning |
| Notifications | alertas de bloqueio, falha, heartbeat perdido e retomada | módulo General |
| Athos Control Room | visão consolidada e ações do operador/agente | módulo Agents & AI futuro |
| Audit/Event infrastructure | checkpoints e commands append-only | infraestrutura transversal |

A interface inicial pode permanecer em Project/Pipeline dentro de Planning. As integrações externas acima precisam de validação e Execution Release explícita antes da implementação.

## 11. Plano executado — Tasks `completed`

| ID | Task | Dependências | Verificação |
|---|---|---|---|
| `SCR-01` | contratos, migration e constraints de checkpoint/assessment | nenhuma | upgrade/downgrade, append-only e idempotência |
| `SCR-02` | evaluator determinístico de conclusão de Stage | SCR-01 | mesmos inputs geram mesmo hash/resultado |
| `SCR-03` | commands block/pause/reconcile/resume/complete | SCR-01–02 | transições inválidas recusadas |
| `SCR-04` | projeção de progresso e timeline | SCR-01–03 | reconstrução somente por banco/eventos |
| `SCR-05` | UI Project/Pipeline Progress no Planning | SCR-04 | mostra exatamente onde parou e por quê |
| `SCR-06` | checkpoints nos adapters e outbox do runtime | SCR-01–04 | recovery após reinício sem duplicidade |
| `SCR-07` | alertas e notificações reconciliáveis | SCR-03–06 | falha de notify não altera estado principal |
| `SCR-08` | integração mínima com Athos e handoff | SCR-04–07 | outra LLM retoma sem conversa anterior |
| `SCR-09` | testes E2E, rollout, rollback e manual | SCR-01–08 | matriz falha/pausa/timeout/stale/restart |

As nove Tasks foram concluídas sob `ER-SCR-01`. A integração de runtime desta onda cobre checkpoints por API e checkpoints automáticos do lifecycle de `TaskExecution`; execução real dos adapters Claude/Codex/Agy continua dependendo da onda de runner/dispatch.

## 12. Critérios de aceite

1. qualquer Project ativo informa macrofluxo e Stage atuais;
2. qualquer interrupção informa último checkpoint confirmado e motivo;
3. bloqueio contém código, evidência, impacto, ações seguras e autoridade necessária;
4. conclusão de Stage depende de assessment vigente e evidências, não de checkbox/status livre;
5. reinício do backend/runner não perde ponto de retomada;
6. heartbeat perdido entra em reconciliação antes de falha;
7. retry/replay não duplica checkpoints nem transições;
8. resultado stale permanece auditável e não avança a baseline atual;
9. usuário pode pausar e assumir o controle sem apagar trabalho;
10. Athos e outra LLM conseguem retomar pelo snapshot persistido;
11. timeline reconstrói quem fez o quê, quando, com qual revisão e evidência;
12. Stage concluído recalcula de forma determinística a próxima ação elegível.

## 13. Registro da Execution Release

`ER-SCR-01` definiu:

- baseline exata deste documento;
- Tasks e paths autorizados;
- migrations/backfill e estratégia de rollback;
- divisão entre backend, frontend e runtime externo;
- producer/reviewer independentes para recovery e segurança;
- comandos de teste e cenários de interrupção;
- autorização explícita para alterações externas ao Planning.

Estado final:

```text
baseline aprovada
  + ER-SCR-01 released
  + SCR-01..SCR-09 completed
  + migration f0c6d3e8a921 aplicada
  + controle de conclusão/retomada publicado
```

## 14. Evidência de implementação e limites

- `progress_checkpoints` mantém fatos append-only com sequência e idempotency key;
- `stage_completion_assessments` registra input hash, requisitos, evidências, blockers e resultado determinístico;
- `pipeline_stages.revision` invalida assessments após alteração da etapa, artifact ou gate;
- conclusão por `PATCH status=completed` foi bloqueada; `:complete` exige assessment `ready` vigente;
- criação e término de `TaskExecution` geram checkpoints automáticos; adapters podem registrar checkpoints intermediários;
- commands `block`, `pause`, `reconcile` e `resume` preservam o último ponto confirmado;
- retry de checkpoint e conclusão não duplica histórico;
- heartbeat/processo ausente pode ser reconciliado antes da classificação como falha;
- a tela de Pipeline mostra macrofluxo, última confirmação, ponto de parada, próxima ação segura, requisitos e timeline;
- Athos pode consultar/gerenciar progresso e concluir Stage somente com ações delegadas e revogáveis;
- bloqueio, pausa, perda e retomada geram Notifications best effort sem reverter o estado principal.

Limites conscientes: ainda não existe runner durável que emita heartbeat/PID diretamente dos três adapters; nesta onda o contrato e os endpoints estão prontos e o lifecycle do `TaskExecution` já produz checkpoints. A ligação automática com processos Claude/Codex/Agy será feita junto da Execution Release do runner, sem ampliar `ER-SCR-01` para dispatch de Tasks.

Verificação da release:

- suíte focal de pipeline/task/orchestration/autoridade: `21 passed`;
- suíte backend completa: `112 passed`; duas falhas ambientais preexistentes no browser de arquivos, pois o diretório temporário criado dentro do container de teste não existe no host bridge;
- Ruff nos arquivos alterados: aprovado;
- build de produção do frontend: aprovado, mantendo somente o aviso existente de chunks grandes;
- migration aplicada: `f0c6d3e8a921 (head)`.
