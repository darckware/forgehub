# Messages — guia completo

Última atualização: 2026-11-19
Público: Marcelo (operador) e quem mantém o código.
Contrato de processo para os agentes: Foundation `30_docs/FORGEHUB_MESSAGE.md`.
Referência de engenharia do despacho: `docs/architecture/MESSAGES.md`.

Este guia junta num só lugar o que o Messages é, como uma mensagem anda, quem decide cada
passo, onde cada situação aparece na tela e o que já foi decidido para amadurecer o controle
das tarefas dos agentes.

---

## 1. O que é o Messages

O Messages é o canal único de trabalho entre agentes. É por ele que um pedido chega, é executado
pelo agente certo, e o resultado fica registrado. Toda execução de agente passa por aqui: tarefas
de projeto, missões, rotinas, checagens de falha e pedidos de manutenção.

- **Mensagens** (`/demands`) mostra o tráfego: o que chegou, o que saiu, o que está rodando, o que
  falhou e o que terminou.
- **Pessoal → Tarefas dos agentes** é onde o operador **decide**: aprova, reconcilia, reprocessa,
  arquiva e responde.

Tabela principal: `company.agent_demands` (modelo `AgentDemand`, `db/models/demand.py`).

## 2. Conceitos

| Conceito | Campo | Significado |
|---|---|---|
| Tipo | `origin_type` | `task` (trabalho executável) ou `incubation` (ideia estacionada até o dono decidir). Obrigatório. |
| Remetente / executor | `from_agent_id` / `target_agent_id` | Uma Task exige os dois. Sem destinatário, a Task é endereçada ao próprio remetente. |
| Dono da incubação | `incubation_owner_id` | Toda incubação tem dono (restrição no banco). |
| Diretório | `working_path` | Onde o agente começa a trabalhar. Precisa ser o diretório real do projeto. |
| Meio de comunicação | `channel` / `channel_ref` | Por onde o pedido chegou e para onde devolver o resultado (Telegram, WhatsApp, agente). |
| Resultado | `dispatch_result` | A resposta do agente, gravada na própria mensagem. |
| Retorno | `reply_to_id` | Mensagem de volta, criada só quando `requires_response` foi pedido. |
| Checagem de falha | `failure_check_source_id` | Tarefa de diagnóstico ligada à falha que ela investiga. |
| Consolidação | `consolidated_into_id` | A mensagem foi resumida num item de incubação. |
| Aprovação | `requires_approval` / `approval_status` / `approved_content_hash` | Só roda depois da aprovação do Marcelo. Editar o texto depois de aprovado anula a aprovação. |

### Três estados que não se confundem

| Estado | Campo | Diz |
|---|---|---|
| Ciclo da mensagem | `status` | Se está ativa ou arquivada. |
| Execução | `dispatch_status` | `NULL` (na fila ou nunca executada), `dispatched`, `running`, `completed`, `failed`, `waiting_quota`. |
| Leitura pelo agente | `agent_processed_at` | O agente viu. Não prova execução nem entrega. |

## 3. Grupos da tela Mensagens

Cada mensagem fica em **um** grupo por vez.

| Grupo | O que entra |
|---|---|
| **Entrada** | Trabalho recebido (inclusive o que o agente mandou para si mesmo) que ainda não começou a rodar. |
| **Saída** | Trabalho encaminhado a outro agente que ainda não começou a rodar. |
| **Incubação** | Ideias estacionadas. Nunca executam sozinhas. |
| **Execução** | Em execução, ou autorizada e aguardando vaga/executor (inclui a espera de cota). |
| **Falhas** | Execução falhou: falha conhecida ou resultado incerto. |
| **Finalizado** | Concluído com `STATUS: DONE`, ou entrega verificada. |
| **Arquivadas** | Histórico preservado. Arquivar não conclui, não cancela e não autoriza nada. |

As **etiquetas** de cada linha (`core/message_classification.py`) explicam por que ela está
parada, por exemplo `executor_busy` com o número da execução que segura o agente.

## 4. Como uma tarefa anda

