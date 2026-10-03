# Operação 24x7 dos Agentes — Especificação

**Data:** 2026-10-02
**Status:** Proposta para aprovação
**Pedido (Marcelo):** "o objetivo das implementações é auditoria, monitoramento do ecossistema, manter os agentes ativos em produção 24x7, tirando eles da inércia. Preciso de uma tela para programação das tarefas diárias, instruções de comunicação entre agentes, instruções que tirem eles da inércia e que promovam melhoria, monitore o ecossistema, cada agente com suas funções estabelecidas, e todas as dúvidas tirar comigo pelo Telegram."

## Diagnóstico

- **Só o Athos tem rotina.** Ele tem 7 jobs em `hermes cron`; os outros 9 perfis Hermes têm zero, e os runtimes externos (Porthus, Aramis, Dartan, Vector) só agem quando chamados. A inércia é estrutural: nenhum agente tem um gatilho próprio.
- As funções existem só como texto: papel e missão em `14_agents/ECOSYSTEM_AGENTS.md` e nos `SOUL.md`. Nada transforma esse papel em trabalho recorrente nem verifica se ele foi feito.
- As peças de execução já existem e funcionam:
  - **Messages** é o único executor (`_execute_dispatch`): agenda (`scheduled_at`), teto de concorrência com no máximo um run por agente, prazo, retry manual, notificação de toda falha, resultado (`dispatch_result`) e retorno por Telegram (`channel`/`channel_ref`).
  - **Incubação** guarda ideias com dono obrigatório, estado explícito e prazo de maturação que cobra a decisão do agente.
  - **Auditoria**: todo check tem um perfil responsável (`audit_checks.agent_profile`).
  - **Agent Activity** mostra em tempo real o que cada agente está fazendo, mais os alertas.
- Faltam quatro coisas: recorrência, a carta de funções de cada agente, instruções comuns (comunicação, iniciativa e melhoria, escalada) e uma tela de controle.

## Princípios

1. **Messages continua sendo o único executor.** Uma rotina não roda nada sozinha: a cada ocorrência ela cria uma mensagem Task para o agente. Assim cada execução aparece em Messages e no Agent Activity, respeita o teto por agente, tem prazo e notifica falha, sem código novo de execução. Não é um segundo scheduler de execução, só um gerador de mensagens agendadas.
2. **Cada agente tem uma carta de funções.** Missão, responsabilidades permanentes, domínios monitorados (incluindo os checks de auditoria que ele possui), com quem coordena e o que nunca faz. A carta é a fonte de verdade da tela, e cada rotina pertence a uma carta.
3. **Toda execução termina com evidência e uma melhoria.** O resultado registra o que foi verificado e feito. Se o agente vê algo a melhorar, abre um item de **Incubação** em vez de agir fora do escopo. A maturação da Incubação já cobra a decisão, então a melhoria nunca é esquecida.
4. **Monitoramento fecha o ciclo.** Um check de auditoria que falha gera uma mensagem Task para o agente responsável. O check volta a passar? A tarefa fecha com evidência. Não volta? Escala.
5. **Dúvidas vão para o Marcelo pelo Telegram, com rastreio.** Toda pergunta vira um registro no ForgeHub (pergunta, contexto, quem pergunta, o que fica bloqueado) e chega ao Telegram dele. A resposta volta ao agente que perguntou.
6. **O sistema se aperfeiçoa sozinho** (Marcelo: "o sistema tem que se aperfeiçoar sozinho"). Ele mede o próprio desempenho, propõe e aplica as melhorias dentro de níveis de autonomia, verifica se a mudança melhorou as métricas e desfaz a que piorou. O Marcelo aprova só o que é arriscado ou irreversível.
7. **Custo e segurança são limites, não esperança.** Cada agente tem orçamento diário de execuções e de custo (ForgeRouter). A Lara nunca contata clientes por rotina. Ações destrutivas continuam exigindo aprovação.

## Componentes

### 1. Carta de funções (`agent_charters`)

Uma por agente (Hermes e externos). Campos:

