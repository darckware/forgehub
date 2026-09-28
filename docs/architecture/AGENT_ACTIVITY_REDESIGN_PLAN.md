# Agent Activity — plano de redesenho (conceito + visual)

> Status: conceito **aprovado** (2026-09-28). **F1 a F5 entregues** em 2026-09-28 — ver §9 a §14.
> Tela atual: `/agent-activity` (`pages/agent-activity/index.tsx`, `components/agent-activity/*`,
> `hooks/useAgentActivity.ts`, backend `core/agent_activity.py` + `api/routes/agent_activity.py`).

Objetivo (Marcelo): *representar o funcionamento dos agentes em tempo real — o que cada agente
está fazendo, o que está processando, com quem está conversando, quais são suas tarefas
pendentes. Monitoramento completo, rastreável, com representação gráfica e contextual de todos
os processos.* Feedback sobre a versão atual: *"ficou estático e pobre"*.

---

## 1. Diagnóstico — por que a tela atual é estática

Medido no payload real de `GET /api/v1/agent-activity` em 2026-09-28 11:41 UTC:

| Sintoma | Evidência | Causa |
|---|---|---|
| Todos "Available" | 13/13 agentes `available`, `last_heartbeat_at = null`, `current_work = null` | Disponibilidade e trabalho atual vêm de `TaskExecution`/checkpoints — **0 execuções nos últimos 7 dias**. Nenhum sinal real de runtime é lido. |
| Nenhuma conversa | `message_edges = 0` | 79 mensagens em 7 dias, mas nenhuma "em voo" na janela; conversas de Telegram/Workspace/cron nem são fontes. |
| Grafo poluído e sem vida | 67 relações estáticas (membership, persistence, ai_routing…) | O grafo desenha **infraestrutura** (quem *pode* falar com quem), não **atividade** (quem *está* falando). As arestas nunca mudam, os cartões se sobrepõem e "agent / Available" se repete 13 vezes. |
| "Tempo real" só no rótulo | `refetchInterval: 5_000` sobre um snapshot | Não há eventos: nada aparece, se move ou some; não existe histórico nem replay. |

**Conclusão:** o problema principal não é visual, é de **fonte de dados**. Redesenhar só o front
produziria outra tela bonita e parada. A atividade real existe, mas em lugares que a tela não lê:

## 2. Onde a atividade real está (fontes já disponíveis)

| Pergunta | Fonte | Sinal | Latência |
|---|---|---|---|
| Está processando **agora**? | Hermes `profiles/<p>/state.db` → `session_turn_leases` | lease ativo = turno em curso (e desde quando) | segundos |
| O que está fazendo? | `state.db` → `messages` (último `tool_name`, `role`, `timestamp`) | "executando `terminal` há 42 s", "pensando", "respondendo" | segundos |
| Com quem conversa? | `state.db` → `sessions` (`source` telegram/cli/cron/tui/kanban/subagent, `chat_id`, `display_name`) | interlocutor + canal | segundos |
| Delegou algo? | `state.db` → `async_delegations` | subagente/delegação em curso, entregue ou falha | segundos |
| Está vivo? | `state.db` → `gateway_heartbeats`, `~/.hermes/gateway_state.json` | heartbeat do backend, estado do adapter Telegram | segundos |
| Quanto está consumindo? | ForgeRouter `ai_router.route_events` (`agent_id`, modelo, tokens, custo, status, `prompt_preview`) — 31 eventos/24 h hoje | cada chamada de LLM, falhas de provider | segundos |
| Conversa entre agentes | ForgeHub `agent_demands` (Messages) | mensagem, dispatch, running, resultado, retorno | segundos |
| Tarefas pendentes | `agent_demands` (Incoming/Incubação por dono), `project_tasks` + `task_assignments`, `approvals` | fila por agente | segundos |
| Rotinas | `profiles/<p>/cron/jobs.json` + `executions.db` | cron rodando, próximo run, falhas | segundos |
| Agentes externos (Porthus/Aramis/Dartan) | **só o Messages** — despacho `dispatched`/`running` para eles (`agent_demands`) | "executando mensagem #N" | segundos |