```
criada ──► fila ──► reserva de vaga ──► execução ──► relatório final
            │            │                              │
            │            └─ espera: vaga global,        ├─ STATUS: DONE ─────► completed
            │               agente ocupado, dependência,│
            │               aprovação, pergunta         ├─ PARTIAL / BLOCKED / sem linha ► failed (conhecida)
            │                                           ├─ BLOCKED | AUTORIZAÇÃO ► volta para Aprovação
            │                                           ├─ BLOCKED | AGUARDANDO RESPOSTA ► completed (aguardando)
            │                                           ├─ limite de cota ─► waiting_quota / outro agente
            │                                           └─ sem resposta do runner ─► failed (incerta)
            └─ agendada (scheduled_at) espera a hora
```

Regras:

- **Uma reserva só** (`core/demand_dispatch_guard.py:reserve_dispatch`). Dois cliques, ou o
  worker mais um clique, nunca iniciam duas execuções.
- **Capacidade**: no máximo 5 execuções simultâneas no total (`MAX_CONCURRENT_DISPATCHES`,
  ajustável até 20) e **uma por agente**. Um agente ocupado é pulado, não trava a fila dos outros.
- **Prazo**: 45 min por execução (`DISPATCH_TIMEOUT_MINUTES`). Passou disso, o resultado vira
  incerto; nunca vira "concluído".
- **Tentativas**: 3 (`DISPATCH_MAX_ATTEMPTS`). O contador nunca é zerado; "Autorizar nova
  tentativa" aumenta o limite.
- **Relatório final obrigatório**: só `STATUS: DONE` com evidência registra `completed`.
- **Dependências** de tarefa de projeto: só roda quando as predecessoras estão `done`/`deployed`.

## 5. Falhas

### Falha conhecida

O agente respondeu `PARTIAL`, `BLOCKED` ou não deu a linha final. O motivo fica em
`dispatch_error` e a resposta em `dispatch_result`.

- O sistema cria automaticamente uma **checagem de falha** (`core/demand_failure_check.py`): uma
  tarefa de diagnóstico ligada à original. Ela responde com a linha
  `ORIGEM: CONCLUIDA | PARCIAL | BLOQUEADA`.
- Enquanto a checagem está aberta, a falha não vai para as Decisões do operador.
- Saídas: **Reprocessar** (dentro do limite), **Autorizar nova tentativa**, ou **Arquivar**.

### Resultado incerto

O runner não confirmou o fim: prazo estourado, run sem resposta, ou erro com "uncertain".

- **Segura a vaga do agente**: a fila daquele agente para até alguém decidir. As tarefas paradas
  atrás dela aparecem com a etiqueta `executor_busy` citando o número que segura o agente.
- Bloqueia **arquivar, excluir e reprocessar**.
- Saídas: **Reconciliar** (pergunta de novo ao runner) ou **Confirmar inativa** (exige motivo,
  evidência e o identificador da execução digitado de novo). Confirmar inativa transforma em falha
  conhecida, sem executar nada.

## 6. Limite de cota do agente

`core/agent_availability.py` reconhece a mensagem de limite de cada runtime (Claude, Codex, agy).

- Trabalho comum volta para a fila e o despacho passa para o próximo agente externo livre
  (codex → agy → claude).
- Ficam no mesmo agente e esperam o reset: tarefa de missão, texto aprovado, checagem de falha e
  mensagem com `fixed_agent`. Ficam em `waiting_quota` e são reagendadas para o reset + 5 min.
- `core/quota_wait.py:release_due_quota_waits` só retoma sozinho quando o reset é conhecido e o
  contexto não mudou. Senão, o motivo aparece no botão:
  `quota_reset_unknown`, `quota_reset_pending`, `quota_context_changed`,
  `quota_run_evidence_missing`.
- Com reset desconhecido, o despacho trata o agente inteiro como ocupado.

## 7. Incubação

- Sempre tem dono e prazo (`matures_at`, padrão 3 dias).
- No prazo, `run_incubation_maturation_pass` muda para `decision_pending` e devolve ao dono para
  decidir (receber como Task ou descartar com motivo). Descartar é arquivar com `drop_reason`,
  nunca apagar.
- O operador também decide pela tela: aprovar (vira Task na fila), adiar, descartar.

## 8. Aprovação do Marcelo

- `requires_approval` pendente: nada executa, nem é entregue na caixa do agente.
- Aprovar grava o hash do texto e coloca na fila. Recusar nunca executa.
- O agente pode parar pedindo autorização (`STATUS: BLOCKED | AUTORIZAÇÃO: …`); a mesma mensagem
  volta para Aprovação e, aprovada, roda de novo dizendo o que foi autorizado.
