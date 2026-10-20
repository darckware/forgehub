# Módulo 08 — Governed Planning Approval

## 1. Estado e autoridade

- Necessidades externas: **aprovadas pelo usuário em 2026-07-13**.
- Planejamento técnico: **baseline aprovada**.
- Tasks: `GPA-01` a `GPA-10`, **completed**.
- Execution Release: `ER-GPA-01`, **liberada pelo usuário e implementada em 2026-07-13**.
- Escopo publicado: aprovação governada do Planning, permissões por ação e delegação limitada do Athos. A liberação não autoriza execução de Tasks por CLI.

## 2. Objetivo

Substituir a decisão declarada pelo frontend por um fluxo governado e reproduzível:

```text
revisão imutável + hash
  → PolicyEvaluation determinística
  → ApprovalRequest
  → autoridade e separação de funções
  → ApprovalDecision pelo principal autenticado/delegado
  → transição do Concept/System Map
  → notificação + AuditEvent
```

O módulo protege inicialmente `ProductConcept` e `SystemBlueprintRevision`, mas os contratos devem ser reutilizáveis por pipeline, release, deploy e manutenção.

## 3. Fronteira aprovada

### Componentes que precisarão mudar

| Área | Mudança planejada |
|---|---|
| Auth/identidade | resolver `ActorPrincipal` a partir da credencial; nunca aceitar ator decisor no payload |
| Access Profiles | adicionar permissões por ação além dos quatro flags genéricos por módulo |
| Governance | requests/decisions versionadas, evaluations e separação de funções |
| Policies | versão, binding e avaliação determinística para aprovação de concepção |
| Planning | integrar submit/decide/authorize ao resultado governado |
| Notifications | avisar solicitação, decisão, expiração e revogação |
| Agents/Athos | delegação limitada, revogável e auditada; sem autoaprovação implícita |
| UI | Approval Inbox e painel de readiness/autoridade em Conception |

### Continuam fora desta onda

- execução de Tasks por Claude/Codex/Agy;
- ExecutionWave genérica e runner durável;
- Athos Control Room completo/Assistant docked;
- gate calculator de pipeline, release e deploy;
- evidência de artefatos e storage;
- manutenção/operação.

## 4. Decisões de desenho

### 4.1 Principal autenticado

Criar um read model/dependency `ActorPrincipal`:

```text
principal_type: user | agent
principal_id: UUID
display_name: string
is_admin: bool
profile_id: UUID?
delegation_id: UUID?
```

- usuário deriva do JWT e da linha ativa em `users`;
- agente deriva de credencial de serviço revogável, nunca de `decided_by` no body;
- AuditEvent guarda tipo/id/nome do principal no payload e nome estável em `actor` durante compatibilidade;
- credencial inválida, principal inativo ou delegação expirada retorna `401/403` antes da command.

### 4.2 Permissão por ação

Os flags atuais `can_view|query|write|delete` são insuficientes para distinguir edição de aprovação. Adicionar `profile_action_permissions`:

```text
profile_id
action_key
allowed
constraints JSONB?
unique(profile_id, action_key)
```

Chaves iniciais:

- `planning.concept.view`
- `planning.concept.edit`
- `planning.concept.submit`
- `planning.concept.decide`
- `planning.blueprint.edit`
- `planning.blueprint.approve`
- `planning.delivery.authorize`
- `governance.approval.view`
- `governance.approval.decide`
- `governance.delegation.manage`

Admin continua com bypass explícito e auditado. Ausência de chave significa deny para commands sensíveis.

### 4.3 Policy e avaliação

Implementar a menor fatia compatível com o Módulo 04:

- `policy_versions`: snapshot imutável e hash;
- `policy_bindings`: target/product/risk/prioridade/vigência;
- `policy_evaluations`: input revision/hash, resultado, requisitos e evaluator version;
- seed `concept_approval_v1` exigindo mapa válido e aprovador autorizado;
- regra opcional `deny_self_approval=true`;
- mesmos inputs + policy version produzem mesmo resultado/hash.

Não interpretar texto livre com LLM para permitir transição. A avaliação usa regras estruturadas.

### 4.4 Approval Request/Decision

Evoluir sem apagar `approvals` atuais:

