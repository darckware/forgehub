# Módulo 05 — Release, Delivery, Operação, Manutenção e Evolução

## 1. Objetivo

Comprovar o conjunto exato entregue, em qual alvo, com que resultado, e transformar operação/feedback/incidente em manutenção ou nova implementação rastreável.

## 2. Entidades-alvo

### Release

- `release_candidates`: ProductVersion/Project, revision, status, source commit/tag, build refs, manifest hash, rollback plan.
- `release_manifest_items`: candidate + ProjectScopeItem/SystemElementRevision + artifacts/tasks/evidence/checksum.
- `releases`: candidate approved, version/name/status/released_at.
- estados candidate `draft|validating|ready|rejected|superseded|promoted`; release `approved|released|withdrawn|deprecated`.

### Build e delivery

- `build_artifacts`: type/uri/digest/SBOM/signature/source revision.
- `environments`: key/type/risk/approval policy/status.
- `deliveries`: Release, environment, channel/type, status, idempotency key, actor/runtime.
- `delivery_attempts`: attempt/log/evidence/start/end/result.
- `deployment_scope_results`: element/result/checks/evidence.
- delivery types: deploy, store publish, package publish, automation activation, data activation/backfill, configuration rollout, research closeout.
- status `planned|awaiting_approval|approved|delivering|succeeded|failed|rolling_back|rolled_back|cancelled`.

### Operação/manutenção

- `operational_signals`: metric/log/alert/feedback/support/security/source refs.
- `incidents`: severity/status/started/resolved/affected environment/elements/root cause.
- `maintenance_work`: class `corrective|preventive|adaptive|evolutionary`, source signal/incident/request, affected elements, urgency/status.
- incident status `detected|triaged|mitigating|monitoring|resolved|closed`.

Mudança de código/config versionada converte MaintenanceWork em DevelopmentRequest + ProductVersion/Project. Ação operacional sem alteração de produto pode permanecer no fluxo operacional, sempre auditada.

## 3. Commands

`CreateReleaseCandidate`, `BuildManifest`, `ValidateCandidate`, `RequestReleaseApproval`, `PromoteRelease`, `PlanDelivery`, `ApproveDelivery`, `ExecuteDelivery`, `RecordOperationalCheck`, `RollbackDelivery`, `IngestOperationalSignal`, `DeclareIncident`, `TriageMaintenance`, `ConvertMaintenanceToProject`, `CloseIncident`.

## 4. Manifest e readiness

Candidate só fica ready quando:

- scope items alvo estão verified;
- Stage/release gates passaram;
- artifacts/builds/digests/SBOM/signatures exigidos existem;
- migrations e ordem/rollback estão definidos;
- release notes e operational checks existem;
- Policies/approvals válidas;
- source revision está imutável.

Manifest é canônico/hash; promoção não o altera.

## 5. Delivery

Adapter por tipo/alvo; comando externo idempotente. ForgeHub registra intenção antes da ação, tenta, coleta resultado e reconcilia estado externo. `ProjectTask.deployed` é derivado somente quando elemento/task aparece em Release entregue com sucesso ao alvo definido pela Policy.

Verificação operacional inclui smoke/health/business checks, observação mínima e evidência. Sucesso técnico sem verificação permanece `succeeded` delivery mas scope ainda não `operationally_verified`.

## 6. Manutenção e novas implementações

| Impacto | Rota |
|---|---|
| operação sem mudança versionada | operational action/runbook |
| bug/hotfix | maintenance request → Project/pipeline corretivo |
| dependência/hardening | preventivo → Project/pipeline proporcional |
| plataforma/regulação externa | adaptativo + risk/policy review |
| melhoria existente | evolutivo + nova ProductVersion |
| capability/process/channel novo | retorna à Concepção completa |

Emergência pode abreviar documentação prévia, nunca eliminar identidade, autorização mínima, evidência e revisão retrospectiva.

## 7. APIs/UI

- Candidate builder/manifest diff/readiness.
- Release approval and history.
- Environment/Delivery planner and live attempts.
- Operational verification/rollback.
- Operations cockpit, signals/incidents.
- Maintenance triage with impacted System Map.
- APIs command-oriented correspondentes a cada command acima.

## 8. Eventos

`CandidateCreated/Validated/Promoted`, `ReleaseApproved`, `DeliveryPlanned/Started/Succeeded/Failed/RolledBack`, `OperationalCheckRecorded`, `SignalIngested`, `IncidentDeclared/Mitigated/Resolved`, `MaintenanceTriaged/Converted`.

## 9. Critérios de aceite

1. Release reproduz conteúdo por hashes/manifest.
2. Delivery duplicada não repete ação externa.
3. Falha preserva tentativa/log e oferece rollback/roll-forward seguro.
4. “Em produção” nunca é campo manual.
5. Cada elemento mostra ambientes e verificações.
6. Signal/incidente aponta para elementos afetados.
7. Manutenção com mudança cria versão/Project apropriado.
8. Capability nova retorna à concepção.
9. Hotfix preserva revisão retrospectiva e audit.