- Moodle, missões e pedidos do grupo STI têm fluxo próprio de aprovação, todos em
  Pessoal → Tarefas dos agentes.

## 9. Arquivar e excluir: uma regra para as duas telas

Uma recusa é sempre um 409 com `{code, message, number}`, e a tela mostra o motivo
(`frontend/src/lib/demandRuleError.ts`). Em ações em lote, cada item é tentado e os recusados são
listados com o motivo.

| Código | Quando |
|---|---|
| `EXECUTION_ACTIVE` | A mensagem está executando. |
| `RECONCILIATION_REQUIRED` | Resultado incerto: reconcilie ou confirme inativa antes. Vale para excluir **e** arquivar. |
| `EXECUTION_CHECK_EVIDENCE` | É evidência de uma checagem de execução. |
| `SUMMARY_HAS_HISTORY` | É um resumo com registros consolidados. |
| `MOODLE_APPROVAL_HISTORY` | Ligada a uma aprovação Moodle: nunca é excluída. |
| `MOODLE_FLOW_REQUIRED` | Mensagem Moodle só é arquivada depois que o fluxo terminou (finalizado ou recusado). |
| `OPEN_SUMMARY` | Edite pelo resumo atual. |

Arquivar preserva tudo (resultado, histórico, vínculos). Excluir só vale para o que não tem
história a preservar.

## 10. Retenção

`run_demand_retention_sweep`, a cada 6 h, **arquiva** (nunca apaga) mensagens `completed`/`failed`
sem alteração há 60 dias (`DEMAND_RETENTION_DAYS`). Entrada, Saída, Execução e Incubação nunca são
tocadas pela retenção.

## 11. Pessoal → Tarefas dos agentes (Fase 1, 2026-11-19)

Lê `GET /api/v1/demands/agent-work` (`core/demand_management.py`). Para cada item o backend
calcula `allowed_actions`, `blocked_actions` (com o motivo) e `stuck` (por que está travado e desde
quando), então a tela nunca decide sozinha o que é permitido.

**Resumo no topo**: Travadas, Aprovações, Perguntas, Em andamento, Aguardando. Cada quadro abre a
aba correspondente.

| Aba | Conteúdo |
|---|---|
| Em andamento | O que executa, está na fila ou aguarda com data. Sem Resolvidas/Arquivadas: tarefa encerrada fica em Mensagens. |
| Decisões | **Só o que está travado** (visão `stuck`, grupo `decisions`), com o motivo na linha. |
| Incubações | Ideias por estado. |
| Aprovações | Tarefas aguardando autorização, Moodle, missões e aprovações de tarefa de projeto. |
| Respostas | Perguntas dos agentes pendentes (bloqueantes primeiro). |

Motivos de travamento (`stuck.reason`, `stuck_wait_sql` + `stuck_reason`):

| Código | Quando |
|---|---|
| `uncertain_run` | Execução incerta; `held` = tarefas do mesmo agente paradas atrás dela. |
| `failure_unresolved` | Falha sem checagem aberta. |
| `retry_limit` | Falha com o limite de tentativas atingido. |
| `quota_reset_unknown` | Cota sem horário de reset. |
| `quota_not_resumed` | Reset passou há mais de 30 min e a tarefa não retomou (`blocker` diz por quê). |
| `queue_stuck` | Tarefa devida há mais de 30 min que não começou, sem execução viva do mesmo agente à frente (`detail` traz a causa; atrás de execução incerta, o Analisar diz qual segura a fila). |
| `incubation_overdue` | Decisão do dono vencida há mais de 3 dias. |
| `approval_pending` / `blocking_question` | Marcados no item, mas listados nas abas Aprovações e Respostas. |

**Analisar** (botão em cada linha; `GET /api/v1/demands/{id}/brief`, `core/demand_brief.py`): só regras
fixas, sem modelo, calculado na hora a cada abertura.
1. Do que se trata (pedido, quem pediu, executor, diretório).
2. Por que está travada (motivo, desde quando, quem segura a fila).
3. O que já aconteceu (tentativas, último erro, checagens com o veredito `ORIGEM:`, retornos,
   mensagens posteriores que citam a tarefa, resumo de consolidação).