- `approval_requests`: target/revision/hash/type/status/policy evaluation/requester/expiry;
- `approval_decisions`: request/decision/principal/authority source/comments/evidence/timestamp;
- decisões append-only;
- request pendente único por target revision + approval type;
- retry com idempotency key retorna a mesma decisão;
- mudança de revisão/hash torna a request anterior `stale` ou `cancelled`;
- decisão válida muda o estado do conceito/mapa na mesma transação.

Estados:

```text
request: pending → decided | expired | cancelled | stale
decision: approved | rejected | changes_requested | abstained
```

### 4.5 Separação de funções

- comparar principal decisor com criador da ConceptRevision e produtor da BlueprintRevision;
- quando a policy proibir, retornar `403 separation_of_duties_violation`;
- admin não ignora automaticamente a regra: override exige ação específica, justificativa e AuditEvent;
- agente executor ou Athos não aprova sua própria produção sem policy/delegação explícita.

### 4.6 Delegação do Athos

Criar `authority_delegations`:

```text
id, grantor_user_id, grantee_type, grantee_id
scope_type, product_id?, project_id?
allowed_actions JSONB
max_risk, budget_limit?, valid_from, expires_at
status, revoked_at, reason
```

- somente usuário com `governance.delegation.manage` concede/revoga;
- delegação nunca amplia a autoridade do grantor;
- `planning.concept.decide` e `planning.delivery.authorize` são ações separadas;
- pausa/revogação tem efeito imediato em novas commands;
- delegação não habilita Claude/Codex/Agy nem libera Tasks.

### 4.7 Notificações

Usar o domínio de Notifications existente para:

- approval requested;
- changes requested/rejected/approved;
- request expiring/expired;
- delegation granted/revoked/expired.

Falha de notificação não desfaz uma decisão já persistida; usar registro/outbox ou retry reconciliável, sem dupla decisão.

## 5. Commands e APIs implementadas

| Command | API | Autoridade |
|---|---|---|
| `SubmitConceptForApproval` | `POST /api/v1/product-concepts/{id}:submit` | `planning.concept.submit` |
| `EvaluateConceptPolicies` | `GET /api/v1/governed/policy-evaluations/{id}` | principal autenticado |
| `DecideApproval` | `POST /api/v1/governed/approval-requests/{id}:decide` | `governance.approval.decide` + policy/delegação |
| `AuthorizeDeliveryPlanning` | endpoint atual | `planning.delivery.authorize` + decisão válida |
| `GrantDelegation` | `POST /api/v1/governed/authority-delegations` | `governance.delegation.manage` |
| `RevokeDelegation` | `POST /api/v1/governed/authority-delegations/{id}:revoke` | grantor/admin autorizado |
| `IssueAgentCredential` | `POST /api/v1/governed/agent-credentials` | `governance.delegation.manage` |
| `RevokeAgentCredential` | `POST /api/v1/governed/agent-credentials/{id}:revoke` | `governance.delegation.manage` |

O endpoint direto `product-concepts/{id}:decide` fica temporariamente compatível, mas deve delegar ao command governado ou retornar `410/409` após migração; ele não poderá mais confiar em `decided_by` do body.

## 6. Plano de migração e compatibilidade

1. criar tabelas novas sem remover `policies`/`approvals` legadas;
2. adicionar permissões por ação com deny por padrão para não-admin;
3. conceder ações sensíveis apenas ao perfil/admin explicitamente escolhido;
4. seed da policy version/binding de concepção;
5. requests antigas não são inventadas; approvals legadas recebem marcador `legacy` somente quando convertíveis;
6. integrar submit primeiro em modo observação, comparar evaluation;
7. ativar enforcement em flag/configuração após testes;
8. desativar decisão direta somente após UI e Approval Inbox estarem publicadas;
9. rollback desliga enforcement e preserva os registros novos; nunca apaga decisões/auditoria.

## 7. Plano executado — Tasks em estado `completed`