## 3. Conceito novo — "Centro de Operações dos Agentes"

A tela responde a quatro perguntas, nesta ordem de destaque:

1. **O que está acontecendo agora?** (pulso ao vivo)
2. **Quem está falando com quem?** (constelação animada)
3. **O que vem depois?** (filas e pendências por agente)
4. **O que aconteceu?** (trilha rastreável, com replay)

### 3.1 Estados reais de um agente (substituem "Available")

| Estado | Regra | Visual |
|---|---|---|
| **Pensando** | turno em curso, última mensagem do usuário/ferramenta sem resposta | halo pulsando |
| **Executando** | turno em curso, última entrada é `tool_call` sem resultado | anel girando + nome da ferramenta |
| **Conversando** | resposta enviada há < 2 min numa sessão ativa | ondas na direção do interlocutor |
| **Aguardando** | tem fila (Incoming/aprovação/incubação vencida) mas não está em turno | badge com contagem |
| **Ocioso** | sem turno; mostra "último sinal há N min" | esmaecido |
| **Degradado / Offline** | heartbeat velho, adapter `fatal`, gateway parado, profile estacionado | vermelho/cinza com o motivo |

Cada agente ganha uma **frase de atividade** em linguagem natural, montada a partir dos eventos:
*"Respondendo Marcelo no Telegram · executando `terminal` há 42 s · claude-sonnet · 12 k tokens"*.

### 3.2 Modelo de evento único

Todas as fontes são normalizadas no backend em um só formato, que alimenta todas as vistas:

```
AgentEvent {
  id, agent_id, occurred_at,
  kind: turn_started | turn_ended | tool_started | tool_ended | message_sent | message_received
      | delegation | llm_call | dispatch | cron_run | error | state_changed,
  channel: telegram | whatsapp | workspace | messages | cron | cli | subagent | api,
  counterpart: {type: human|agent|system, id, label},
  summary,            # curto, já sanitizado
  ref: {source_type, source_id, canonical_path},   # rastreabilidade (PRD)
  metrics: {tokens, cost, duration_ms, model}
}
```

## 4. Visual — composição da tela

Layout desktop (≥ 1280 px), de cima para baixo:

```
┌ Pulso ────────────────────────────────────────────────────────────────────────┐
│ 4 ativos · 2 em turno · 17 msgs/h · 184k tokens/h · US$ 3,20 hoje · 0 falhas  │  ← contadores animados + sparkline 60 min
├ Constelação viva ─────────────────────────────┬ Inspector ─────────────────────┤
│        (Telegram)      (Workspace)            │ Athos · Executando             │
│             ╲             ╱                   │ "Respondendo Marcelo…"         │
│      Aegis ● ──►── ◉ Athos ──►── ● Hephaestus │ Conversa atual (resumo)        │
│              ↖  partículas  ↘                 │ Ferramentas (últimas 10)       │
│      Scriba ○        ◎ Porthus        ○ Lara  │ Delegações · Fila · Custo      │
│   (Cron)                       (Messages)     │ Links canônicos                │
├ Raias (últimas 2 h, zoom, replay) ────────────┴────────────────────────────────┤
│ Athos     ▇▇▁▁▇▇▇▁ ▲tool ▲tool   ↓msg→Hephaestus                               │
│ Hephaestus      ▁▇▇▇▇▇▇▁                                                        │
│ Aegis  ▁ cron ▇                                                                 │
│ ◄──────────────── slider de tempo ───────────────────────────────────── agora ► │
└────────────────────────────────────────────────────────────────────────────────┘
```

- **Constelação** — layout radial determinístico (sem física aleatória, sem cartões sobrepostos):
  humanos e canais (Telegram, WhatsApp, Workspace, Cron, Messages) no anel externo, agentes no
  anel interno, Athos (orquestrador) no centro. **Só existem arestas de atividade real**: uma
  mensagem, delegação ou chamada cria uma aresta com partícula viajando de A→B que desbota em
  ~2 min. Os nós usam avatar, estado (halo/anel) e badge de fila. Infraestrutura (ForgeRouter,
  Vault, bancos, portais) sai do grafo principal e vira uma camada opcional ("mostrar infra").