4. Já foi feito em outro lugar? Ainda não: chega na Fase 3.
5. O que fazer: as ações permitidas, cada uma com a consequência escrita, a recomendada primeiro
   (★), e as indisponíveis com o motivo.

O link `?brief=<id>` abre a análise direto; é o que a tela Mensagens usa no atalho **"Analisar em
Tarefas dos agentes"**.

**Analisar todas** (antigo "Analisar e encaminhar", `core/message_triage.py`) continua no topo:
1. **Regras fixas** (`deterministic_analysis`): cota, executor ocupado, retorno informativo,
   entrega verificada, checagem que superou a falha, Moodle concluído, autorização, pergunta.
2. **Recomendação do modelo** (`analyze_messages`), só consultiva em produção
   (`MESSAGE_TRIAGE_ENABLED=false`, `MESSAGE_ANALYSIS_ON_DEMAND_ENABLED=true`).
3. Quando as regras fixas **provam** resolução, a mensagem é arquivada com o motivo gravado.

O motivo de um botão desabilitado aparece escrito abaixo dele (linha e detalhe). Arquivar sempre
pede o motivo (MSG-060).

## 12. Lacunas encontradas (produção, 30 dias até 2026-11-19)

- **Continuidade se perde depois da falha**: 94 checagens disseram PARCIAL/BLOQUEADA; 46 dessas
  tarefas não tiveram continuação, 48 tiveram continuação que também falhou; nenhuma chegou a
  concluir. Nenhum código lê a linha `ORIGEM:`.
- **Arquivamento sem registro**: 199 de 271 falhas arquivadas não têm evento dizendo quem arquivou
  e por quê. Arquivar pelo agente (MCP `archive_agent_message`) e a retenção não gravavam auditoria
  (corrigido na Fase 1: MSG-060).
- **Analisador**: a parte com modelo falhou em 15/11 e 17/11 (provedor); a busca de "já foi feito"
  só olha o mesmo diretório/projeto entre as 300 mensagens mais recentes.
- **Travamentos que não chegam a Decisões**: fila parada atrás de execução incerta, cota sem
  retomada automática, incubação vencida esquecida.
- **Decisões espalhadas**: propostas de manutenção (Acesso remoto), e-mails de clientes
  (`/client-emails`) e alertas de rotinas ficam em outras telas.

## 13. Direção decidida (2026-11-19, Marcelo)

Princípio: **o controle das tarefas dos agentes precisa ser coeso**. Mensagens mostra o tráfego;
Pessoal → Tarefas dos agentes é o único lugar de decisão, e mostra **só o que está travado**.
Tarefas encerradas não aparecem nessa tela (continuam em Mensagens → Arquivadas e no histórico).

### 13.1 Os sete motivos de travamento (entrada única em Decisões)

1. Execução incerta (com as tarefas que ela segura).
2. Falha sem continuidade (checagem disse PARCIAL/BLOQUEADA e ninguém continuou).
3. Cota sem retomada automática (reset desconhecido, vencido em tarefa protegida, contexto mudou).
4. Fila travada há mais de 30 min, com a causa.
5. Incubação vencida há mais de 3 dias.
6. Aprovação pendente (tarefa, Moodle, missão, STI).
7. Limite de tentativas atingido.

"Aguardando" fica só com o que segue sozinho **e tem data**; passou da data, vira travada.

### 13.2 O fio

Uma tarefa é acompanhada como **fio**: original → tentativas → checagem → continuação → desfecho,
ligados por vínculo no banco (não por menção no texto). Um fio só sai da tela com desfecho
explícito: entregue (com evidência), feito por outra tarefa (com vínculo), descartado com motivo,
ou consolidado. Todo arquivamento, por qualquer caminho (tela, agente, Auditor, analisador,
retenção), grava quem e por quê.

### 13.3 Botão Analisar por tarefa

Unificação decidida: há **um analisador**, em Pessoal → Tarefas dos agentes.

- **Analisar** em cada tarefa travada, com cinco seções:
  1. do que se trata; 2. por que está travada; 3. o que já aconteceu;
  4. já foi feito em outro lugar? (com evidência); 5. o que fazer, com a consequência de cada
  opção e a recomendada.