| Campo | Descrição |
|---|---|
| `agent_id` | Agente (FK) |
| `mission` | Missão em uma frase |
| `responsibilities` | Lista de responsabilidades permanentes |
| `monitored_domains` | O que este agente vigia (infra, segurança, docs, memória...) |
| `owned_audit_checks` | Derivado de `audit_checks.agent_profile`, não editado à mão |
| `coordinates_with` | Agentes com quem troca trabalho, e para quê |
| `never_does` | Limites explícitos |
| `daily_run_budget` / `daily_cost_budget` | Limites de execução por dia |
| `escalation` | `telegram_direct` (perfis com Telegram: athos, aegis, kairos, lara) ou `via_athos` |

A carta é renderizada num bloco gerenciado do `HEARTBEAT.md` do agente (marcadores de início e fim; o resto do arquivo não é tocado), usando o endpoint de profile files que o ForgeHub já tem. Assim o próprio agente "sabe" suas funções em qualquer conversa, não só nas rotinas.

### 2. Rotinas (`agent_routines` + `agent_routine_runs`)

| Campo | Descrição |
|---|---|
| `agent_id`, `title`, `instructions` | O que fazer, em linguagem natural |
| `schedule` | Expressão cron + fuso (America/Sao_Paulo) |
| `kind` | `monitoring`, `maintenance`, `improvement`, `report`, `coordination` |
| `expected_evidence` | O que o resultado precisa conter para contar como feito |
| `linked_audit_checks` | Checks que a rotina deve verificar ou manter verdes |
| `enabled`, `priority`, `deadline_minutes` | |

Um loop do ForgeHub (mesmo padrão dos loops de Messages em `main.py`) calcula as ocorrências vencidas e, para cada uma, cria uma `AgentDemand` Task: `from` = Athos (coordenador) ou o próprio agente, `to` = o agente da rotina, `scheduled_at` = a ocorrência. O corpo traz instruções da rotina + carta + instruções comuns. É idempotente por `(routine_id, occurrence_at)` em `agent_routine_runs`, que liga a ocorrência à mensagem e guarda o desfecho (`completed`/`failed`/`missed`/`skipped_budget`). Uma ocorrência que passa do prazo sem rodar vira `missed` e alerta. Rotina parada também é inércia.

### 3. Instruções comuns (política versionada)

Um documento da Foundation (`52_policies/agent-operations.md`), injetado no corpo de toda mensagem de rotina e referenciado na carta:

- **Comunicação entre agentes:** sempre por Messages (`send_agent_message`), com assunto, contexto, pedido claro e prazo; `requires_response` quando precisar de retorno. O dono do domínio decide; quem descobre um problema fora do seu domínio avisa o dono em vez de corrigir. Athos coordena os conflitos.
- **Contra a inércia:** a cada execução, verificar o próprio domínio, agir no que estiver dentro do escopo e da carta, e registrar evidência. "Nada a fazer" é um resultado válido só com evidência do que foi verificado.
- **Melhoria contínua:** toda execução avalia uma melhoria possível no seu domínio. Achou? Abre Incubação, com o agente como dono e a justificativa. Não implementa fora do escopo sem aprovação.
- **Dúvidas:** perguntar ao Marcelo (componente 5) só quando a decisão não cabe na carta ou é irreversível, deixando claro o que fica bloqueado e qual a recomendação do agente.

### 4. Monitoramento → ação

- Check de auditoria que falha gera uma Task para `agent_profile`, deduplicada por check (sem pilha de tarefas para a mesma falha), com a evidência e o comando de verificação.
- O catálogo v2 (spec da Auditoria) define quem vigia o quê. Cada novo módulo do ecossistema entra como check com dono.
- O Agent Activity continua sendo o painel do que acontece agora. A tela nova é o plano e o controle do que deveria acontecer. As duas se ligam (um clique do run para o detalhe no Agent Activity e vice-versa).

### 5. Dúvidas para o Marcelo pelo Telegram (`agent_questions`)

- MCP `ask_marcelo(question, context, blocking, recommendation)` no servidor `forgehub`: cria o registro, notifica no ForgeHub e envia pelo Telegram. Perfis com Telegram próprio mandam do próprio bot; os demais mandam pelo bot do Athos, identificando o agente e o número da pergunta.
- A resposta do Marcelo (no Telegram ou na tela) é gravada na pergunta e entregue ao agente como mensagem de retorno (`reply_to_id`). O agente retoma o trabalho bloqueado.
- Pergunta sem resposta não bloqueia o resto do agente: ele segue nas outras rotinas e lembra uma vez por dia (resumo matinal do Athos), nunca em loop.

### 6. Tela "Operação 24x7" (`/operations`)