- **Cartões vivos** (vista alternativa à constelação, e padrão no celular): um cartão por agente,
  com estado, frase de atividade, sparkline de tokens de 60 min, fila e último erro, ordenados por
  "mais ativo primeiro".
- **Raias (swimlanes)** — uma linha por agente: blocos de turno, marcadores de ferramenta,
  mensagens entre agentes como setas verticais entre raias e runs de cron. É a vista de
  **rastreabilidade**. Clicar em qualquer elemento abre o registro canônico.
- **Replay** — o slider de tempo reposiciona constelação e raias num instante passado.
- **Inspector** — drill-down do agente selecionado: resumo da conversa atual, ferramentas,
  delegações, tarefas pendentes (Messages/Incubação/Tasks/Aprovações), custo do dia, crons.
- **Severity inbox** é mantida, mas alimentada pelos novos sinais: turno travado > N min, adapter
  Telegram `fatal`, cron falhando, erro de provider no ForgeRouter, custo fora do padrão.

Movimento: Framer Motion (já é stack), respeitando `useReducedMotion`. Nada de biblioteca nova de
grafo — SVG + layout radial próprio (evita ADR, §7 do SPEC). Mobile: pulso + cartões vivos +
raias com scroll horizontal; a constelação vira opcional.

## 5. Arquitetura

