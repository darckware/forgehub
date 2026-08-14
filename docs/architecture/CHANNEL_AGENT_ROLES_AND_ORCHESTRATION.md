# ForgeHub — Funções e Orquestração de Agentes nos Canais (Software Factory)

**Implementação:** Canais multiagente + Funções e Orquestração (Software Factory Rooms)
**Data:** 2026-08-05
**Autor:** Porthus (Claude Code), a pedido de Marcelo
**Status:** Implementado — canais (`ChatChannel`/`ChatChannelMember`/`ChatChannelMessage`/`ChatChannelTask`) e a camada de funções/orquestração descrita aqui (modelo, migrações, rotas, MCP e frontend) foram concluídos e verificados (283 testes de backend, build de frontend limpo, smoke test ponta a ponta) em 2026-08-05.

## 1. Objetivo e status deste documento

Este documento registra o desenho de como agentes de IA nos **canais** do ForgeHub (Workspace → modo "Canais", ver `backend/app/db/models/channel.py`) recebem **funções bem definidas** e como a **orquestração** entre eles — e entre eles e Marcelo — funciona, para que um agente não faça o trabalho de outro sem autorização.

Legenda usada abaixo (mesma convenção de `docs/architecture/PLANNING_DELIVERY_ARCHITECTURE.md`):

- **Implementado**: modelo e API sustentam a regra.
- **Proposto**: mudança necessária; não deve ser presumida por agentes como funcionalidade existente.

Para o desenho completo dos canais em si (por que ficam no domínio Workspace/Chat e não no Messages, contexto compartilhado, ponte de execução real via `AgentDemand`), ver o plano original desta sessão em `/root/.claude/plans/https-github-com-block-buzz-analise-e-qu-radiant-flute.md` — este documento cobre especificamente a camada de **funções e orquestração** que vem por cima daquilo.

## 2. Origem da decisão

Marcelo definiu o modelo em três falas, nesta ordem:

1. *"os agente nos canais irão interagir no software factory... o agente pode adicionar tarefas... entre os agentes que precisão ter suas responsabilidades bem definidas para não fazer a tarefa do outro. no cadastro de cada agente precisa ter sua função"* — cada agente tem uma função declarada no cadastro (`Agent`), e o canal pode redeterminar essa função por membro.
2. *"mas as tarefas dentro do canal eu sou o chefe e por exemplo o Athos como orquestrador dos agentes com suas funções no projeto"* — Marcelo é a autoridade final; um agente específico (ex.: Athos) pode ser designado orquestrador operacional, sem substituir essa autoridade.
3. *"o orquestrador vai validar, eu como governança... validação do lote = Planejamento"* — a validação de uma tarefa proposta por um agente é a mesma "Governança" que o ForgeHub já usa para aprovar itens do pipeline, não um mecanismo novo e paralelo.

## 3. Decisão central de arquitetura

**Nenhuma segunda hierarquia de autoridade.** "Quem pode aprovar o quê" usa 100% o mecanismo de `AuthorityDelegation`/`Approval` que o ForgeHub já tem (`backend/app/api/routes/governance.py`, `backend/app/api/routes/governed_approval.py`) — Athos vira "orquestrador" recebendo uma `AuthorityDelegation` real (`allowed_actions: ["governance.approval.decide"]`), não uma flag nova exclusiva de canal. Isso já bate com a documentação existente: `PLANNING_DELIVERY_ARCHITECTURE.md` já descreve Athos como *"o operador-orquestrador padrão do ForgeHub... monta equipes, gera planos... O usuário é a autoridade final"* — este pacote é a implementação concreta, dentro de canais, dessa relação que já estava descrita em prosa.

### 3.1 Vocabulário de função — compartilhado, não duplicado

`PROJECT_AGENT_ROLES` (`backend/app/db/models/orchestration.py`: `coordinator, planner, architect, designer, developer, data_engineer, qa, security_reviewer, reviewer, release_manager`) ganha `"documentation"` e passa a ser a única fonte de vocabulário de função, reaproveitada em três lugares:

| Campo | Onde | Significado |
|---|---|---|
| `Agent.default_role` | `agents` (cadastro) | Especialidade declarada do agente — nullable, nunca imposta. **Implementado.** |
| `ChatChannelMember.role` | `chat_channel_members` | Função *deste* agente *neste* canal — pode divergir do cadastro. **Implementado.** |
| `ProjectAgentMembership.role` | `project_agent_memberships` | Já existente — papel do agente no projeto formal. **Implementado.** |

### 3.2 Proposta de tarefa entre agentes — nasce pendente de Governança

`ChatChannelTask` ganha `role_required`, `created_by_agent_id` e `approval_id` (FK para `governance.approvals.id`). **Implementado.**

- Um agente propondo uma tarefa **para si mesmo**, dentro do próprio `role` no canal → `approval_id` fica `NULL`, a tarefa já nasce pronta.
- Um agente propondo uma tarefa **para outro agente** → sempre cria uma `Approval(entity_type="chat_channel_task", approval_type="channel_task_delegation", status="pending")` real e aponta `approval_id` para ela. É o mecanismo concreto de "tarefas sem validadas entre os agentes".
- Decidir (`approve`/`reject`) usa a rota de Governança **já existente** (`POST /governance/approvals/{id}/approve|reject`) — Marcelo decide hoje sem nenhum código novo (é admin); um agente-orquestrador decide com sua própria credencial (`agt_...`) só depois de receber a `AuthorityDelegation` correspondente.

### 3.3 Execução real fica só com Marcelo

O disparo de execução real (`:dispatch-task`, que aciona `AgentDemand`/`core/agent_runs.py`) **não** é estendido a agentes nesta etapa — orquestração/aprovação de tarefa é uma camada; rodar CLI de verdade continua 100% sob controle humano, sem exceção, mesmo para um agente-orquestrador delegado.

## 4. Referências

- Plano de implementação detalhado (modelo de dados, rotas, MCP, frontend, sequenciamento): `/root/.claude/plans/https-github-com-block-buzz-analise-e-qu-radiant-flute.md`.
- Canais multiagente (base sobre a qual este documento se apoia): `backend/app/db/models/channel.py` (docstring do módulo).
- Governança/Approval reaproveitados: `backend/app/api/routes/governance.py`, `backend/app/api/routes/governed_approval.py`.
- Papel de Athos como orquestrador padrão, já descrito antes deste pacote: `docs/architecture/PLANNING_DELIVERY_ARCHITECTURE.md` §1.
