# Missão — análise e planejamento

**Data:** 2026-10-24
**Status:** proposta para aprovação do Marcelo. É a frente M do
[plano integrado](../plans/2026-10-24-plano-integrado.md), que define a ordem: validar o Software
Factory, ligar os componentes e documentação, e só então a Missão.
**Origem:** pedidos #39779, #39780, #39781 e #39784 (Maia → Aramis, 24/10, a pedido do Marcelo) e o
diagnóstico de memória #39778 (Athos). Os quatro pedidos foram registrados como concluídos, mas o
Aramis parou no meio. O código parcial está no branch `wip/missao-aramis` (`3c7c609`), fora do
`develop`, e serve só como referência.
**Direção do Marcelo (24/10):** "integrar a missão com operação 24x7 e software factory, para
gerenciar as tarefas e registro das implementações e da documentação".

## 1. O que foi pedido

1. **Tela de Missão (#39779):** coordenar todos os agentes em torno de um objetivo, com:
   - responsável, participantes, status, prioridade e prazo;
   - próximos passos, decisões, pendências e histórico;
   - distribuição de subtarefas conforme a função de cada agente, acompanhamento e consolidação do resultado.
2. **Controle explícito de contexto (#39780), obrigatório:**
   - tipos de contexto: temporário, resumo de continuidade, memória persistente, base de conhecimento
     versionada, compartilhável, privado, descartável/arquivado;
   - ações: salvar, não salvar, compartilhar com escopo e finalidade, substituir, revisar, arquivar, redigir segredos;
   - em cada item: origem, dono, canal, confiabilidade, validade e escopo.

   A troca entre agentes acontece só por resumos autorizados e mínimos.
3. **Operação 24x7 e "AGI própria" (#39781):** a Missão define objetivo e governança, e a operação 24x7
   executa, monitora e escala. Pede um roadmap por fases, critérios de autonomia e testes de segurança.
4. **Arquitetura dos quatro sistemas (#39784):** Hermes executa os agentes, o ForgeHub coordena, o
   ForgeRouter fornece os modelos e o ForgeVault protege os segredos. Pede os contratos, autenticação,
   isolamento, fluxo de contexto, auditoria, falhas e aprovação humana.

## 2. O que já existe (não reconstruir)

| Peça pedida | Já existe | Onde |
|---|---|---|
| Organizar o trabalho em fases e tarefas com dependência | Software Factory: Produto → Versão → Projeto → Planning Item → ProjectTask, `TaskDependency` | `factory.py`, `backlog.py`, `task.py` |
| Atribuir a tarefa a um agente e executá-la | `TaskAssignment` + `POST /tasks/{id}/dispatch`, que vira mensagem no Messages (único executor) | `task.py` → `demand.py` |
| Saber se a tarefa foi realmente feita | `STATUS: DONE` no Messages (desde 24/10) e `TaskExecution.evidence_ref` (`file:`, `git:`, `db:`) verificada automaticamente | `core/completion_report.py`, `core/task_evidence.py` |
| Registrar documentação ligada ao trabalho | `DocLink`: documento em `/docs` ligado a produto, versão, projeto, planning item, tarefa ou artefato | `db/models/doc_link.py`, `docs.py` |
| Aprovação humana | `Approval` (aprovar uma `project_task` já despacha), `AuthorityDelegation` | `governance.py` |
| Função de cada agente | 13 cartas de função (missão, responsabilidades, "nunca faz") | `agent_charters`, `/operations` |
| Operação 24x7 | Rotinas → Messages (18 rotinas, só 3 ligadas), dúvidas pelo Telegram (`ask_marcelo`), Evolução A0/A1/A2 com reversão, monitoramento → Task | `operations.py` |
| Tempo real | Agent Activity (SSE, timeline, replay, alertas) | `core/agent_live_state.py` |
| Redação de segredos | `core/secret_masking.py` | — |
| Segredos, modelos | ForgeVault (só pelo host-bridge); ForgeRouter (Hermes) e modelos nativos (Claude Code, Codex, agy) | `forgevault_proxy.py`, `core/agent_runs.py` |
| Memória | Hindsight (`hermes` coletivo, `maia` privado), `MEMORY.md`/`USER.md`, Knowledge Base, hook `knowledge_cycle.py` | diagnóstico #39778 |

**Uso real hoje:** o Software Factory só tem 4 projetos de teste e nenhum produto real. A Missão passa
a ser a forma de usar o Software Factory no dia a dia do ecossistema.

**O que de fato falta:**
1. Um objetivo acima do projeto: critério de sucesso, coordenador, agentes participantes com papel,
   consolidação do resultado e nível de autonomia.
2. **Contexto por destinatário:** hoje cada tarefa leva o texto que alguém escreveu. Não há como
   dizer "este fato vale para Maia e Lara, este só para Maia", nem garantir que um segredo não vá junto.
3. **Documentação obrigatória por entrega:** o `DocLink` existe, mas nada exige que uma implementação
   termine com o documento registrado.
4. A Operação 24x7 não enxerga projetos nem missões: a triagem e o briefing do Athos olham rotinas e
   mensagens, não tarefas de projeto paradas.
5. Um documento canônico dos **contratos entre os quatro sistemas**.

## 3. Achados do diagnóstico de memória (#39778) que a Missão precisa respeitar

- O hook `knowledge_cycle.py` busca em toda a `knowledge_base`, não só na pasta do agente. Um perfil
  pode receber trechos de outro (sensível para Maia e Lara). **Corrigir antes do compartilhamento de contexto.**
- A mesma informação pode estar em `SOUL.md`, `AGENTS.md`, `USER.md`, Hindsight e KB, sem precedência.
- Maia e Lara compactam agressivamente (`protect_last_n: 10`): decisão não registrada se perde.
- A Maia não tem pasta própria na Knowledge Base.
- Hindsight é recuperação derivada, não fonte canônica.

Consequência: a Missão não escreve direto em Hindsight, `MEMORY.md` nem na Foundation. Promover
contexto a memória ou a base de conhecimento vira uma **tarefa** para Mnemosyne ou Scriba, revisada.

## 4. Desenho

### 4.1 Uma missão = um projeto do Software Factory + coordenação

```
Missão #N (objetivo, critério de sucesso, coordenador, participantes, autonomia, contexto)
 └─ Projeto (Software Factory)            ← 1:1, criado junto com a missão
     ├─ Planning Item "Fase 1 …"          ← fases da missão
     │   ├─ ProjectTask (agente X)         ← etapa; despachada pelo Messages
     │   │   └─ TaskExecution + evidência verificada + DocLink
     │   └─ ProjectTask (documentação)     ← obrigatória por fase
     ├─ Planning Item "Fase 2 …"
     └─ Planning Item "Consolidação"       ← criado no fim, coordenador
```

- **Produto e versão:** missões do ecossistema ficam no produto interno **"Ecossistema Foundation"**
  (um só, com uma versão por trimestre, ex.: `2026.4`). Missão que muda um sistema específico usa o
  produto dele (ForgeHub, ForgeRouter, ForgeVault, Darckware...), que passa a ser cadastrado.
  Regra 6.1.3 (produto sempre com versão) e a trava de versão publicada continuam valendo.
- **Projeto interno, sem cliente** (Marcelo, 24/10: "o projeto criado não precisa ter um cliente
  associado. podendo ser um projeto interno no software factory"). Os produtos internos acima não têm
  `darckware_client_id`, então o projeto da missão nasce sem cliente (o campo já é opcional; o
  projeto só herda o cliente quando o produto tem um). A tela e o Cockpit marcam esses projetos como
  "Interno". Uma missão nunca exige cliente, nem converte lead.
- **Etapas são ProjectTasks.** Não há tabela de etapas própria: atribuição (`TaskAssignment`),
  dependência (`TaskDependency`), despacho, `STATUS: DONE`, evidência e aprovação são os do Software
  Factory. A Missão só acrescenta o que falta.

### 4.2 Princípios

1. **Messages continua sendo o único executor.** A Missão nunca despacha por conta própria: usa o
   `dispatch` da ProjectTask.
2. **O contexto é aplicado no despacho.** Ao despachar uma tarefa de missão, o ForgeHub acrescenta ao
   corpo o objetivo da missão e **apenas** os itens de contexto cujo escopo inclui aquele agente, já
   redigidos. É isso que garante o resumo autorizado e mínimo, e não a boa vontade do agente.
3. **Toda entrega deixa registro.** Uma tarefa de missão só é aceita (`done`) com evidência
   verificada (`git:`/`file:`/`db:`). Cada fase só fecha com a tarefa de documentação concluída e o
   documento ligado por `DocLink`.
4. **A função vem da carta.** A tela mostra a carta do agente antes de atribuir; nada fixo no código.
5. **Status derivado, nunca digitado.** Fase reflete as tarefas, missão reflete as fases.
6. **O humano aprova o que é irreversível.** Abrir a missão, aprovar o plano e aceitar o resultado
   ficam com o Marcelo ou com quem ele delegar. A autonomia segue A0/A1/A2.
7. **Nada de segredo no contexto.** Todo texto de contexto passa por `secret_masking` ao gravar e ao
   despachar. Segredo se referencia pelo nome no ForgeVault.

### 4.3 Modelo de dados novo (schema `company`)

| Tabela | Campos principais |
|---|---|
| `missions` | `number`, `title`, `objective`, `success_criteria`, `project_id` (1:1, obrigatório), `coordinator_agent_id` (padrão Athos), `status` (`draft` → `planned` → `active` → `consolidating` → `done` / `cancelled`), `priority`, `due_at`, `autonomy` (`A0`/`A1`/`A2`, padrão `A2`), `summary` (resumo de continuidade, versionado por `AuditEvent`), `result` (consolidação final), `result_doc_path` |
| `mission_participants` | `mission_id`, `agent_id`, `role_in_mission`, único por par |
| `mission_context_items` | Modelo do branch do Aramis, revisto: `kind` (`continuity`, `fact`, `decision`, `constraint`, `reference`), `content` (redigido), `origin` + `origin_ref` (tarefa, mensagem, pergunta, pessoa), `owner_agent_id`, `channel`, `reliability` (`confirmed` / `reported` / `assumed`), `valid_until`, `sharing` (`mission` / `agents` / `private`), `shared_with`, `purpose`, `state` (`active` / `pending_confirmation` / `replaced` / `archived`), `replaced_by_id`, `promotion` (`none` / `requested_memory` / `requested_kb` / `promoted`, com a ProjectTask que fez a promoção) |

Colunas novas em tabelas existentes (opcionais, sem quebrar nada):
- `agent_questions.mission_id` e `agent_demands.mission_id` (dúvidas e mensagens da missão);
- `doc_links.entity_type` ganha `mission`.

Histórico e auditoria: `AuditEvent(entity_type="mission" | "mission_context")`.

Os tipos de contexto pedidos em #39780, mapeados para o que existe:

| Pedido | Na Missão |
|---|---|
| Contexto temporário da sessão | Não é guardado: fica na sessão do agente (Hermes) |
| Resumo de continuidade revisável | `missions.summary` + itens `kind=continuity`, com histórico |
| Memória persistente | `promotion=requested_memory` → ProjectTask para a Mnemosyne gravar no Hindsight certo |
| Base de conhecimento versionada | `promotion=requested_kb` → ProjectTask para o Scriba publicar na KB/Foundation, com `DocLink` |
| Compartilhável entre agentes | `sharing=mission` ou `agents`, com `purpose` obrigatório |
| Privado por agente/canal | `sharing=private` (só o dono vê e recebe) |
| Descartável ou arquivado | `state=archived` (nunca DELETE), com motivo |

### 4.4 Fluxo

1. **Criar** (Marcelo na tela, ou agente por MCP `mission_create`, que fica em `draft` até aprovação):
   objetivo, critério de sucesso, prazo, produto. O ForgeHub cria a missão e o Projeto na versão
   aberta do produto, em uma transação.
2. **Planejar:** o coordenador propõe fases (Planning Items) e tarefas com agente, dependência e
   evidência esperada, a partir das cartas (MCP `mission_propose_plan`). Cada fase recebe
   automaticamente uma tarefa de documentação (Scriba por padrão). O Marcelo revisa e aprova na tela.
3. **Executar:** tarefa pronta (dependências `done`) é despachada pelo caminho existente, com o corpo
   acrescido do objetivo e do contexto filtrado. Respeita fila, teto por agente e orçamento da carta.
4. **Verificar e registrar:** `STATUS: DONE` + evidência verificada levam a tarefa a `done`.
   `PARTIAL`/`BLOCKED`/sem linha deixam a tarefa `blocked` com o motivo. O coordenador reprocessa,
   reatribui ou pergunta ao Marcelo (`ask_marcelo` com `mission_id`).
5. **Documentar:** a tarefa de documentação de cada fase grava o documento em
   `/docs/missions/<numero>-<slug>/` e o liga por `DocLink` à fase e às tarefas implementadas. A fase
   só fecha com esse vínculo.
6. **Consolidar:** fases concluídas → o ForgeHub cria a fase "Consolidação" para o coordenador, que
   escreve o resultado (`missions.result` + documento final ligado à missão). O Marcelo aceita e encerra.

### 4.5 Integração com a Operação 24x7

| Operação 24x7 | Passa a cobrir |
|---|---|
| Triagem do Athos (a cada 2 h) | Tarefas de missão paradas, `blocked`, sem evidência, prazos vencendo, dúvidas sem resposta |
| Briefing matinal | Missões ativas: avanço por fase, bloqueios e o que precisa do Marcelo |
| Rotina do Scriba (18:00) | Fases concluídas sem documento ligado (aciona a tarefa de documentação) |
| Rotina do Atlas (09:30) | Dependências bloqueadas e tarefas sem dono nos projetos de missão |
| Evolução | Métricas por missão: tempo por fase, retrabalho (reprocessos), taxa de `DONE` na primeira tentativa, documentação em dia |
| Monitoramento → ação | Um check que falha pode abrir tarefa dentro de uma missão existente do domínio, em vez de uma Task solta |
| Agent Activity | A execução mostra a missão e a tarefa; um clique leva à missão |
| Cockpit (Software Factory) | O projeto de missão aparece na árvore com a marca da missão |

Resumindo: a Missão define o objetivo, o Software Factory organiza e registra, o Messages executa,
a Operação 24x7 vigia e escala, e o Agent Activity mostra o tempo real.

### 4.6 Inteligência operacional própria (roadmap de autonomia)

Sem promessa de AGI geral. É a evolução da autonomia das missões, com critério verificável para subir:

| Nível | O que o sistema faz | Critério para habilitar |
|---|---|---|
| M0 | Marcelo cria e aprova o plano; agentes executam tarefas | Fase 1 entregue |
| M1 | O coordenador propõe o plano; o Marcelo aprova | 10 missões M0 com ≥ 80% das tarefas `DONE` na primeira tentativa e 100% das fases documentadas |
| M2 | Tarefas de baixo risco (diagnóstico, leitura, documentação) despacham sem aprovação item a item; código e ações externas continuam A2 | M1 por 30 dias sem incidente de contexto (vazamento entre agentes ou segredo) |
| M3 | A retrospectiva propõe missões novas (lacunas, checks recorrentes) em `draft` para o Marcelo | M2 estável; testes de segurança verdes |

Em nenhum nível o sistema altera carta de função, identidade, política comum ou Foundation sem A2.

### 4.7 Arquitetura dos quatro sistemas (documento a produzir)

`docs/architecture/FOUNDATION_FOUR_SYSTEMS.md`, mapeando o que **já existe**:

| Contrato | Real hoje |
|---|---|
| ForgeHub → Hermes (executar) | host-bridge `/v1/agent-runs` com run id reservado antes; `hermes chat` para Hermes, CLI nativa para externos |
| Hermes → ForgeHub (agir) | MCP `forgehub` com credencial `agt_` por agente; telemetria por webhook HMAC |
| Hermes → ForgeRouter (modelos) | chave por agente; externos fora do ForgeRouter |
| Qualquer um → ForgeVault (segredos) | só o host-bridge, service account por finalidade; nada de valor em mensagem, log ou memória |
| Auditoria | `AuditEvent` (ForgeHub), auditoria do ForgeVault, logs do ForgeRouter |
| Falhas | prazo e incerteza com run id no Messages, gateway único, alertas do Agent Activity |
| Aprovação humana | `Approval`, `AuthorityDelegation`, `ask_marcelo`, A2 |

Lista também as lacunas reais (escopo do `knowledge_cycle.py`, falta de contexto por destinatário),
sem inventar integração.

## 5. Plano de implementação

O próprio plano é a primeira missão: depois da Fase 1 ele é cadastrado como Missão #1, "Missão",
no produto ForgeHub. Antes disso (Fase 0 e Fase 1), segue como ProjectTasks de um projeto comum no
Software Factory, com `TaskDependency`. Quem escreve não revisa o próprio código: Porthus revisa
Aramis e Dartan.

### Fase 0 — Base

| # | Tarefa | Dono | Depende de | Aceite |
|---|---|---|---|---|
| 0.1 | Cadastrar os produtos internos (Ecossistema Foundation, ForgeHub, ForgeRouter, ForgeVault, Darckware) com versão aberta e **sem cliente** | Atlas (dados), Marcelo aprova | — | Aparecem no Cockpit como internos |
| 0.2 | Documento dos quatro sistemas (4.7) | Porthus | — | Cada contrato aponta arquivo/rota real; registrado por `DocLink` |
| 0.3 | `knowledge_cycle.py` restrito à pasta do agente + `shared/` | Porthus (código), Mnemosyne valida | — | Teste: perfil A nunca recebe trecho da KB de B |
| 0.4 | Pasta privada da Maia na Knowledge Base | Mnemosyne | — | Fora do alcance dos outros perfis |

### Fase 1 — Núcleo (M0)

| # | Tarefa | Dono | Depende de | Aceite |
|---|---|---|---|---|
| 1.1 | `missions` + `mission_participants` + migration; criação atômica missão + projeto | Aramis | 0.1 | Uma cabeça de migration; regra 6.1.3 respeitada |
| 1.2 | API: missão, participantes, transições, status derivado de fases/tarefas, auditoria | Aramis | 1.1 | Testes de rota; nunca DELETE de missão ativa |
| 1.3 | Plano: fases e tarefas criadas pela missão, com tarefa de documentação automática por fase | Aramis | 1.2 | Fase sem tarefa de documentação não pode ser aprovada |
| 1.4 | Aceite com evidência: tarefa de missão só vai a `done` com `evidence_ref` verificada; `PARTIAL`/`BLOCKED` → `blocked` com motivo | Aramis | 1.3 | Testes cobrindo os três desfechos |
| 1.5 | Documentação: `doc_links` aceita `mission`; fase só fecha com documento ligado; pasta `/docs/missions/` | Aramis | 1.3 | Teste: fase não fecha sem `DocLink` |
| 1.6 | Consolidação automática + aceite do Marcelo | Aramis | 1.4, 1.5 | Missão só fica `done` com resultado aceito e documento final |
| 1.7 | Tela `/missions` (Agentes & IA): lista, detalhe com objetivo, participantes (carta), fases e tarefas, documentos, linha do tempo; criar e aprovar plano; ViewModel §21, i18n, celular | Dartan | 1.2 | 390 px e 1440 px; `tsc` e testes |
| 1.8 | MCP para agentes: `mission_list`, `mission_get`, `mission_create` (draft) | Aramis | 1.2 | Registro e permissão testados |
| 1.9 | Revisão | Porthus | 1.1–1.8 | Aprovação registrada |

### Fase 2 — Controle de contexto

| # | Tarefa | Dono | Depende de | Aceite |
|---|---|---|---|---|
| 2.1 | `mission_context_items` + ações (confirmar, compartilhar, substituir, arquivar, redigir) + auditoria | Aramis | 1.9, 0.3 | Segredo nunca gravado em claro |
| 2.2 | Filtro de contexto por destinatário no despacho das tarefas de missão | Aramis | 2.1 | Teste: item `private` da Maia nunca vai no corpo enviado à Lara |
| 2.3 | Promoção a memória/KB como ProjectTask para Mnemosyne/Scriba | Aramis | 2.1 | Nada escreve direto no Hindsight |
| 2.4 | Aba "Contexto" na tela | Dartan | 2.1 | Ações com confirmação; celular |
| 2.5 | MCP `mission_context_add` / `mission_context_list` (só o que o agente pode ver) | Aramis | 2.2 | Agente não lista item fora do escopo |
| 2.6 | Testes de segurança (vazamento, segredo, expirado, substituído) | Porthus | 2.1–2.5 | Suíte dedicada verde |

### Fase 3 — Operação 24x7

| # | Tarefa | Dono | Depende de | Aceite |
|---|---|---|---|---|
| 3.1 | `mission_id` em `agent_questions` e `agent_demands`; exibição na missão | Aramis | 1.9 | Pergunta de missão aparece nos dois lugares |
| 3.2 | Triagem e briefing do Athos, rotina do Scriba e do Atlas cobrindo missões (4.5) | Athos (instruções), Aramis (dados) | 3.1 | Briefing lista missões bloqueadas; Scriba aciona fase sem documento |
| 3.3 | Métricas de missão na Evolução | Aramis | 1.9 | Tendência semanal com missões |
| 3.4 | Missão no Agent Activity e no Cockpit | Dartan | 1.9 | Clique da execução leva à missão |
| 3.5 | Ligar as rotinas da Fase 3 que hoje estão desligadas (Scriba, Atlas) | Athos, Marcelo aprova | 3.2 | Rodando com orçamento da carta |

### Fase 4 — Autonomia M1

| # | Tarefa | Dono | Depende de | Aceite |
|---|---|---|---|---|
| 4.1 | MCP `mission_propose_plan` para o coordenador | Aramis | Fase 2 | Plano entra como proposta, nunca ativo |
| 4.2 | Critérios de nível (4.6) calculados e exibidos | Aramis + Dartan | 3.3 | Tela mostra o nível atual e o que falta |

## 6. Riscos

- **Escopo grande de uma vez:** foi o que fez a primeira tentativa parar. Mitigação: tarefas pequenas,
  uma por vez por agente, `STATUS: DONE` com evidência verificada.
- **Software Factory pouco usado até agora:** a Missão vai exercitar fluxos que só têm dados de teste
  (dispatch de ProjectTask, verificação de evidência, `DocLink`). Esperar ajustes na Fase 1.
- **Sobreposição:** a Missão não repete Projeto (ela usa um) nem rotina (recorrente). Missão é objetivo único com fim.
- **Vazamento de contexto:** filtro no despacho (2.2) e `knowledge_cycle.py` (0.3), ambos com teste dedicado.
- **Custo:** tarefas respeitam o orçamento diário por agente das cartas.

## 7. Decisões pendentes do Marcelo

1. Produto interno "Ecossistema Foundation" para missões que não são de um sistema específico, com
   versão por trimestre (recomendado), ou um produto por área.
2. MVP com Fases 0 e 1 antes do contexto (recomendado), ou contexto já no MVP.
3. Coordenador padrão: Athos (recomendado) ou escolhido por missão.
4. Quem pode criar missão: só o Marcelo, ou também agentes em `draft` (recomendado: agentes em `draft`).
5. Documentação: Scriba como dono padrão da tarefa de documentação de cada fase (recomendado), ou o
   próprio agente que implementou.
6. Descartar o branch `wip/missao-aramis` após a Fase 2.