- **Coleta por push, não por leitura** (decisão do Marcelo em 2026-09-28: *"não usar o sqlite. Use o
  banco de dados do forgehub, que é o responsável pelo ecossistema"*): os runtimes enviam os eventos
  ao ForgeHub e ele os grava no próprio Postgres. O ForgeHub nunca lê o `state.db` de um perfil. Os
  Hermes usam os webhooks nativos (`hooks.outbound`); os runtimes externos (F5) seguem o mesmo contrato.
  Complementam: `active_turns` (turnos do Workspace), `agent_demands` (fila) e ForgeRouter.
- **Stream**: `GET /api/v1/agent-activity/stream` (SSE, com `: ping` a cada 15 s, mesmas regras do
  chat) emite `AgentEvent`s e deltas de estado; o `GET` atual continua como snapshot inicial. O
  polling de 5 s é removido.
- **Persistência para replay**: tabela `agent_activity_events` (schema `company`, retenção de 14
  dias, só metadados sanitizados — nunca o conteúdo completo das conversas).
- **Frontend**: `useAgentActivityStream` (ViewModel §21 com `status`
  idle/connecting/live/reconnecting/error) + componentes `ActivityPulse`, `AgentConstellation`,
  `LiveAgentCard`, `ActivitySwimlanes`, `TimeScrubber`; o `AgentInspector` é reaproveitado.

## 6. Fases (cada uma entregável sozinha)

| Fase | Entrega | Critério de aceite |
|---|---|---|
| **F1 — Dados reais** | Coletores Hermes + ForgeRouter + Messages; estados reais e frase de atividade no payload atual | Com um agente respondendo no Telegram, a tela atual já mostra "Executando/Conversando" com o interlocutor certo em ≤ 10 s |
| **F2 — Ao vivo** | SSE + faixa de Pulso + Cartões vivos | Nova mensagem/turno aparece sem refresh em ≤ 3 s; reconexão automática visível |
| **F3 — Constelação** | Grafo radial com arestas de atividade animadas; infra como camada opcional | Nenhum cartão sobreposto a 1440 px; sem atividade, a tela mostra "calma", sem arestas estáticas |
| **F4 — Rastreabilidade** | Tabela de eventos + raias + replay | Reconstruir "o que o Athos fez entre 14h e 15h" só pela tela, com clique até o registro canônico |
| **F5 — Alertas** | Severity inbox com novos sinais (turno travado, adapter `fatal`, cron falhando, erro de provider, custo fora do padrão) | Turno travado e adapter `fatal` geram incidente |

Estimativa relativa: F1 e F4 são as maiores (backend); F2, F3 e F5 são médias.

## 7. Riscos e cuidados

- **Privacidade**: Lara atende clientes (site/WhatsApp). O conteúdo das conversas não vai para a
  tela — só canal, interlocutor mascarado ("cliente WhatsApp ···1234") e resumo técnico. Admin-only
  para qualquer detalhe além disso. `prompt_preview` do ForgeRouter não é exibido por padrão.
- **Carga**: 13 profiles × leitura de SQLite — o coletor lê incrementalmente (cursor por
  `timestamp`/id) a cada 2 s em um único loop, nunca por requisição de cliente.
- **Agentes externos não são residentes** (Marcelo, 2026-09-28: *"são agentes externo só interagem
  quando são executados pelo Messages"* / *"toda a interação dos agentes externos são pelo
  Messages"*): Porthus (claude), Aramis (codex) e Dartan (agy) não têm coleta de runtime. Só
  aparecem na tela enquanto o Messages executa uma mensagem ou tarefa para eles. O Vector (openclaw)
  não é agente registrado no ForgeHub e saiu do escopo.
- **Não duplicar Messages**: a tela é observação; ações continuam nas telas donas (Messages,
  Tasks, Governance), como no Cockpit.

## 8. Decisões pendentes (Marcelo)

1. Aprovar o conceito (constelação de atividade + raias) e a ordem das fases.
2. Retenção dos eventos para replay (proposta: 14 dias).
3. Nível de detalhe das conversas na tela (proposta: só resumo técnico; conteúdo apenas no link).
4. Incluir Marcelo/humanos como nós da constelação (proposta: sim, no anel externo).

## 9. Entrega da F1 (2026-09-28)

- **Tabela** `company.agent_activity_events` (migration `a7c2e9f4b1d6`), só metadados: tipo, sessão,
  turno, canal, interlocutor mascarado, modelo, ferramenta, status e duração. Retenção de 14 dias
  (`_agent_activity_retention_loop`).
- **Endpoint** `POST /api/v1/agent-activity/events`: público no middleware, autenticado por HMAC
  (`AGENT_ACTIVITY_WEBHOOK_SECRET` no `.env` do ForgeHub = `FORGEHUB_ACTIVITY_WEBHOOK_SECRET` no
  `.env` de cada perfil). É idempotente por `delivery_id` e descarta o histórico da conversa que o
  webhook traz.
- **Hermes**: os 10 perfis principais ganharam `hooks.outbound` (`pre_llm_call`, `pre_tool_call`,
  `post_tool_call`, `on_session_end` → `http://127.0.0.1:8000/...`). Backup em
  `profiles/athos/state-snapshots/agent-activity-webhooks-2026-09-28/`.
- **Estado ao vivo** (`core/agent_live_state.py`): executing, thinking, conversing, waiting,
  degraded e idle; exposto em `GET /agent-activity` como `agents[].live`. Um turno aberto há mais de
  30 min é tratado como abandonado.
- **UI**: o cartão de cada agente mostra a frase de atividade no lugar de "agent / Available"; o
  inspector ganhou o bloco "Agora" (turnos, ferramentas e falhas na última hora, e pendências).
- Validado com um turno real do Atlas: início, `terminal` por 15 s, fim, tudo visível na API em
  segundos.

## 10. Entrega da F2 (2026-09-28)

- **Stream** `GET /api/v1/agent-activity/stream` (SSE, `event: snapshot`), em
  `core/agent_activity_stream.py`. Envia um snapshot completo ao conectar, ~0,3 s depois de cada
  evento de runtime (broadcaster em memória, com rajadas agrupadas) e a cada 10 s. Snapshots inteiros
  em vez de deltas: uma conexão perdida nunca deixa o cliente num estado que o servidor não tem.
  Cada frame abre a própria sessão de banco.
- **Pulso**: agentes ativos/total e quantos estão em turno, turnos na última hora com barras por
  minuto, ferramentas, chamadas de LLM, tokens na última hora, custo do dia (ForgeRouter, cache de
  30 s; "—" quando o ForgeRouter está fora, nunca zero), falhas e pendências.
- **Cartões vivos** (visão padrão; a Topologia continua como alternativa): um cartão por agente, com
  estado, frase de atividade, sparkline de 60 min, tokens, pendências e falhas. Mais ativos primeiro,
  reordenação animada e uma faixa animada no topo enquanto o agente está num turno.
- **Agentes externos**: estado derivado do despacho do Messages (`source="messages"`,
  `message_number`); fora da tela quando parados, na Topologia também.
- **Frontend**: `useAgentActivityStreamViewModel` (§21: `idle → connecting → live → reconnecting →
  error`, backoff de 1/2/5/10 s, conexão muda por 25 s é derrubada e refeita). Com o stream ativo, o
  read model completo passa a atualizar a cada 30 s em vez de 5 s.

## 11. Entrega da F3 (2026-09-28)

- **Constelação** (`AgentConstellation.tsx`), que substitui a topologia antiga; os arquivos
  `ActivityTopology`, `TopologyNode`, `useTopologyPositions` e `useAgentActivityViewModel` foram
  removidos. Layout radial determinístico (`constellationLayout.ts`): Athos no centro, os outros
  agentes num anel em ordem de nome, e Você / Contatos / Sistema (e ForgeRouter, na camada de
  infraestrutura) em pontos fixos por fora. As dimensões (viewBox 1000×760, anel 310×250, nós de
  96 px) foram escolhidas por busca para que de 1 a 12 agentes no anel nunca se sobreponham; um
  teste garante isso.
- **Só atividade real**: o snapshot ganhou `links` (últimos 5 min) — conversas (quem → agente, por
  qual canal), turnos do Workspace e mensagens do Messages entre agentes. Um link ativo tem partícula
  animada; depois de encerrado, esmaece até um traço fraco. As linhas de fora curvam por fora do anel
  e as de agente para agente por dentro, sem passar por cima dos nós. Sem atividade: "Tudo calmo".
- **Infraestrutura** opcional: ForgeRouter ligado aos agentes que usaram LLM na última hora, com
  espessura proporcional aos tokens.
- Lista textual das interações recentes e dos registros de mensagem abaixo do gráfico
  (acessibilidade). Com movimento reduzido, não há partículas.
- Validado em produção com um turno real do Atlas a 1440 px e 390 px: linha Você → Atlas com
  partícula, "Pensando · 15 s", nenhum nó sobreposto, sem rolagem horizontal.

## 12. Ajustes pós-F3 (2026-09-28)

- **Canal "site" da Lara**: o darckware chama o host-bridge (`/v1/chat`) com `channel="site"`, e o
  turno roda em `profiles/lara/channels/site`. O `cwd` é o único campo do webhook que o chamador
  controla, então `normalize_hermes_hook` reconhece `/channels/<canal>` e registra o interlocutor
  como contato externo (`human`), nunca como o operador no terminal. Na constelação: "Contatos →
  Lara" pelo canal "Site darckware" (ícone de globo). A Lara do site responde sempre pelo Hermes —
  o fallback direto ao ForgeRouter foi removido no darckware (ele escondia um token de bridge errado
  fixado no `docker-compose.yml` de lá, que devolvia 401 em todo turno).
- **`AgentDemand.dispatched_at`** (migration `b3d8f1a6c2e9`): quando o despacho mais recente
  começou. O `dispatch_deadline_at` é limpo ao fim do run, então um run terminado tinha fim
  (`task_execution_at`) mas não início. Base para as raias e o replay da F4; linhas antigas caem
  para `scheduled_at`.
- Validado em produção: turnos reais da Lara pelo site gravados com `platform=site`,
  `counterpart_kind=human`, e o link correspondente gerado para a constelação.

## 13. Entrega da F4 — rastreabilidade (2026-09-28)

- **`GET /api/v1/agent-activity/timeline?start&end&agent_id`** (`core/agent_activity_timeline.py`):
  raias por agente numa janela de até 24 h (padrão 2 h, nunca além da retenção de 14 dias). Três
  fontes, todas registros do próprio ForgeHub: turnos do runtime com suas ferramentas
  (`agent_activity_events`, pareados início/fim por `pair_runtime_events` — mesma regra do estado ao
  vivo: sem fim após 30 min é "abandonado"), execuções do Messages (`dispatched_at` →
  `task_execution_at`) e turnos do Workspace (`active_turns`); mais as mensagens entre agentes (setas
  entre raias) e a tabela de eventos (até 2.000 linhas; `truncated` avisa).
- **Replay** — `GET /api/v1/agent-activity/snapshot?at=`: o mesmo frame do stream, reconstruído no
  instante pedido (`build_live_snapshot(historical=True)`). Todas as leituras limitadas ao instante;
  fila e custo do ForgeRouter não têm passado registrado e ficam de fora ("—"/0), em vez de mostrar
  os de hoje como se fossem de então. No modo ao vivo nada mudou (o limite só vale no replay, para um
  relógio de runtime levemente adiantado não sumir com um evento).
- **Frontend**: vistas "Raias" (padrão) e "Eventos" no seletor operacional
  (`ActivitySwimlanes`, `ActivityEventTable`), estado em `useActivityTraceViewModel` (janela
  1/2/6/24 h ou período, cursor, reprodução a 60×). Clicar na raia (ou setas do teclado) move o
  cursor; com o cursor no passado, cartões, constelação e pulso mostram aquele instante, com faixa
  "Replay de …" e botão "Ao vivo". Um bloco abre o detalhe (duração, ferramentas, modelo, sessão) com
  "Reproduzir daqui" e o link para o registro canônico (agente, mensagem ou Workspace). Filtro por
  agente só quando o usuário escolhe um (não pelo incidente que o inspector abre sozinho).
- Validado em produção a 1440 e 390 px: turnos do site da Lara nas raias, detalhe, replay no turno
  (Lara "pensando", Contatos → Lara ativo) e tabela de eventos; sem rolagem horizontal da página.

## 14. Entrega da F5 — alertas (2026-09-28)

`core/agent_activity_alerts.py` alimenta a caixa de severidade (só na visão sem filtro de projeto)
com cinco sinais novos, cada um lido de onde é verdade e opcional (fonte fora = sem alerta daquela
fonte, nunca "tudo certo" falso; cache de 60 s, timeout de 5 s):

| Sinal | Regra | Severidade |
|---|---|---|
| `turn_stuck` | turno mais recente do agente sem fim há ≥ 10 min | aviso; erro a partir de 30 min |
| `adapter_fatal` | Telegram configurado e adapter do gateway fora de `connected` | crítico se `fatal`, senão erro |
| `cron_failing` | cron habilitado com última execução em erro, ou atrasado | erro / aviso |
| `provider_error` | ≥ 3 chamadas não-`success` no ForgeRouter em 15 min | aviso; erro a partir de 9 |
| `usage_anomaly` | tokens de hoje > 3× a média diária dos 7 dias anteriores (e ≥ 200 k), ou custo > 3× (e ≥ US$ 1) | aviso (tokens) / erro (custo) |

Tokens contam além do custo porque quase tudo neste host custa US$ 0 (modelos gratuitos/assinatura)
— um alerta só de custo nunca dispararia. Serviços do ForgeRouter (ex.: Hindsight) não viram
incidente de agente. A leitura do estado do Telegram saiu da rota para
`agent_telegram.read_telegram_platform_states`, compartilhada com a tela de Agentes.

Na primeira execução em produção, os sinais apontaram quatro crons do Athos falhando de fato
(`daily_hermes_update_check`, `docker-daily-cleanup`, `foundation-clear`, `memory-maintenance`:
"cron external worker exited before ownership acknowledgement").