| ID | Task | Paths principais | Dependências | Verificação |
|---|---|---|---|---|
| `GPA-01` | contratos, migration e seeds | `db/models/governance.py`, Alembic, schemas | nenhuma | upgrade/downgrade + constraints |
| `GPA-02` | `ActorPrincipal` humano/agente | `core/security.py`, `core/deps.py`, auth tests | GPA-01 | ator do payload não altera identidade |
| `GPA-03` | action permissions e Profile UI | profile model/routes/schemas, `pages/profiles` | GPA-01–02 | deny-by-default e admin auditado |
| `GPA-04` | policy version/binding/evaluator | governance service/routes | GPA-01–02 | determinismo por revision/hash |
| `GPA-05` | approval request/decision e SoD | governance commands/routes | GPA-02–04 | autoaprovação negada e retry idempotente |
| `GPA-06` | integrar ProductConcept/System Map | `routes/system_scope.py`, schemas/hooks | GPA-05 | nenhuma transição sem decisão válida |
| `GPA-07` | Approval Inbox e painel Conception | governance/conception frontend | GPA-03–06 | ações elegíveis e motivos de bloqueio |
| `GPA-08` | delegação limitada do Athos | agent/governance/auth + UI mínima | GPA-02–05 | expiração/revogação bloqueia nova ação |
| `GPA-09` | notificações e reconciliação | notifications + governance event handler | GPA-05–08 | decisão persiste mesmo com notify fail |
| `GPA-10` | suíte E2E, rollout e manual | tests/docs/config | GPA-01–09 | matriz humana/Athos/SoD/expiry/rollback |

As dez Tasks foram executadas sob `ER-GPA-01`. Nenhum adapter CLI foi habilitado: a liberação governa aprovação e delegação, não dispatch ou execução de Tasks.

## 8. Ordem de execução e revisão

```text
GPA-01
  → GPA-02
  → GPA-03 + GPA-04
  → GPA-05
  → GPA-06
  → GPA-07 + GPA-08
  → GPA-09
  → GPA-10
```

- producer e reviewer devem ser diferentes em GPA-02, GPA-05, GPA-06 e GPA-08;
- alterações de segurança e migração exigem revisão humana antes do merge/deploy;
- Athos pode acompanhar o plano, mas não liberar `ER-GPA-01` usando a própria delegação criada nesta onda.

## 9. Critérios de aceite da onda

1. backend ignora/rejeita identidade decisora fornecida pelo cliente;
2. usuário sem action permission recebe `403` mesmo vendo o módulo;
3. PolicyEvaluation é reproduzível por version/hash;
4. revisão alterada invalida request anterior;
5. separação de funções impede autoaprovação quando configurada;
6. ApprovalDecision válida e transição ocorrem atomicamente;
7. autorização de delivery exige decisão vigente para a revisão exata;
8. Athos só age dentro de delegação, risco, produto/projeto e validade;
9. revogação impede a próxima ação sem apagar histórico;
10. UI explica política, autoridade, pendência e bloqueio;
11. auditoria reconstrói requester, evaluator, policy, approver, delegation e hashes;
12. falha de notificação não duplica nem reverte decisão;
13. nenhuma Task de construção é liberada por consequência da aprovação conceitual.

## 10. Registro da Execution Release

`ER-GPA-01` contém:

- baseline exata deste documento;
- Tasks `GPA-01` a `GPA-10`;
- paths permitidos por Task;
- producer/reviewer;
- comandos de teste;
- estratégia de backup/rollback da migration;
- autorização humana explícita para executar e publicar, registrada em 2026-07-13.

Estado final da onda:

```text
necessidades aprovadas
  + baseline aprovada
  + ER-GPA-01 released
  + GPA-01..GPA-10 completed
  + aprovação governada publicada
  + execução de Tasks por CLI ainda bloqueada
```

## 11. Evidência de implementação e limites

- migration `e9b5c2d4f710` cria versões/bindings/evaluations de policy, requests/decisions, permissões por ação, delegações e credenciais revogáveis;
- a identidade do requester/decisor é derivada de JWT ou credencial de serviço, e campos de identidade enviados pelo cliente não concedem autoridade;
- a policy inicial é estruturada e determinística por revisão/hash; interpretação livre por LLM não decide transições;
- autoaprovação é recusada, retry de decisão é idempotente e revisão divergente torna a solicitação inválida;
- a autorização de delivery exige aprovação vigente para a revisão e o hash exatos;
- Athos pode receber somente as ações, escopo e validade concedidos, com revogação imediata;
- a tela Governance contém o Approval Inbox e o painel mínimo de delegação do Athos; Conception encaminha a decisão para esse inbox;
- notificações de decisão são best effort após commit e deduplicadas por chave de evento, sem reverter a decisão persistida.

Limites conscientes: o evaluator entregue cobre a policy de aprovação de concepção, não o Policy Engine geral; a credencial do Athos deve ser emitida e instalada no runtime autorizado; Athos Control Room, Assistant docked, runner durável, Claude/Codex/Agy e liberação de Tasks continuam nas ondas próprias.
