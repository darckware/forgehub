# Módulo 02 — Pipeline, Planejamento e Liberação da Execução

## 1. Objetivo

Transformar ProjectScope aprovado em plano executável, sem iniciar trabalho prematuramente. O módulo resolve a linha de produção, decompõe escopo em Planning Items/Tasks, congela baseline e libera somente Tasks elegíveis por ondas controladas.

```text
ProjectScope
  -> pipeline/classification/tracks
  -> plano + artifacts + staffing
  -> Planning Items
  -> Tasks planned + dependencies + critérios
  -> PlanBaseline
  -> Delivery Authorization
  -> ExecutionWave
  -> Tasks ready
```

## 2. Regra principal

`planned != ready`.

- `planned`: faz parte do plano e ainda pode estar incompleta/não autorizada.
- `ready`: passou pelo Planning Preflight e foi incluída em ExecutionWave aprovada.
- scheduler e agentes executores consultam apenas `ready`.
- nenhuma configuração de auto-dispatch contorna baseline ou Execution Release.

## 3. Entidades-alvo

### Classificação e tracks

- `development_types`: catálogo `key/name/description/status`.
- `project_development_types`: Project/type/primary.
- `project_classifications`: strategy/risk/data classification.
- `project_targets`: platform/version/distribution.
- `project_tracks`: key/name/type/status/owner.
- `pipeline_stage_tracks` e `planning_item_tracks`.

### Template versionado

- `pipeline_templates`: identidade, key, status.
- `pipeline_template_versions`: semver/revision/status/content_hash.
- stages, dependencies, requirements e gates pertencem à versão, não ao template mutável.
- `pipeline_template_applicability`: filtros de classificação, prioridade e packs.

### Plano e baseline

- `project_plan_revisions`: Project, revision, objectives, deliverables, assumptions, risks, schedule/cost/staffing summaries, status, hash.
- `plan_scope_items`: plan revision + ProjectScopeItem.
- `plan_baselines`: revision id, blueprint/scope/pipeline/policy/staffing snapshots, canonical JSON/hash, frozen_at.
- baseline imutável e única por revision aprovada.

### Planning e Tasks

Ampliar Planning Item com `department`, critérios, estimate, risk, owner role e associations M:N de scope/module/track.

Ampliar ProjectTask com `project_id`, `pipeline_stage_id`, scope M:N, acceptance criteria, DoD, risk, review requirements e paths/outputs/verifications.

### `execution_waves`

`id`, `project_id`, `baseline_id`, `pipeline_stage_id`, `name`, `status`, `authorized_by_type/id`, `delegation_id`, `wip_limit`, `budget_limit`, `starts_at`, `expires_at`, `paused_at`, `completed_at`.

- status `draft|approved|active|paused|completed|cancelled`.

### `execution_wave_tasks`

`id`, `execution_wave_id`, `task_id`, `release_order`, `released_at`.

- Task aparece em no máximo uma wave ativa.
- Unique wave/task e proteção contra wave de baseline divergente.

## 4. Resolução de pipeline

Input: Project classification, ProjectScope families/types, risk/data/platform, Policies e delivery strategy.

Output preview:

- template version + packs;
- stages incluídos/omitidos;
- tracks;
- required artifacts/tests/gates;
- staffing/skills;
- justificativa por decisão;
- warnings/overrides.

`InstantiatePipeline` ocorre após aprovação do preview e cria tudo atomicamente com stable keys internas para resolver dependências.

## 5. Commands