Separada do Agent Activity, que continua sendo o tempo real.

| Aba | Conteúdo |
|---|---|
| **Agentes** | Uma linha por agente: carta (editável), rotinas, checks que possui, saúde de hoje (feitas/falhas/perdidas), orçamento usado |
| **Programação** | Grade agente × horário do dia/semana; criar, editar, pausar e duplicar rotinas; prévia das próximas ocorrências |
| **Execuções** | Hoje e histórico: ocorrência → mensagem → resultado/evidência; filtros por agente, tipo e desfecho; reprocessar uma falha |
| **Melhorias** | Itens de Incubação abertos pelas rotinas, por agente e estado de maturação |
| **Dúvidas** | Perguntas pendentes/respondidas; responder pela tela também |
| **Instruções** | Leitura e edição da política comum (versionada) |

Segue o padrão do frontend: ViewModel (§21), `ConfirmDialog`, React Hook Form + Zod, i18n pt-BR/en/es, celular.

### 7. Ciclo de autoaperfeiçoamento

O sistema não espera o Marcelo para melhorar. O ciclo tem quatro etapas, todas registradas.

**Medir:** cada `agent_routine_run` guarda desfecho, duração, custo (ForgeRouter), se a evidência esperada veio e se houve "nada a fazer". Também são medidos checks de auditoria vermelhos e há quanto tempo, alertas do Agent Activity, dúvidas sem resposta, melhorias de Incubação promovidas ou descartadas, e taxa de falha e reprocesso no Messages.

**Retrospectiva:** rotina do Athos, diária curta e semanal completa, com revisão técnica do Porthus na semanal. Ela lê as métricas e produz **propostas de mudança** estruturadas (o quê, por quê, métrica que deve melhorar, como desfazer). Fontes:
- rotinas que falham ou se perdem com frequência, ou que só retornam "nada a fazer" (frequência alta demais);
- domínios com problema recorrente e sem rotina (lacuna de cobertura);
- checks que falham repetidamente com a mesma causa (a correção precisa virar código ou rotina);
- melhorias maduras na Incubação;
- instruções que geram resultado sem evidência (instrução vaga);
- custo crescendo sem ganho correspondente.

**Aplicar, por nível de autonomia:**

| Nível | Exemplos | Quem aprova |
|---|---|---|
| **A0 — automático** | Ajustar frequência de rotina dentro de limites (no máximo dobrar ou reduzir à metade por ciclo, nunca abaixo de 1 por semana); reordenar horários para resolver conflito de concorrência; reforçar `expected_evidence`; pausar uma rotina que falhou 3 vezes seguidas (com alerta) | Ninguém: aplicado e registrado |
| **A1 — automático com aviso** | Reescrever instruções de uma rotina; criar rotina nova dentro do orçamento do agente; propor e ativar um check de auditoria novo; promover uma melhoria de Incubação a Task no domínio do próprio agente | Aplica e informa no briefing matinal; o Marcelo pode desfazer com um toque |
| **A2 — aprovação do Marcelo** | Mudança de código em qualquer repositório; alterar a carta de funções; aumentar orçamento; mudar a política comum; qualquer ação destrutiva ou externa (clientes, domínios, segredos) | Pergunta pelo Telegram (`ask_marcelo`) com recomendação; nada é aplicado antes do sim |

Mudanças de código (A2 aprovado) seguem o fluxo de produto que já existe: item de planejamento → Task → execução pelo agente dono via Messages → revisão do Porthus → testes → deploy pelo gate normal. A autonomia não pula as travas de aprovação.

**Verificar e desfazer:** toda mudança aplicada vira uma `operations_change` (versão anterior, versão nova, métrica-alvo, janela de avaliação, normalmente 7 dias). No fim da janela, a retrospectiva compara antes e depois: melhorou, a mudança fica; piorou, A0/A1 é **desfeita automaticamente** e registrada como aprendizado; neutro, fica e entra no relatório. As rotinas, cartas e política têm histórico de versões, e qualquer estado anterior pode ser restaurado pela tela.

**Aprendizado persistente:** cada mudança avaliada (o que funcionou e o que não) é registrada na memória do ecossistema (Hindsight, via Mnemosyne) e no relatório semanal ao Marcelo, para que as próximas retrospectivas não repitam propostas já testadas e rejeitadas.

