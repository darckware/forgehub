# Módulo 04 — Governance, Policies, Gates, Artifacts e Evidências

## 1. Objetivo

Transformar governança de registros livres em decisões reproduzíveis. Policies versionadas determinam requisitos; avaliações calculam resultados; approvals registram autoridade; gates agregam tudo sem booleano manual; ArtifactVersions/evidências provam o trabalho.

## 2. Separação de conceitos

- PolicyDefinition: regra reutilizável e versionada.
- PolicyBinding: onde/quando a regra se aplica.
- PolicyEvaluation: execução determinística da regra com inputs/hash.
- ApprovalRequest/Decision: decisão de ator autorizado.
- Gate: condição de passagem calculada, não decisão duplicada.
- Artifact: identidade lógica do entregável.
- ArtifactVersion: conteúdo/revisão imutável.
- Evidence: referência/hash que sustenta um critério ou avaliação.
- AuditEvent: fato append-only de que algo ocorreu.

## 3. Entidades-alvo

### Policies

- `policy_definitions`: key/name/type/description/status.
- `policy_versions`: definition_id/version/schema/rules/evaluator_type/content_hash/status.
- `policy_bindings`: policy_version_id + target scope (org/product/project/stage/element/risk/environment), priority/effective dates.
- `policy_evaluations`: binding/version/context/input hash/result/pass-fail-warn/errors/evaluated_at/evaluator version.

Tipos iniciais: state transition, required artifact, approval, separation of duties, security/privacy, budget, staffing, execution permission, release, environment/deploy, maintenance/emergency.

### Approvals

- `approval_requests`: target type/id/revision, approval_type, policy_binding_id, status, requested_by/at, expires_at.
- `approval_decisions`: request_id, decision, decided_by type/id, authority source, comments, evidence, decided_at.
- request `pending|decided|expired|cancelled`; decision `approved|rejected|changes_requested|abstained`.
- decisões append-only; nova análise cria request/revision.

### Gates

- `gate_definitions` pertencem ao template version.
- `stage_gates` materializam definition no ProjectPipeline.
- `gate_evaluations`: stage_gate_id, input_revision/hash, status, requirements snapshot, calculated_at.
- status `not_ready|ready_for_review|awaiting_approval|passed|failed|stale`.

### Artifacts/evidence

Ampliar Artifact com Product/Version/Project obrigatórios conforme contexto e stable key. ArtifactVersion: immutable content URI/hash, media/schema type, producer execution, status.

Associations: ArtifactVersion ↔ ProjectScopeItem, PlanningItem, Task/Execution, Stage requirement, PolicyEvaluation e Release manifest.

`evidence_records`: type, uri, hash, captured_at, producer, verification metadata, retention/sensitivity.

## 4. Commands

`PublishPolicyVersion`, `BindPolicy`, `EvaluatePolicies`, `RequestApproval`, `DecideApproval`, `CreateArtifactVersion`, `SubmitArtifactVersion`, `ReviewArtifactVersion`, `BindEvidence`, `EvaluateGate`, `InvalidateEvaluation`.

Todas recebem target revision/hash. Mudança de input invalida evaluation/gate anterior e exige nova avaliação.

## 5. Gate calculator

Para Stage, calcular:

1. dependencies completas;
2. scope coverage exigida;
3. Tasks/Executions verificadas;
4. ArtifactVersions corretas e aprovadas;
5. PolicyEvaluations pass;
6. ApprovalDecisions válidas/não expiradas;
7. ausência de bloqueios críticos.

Retorno inclui requisito por requisito, status, evidence refs e ação de correção. `is_fulfilled` manual deixa de ser fonte de verdade.

## 6. Autoridade

- Agent/humano precisa de role/permission no target.
- executor não aprova próprio resultado quando Policy exigir independência.
- approvals humanos críticos não podem ser delegados sem Policy explícita.
- override tem escopo, expiração, justificativa e risco; nunca altera avaliação histórica.

## 7. APIs-alvo

- `/api/v1/policy-definitions` e `/versions`
- `/api/v1/policy-bindings`
- `POST /api/v1/policy-evaluations:run`
- `/api/v1/approval-requests` e `POST .../{id}:decide`
- `POST /api/v1/stage-gates/{id}:evaluate`
- `/api/v1/artifacts/{id}/versions`
- `POST .../versions/{id}:submit|:approve|:reject`
- `/api/v1/evidence-records` e bindings.

## 8. Interface

- Policy catalog/version/diff/binding simulator.
- Approval inbox com autoridade e impacto.
- Gate detail com árvore de requisitos e evidências.
- Artifact/evidence version viewer e scope coverage.
- Audit timeline filtrável.

## 9. Migração

- preservar Policies JSON atuais como legacy version 1 draft/inactive até validação;
- converter Approvals atuais em request+decision quando dados permitirem; marcar unknown origin;
- manter Gate/required `is_fulfilled` apenas como legacy display durante transição;
- backfill project/version de Artifact por Stage/Execution; casos ambíguos ficam migration exception, nunca inferência silenciosa.

## 10. Critérios de aceite

1. Mesmos inputs/revision produzem mesma avaliação.
2. Mudança de input torna gate stale.
3. Gate explica exatamente o requisito ausente.
4. ArtifactVersion aprovada é imutável e verificável por hash.
5. Executor não autoaprova quando proibido.
6. Approval repetida é idempotente ou nova decisão explicitamente versionada.
7. Nenhum Stage conclui por booleano manual.
8. Audit reconstrói regra, input, decisão, ator e evidência.
