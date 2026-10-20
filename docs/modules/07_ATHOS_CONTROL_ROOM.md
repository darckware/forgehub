# Módulo 07 — Athos Control Room e Browser Assistido

## 1. Objetivo

Criar uma tela dentro do ForgeHub para o usuário acompanhar Athos operando o sistema, navegar pelo mesmo contexto e interagir pelo Assistant existente. Athos continua usando commands/APIs governadas; o browser é visualização, navegação e controle humano, não automação frágil por clique em DOM.

Rota proposta: `/athos`.

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Product / Project / Stage | Controller: Athos | Follow | Pause | Take│
├──────────────────────────────────────┬───────────────────────────────┤
│ ForgeHub Browser                     │ Athos Assistant               │
│                                      │                               │
│ rota/entidade que Athos está usando  │ plano e raciocínio resumido   │
│ dados, mapa, plan, wave, execution    │ ação proposta/executada       │
│                                      │ approvals e perguntas         │
│ usuário também pode navegar          │ ChatPane reutilizado          │
├──────────────────────────────────────┴───────────────────────────────┤
│ Activity timeline | events | evidence | errors | next eligible action│
└──────────────────────────────────────────────────────────────────────┘
```

## 2. Princípios

1. Athos opera o ForgeHub por commands de domínio autenticadas.
2. Cada command produz `OperatorAction` persistida antes/depois da execução.
3. O browser segue o `focus_ref` da ação; não simula que clique equivale a comando.
4. O usuário pode desligar “Follow Athos” e navegar sem alterar o foco operacional.
5. Ações humanas na tela usam as mesmas APIs e registram actor humano.
6. Assistant nunca submete formulário/approval silenciosamente; prepara e solicita confirmação conforme Policy.
7. Pause/Take Control interrompe novos commands automáticos, preservando execuções em andamento.

## 3. Reuso do frontend atual

- Extrair de `AssistantDrawer` um `AssistantPanel` reutilizável.
- `AssistantDrawer` continua usando `AssistantPanel` em modo drawer.
- Athos Control Room usa o mesmo painel em modo docked, com Agent Athos fixado.
- Reutilizar `ChatPane`, assistant store/context, anexos, streaming e form-fill controlado.
- Não montar um segundo `AppLayout` dentro da visualização.

### Browser pane

Implementação preferencial:

- shell próprio com address/breadcrumb lógico, back/forward e open-in-main-view;
- preview same-origin em modo `embed`, sem sidebar/global Assistant duplicados;
- allowlist somente para rotas internas do ForgeHub;
- comunicação pai/preview por mensagens tipadas e origin check;
- alternativa progressiva: renderizar Entity Inspectors diretamente antes do preview genérico.

Não aceitar URL externa arbitrária. Conteúdo de GitHub/ForgeRouter usa adapters/telas específicas e suas Policies.

## 4. Entidades

### `operator_sessions`

`id`, `controller_type`, `controller_id`, `delegation_id`, `product_id`, `project_id`, `status`, `started_at`, `paused_at`, `ended_at`, `last_heartbeat_at`.

- status `active|paused|waiting_human|completed|cancelled|failed`.
- Athos é controller padrão com delegação; usuário pode assumir.

### `operator_actions`

`id`, `operator_session_id`, `sequence`, `actor_type/id`, `command_name`, `target_type/id`, `input_revision/hash`, `status`, `reason`, `started_at`, `finished_at`, `result_ref`, `error_code`.

- status `proposed|waiting_approval|authorized|running|succeeded|failed|blocked|cancelled|stale`.
- append-only para resultado; correção cria nova action relacionada.

### `operator_focus_events`

`id`, `operator_session_id`, `sequence`, `focus_type`, `entity_type/id`, `route`, `label`, `source_action_id`, `occurred_at`.

- foco é projeção; não concede autoridade.

## 5. Componentes da tela

### Header de controle

- Product/Version/Project/Stage/Wave.
- controller atual e autonomy mode/boundary.
- conexão/heartbeat de Athos.
- Follow Athos toggle.
- Pause, Take Control, Return Control.
- alertas de approval/block/budget.

### Athos Browser

- route breadcrumb e entidade/revision.
- back/forward/follow current focus.
- banner `Viewing Athos focus` ou `Exploring independently`.
- highlight dos elementos/scope IDs envolvidos na action.
- diff/readiness/evidence drawer quando aplicável.

### Assistant docked

- Agent Athos fixado, identidade visível.
- conversa persistida por operator session/Project.
- cards estruturados para plan, proposed command, approval request, result, block e handoff.
- botões usam commands elegíveis recebidas do backend; não parseiam texto livre para executar ação crítica.
- texto/fenced form-fill existente permanece somente para preencher drafts, nunca salvar/aprovar.

### Activity timeline

- actions humanas/sistema/Athos ordenadas por sequence.
- command, target, state, duração, custo, result/evidence.
- filtro proposed/running/blocked/failed/approval.
- clicar sincroniza Browser e Assistant context.

## 6. Fluxos

### Acompanhar Athos

1. usuário abre `/athos` e escolhe Project;
2. backend abre/retoma operator session;
3. Athos calcula eligible action e registra proposal/focus;
4. browser navega ao target se Follow ativo;
5. Assistant explica objetivo, precondições e efeito;
6. Policy autoriza automaticamente ou solicita usuário;
7. command executa; timeline/result/readiness atualizam.

### Usuário assume

1. `TakeControl` pausa novos commands de Athos;
2. running actions entram em safe-stop/reconciliation conforme tipo;
3. controller muda após confirmação persistida;
4. usuário navega/executa commands;
5. `ReturnControl` emite nova delegação/revision/handoff.

### Planejamento e liberação

- Athos usa Browser para mostrar System Map, ProjectScope, plan e tarefas `planned`.
- Assistant apresenta Planning Preflight e inelegibilidades.
- Baseline/Delivery Authorization e ExecutionWave aparecem como cards de decisão.
- Somente após approval/activation o Browser mostra Tasks `ready` e execuções Claude/Codex/Agy.

## 7. APIs e streaming

- `POST /api/v1/operator-sessions`
- `GET /api/v1/operator-sessions/{id}`
- `POST .../{id}:pause|:resume|:take-control|:return-control|:close`
- `GET /api/v1/operator-sessions/{id}/actions`
- `POST /api/v1/operator-actions/{id}:authorize|:reject|:cancel`
- `GET /api/v1/operator-sessions/{id}/eligible-actions`
- SSE/WebSocket `/api/v1/operator-sessions/{id}/stream` para action/focus/readiness/approval/heartbeat.

Stream é conveniência; reconnect usa cursor/sequence e reconstrói do banco.

## 8. Segurança

- rotas internas allowlisted e IDs autorizados;
- preview same-origin com modo embed e CSP adequada;
- `postMessage` valida origin/schema/session nonce;
- nenhum token/secret aparece em route, chat ou timeline;
- command cards vêm do backend e possuem ID/revision/expiry;
- proteção contra clickjacking/recursão do próprio Control Room;
- approvals críticas exigem confirmação fora do conteúdo gerado pela LLM;
- logs/chat passam por redaction/retention.

## 9. Entrega incremental

1. **Shell read-only:** split view, AssistantPanel docked, Project selector e timeline mock/read model.
2. **Focus follow:** operator session/focus events e preview de rotas internas.
3. **Command proposals:** cards backend, approvals e resultados.
4. **Live control:** streaming, pause/take/return e heartbeat.
5. **Full orchestration:** waves, CLIs, review, release e operations integrados.

Fases 1–2 podem ser entregues antes de toda a automação; não devem fingir que Athos executou commands inexistentes.

## 10. Critérios de aceite

1. AssistantDrawer e Control Room reutilizam o mesmo AssistantPanel sem regressão.
2. Athos fica fixado como Agent da sessão.
3. Follow Athos navega pelo focus persistido e pode ser desligado.
4. Timeline reconstrói após refresh/reconnect.
5. Usuário pausa/assume/devolve controle com AuditEvent.
6. Browser não abre URL externa arbitrária nem duplica AppLayout/Assistant.
7. Texto da LLM não executa command crítico sem card/autorização backend.
8. Planejamento mostra Tasks planned; execução só aparece após ExecutionWave.
9. Erro/bloqueio apresenta causa, evidência e ação segura.
10. Tela funciona em desktop split; mobile alterna Browser/Assistant/Activity por tabs.