### 8. Tela: aba "Evolução"

Uma sétima aba na tela `/operations` lista as mudanças propostas, aplicadas, em avaliação, mantidas e desfeitas, com o nível de autonomia, a métrica antes e depois e um botão de desfazer. Mostra também a tendência semanal: rotinas cumpridas, checks verdes, falhas, custo e melhorias entregues.

## Catálogo inicial de rotinas (proposta)

| Agente | Rotina | Agenda |
|---|---|---|
| Athos | Briefing matinal ao Marcelo pelo Telegram: saúde do ecossistema, falhas da noite, dúvidas pendentes, plano do dia | diário 08:00 |
| Athos | Triagem: rotinas perdidas/falhas, conflitos entre agentes, redistribuição | a cada 2 h |
| Athos | Retrospectiva: métricas → propostas de mudança (A0/A1 aplicadas, A2 ao Marcelo) | diário 22:00 / semanal dom 20:00 com Porthus |
| Athos | Auditoria semanal completa (já existe: `ecosystem-weekly-audit`) | dom 19:00 |
| Hephaestus | Saúde da infra: containers, disco, restart policy, logs, backup externo da noite | a cada hora |
| Hephaestus | Verificação do backup (snapshot recente, restauração de amostra semanal) | diário 07:00 / dom |
| Aegis | Segurança: portas expostas, Cloudflare Access, permissões de segredos, logins/SSH, tokens expirando | diário 06:00 |
| Daedalus | Higiene dos repositórios: alterações sem commit, testes quebrados, dependências desatualizadas → propostas | diário 09:00 |
| Atlas | Planejamento: tarefas paradas, dependências bloqueadas, itens sem dono; resumo para o Athos | diário 09:30 |
| Mnemosyne | Qualidade da memória (Hindsight): retenção, fatos obsoletos, consolidação | diário 05:00 |
| Scriba | Documentação: divergência entre CLAUDE.md/Foundation e o código do dia; atualizar a KB | diário 18:00 |
| Themis | Conformidade: LGPD nos dados da Lara, licenças de dependências novas | semanal seg 10:00 |
| Kairos | Inteligência de mercado: digest para o Marcelo | diário 08:30 |
| Lara | Pipeline comercial interno (sem contato com clientes por rotina) | diário 10:00 |
| Porthus | Revisão de arquitetura e código dos commits do dia | diário 20:00 |
| Aramis | Engenharia de repositório: pendências técnicas atribuídas | diário 14:00 |
| Dartan | Auditoria de UI/celular das telas alteradas no dia | diário 16:00 |

Os horários respeitam o teto global de concorrência (hoje 5) e o limite de um run por agente. A grade da tela mostra os conflitos.

## Fases de implementação

1. **Fundação:** `agent_charters`, `agent_routines`, `agent_routine_runs`, gerador de ocorrências → Messages, política comum, cartas e rotinas iniciais (seed). Testes do gerador (idempotência, missed, orçamento).
2. **Dúvidas pelo Telegram:** `agent_questions` + MCP `ask_marcelo` + retorno da resposta.
3. **Monitoramento → ação:** check falho gera Task para o dono; depende do catálogo v2.
4. **Tela `/operations`:** as seis abas.
5. **Autoaperfeiçoamento:** métricas por execução, retrospectiva do Athos (+ Porthus), `operations_change` com níveis A0/A1/A2, avaliação, desfazer automático e aba "Evolução".
6. **Ativação gradual:** primeiro Athos, Hephaestus e Aegis (monitoramento), depois os demais, observando custo e ruído por uma semana antes de ampliar.

## Decisões pendentes do Marcelo

1. Rotinas via **Messages** (recomendado: cobre também os agentes externos e reaproveita prazo, falha e Telegram) ou via `hermes cron` por perfil (só agentes Hermes).
2. Tela nova `/operations` separada do Agent Activity (recomendado) ou abas dentro dele.
3. Orçamento diário de custo por agente (sugestão: começar baixo e subir com base na telemetria da primeira semana).
4. Aprovação ou ajuste do catálogo inicial de rotinas e horários.
5. Limites do nível A1 (o que pode ser aplicado só com aviso) e da janela de avaliação (sugestão: 7 dias).
6. Horário de silêncio para mensagens no seu Telegram (ex.: 23:00–07:00, só urgências), mesmo com os agentes trabalhando 24x7.
