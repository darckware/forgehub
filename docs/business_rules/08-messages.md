# 08 — Messages

Base: `main` em `d2513997` (14/11/2026), com a espera por cota (`ba575a1b`, migração
`d3f6a8b2c901`) publicada em produção. Este guia reúne as regras de negócio do Messages,
o canal único de execução e de comunicação entre agentes do ForgeHub (rota `/demands`,
domínio `demand`, tabela `company.agent_demands`). As regras MSG-002 a MSG-014 vieram do
guia [02](02-agentes-messages-canais.md), com os mesmos IDs; MSG-001 e MSG-015 a MSG-019
continuam lá (identidade, runtime, skills e canais).

Os estados seguem o [catálogo](README.md#como-interpretar): IMPLEMENTADA, PARCIAL,
POLÍTICA, GAP e HISTÓRICA. Fontes citadas por função; confira a linha atual antes de mudar.

## 1. O que é uma mensagem

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-054 | POLÍTICA | **Objetivo do Messages** (Marcelo, 14/11/2026): comunicação entre os agentes, envio de arquivos, envio de tarefas e envio do feedback quando solicitado. O que é só comunicação e não deve executar nada entra como **Incubação** (demanda sem execução); só uma **Task** executa. Um aviso nunca é criado como Task: uma Task cujo único desfecho possível é `BLOCKED` vira falha, checagem de falha e decisão do operador sem que haja trabalho algum. | Decisão do Marcelo; `backend/app/db/models/demand.py` (`DEMAND_ORIGIN_TYPES`) |
| MSG-020 | IMPLEMENTADA | Toda execução de Task passa pelo Messages (Marcelo, 2026-07-26). `POST /tasks/{id}/dispatch` cria a mensagem ligada à ProjectTask (`origin_type="task"`, `origin_id`) e usa o mesmo `_execute_dispatch`; não existe um segundo executor. | `backend/app/api/routes/task.py` (`dispatch_task`); `backend/app/api/routes/demand.py` (`_execute_dispatch`) |
| MSG-005 | IMPLEMENTADA | Uma mensagem tem três eixos independentes: **status** (`new`, `read`, `converted`, `archived`), **dispatch** (`NULL`, `dispatched`, `running`, `completed`, `failed`, `waiting_quota`) e **acknowledgment** (`agent_processed_at`). Nenhum eixo é inferido de outro, nem do aceite da ProjectTask. `NULL` no dispatch significa que nada começou; `pending` foi retirado. | `backend/app/db/models/demand.py` (`DEMAND_STATUSES`, `DEMAND_DISPATCH_STATUSES`) |
| MSG-021 | IMPLEMENTADA | O **meio de comunicação** (`channel`) diz por onde o pedido chegou e para onde o resultado volta: `workspace`, `assistant`, `factory`, `agent`, `telegram`, `whatsapp_group`. `channel_ref` é o endereço concreto. Não confundir com `origin_type` (o Tipo). | `backend/app/db/models/demand.py` (`DEMAND_CHANNELS`) |
| MSG-022 | IMPLEMENTADA | Cada mensagem tem número sequencial (`#número`) usado por agentes, MCP e tela. Mensagens arquivadas continuam no banco; nada é apagado por fluxo de negócio. | `backend/app/db/models/demand.py` (`AgentDemand.number`) |

## 2. Tipo e criação

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-006 | IMPLEMENTADA | O Tipo (`origin_type`) é obrigatório e tem dois valores: `task` (trabalho a executar) e `incubation` (pensamento estacionado). Tipo ausente vira `incubation`. Uma Task precisa de **remetente e destinatário**; se faltar um deles, ela é rebaixada para `incubation` (com `origin_id` limpo), nunca recusada. Destino em branco na criação aponta para o próprio remetente. | `backend/app/api/routes/demand.py` (`_reconcile_task_origin`, `create_demand_and_notify`, `update_demand`) |
| MSG-023 | IMPLEMENTADA | Só `task` carrega `origin_id` (o vínculo com a ProjectTask). `incubation` é classificação, nunca vínculo. | `backend/app/db/models/demand.py` (`DEMAND_LINKED_ORIGIN_TYPES`); `_resolve_origin` |
| MSG-024 | IMPLEMENTADA | Uma Task com destinatário e sem `scheduled_at` recebe `scheduled_at = agora` uma única vez e acorda o despachante na hora; o ciclo de 30 s fica só como contingência. Edição posterior não reagenda. | `backend/app/api/routes/demand.py` (`create_demand_and_notify`); `backend/app/core/dispatch_signal.py` |
| MSG-025 | IMPLEMENTADA | Toda mensagem nova cria uma notificação persistente (sino), para que nenhuma chegada passe despercebida. | `backend/app/api/routes/demand.py` (`create_demand_and_notify`) |
| MSG-026 | IMPLEMENTADA | Agentes criam, leem, editam e arquivam as **próprias** mensagens pelo MCP com o token de bridge (`send_agent_message`, `update_agent_message`, `archive_agent_message`); a mensagem de outro agente devolve 403. | `backend/app/api/routes/demand.py` (`update_demand_as_agent`, arquivamento por agente); `backend/app/tests/test_demand_agent_crud.py` |

## 3. Incubação

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-027 | IMPLEMENTADA | Toda incubação tem **dono** (`incubation_owner_id`: destinatário, senão remetente; sem nenhum dos dois a escrita é recusada), **estado** (`incubating` → `decision_pending` → `promoted` ou `dropped`) e **prazo** (`matures_at`, padrão 3 dias). As três são `CheckConstraint` no banco. | `backend/app/db/models/demand.py` (`INCUBATION_STATES`, `INCUBATION_DEFAULT_MATURATION_DAYS`, listener `before_insert/before_update`) |
| MSG-028 | IMPLEMENTADA | Uma incubação nunca é despachada. Vencido o prazo, o ciclo de maturação (5 min) passa para `decision_pending`, zera `agent_processed_at` (ela volta à caixa do dono) e avisa. É idempotente por estado. | `backend/app/api/routes/demand.py` (`run_incubation_maturation_pass`, `reserve_dispatch` recusa incubação); `backend/app/tests/test_incubation_maturation.py` |
| MSG-029 | IMPLEMENTADA | Só o dono decide: receber (vira Task) ou descartar **com motivo**. Descarte é `status=archived`, nunca DELETE. Outro agente recebe 403; decidir duas vezes, 409. | `backend/app/api/routes/demand.py` (`receive_incubation`, `drop_incubation`); `backend/app/tests/test_incubation_decision.py` |

## 4. Fila e despacho

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-008 | IMPLEMENTADA | Despachar exige: aprovações e workflow liberados, dependências concluídas, executor elegível, vaga livre e diretório de trabalho absoluto. Item na fila não prova que o runner começou. | `backend/app/core/demand_dispatch_guard.py` (`reserve_dispatch`); `backend/app/tests/test_demand_dispatch.py` |
| MSG-030 | IMPLEMENTADA | **Reserva única:** todo caminho até o runner passa por `reserve_dispatch`, numa transação com lock consultivo que relê a linha, confere tudo e grava `agent_run_id` **antes** de chamar o bridge. Dois cliques, ou o ciclo e um clique, iniciam no máximo um run. | `backend/app/core/demand_dispatch_guard.py` (`reserve_dispatch`) |
| MSG-031 | IMPLEMENTADA | **Capacidade:** no máximo `MAX_CONCURRENT_DISPATCHES` runs em voo (padrão 5, ajustável até 20) e **um por agente**. O teto conta o que já está em voo; um agente ocupado é pulado, sem bloquear a fila. | `backend/app/core/config.py`; `backend/app/api/routes/demand.py` (`_dispatch_slots`, `_agents_already_running`) |
| MSG-032 | IMPLEMENTADA | A ordem da fila não é configurada: o Tipo decide se entra, `scheduled_at` decide a posição. Reprocessar é um novo lançamento e vai para o fim. | `backend/app/api/routes/demand.py` (`run_scheduled_dispatch_pass`) |
| MSG-033 | IMPLEMENTADA | O diretório de trabalho do run vem de `working_path` da mensagem, senão do padrão do runtime; um caminho relativo é recusado. | `backend/app/api/routes/demand.py` (`AgentDemand.working_path`); `reserve_dispatch` |
| MSG-034 | IMPLEMENTADA | Claude Code, Codex e agy rodam com login e modelo próprios, nunca pelo ForgeRouter. Com `autonomous_runs` ligado, rodam sem pedir permissão; o modo plano continua só leitura. | `host-bridge/app.py` (`_agent_run_command`); `backend/app/db/models/agent.py` (`autonomous_runs`) |
| MSG-035 | IMPLEMENTADA | Uma Task de missão ou de ProjectTask só roda como o baseline atual a congelou, e só se a dependência anterior estiver `done`/`deployed`. A recusa deixa o item na fila sem gastar tentativa. | `backend/app/core/task_baseline_guard.py`; `_ensure_demand_dependencies_satisfied` |

## 5. Execução e conclusão

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-002 | IMPLEMENTADA | A resposta só conta se corresponder ao dispatch, tarefa, agente e `run_id` esperados. Uma resposta atrasada não conclui outra tentativa. | `backend/app/api/routes/demand.py` (`_finalize_dispatch`); `backend/app/tests/test_messages_execution_guards.py` |
| MSG-003 | IMPLEMENTADA | Todo prompt de dispatch termina com o contrato de conclusão. Só a última linha `STATUS: DONE` vira `completed`; `PARTIAL`, `BLOCKED` ou linha ausente viram `failed`, com o motivo em `dispatch_error` e o resultado preservado. Código de saída 0 não é conclusão. | `backend/app/core/completion_report.py`; `_finalize_dispatch` |
| MSG-036 | IMPLEMENTADA | **Prazo:** todo dispatch tem `dispatch_deadline_at` = início + 45 min (acima dos 30 min do bridge). O ciclo de timeout marca como falha o que passar do prazo, inclusive se o bridge tiver caído. | `backend/app/db/models/demand.py` (`DISPATCH_TIMEOUT_MINUTES`); `run_dispatch_timeout_pass` |
| MSG-004 | IMPLEMENTADA | Timeout, 404 ou falta de registro no runner não provam que o trabalho parou. Um run incerto continua ocupando a vaga do agente e bloqueia nova tentativa e arquivamento até o operador reconciliar com evidência do mesmo run. | `backend/app/core/demand_workflow.py` (`requires_reconciliation`, `decide_demand`) |
| MSG-037 | IMPLEMENTADA | Reconciliar: `record_investigation` só acrescenta evidência; `confirm_inactive` exige motivo, evidência e o `run_id` digitado de volta, e transforma o caso em falha conhecida sem executar nada. | `backend/app/core/demand_workflow.py` (`decide_demand`) |

## 6. Falhas, tentativas e reprocessamento

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-038 | IMPLEMENTADA | **Toda falha notifica**, por um único `_fail_dispatch` usado por todos os caminhos. Falhas transitórias de início ficam na fila com espera de 60 s e 300 s; a terceira vira falha terminal. | `backend/app/api/routes/demand.py` (`_fail_dispatch`); `backend/app/db/models/demand.py` (`DISPATCH_TRANSIENT_RETRY_DELAYS_SECONDS`) |
| MSG-009 | IMPLEMENTADA | Reprocessar é **manual** e limitado a `retry_limit` (padrão 3, contando a primeira). `dispatch_attempts` nunca é zerado. Passar do limite exige `authorize_retry` com motivo e evidência, que só aumenta o limite e devolve à fila. Reprocessar nunca despacha direto: devolve à fila, que respeita o teto. | `backend/app/api/routes/demand.py` (`reprocess_demand`); `backend/app/core/demand_workflow.py` |
| MSG-057 | IMPLEMENTADA | **"Analisar e encaminhar" é conselheira** (Marcelo, 2026-11-15). Com `MESSAGE_ANALYSIS_ON_DEMAND_ENABLED`, o botão analisa as tarefas quando clicado e grava resumo e recomendação em cada uma, mas nada depende dela: nenhuma execução exige análise, não há análise automática em segundo plano, e um "queue" do modelo fica só como recomendação. Só as ações provadas sem IA (entrega verificada, aviso de retorno) arquivam sozinhas. O desenho completo, com portão no despacho e análise contínua, fica em `MESSAGE_TRIAGE_ENABLED`, desligado: na única vez que rodou (2026-11-09) a análise falhou em 3 de 5 tentativas, e com o portão a fila pararia junto. A tela consulta `GET /demands/agent-work/triage-settings` e diz quando a análise das tarefas está desligada; uma análise antiga aparece só como histórico datado. | `backend/app/core/message_triage.py` (`analysis_enabled`, `advisory_only`, `_apply`, `message_triage_loop`); `backend/app/api/routes/message_triage.py`; `backend/app/tests/test_message_triage.py` |
| MSG-013 | GAP | A checagem automática de falha exclui grupos, incubação, execução incerta, itens arquivados/consolidados, falhas antigas e tarefas de missão. A arquitetura descreve elegibilidade mais ampla; não crie demanda diagnóstica fora dos critérios implementados. | `backend/app/core/demand_failure_check.py`; `docs/architecture/MESSAGES.md` |

## 7. Espera por cota e troca de executor

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-039 | IMPLEMENTADA | Limite de uso reconhecido de Codex, Claude Code ou agy é espera de capacidade, não falha do trabalho: a mensagem entra em `waiting_quota` (não terminal, "Aguardando reset da cota"), guarda o horário de reset informado pelo provedor (`quota_reset_at`) e conserva agente, `run_id`, saída e histórico. Não gera falha, diagnóstico, conclusão nem arquivamento, e não consome tentativas de falha. | `backend/app/core/quota_wait.py` (`enter_quota_wait`); `backend/app/core/agent_availability.py`; migração `d3f6a8b2c901` |
| MSG-040 | IMPLEMENTADA | Depois do reset + 5 min de margem, trabalho comum volta à fila **no mesmo executor**, só se conteúdo e autorizações não mudaram. Sem horário de reset conhecido, fica esperando e o executor é tratado como indisponível para outras tarefas. A espera não ocupa vaga. | `backend/app/core/quota_wait.py` (`release_due_quota_waits`, `quota_resume_blocker`); `reserve_dispatch` |
| MSG-041 | IMPLEMENTADA | Trabalho que **ainda não rodou** pode mudar de executor quando o agente está sem cota, na ordem codex → agy → claude. Não muda: `fixed_agent` (ex.: revisão), item com aprovação, execução de ProjectTask, missão, checagem de falha, ou item que já rodou e parou na cota. | `backend/app/core/agent_failover.py` (`can_switch`, `FAILOVER_ORDER`) |
| MSG-042 | IMPLEMENTADA | Execuções da Fábrica, de missões e aprovações de efeito único exigem revisão explícita dos efeitos antes de continuar ("Autorizar nova tentativa", com motivo, evidência e `run_id` exato), seguida da aprovação do conteúdo. Moodle segue o fluxo próprio. | `backend/app/core/quota_wait.py` (`is_factory_quota_continuation`); `backend/app/core/demand_workflow.py` |

## 8. Aprovação e decisões do operador

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-043 | IMPLEMENTADA | Com `requires_approval`, nada roda antes da aprovação do Marcelo. A aprovação grava o hash do conteúdo (`approved_content_hash`); **qualquer edição depois anula a aprovação**. O runner confere isso de novo (`assert_execution_allowed`). | `backend/app/core/demand_workflow.py` (`approval_fingerprint`, `invalidate_changed_approval`, `assert_execution_allowed`) |
| MSG-044 | IMPLEMENTADA | Decisões do operador (`POST /demands/{id}/decision`, admin): aprovar, recusar, adiar, descartar, arquivar, restaurar e `authorize_retry`. Restaurar limpa o agendamento e exige nova aprovação; não roda sozinho. Nenhuma decisão vale para execução ativa ou reservada, nem para item que mudou desde que foi lido (`expected_updated_at`). Cada decisão vira `AuditEvent(entity_type="agent_demand")`. | `backend/app/core/demand_workflow.py` (`decide_demand`, `restore_demand`, `record_transition`) |
| MSG-053 | IMPLEMENTADA | A aba **Aprovações** (Pessoal → Tarefas dos agentes) recebe só o que espera autorização do Marcelo: mensagens com `requires_approval` e aprovação pendente, aprovações Moodle, decisões de missão e conclusões de ProjectTask. Falha ou execução incerta é decisão, não autorização: fica em Tarefas → Sua decisão. Pergunta bloqueante fica em Respostas. Cada item aparece uma vez. | `backend/app/core/demand_management.py` (`view_filter`, `approvals_queue`); `backend/app/tests/test_demand_management.py` |
| MSG-045 | IMPLEMENTADA | Mensagens de aprovação do Moodle são decididas só pelo fluxo próprio do Moodle; a única exceção é arquivar quando esse fluxo terminou (concluído ou recusado). | `backend/app/core/demand_workflow.py` (`decide_demand`) |

## 9. Resultado, retorno e feedback

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-011 | IMPLEMENTADA | O resultado fica na própria mensagem (`dispatch_result`). Uma mensagem de retorno separada (`reply_to_id`) só é criada quando `requires_response=true` e há remetente conhecido; o retorno nasce concluído e não pede outro retorno. | `_finalize_dispatch`; `backend/app/tests/test_demand_reply_routing.py` |
| MSG-012 | IMPLEMENTADA | `channel`/`channel_ref` não autorizam envio externo. Feedback pelo Telegram só sai se o assunto ou corpo pedir isso explicitamente; sem pedido, o resultado fica na notificação interna. Feedback só em estado terminal (`completed`/`failed`), idempotente por `feedback_sent_at`, e quem recebeu o pedido responde. `channel="agent"` não recebe feedback por aqui (o retorno já faz isso). | `backend/app/core/feedback.py`; `backend/app/tests/test_notifications.py` |

## 10. Caixa do agente

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-007 | IMPLEMENTADA | `GET /demands/pending` entrega cada item uma vez por agente e **é** o reconhecimento (`agent_processed_at`); não executa nada. `/for-agent` é consulta sem consumo. | `backend/app/api/routes/demand.py` (`list_pending_for_agent`, `list_for_agent`) |
| MSG-055 | IMPLEMENTADA | **Pergunta respondida** retoma o trabalho: o agente que perguntou recebe uma Task de continuação ligada à mensagem bloqueada (`reply_to_id`) e à mesma tentativa da ProjectTask, quando houver. **Pergunta arquivada sem resposta** é aviso, não trabalho: o agente recebe uma **Incubação** que é dele, ligada à mensagem bloqueada, com o mesmo diretório, projeto e contexto. Ele recebe a incubação (vira Task) se dá para seguir sem a resposta, ou descarta com motivo. Nada roda e nenhuma falha é criada. Agente inativo não recebe nada; o cancelamento fica auditado (`asker_notified: false`). | `backend/app/core/agent_questions.py` (`record_answer`, `record_cancellation`, `_notify_asker_cancelled`); `backend/app/tests/test_agent_questions.py` |
| MSG-046 | IMPLEMENTADA | Item com `requires_approval` só é entregue depois de aprovado e com o conteúdo aprovado inalterado. Um item recusado é entregue uma vez, como informação, e arquivado na mesma chamada. O cabeçalho do MCP marca "AGUARDANDO AUTORIZAÇÃO — não execute" ou "RECUSADA — não execute". | `list_pending_for_agent`; MCP de mensagens |
| MSG-014 | GAP | O modelo retirou `pending` dos estados de dispatch, mas a descrição de `/for-agent` ainda o cita. Corrija o texto sem reintroduzir o estado. | `backend/app/db/models/demand.py`; `list_for_agent` |

## 11. Retenção, arquivo e consolidação

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-010 | IMPLEMENTADA | A retenção (a cada 6 h) arquiva mensagens `completed` paradas há mais de 60 dias desde a última escrita. Arquiva, nunca apaga; não toca falhas, entrada, saída, execução nem incubação. | `backend/app/api/routes/demand.py` (`run_demand_retention_sweep`); `DEMAND_RETENTION_DAYS` |
| MSG-047 | IMPLEMENTADA | Os botões de limpeza da tela (30 d, 15 d, limpar tudo) seguem o mesmo filtro: só mensagens em estado terminal. | `frontend/src/pages/demands/index.tsx` (`cleanupTargetIds`) |
| MSG-048 | IMPLEMENTADA | Consolidar (`POST /demands/consolidate`, admin) junta falhas e incubações antigas num resumo de incubação por projeto/`context_area` e arquiva as originais com `consolidated_into_id`. Item consolidado só aceita decisão pelo resumo. | `backend/app/core/demand_consolidation.py`; `decide_demand` |

## 12. Canal restrito do grupo de WhatsApp

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-049 | IMPLEMENTADA | Mensagens `channel="whatsapp_group"` (pedidos dos grupos servidos pela Maia) rodam sempre pelo `/v1/agent-runs/restricted` do bridge, com ferramentas só de leitura/captura; nenhum escritor comum pode definir esse canal, e elas ficam fora de checagem de falha, de `/pending` e de aviso no Telegram. Escrita em CoreTI/SAEDAS vira tarefa com aprovação. | `backend/app/core/instructor_group.py`; `backend/app/api/routes/demand.py` |

## 13. Tela de Mensagens

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-050 | IMPLEMENTADA | Cada mensagem fica em **um** grupo por vez: Entrada → Execução → Concluídas ou Falhas. Sai de Entrada/Saída no instante em que começa a rodar. Mensagem para si mesmo é Entrada. "Sistema" é só o que não tem remetente nem destinatário. | `frontend/src/hooks/useDemands.ts` (`isIncomingItem`, `isOutboxItem`, `computeInboxTotalCount`) |
| MSG-056 | IMPLEMENTADA | Os rótulos da tela Mensagens seguem uma ordem de precedência (execução ativa, execução incerta, entrega verificada, arquivada, espera por cota, autorização pendente, pergunta, ...). Uma execução já **concluída** nunca é rotulada como "aguardando autorização", mesmo que a aprovação tenha expirado ou mudado depois (ex.: aprovação Moodle vencida após o run). | `backend/app/core/message_classification.py` (`classify_messages`); `backend/app/tests/test_message_classification.py` |
| MSG-051 | IMPLEMENTADA | Os três contadores de chegada (menu lateral, cabeçalho e raiz da Entrada) usam a mesma função, para nunca divergirem. | `computeInboxTotalCount` |
| MSG-052 | GAP | O frontend valida `dispatch_status` com uma lista fechada (Zod). Um valor novo do backend derruba a caixa de entrada inteira de uma aba aberta antes do deploy (ex.: `waiting_quota` em 14/11/2026, até recarregar a página). Recarregar resolve, porque o `index.html` vai sem cache; o comportamento desejado (tolerar valor desconhecido ou avisar que há versão nova) ainda não foi decidido. | `frontend/src/hooks/useDemands.ts` (`dispatch_status: z.enum(...)`) |
| MSG-053 | IMPLEMENTADA | Todo arquivamento registra quem e por quê (`demand_archive` com `source` e `reason`), por qualquer caminho: tela Mensagens (`archive_reason`, senão "Arquivada manualmente na tela Mensagens."), decisão em Tarefas dos agentes (motivo obrigatório, inclusive em lote), agente pelo MCP (`reason` obrigatório; 422 `ARCHIVE_REASON_REQUIRED`), Auditor, analisador, consolidação, missões e retenção. Arquivar numa subpasta obedece à mesma regra de execução incerta. | `backend/app/core/demand_workflow.py` (`archive_with_reason`); `backend/app/tests/test_demand_management.py`, `test_demand_agent_crud.py` |
| MSG-054 | IMPLEMENTADA | Pessoal → Tarefas dos agentes → Decisões lista só o que está travado, com o motivo (`stuck.reason`): execução incerta, falha sem checagem aberta, limite de tentativas, cota sem reset ou não retomada 30 min após o reset, fila devida há mais de 30 min, decisão de incubação vencida há mais de 3 dias. "Em andamento" não mostra resolvidas nem arquivadas. "Analisar" (`GET /demands/{id}/brief`) explica a tarefa só com regras fixas, com a consequência de cada ação e a recomendada. | `backend/app/core/demand_management.py` (`stuck_wait_sql`, `stuck_reason`), `backend/app/core/demand_brief.py`; `backend/app/tests/test_demand_management.py` |

## Instruções para agentes

- Ao arquivar, diga sempre o motivo (entregue com evidência, feito em #N, obsoleta). Não arquive
  falha que você não terminou só para limpar a lista (MSG-053).
- Antes de reenviar ou arquivar, olhe separadamente status, dispatch, acknowledgment,
  tentativas e o run remoto. Estado incerto se resolve pelo `run_id`, nunca por suposição.
- Não use `pending` para dispatch e não deixe trabalho em execução indefinida: a falha tem
  causa, o histórico fica e as tentativas têm limite.
- Cota esgotada não é falha: não reprocesse nem troque de executor um item em
  `waiting_quota` por conta própria.
- Aprovação vale para o texto aprovado. Editou, perdeu a aprovação.
- Mensagem, reação em canal ou proposta não equivalem a aprovação governada nem ao aceite da tarefa.
- Ao mudar estados, tentativas, feedback, retenção ou cota, atualize este guia, a
  arquitetura e os manuais na mesma mudança, e acrescente o valor novo também no frontend
  (MSG-052).

## Referências

- [Guia completo de Messages](../architecture/MESSAGES_GUIA.md)
- [Arquitetura de Messages](../architecture/MESSAGES.md)
- [Recuperação de dispatch](../MESSAGES_DISPATCH_RECOVERY.md)
- [Triagem de Messages](../runbooks/messages-triage.md)
- [Falhas e checagens de Messages](../runbooks/MESSAGES_FAILURE_CHECKS.md)
- [Espera por cota (relatório)](../reports/2026-11-14-quota-wait-indicator.md)
- Contrato para agentes: `/root/memory/foundation/30_docs/FORGEHUB_MESSAGE.md`
- Modelo: `backend/app/db/models/demand.py`
