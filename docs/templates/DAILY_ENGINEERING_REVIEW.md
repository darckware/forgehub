# Daily Engineering Review — `<date>`

## Identificação

```yaml
product_id: <uuid>
product_version_id: <uuid>
project_id: <uuid>
baseline_id: <uuid|null>
macroflow: conception | delivery | operations
pipeline_stage_id: <uuid|null>
reviewed_by: <identity>
current_controller: human | agent
autonomy_mode: manual | assisted | supervised | delegated
```

## 1. Estado calculado

| Dimensão | Atual | Esperado | Desvio | Fonte |
|---|---|---|---|---|
| escopo | | | | |
| stage/gates | | | | |
| tasks/executions | | | | |
| custo/capacidade | | | | |
| release/ambientes | | | | |
| saúde operacional | | | | |

## 2. Cobertura do System Blueprint

| Grupo | Total | Specified | Planned | Implemented | Verified | Delivered | Blocked |
|---|---:|---:|---:|---:|---:|---:|---:|

Elementos sem cobertura ou `not_applicable` justificado:

- `<stable_key>` — `<gap>`

## 3. Trabalho em andamento

| Task/Execution | Owner | Runtime | Lease/heartbeat | Último checkpoint | Parou em/motivo | Estado | Próxima ação segura |
|---|---|---|---|---|---|---|---|

## 3.1 Conclusão das etapas

| Stage | Requisitos | Confirmados | Faltantes | Assessment | Última confirmação | Pode concluir? |
|---|---:|---:|---|---|---|---|

## 4. Bloqueios, riscos e divergências

| ID | Tipo | Impacto | Evidência | Opções seguras | Autoridade necessária |
|---|---|---|---|---|---|

## 5. Decisões pendentes

| Decisão | Prazo | Recomendação do agente | Alternativas | Decisor |
|---|---|---|---|---|

## 6. Mudanças desde a última revisão

- baseline/Change Requests:
- decisões:
- artifacts:
- código/migrations:
- Policies/approvals:
- releases/deployments:

## 7. Ações elegíveis

| Prioridade | Ação calculada | Precondições | Ator elegível | Aprovação | Budget |
|---:|---|---|---|---|---:|

Uma recomendação narrativa não transforma uma ação inelegível em elegível.

## 8. Controle e delegação

- continuar no modo atual:
- pausar/revogar:
- assumir controle humano:
- delegar ao agente:
- limites revisados:

## 9. Decisão do dia

```yaml
approved_actions: []
rejected_actions: []
paused_actions: []
change_requests_to_open: []
delegation_changes: []
notes: <text>
```

## 10. Handoff

- concluído:
- pendente:
- bloqueado:
- artifacts/revisões vigentes:
- riscos residuais:
- primeira ação segura da próxima sessão:
