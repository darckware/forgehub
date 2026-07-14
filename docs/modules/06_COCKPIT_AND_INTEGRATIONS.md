# Módulo 06 — Cockpit Diário, Controle Humano/Agente e Integrações

## 1. Objetivo

Oferecer a visão operacional única para acompanhar, decidir, delegar e ajustar todos os macrofluxos. Integrações projetam ou executam ações; o Cockpit deriva estado do ForgeHub e nunca de narrativa isolada da LLM.

## 2. Read models

- `project_daily_status`: macrofluxo/Stage/baseline/controller/readiness.
- `scope_coverage_summary`: counts e gaps por family/track/stage.
- `work_in_progress`: waves/tasks/executions/leases/heartbeats/cost.
- `decision_inbox`: approvals, CRs, overrides, blocks.
- `release_environment_status`: candidates/deliveries/health.
- `eligible_actions`: command, reasons, authority, budget, preconditions.

Read models são reconstruíveis de tabelas/eventos e trazem `calculated_at`/input revision. LLM pode resumir, não alterar números.

## 3. Delegation e controle

Athos é o grantee padrão da delegação de coordenação do Project e o usuário é o grantor/autoridade final. Athos pode analisar, planejar, formar equipe, criar waves, liberar Tasks elegíveis e tratar rework conforme limites; approvals reservadas, exceções, expansão de escopo e produção permanecem humanas quando a Policy assim definir.

### `delegations`

`id`, grantor human, grantee agent/membership, Product/Project/Stage/scope, allowed commands, risk/environment limits, budget/WIP/iterations, approvals retained by human, valid_from/to, status.

- status `draft|active|paused|revoked|expired|completed`.
- comandos `GrantDelegation`, `PauseDelegation`, `RevokeDelegation`, `TakeControl`, `ReturnControl`.
- Cockpit exibe controller/next decision owner/autonomy boundary.

## 4. Cockpit

Views:

- Portfolio: products/versions/projects e macrofluxo.
- Daily Project: template `DAILY_ENGINEERING_REVIEW` preenchido por dados.
- System Map/Coverage matrix.
- Planning Release: baseline e waves.
- Execution Control: CLIs, leases, costs, blocks.
- Decision Inbox.
- Release/Operations.
- Timeline/Audit/traceability.

Usuário pode filtrar, simular impacto, aprovar, pausar, assumir controle ou delegar. Agente pode propor e executar somente eligible actions.

## 5. Integrações

| Integração | Papel | Fonte de verdade |
|---|---|---|
| ForgeFlow | workspace/CLI adapter/checkpoint/outbox | ForgeHub em managed mode |
| Claude/Codex/Agy | execução de Work Package | TaskExecution/Result no ForgeHub |
| ForgeRouter | roteamento/model/custo | runtime profile + usage reconciliado |
| Git/GitHub | source/commit/PR/checks | evidência externa referenciada; estado de domínio no ForgeHub |
| CI | build/test/security evidence | evidence/build records |
| Kanboard | projeção visual | ForgeHub; inbound vira command validado |
| Hermes Foundation | identidade/skills/org source | Foundation canônica; membership local no ForgeHub |
| Hindsight | memória semântica | auxiliar; decisões no ForgeHub |
| observabilidade | signals/checks | fonte técnica do sinal; interpretação/estado no ForgeHub |

Cada adapter define health, capability, timeout, retry, idempotency, cursor/webhook, reconciliation, ownership e redaction.

## 6. Inbound reconciliation

Evento externo nunca faz UPDATE direto de status. Fluxo:

```text
receive -> authenticate -> deduplicate -> map identity/revision
        -> validate domain command -> apply/reject
        -> audit -> update projection
```

Eventos sem mapping ficam em integration inbox para reconciliação; não são descartados nem aplicados por aproximação.

## 7. Daily review automation

`GenerateDailyReview` calcula snapshot; LLM opcional produz resumo citando IDs. Operador/agente registra decisão do dia. Handoff contém revisões, ações elegíveis e bloqueios. Próxima sessão começa desse snapshot, não da conversa anterior.

## 8. APIs/UI

- `GET /api/v1/cockpit/portfolio`
- `GET /api/v1/projects/{id}/daily-status|coverage|eligible-actions|timeline`
- `POST /api/v1/projects/{id}/daily-reviews`
- `/api/v1/delegations` + commands pause/revoke/take-control/return-control.
- `/api/v1/integrations/{adapter}/health|reconcile`
- `/api/v1/integration-inbox` e resolve/reject commands.

## 9. Critérios de aceite

1. Cockpit é reconstruível sem LLM.
2. Outra LLM continua pelo Daily Review/handoff.
3. Usuário assume ou devolve controle sem perder execução/histórico.
4. Agente não executa command fora da delegação.
5. Kanboard/Git/CI repetidos não duplicam transição/evidência.
6. Evento externo inválido fica visível e não corrompe domínio.
7. Custos/readiness/gaps citam fonte/revisão.
8. Portfolio cobre sistema completo e componente isolado.
9. Integração indisponível produz estado degradado/bloqueio explicável.