- **Analisar todas** no topo (o atual "Analisar e encaminhar") roda em lote.
- As seções 1, 2, 3 e 5 vêm das regras fixas: aparecem na hora e funcionam sem o modelo. A seção 4
  usa o modelo; se ele falhar, a tela diz "assistente indisponível" e o resto continua.
- A análise roda no clique (contexto atual, sem custo à toa) e fica guardada na tarefa até ela
  mudar.
- Na tela Mensagens, o item ganha só o atalho **"Ver em Tarefas dos agentes"**.

Encaminhamentos, agora com o que acontece:

| Hoje (técnico) | Botão | Efeito |
|---|---|---|
| queue | Colocar na fila de novo | Volta ao agente (ou a outro, se for cota). |
| resolve | Encerrar como entregue | Fecha com a evidência citada. |
| link | Feito por #N | Liga à tarefa que fez e encerra. |
| archive_notice | Era só aviso: arquivar | Arquiva com motivo. |
| diagnose | Pedir checagem | Cria checagem ligada ao fio. |
| — | Criar continuação | Nova tarefa só com o que faltou, ligada ao fio. |
| — | Descartar com motivo | Sai da lista; motivo registrado. |

### 13.4 Fases

| Fase | Entrega | Situação |
|---|---|---|
| 1 | Tela focada nas travadas; motivos em Decisões; arquivamento sempre com motivo e auditoria; botão Analisar (seções 1, 2, 3, 5); atalho em Mensagens. | Implementada no branch `fix/messages-rule-feedback` (seção 11), não publicada. Publicar o MCP antes do backend. |
| 2 | Vínculo de continuidade no banco; a linha `ORIGEM:` passa a decidir (hoje só é exibida); campo "continua #N" no MCP; fio inteiro na tela; botões Criar continuação, Feito por #N e Encerrar como entregue. | A fazer. |
| 3 | Seção 4: busca em todos os agentes do projeto/área, sempre com evidência; resistência a falha do modelo; análise guardada até a tarefa mudar. | A fazer. |

Ficou fora da Fase 1, de propósito: Aprovações continua como aba própria (não virou filtro de
Decisões); a seção 5 usa as ações que já existiam, e as novas (continuação, "feito por") dependem do
vínculo da Fase 2.

As fases 1 e 2 mudam o fluxo dos agentes e passam por revisão independente antes da publicação.

## 14. Mapa do código

| Assunto | Onde |
|---|---|
| Modelo e constantes | `backend/app/db/models/demand.py` |
| Rotas (criar, editar, excluir, despachar, reprocessar, pendentes) | `backend/app/api/routes/demand.py` |
| Reserva e capacidade | `backend/app/core/demand_dispatch_guard.py` |
| Decisões do operador e incerteza | `backend/app/core/demand_workflow.py` |
| Tarefas dos agentes (estados, ações, bloqueios) | `backend/app/core/demand_management.py` |
| Etiquetas | `backend/app/core/message_classification.py` |
| Analisador | `backend/app/core/message_triage.py`, `message_triage_context.py`, `api/routes/message_triage.py` |
| Checagem de falha | `backend/app/core/demand_failure_check.py` |
| Cota | `backend/app/core/agent_availability.py`, `agent_failover.py`, `quota_wait.py` |
| Relatório final | `backend/app/core/completion_report.py` |
| Retorno ao canal | `backend/app/core/feedback.py` |
| Tela Mensagens | `frontend/src/pages/demands/index.tsx`, `frontend/src/hooks/useDemands.ts` |
| Tela Tarefas dos agentes | `frontend/src/pages/personal/AgentTasksTab.tsx`, `TaskBriefPanel.tsx`, `frontend/src/hooks/useAgentTasksViewModel.ts` |
| Analisar (por tarefa) | `backend/app/core/demand_brief.py`, `GET /api/v1/demands/{id}/brief` |
| Arquivar com motivo | `backend/app/core/demand_workflow.py:archive_with_reason` |
| Mensagens de recusa | `frontend/src/lib/demandRuleError.ts`, `i18n/locales/*/demands.json` (`ruleErrors`) |
| MCP dos agentes | `host-bridge/forgehub_messages_mcp.py`, `backend/app/mcp/factory_server.py` |
