# Module Specification — `<module-name>`

## 1. Controle

```yaml
spec_id: <stable-id>
revision: 1
status: draft | in_review | approved | superseded
owner: <identity>
approvers: []
target_release: <version|null>
architecture_refs: []
decisions: []
open_blocking_questions: []
```

Uma spec com `open_blocking_questions` não autoriza implementação autônoma.

## 2. Objetivo e limite

- Problema resolvido:
- Resultado esperado:
- Atores:
- Responsabilidade deste módulo:
- Responsabilidades de outros módulos:
- Dentro do escopo:
- Fora do escopo:
- Classificações/solution types aplicáveis:

## 3. Casos de uso e processos

Para cada caso:

| ID | Ator | Gatilho | Fluxo principal | Alternativas | Resultado | Scope elements |
|---|---|---|---|---|---|---|

## 4. Modelo de domínio e dados

### Entidades

| Entidade | Atributo | Tipo | Obrigatório | Default | Constraint | Sensibilidade |
|---|---|---|---|---|---|---|

### Relações

| Origem | Relação | Destino | Cardinalidade | On delete | Regra cross-domain |
|---|---|---|---|---|---|

### Invariantes

1. `<regra>`

### Migração e backfill

- Estado anterior:
- Transformação:
- Backfill:
- Compatibilidade:
- Rollback/roll-forward:

## 5. Máquinas de estados

### Estados

| Estado | Significado | Entradas permitidas | Saídas permitidas | Terminal? |
|---|---|---|---|---|

### Comandos

| Comando | Ator | Precondições | Transição | Side effects | Idempotência | Erros |
|---|---|---|---|---|---|---|

PATCH livre de status não substitui comandos de domínio.

## 6. Policies e permissões

| Ação | Papel/authority | Policy | Aprovação humana | Separation of duties | AuditEvent |
|---|---|---|---|---|---|

## 7. Contratos de API

Para cada operação:

```yaml
operation_id: <id>
method: GET | POST | PATCH | DELETE
path: /api/v1/...
authorization: <rule>
idempotency: <rule|null>
request_schema: <ref>
response_schema: <ref>
errors:
  - {status: 409, code: <code>, condition: <condition>}
events: []
```

## 8. Eventos e auditoria

| Evento | Producer | Payload version | Consumer | Idempotency key | Retention |
|---|---|---|---|---|---|

## 9. Interface

| Tela/Componente | Rota | Atores | Dados | Ações | Policies |
|---|---|---|---|---|---|

Para cada tela especificar:

- loading, empty, success, stale, blocked e error;
- validação e mensagens;
- confirmação de ação destrutiva;
- acessibilidade e navegação por teclado;
- responsividade;
- atualização otimista ou refetch;
- indicação de revisão, estado e próximo decisor.

## 10. Integrações e falhas

| Integração | Ownership | Timeout | Retry | Circuit/reconciliation | Falha visível | Fonte de verdade |
|---|---|---|---|---|---|---|

## 11. Observabilidade

- logs estruturados:
- métricas:
- traces:
- health/readiness:
- alertas:
- SLO/SLA aplicáveis:
- dashboards:

## 12. Segurança e privacidade

- threat model:
- autenticação/autorização:
- secrets:
- dados pessoais/sensíveis:
- retenção e exclusão:
- abuso/rate limit:
- supply chain:

## 13. Critérios de aceite

| ID | Given | When | Then | Nível do teste | Evidência |
|---|---|---|---|---|---|

Cobrir ao menos:

- fluxo principal;
- cada transição inválida;
- autorização negada;
- idempotência/duplicação;
- concorrência;
- falha da integração;
- migration/backfill;
- acessibilidade da UI;
- auditabilidade;
- recovery/rollback.

## 14. Plano de entrega

- ordem de implementação:
- feature flags:
- rollout:
- dados de seed:
- compatibilidade:
- rollback/roll-forward:
- documentação/manual:

## 15. Definition Gate

- [ ] limites e casos de uso aprovados
- [ ] entidades/constraints aprovadas
- [ ] estados/comandos aprovados
- [ ] Policies/permissões aprovadas
- [ ] API/eventos aprovados
- [ ] UI e estados aprovados
- [ ] migration/rollback aprovados
- [ ] testes e evidências definidos
- [ ] observabilidade definida
- [ ] nenhuma questão bloqueante aberta

Somente após este gate o módulo pode originar Work Packages de implementação.
