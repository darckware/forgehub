# 02 — Agentes, Messages e canais

Base: `main` em `43a6a7f`. Confirme a identidade do agente, o vínculo da execução e
o estado persistido; uma resposta isolada não prova conclusão.

**As regras do Messages (MSG-002 a MSG-014 e as novas MSG-020 em diante) estão no guia
[08 — Messages](08-messages.md)** desde 14/11/2026. Aqui ficam identidade, runtime, skills e canais.

| ID | Estado | Regra de negócio | Fonte principal |
|---|---|---|---|
| MSG-001 | IMPLEMENTADA | O agente autenticado é identificado pela credencial ativa; nome/modelo exibido não concede identidade nem autorização. | `backend/app/core/deps.py`; `backend/app/db/models/agent.py`; `backend/app/tests/test_auth.py` |
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