| Command | Precondições | Resultado |
|---|---|---|
| `ClassifyProject` | scope draft | classificação versionada |
| `ResolvePipelinePreview` | classificação/Policies | preview determinístico |
| `InstantiatePipeline` | preview aprovado | ProjectPipeline draft completo |
| `CreatePlanRevision` | scope/pipeline | plan draft |
| `GeneratePlanningDraft` | artifacts/context aprovados | Planning Items/Tasks `planned`, nunca ready |
| `ValidatePlan` | plano completo | erros/warnings/readiness |
| `ApprovePlanRevision` | authority + validação | revision approved |
| `CreateBaseline` | plan/scope/pipeline approved | snapshot/hash e Delivery Authorization request |
| `DecideDeliveryAuthorization` | approval authority | baseline authorized/rejected |
| `CreateExecutionWave` | baseline authorized | wave draft com Tasks candidatas |
| `ApproveExecutionWave` | Planning Preflight passa | wave approved |
| `ActivateExecutionWave` | WIP/capacity/policies | Tasks elegíveis `planned -> ready` |
| `PauseExecutionWave` | wave active | sem novos dispatches |
| `ResumeExecutionWave` | bloqueios resolvidos | wave active |
| `CompleteExecutionWave` | todas tasks terminais | wave completed |

## 6. Planning Preflight

Para cada Task candidata:

- baseline/Project/Stage/scope consistentes;
- origem de Planning Item/Change Request válida;
- descrição, aceite e DoD completos;
- dependências sem ciclo e predecessor compatível;
- input artifacts/revisions definidos;
- output/evidence e verification commands definidos;
- paths/locks e risco definidos;
- required skills e papéis producer/reviewer definidos;
- orçamento, capacidade, WIP e Policy satisfeitos.

Resultado por Task: `eligible`, `waiting_dependency`, `incomplete`, `policy_blocked`, `capacity_blocked`, `conflict`. Somente `eligible` é liberada.

## 7. Ajustes

- Antes da baseline: revisar plano/Tasks livremente com histórico de revision.
- Depois da baseline e antes da wave: Change Request quando muda escopo/custo/prazo/arquitetura/risco.
- Wave draft: adicionar/remover somente Tasks da mesma baseline.
- Wave ativa: pausar; Tasks não despachadas podem ser retiradas com audit; Tasks ativas preservam Execution e exigem cancel/replan.
- Template muda por nova versão; pipeline instanciado não muda silenciosamente.

## 8. APIs-alvo

- `/api/v1/projects/{id}/classification`
- `/api/v1/projects/{id}/pipeline-resolution:preview`
- `/api/v1/projects/{id}/pipelines:instantiate`
- `/api/v1/projects/{id}/plan-revisions`
- `/api/v1/plan-revisions/{id}:validate|:approve|:baseline`
- `/api/v1/projects/{id}/planning:draft`
- `/api/v1/projects/{id}/execution-waves`
- `/api/v1/execution-waves/{id}:preflight|:approve|:activate|:pause|:resume|:complete`
- `/api/v1/execution-waves/{id}/eligible-tasks`

## 9. Interface

- Classification wizard e pipeline preview explicado.
- Pipeline designer/version viewer.
- Planning workspace: scope → items → tasks → dependencies → staffing.
- Baseline diff/approval.
- Execution Release screen com Tasks candidatas, motivos de inelegibilidade, WIP/custo/capacidade.
- Wave board/timeline com pause/resume e controller atual.

## 10. Eventos

`ProjectClassified`, `PipelineResolved`, `PipelineInstantiated`, `PlanDraftGenerated`, `PlanValidated`, `PlanApproved`, `BaselineCreated`, `DeliveryAuthorized`, `ExecutionWaveCreated`, `ExecutionWaveApproved`, `TaskReleased`, `ExecutionWavePaused/Resumed/Completed`.

## 11. Critérios de aceite

1. Gerar plano nunca despacha agente.
2. Task planned não aparece no endpoint de dispatch.
3. Baseline não aprovada impede wave.
4. Task incompleta apresenta motivos determinísticos.
5. Ativar wave libera apenas Tasks elegíveis e dentro do WIP.
6. Retry de ativação não duplica wave/task/evento.
7. Pausa impede novo dispatch sem apagar execução ativa.
8. Mudança pós-baseline exige Change Request.
9. Usuário ou agente delegado pode gerir waves dentro da autoridade registrada.
10. Toda Task ready pode ser rastreada à baseline, scope, Stage e wave que a liberou.
