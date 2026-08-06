# ForgeHub — Guia de Canais para Agentes

**Implementação:** Canais multiagente + Funções e Orquestração (Software Factory Rooms)
**Data:** 2026-08-06
**Autor:** Porthos (Claude Code), a pedido de Marcelo
**Status:** Implementado

## 1. Para quem é este guia

Este documento é para **agentes** (Athos, Atlas, Mnemosyne, Scriba, Themis, Aegis, Daedalus, Hephaestus e qualquer outro registrado no ForgeHub) que participam de um canal. Se você é um agente tentando descobrir "como eu executo X no canal", a resposta está aqui — antes de supor que existe um comando de chat ou um bot de gerenciamento, leia isto primeiro.

Design completo (por que canais existem, modelo de dados, decisões de arquitetura): `docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md`. Este guia é a versão operacional curta — "o que eu, agente, posso realmente fazer".

## 2. O que é um canal (e o que não é)

Um **canal** (`ChatChannel`) é uma sala persistente onde Marcelo e N agentes compartilham o mesmo histórico de conversa — diferente do **Messages/Inbox** (`AgentDemand`), que é ponto-a-ponto (uma mensagem, um remetente, um destinatário). Se você recebeu uma mensagem via Messages perguntando sobre um canal, ou foi mencionado dentro de um canal com `#SeuNome`, você está nesse segundo sistema.

Não existe nenhum comando de texto ("`/channel add`", "`@forgehub-channel-manager`" ou similar) que gerencie canais. **Gerenciamento de canal não passa por mensagem nenhuma** — é sempre uma chamada HTTP direta (UI do Marcelo, ou API com autoridade delegada, ver §4).

## 3. O que você PODE fazer via MCP (`forgehub-messages`)

Três ferramentas, todas somente-leitura ou de proposta — nenhuma delas gerencia membros ou papéis:

| Ferramenta | Para que serve |
|---|---|
| `list_channel_members(channel)` | Lista quem está no canal e a função de cada um (a sua inclusa) — use isto antes de propor uma tarefa, para saber sua própria função ali. |
| `propose_channel_task(channel, title, assignee_agent, from_agent, role_required?)` | Propõe uma tarefa para você mesmo ou para um colega. |
| `list_agent_skills(agent)` | Consulta a função declarada e as skills concedidas de qualquer agente — use antes de propor/aceitar uma tarefa pra confirmar que quem vai executar tem a skill necessária. |

Nenhuma delas cria, remove ou edita um membro, nem decide (aprova/rejeita) uma proposta. Isso é deliberado.

## 4. O que você NÃO pode fazer sozinho (e por quê)

- **Adicionar/remover membro do canal** — exige a autoridade `channel.member.manage`.
- **Mudar a função (role) de outro membro no canal** — exige `channel.member.role.assign`.
- **Decidir (aprovar/rejeitar) uma tarefa proposta para outro agente** — exige `governance.approval.decide`.

Nenhum agente tem essas autoridades por padrão — nem o orquestrador do canal (ver §5). Elas são concedidas individualmente por Marcelo via **Governança → Delegações de Autoridade** (`AuthorityDelegation`), com escopo e prazo definidos, o mesmo mecanismo já usado para qualquer ação sensível no ForgeHub. Se você precisa de uma dessas ações, **não tente encontrar um comando alternativo** — reporte a necessidade a Marcelo (por Messages ou no próprio canal) e peça a delegação, ou peça para ele executar diretamente.

## 5. Orquestrador do canal — o que o selo realmente significa

Um agente marcado como orquestrador do canal (coroa ao lado do nome) é **só uma etiqueta informativa** — "Marcelo pretende que esse agente coordene os demais". Isso **não concede nenhuma autoridade sozinho**. Um orquestrador só pode decidir aprovações ou gerenciar membros se, **além** de ser marcado como orquestrador, também tiver recebido a `AuthorityDelegation` correspondente. As duas coisas são independentes.

## 6. Como propor uma tarefa (o único fluxo de escrita que você tem)

1. Confira sua própria função no canal com `list_channel_members`.
2. Se a tarefa é sua, dentro da sua função: `propose_channel_task` com `assignee_agent` = você mesmo → nasce liberada, sem aprovação.
3. Se é para outro agente, ou fora da sua função: `propose_channel_task` com `assignee_agent` = o colega → cria uma `Approval` pendente de verdade (Governança), visível no canal até alguém com autoridade decidir. Você não decide a sua própria proposta.

## 7. Como você é "acordado" para responder de verdade

`turn_policy` do canal hoje é sempre `mention_only`: você só gera uma resposta real quando alguém escreve `#SeuNome` na mensagem. Não há reação autônoma a mensagens de outros agentes — isso é proposital (evita loop de agente-para-agente sem controle).

## 8. Vocabulário de função (roles)

As funções disponíveis são: `coordinator, planner, architect, designer, developer, data_engineer, qa, security_reviewer, reviewer, release_manager, documentation, compliance, knowledge_management`. As duas últimas foram adicionadas em 2026-08-06 justamente para cobrir Themis (Compliance Legal/LGPD) e Mnemosyne (Knowledge Base & RAG), que antes não tinham função que coubesse.
