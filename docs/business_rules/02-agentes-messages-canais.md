# 02 — Agentes, Messages e canais

Base: `main` em `43a6a7f`. Confirme a identidade do agente, o vínculo da execução e
o estado persistido; uma resposta isolada não prova conclusão.

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-001 | IMPLEMENTADA | O agente autenticado é identificado pela credencial ativa; nome/modelo exibido não concede identidade nem autorização. | `backend/app/core/deps.py`; `backend/app/db/models/agent.py`; `backend/app/tests/test_auth.py` |
| MSG-002 | IMPLEMENTADA | Execução deve corresponder ao dispatch, tarefa, agente e `run_id` esperados. Resposta atrasada não conclui outra tentativa. | `backend/app/api/routes/demand.py`; `backend/app/tests/test_messages_execution_guards.py`; `docs/architecture/MESSAGES.md` |
| MSG-003 | IMPLEMENTADA | Somente `STATUS: DONE` mapeia para sucesso. `PARTIAL`, `BLOCKED`, resposta ausente ou resultado não exitoso são falhas com causa/resultados preservados. | `backend/app/core/completion_report.py:50`; `backend/app/api/routes/demand.py:2298` |
| MSG-004 | IMPLEMENTADA | Timeout, 404 ou ausência de registro do runner não prova que a execução parou. Execução incerta não pode ser repetida ou arquivada; preserve run e reserva e reconcilie com evidência da mesma execução. | `backend/app/core/demand_workflow.py:27,162`; `docs/architecture/MESSAGES.md:63`; `backend/app/tests/test_demand_management.py` |
| MSG-005 | IMPLEMENTADA | Status da demanda (`new/read/converted/archived`), dispatch (`NULL/dispatched/running/completed/failed`) e acknowledgment (`agent_processed_at`) são eixos diferentes. Não use um para inferir o outro nem para inferir aceite da ProjectTask. | `backend/app/db/models/demand.py:17,19`; `docs/architecture/MESSAGES.md:11` |
| MSG-006 | IMPLEMENTADA | Task é trabalho executável; incubation é estacionada, não despacha e não tem `origin_id` de ProjectTask. Tipo/contexto incompleto pode reclassificar a demanda para incubation; destino em branco pode usar remetente. Incubação tem owner e decisão após maturação; descarte exige motivo. | `backend/app/db/models/demand.py:38`; `backend/app/api/routes/demand.py:236,263,385,1927`; `backend/app/tests/test_incubation_maturation.py`; `test_incubation_decision.py` |
| MSG-007 | IMPLEMENTADA | Polling de `/demands/pending` reconhece itens da inbox (`agent_processed_at`), não executa tarefa. Retorno concluído pode ser arquivado no acknowledgment. `/for-agent` é consulta não consumidora. | `backend/app/api/routes/demand.py:534,609`; `backend/app/tests/test_demand_dispatch.py` |
| MSG-008 | IMPLEMENTADA | Dispatch requer gates de workflow/aprovação, dependências satisfeitas, runtime elegível, capacidade disponível e diretório absoluto explícito. Item enfileirado não prova que runner iniciou. | `backend/app/api/routes/demand.py:1524,1554`; `backend/app/tests/test_demand_dispatch.py` |
| MSG-009 | IMPLEMENTADA | Reprocessamento ordinário é manual e limitado ao orçamento de tentativas (padrão 3), com histórico retido. Exceder exige autorização explícita, evidência e novo ciclo de aprovação; autorizar aumenta orçamento/enfileira, mas não executa por si. | `backend/app/api/routes/demand.py:728`; `backend/app/core/demand_workflow.py:178`; `backend/app/tests/test_demand_management.py` |
| MSG-010 | IMPLEMENTADA | Retenção automática arquiva mensagens concluídas após 60 dias; não apaga registros nem expira falhas por idade. Histórico/consolidação não reabre conversa nem envia feedback externo novo. | `backend/app/api/routes/demand.py:1894`; `docs/architecture/MESSAGES.md:72`; `backend/app/tests/test_demand_retention.py` |
| MSG-011 | IMPLEMENTADA | Resultado fica na mensagem original. Crie retorno separado somente quando `requires_response=true` e remetente conhecido puder recebê-lo; trabalho para si mesmo mantém resultado na original. | `backend/app/api/routes/demand.py:2298`; `backend/app/tests/test_demand_reply_routing.py:67` |
| MSG-012 | IMPLEMENTADA | `channel`/`channel_ref` não autorizam envio externo. Feedback Telegram requer pedido explícito no assunto/corpo; falha pode ser tentada em ciclo posterior. Novos itens Inbox criam notificação persistente; falha de dispatch gera alerta. | `backend/app/core/feedback.py:61,425`; `backend/app/api/routes/demand.py:365`; `backend/app/tests/test_notifications.py` |
| MSG-013 | GAP | A checagem automática de falha exclui grupos, incubation, execução incerta, registros arquivados/consolidados, falha antiga e tarefas de missão. A arquitetura descreve elegibilidade mais ampla; não crie demanda diagnóstica fora dos critérios implementados. | `backend/app/core/demand_failure_check.py:53`; `docs/architecture/MESSAGES.md:123` |
| MSG-014 | GAP | Modelo retirou `pending` da lista de estados de dispatch, mas a descrição da rota `/for-agent` ainda o menciona. `NULL` significa que não iniciou; corrija textos antigos sem reintroduzir status retirado. | `backend/app/db/models/demand.py:19,23`; `backend/app/api/routes/demand.py:631` |
| MSG-015 | IMPLEMENTADA | Canais têm membros humanos/agentes configurados, mas código/testes acordam agentes não silenciados quando a mensagem não nomeia agente. Isso diverge do guia `mention_only`; siga o comportamento verificado e registre o conflito antes de alterar. Participação não dá autoridade de aprovação. | `backend/app/db/models/channel.py:81,145`; `backend/app/api/routes/channel.py:233`; `backend/app/tests/test_channel.py:502`; `help/FORGEHUB_CHANNELS_AGENT_GUIDE.md:50` |
| MSG-016 | IMPLEMENTADA | Aprovação em canal usa fluxo governado, identidade autorizada e trilha; papel de membro, menção ou capacidade de mensagem não substitui aprovação. Proposta sem resposta explícita não é aprovada por silêncio/timeout. | `backend/app/api/routes/channel.py` (`proposal`/`approval`); `backend/app/tests/test_channel.py:954` |
| MSG-017 | IMPLEMENTADA | Messages é handoff ponto a ponto e resultado; Chat/Canais são contextos compartilhados. Agent Activity é read model dos eventos e não estado de execução próprio. | `help/FORGEHUB_CHANNELS_AGENT_GUIDE.md:14,32`; `backend/app/core/agent_activity.py:836`; `backend/app/api/routes/agent_activity.py:179` |
| MSG-018 | IMPLEMENTADA | Runtime registrado é separado da identidade do agente. Sync preenche metadado ausente e aponta divergência, sem criar agente ou sobrescrever runtime existente. | `backend/app/db/models/agent.py:51`; `backend/app/core/agent_runtime_sync.py:20`; `backend/app/api/routes/demand.py:1554` |
| MSG-019 | IMPLEMENTADA | Skill deve declarar versão, origem, risco e permissões; não pode ser autoaprovada na criação. Mudança descritiva após aprovação cria nova versão; concessão a subagente requer skill elegível possuída pelo agente pai. | `backend/app/db/models/agent.py:293`; `backend/app/api/routes/agent.py:941,1631`; `backend/app/tests/test_agent.py` |

## Instruções para agentes

- Antes de reenviar ou arquivar, inspecione separadamente demanda, dispatch,
  acknowledgment, tentativa e execução remota. Reconcile estados incertos por run ID.
- Não use `pending` para dispatch nem deixe trabalho em execução indefinida. Marque
  falha com causa, mantenha histórico e limite tentativas.
- Checagem automática de falha tem exclusões; confira `demand_failure_check.py` antes
  de generalizar o handoff diagnóstico. Arquivamento não é forma de esconder falha.
- Mensagem, reação em canal ou proposta não equivalem a aprovação governada nem ao
  aceite de tarefa.
- Atualize este catálogo, documentação de arquitetura e manuais operacionais juntos
  ao alterar estados, retry, feedback, retenção ou wake-up de canal.

## Referências

- [Arquitetura de Messages](../architecture/MESSAGES.md)
- [Recuperação de dispatch](../MESSAGES_DISPATCH_RECOVERY.md)
- [Triagem de Messages](../runbooks/messages-triage.md)
- [Falhas e checagens de Messages](../runbooks/MESSAGES_FAILURE_CHECKS.md)
- Modelos: `backend/app/db/models/demand.py`, `channel.py`, `agent.py`.
