# Plano integrado — todos os componentes do ForgeHub interligados (Service Factory)

**Data:** 2026-10-24
**Status:** proposta para aprovação do Marcelo — organizada em três ondas (seção 0)
**Pedidos do Marcelo (24/10):**
- "integrar a missão com operação 24x7 e software factory, para gerenciar as tarefas e registro das implementações e da documentação"
- "o projeto criado não precisa ter um cliente associado, podendo ser um projeto interno"
- "eu ainda preciso validar o software factory, que ainda não foi testado. Esse módulo foi criado para o gerenciamento da implementação dos sistemas. O software factory também pode ser utilizado para manutenção de sistema e execução de serviços de manutenção, pois a VPN Tailscale possui o acesso a todas as estações de trabalho e servidores"
- "preciso adicionar no planejamento da implementação em um conjunto completo, interligando todos os componentes criados"
- "a tela de atividades dos agentes precisa acompanhar todas as rotinas e monitorar todos os agentes"
- "o Darckware precisa ser adicionado, ele é minha ponte com a internet para captação de cliente no nosso ecossistema"
- "a ideia do Software Factory é que o agente use o módulo e eu monitore as atividades e adicione anotações e documentações adicionais para ajudar no contexto"
- "o objetivo do Software Factory é o gerenciamento da documentação, manual do sistema, controle das tarefas, distribuição das demandas entre os agentes, para a pasta do projeto ficar organizada e bem descritiva, que eu possa administrar e auditar o desenvolvimento e ajudar no contexto do projeto: definição do escopo do sistema, banco de dados, deploy, metodologia e spec adotadas para implementação"
- "adicione design system, logomarca, etc"
- "queria evoluir software factory para service factory para englobar todos os serviços"
- "como quero implementar uma missão para o grupo de agentes, eles precisam registrar isso como um projeto no Service Factory para poderem gerenciar as atividades e a documentação dos projetos em execução e a distribuição das tarefas"
- "precisa criar um pipeline para missão, service factory, operação 24x7 e atividades dos agentes. A missão é a garantia que o serviço foi concluído, ele faz o controle e monitoramento da execução"
- "na missão pode nomear os agentes, orquestrador, os executores; o contexto da missão; a validação da documentação e do plano"
- "queria adicionar o controle do contexto: memória dos agentes, Hindsight (memória estendida), base de conhecimento e a documentação da Foundation"

**Documentos ligados:** `docs/superpowers/specs/2026-10-24-missao-design.md` (frente Missão),
`docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md` (Operação 24x7),
`docs/superpowers/plans/2026-10-02-roadmap-geral.md` (roadmap anterior),
`docs/architecture/REMOTE_MAINTENANCE_PLAN.md` (manutenção remota).

## 0. Diagnóstico: o caminho está certo? (revisão de 24/10)

**Sim, a direção está certa.** Os pedidos formam um desenho coerente e quase todo apoiado no que já
existe:
- um caminho único e rastreável para todo trabalho;
- os agentes operam e o Marcelo supervisiona e dá contexto;
- a Missão garante a conclusão com critérios comprovados;
- o Service Factory organiza documentação, tarefas e pasta do projeto;
- a Operação 24x7 vigia e as Atividades dos Agentes mostram;
- o contexto é controlado por camadas;
- o Darckware é a porta de entrada;
- autonomia só sobe com critério.

**Mas há quatro problemas de execução, e o plano foi ajustado para eles:**

| # | Problema | Evidência | Ajuste |
|---|---|---|---|
| 1 | **O plano cresceu mais rápido do que qualquer entrega.** São cerca de 130 tarefas em 14 frentes e 17 decisões abertas, e nada foi implementado. Foi exatamente assim que a primeira tentativa da Missão parou no meio | Seções 6–9 | Organizado em **três ondas** com critério de saída (0.1). Cada onda só começa quando a anterior sai. O escopo fica congelado: pedido novo vira item do projeto do plano (M0.5), não texto neste documento |
| 2 | **A base ainda não foi provada.** O Service Factory nunca foi usado de verdade, o MCP não cobre o ciclo, e a regra `STATUS: DONE` tem um dia. A qualidade real das entregas dos agentes ainda é desconhecida: nos últimos 7 dias, só 1 de 170 despachos falhou, mas antes da regra "concluído" incluía trabalho cortado no meio | V, M0.2 | A Onda 1 prova a base com **uma missão real pequena** antes de construir camadas em cima |
| 3 | **Há riscos reais hoje que o plano deixava para depois.** O hook de conhecimento varre toda a `knowledge_base` (a Lara pode receber dado pessoal da Maia). O `dev.sh` e a produção usam o mesmo banco | `knowledge_cycle.py` (`rglob` na raiz); `dev.sh` | C.2 e Q.4 sobem para a **Onda 1** |
| 4 | **Conceitos demais para a mesma coisa.** Missão, Projeto, Linha de serviço, Objetivo e Rotina, com risco de confusão para os agentes e para o Marcelo | 1.3–1.6, G.1 | **A Missão vira uma extensão do Projeto**, não uma entidade nova: `project_type = mission` + critérios de aceite + papéis + brief. Objetivos (G.1) só na Onda 3 |

Também corrigido: o backup externo **já funciona** (38 execuções `ok`, a última em 24/10). O risco
"sem snapshot" estava desatualizado. Resta testar a restauração (G.12).

### 0.1 As três ondas

**Onda 1 — Base provada e riscos fechados.** Pequena, para terminar.

| Item | Por quê agora |
|---|---|
| **C.2** isolamento do `knowledge_cycle.py` (modo observação, depois ativo) | Risco de privacidade real hoje |
| **Q.4** homologação com banco separado do da produção | Agentes e o `dev.sh` tocam dado real |
| **V-a** validação do Service Factory pela tela/API | Nada se apoia em módulo não provado |
| **M0.1–M0.4** produto "Ecossistema Foundation", MCP mínimo, convenção de missão (papéis, brief, plano aprovado) e skill | Os agentes precisam conseguir registrar e conduzir uma missão |
| **M0.5** primeira missão real, pequena, conduzida pelos agentes | Prova o caminho inteiro de ponta a ponta |
| **A.1/A.2** todos os agentes e todas as rotinas nas Atividades dos Agentes | O Marcelo precisa ver o que acontece |

**Saída da Onda 1:**
- uma missão real abriu, planejou, executou, comprovou e fechou só com os agentes pelo MCP, com o
  Marcelo acompanhando, anotando e aprovando;
- C.2 está ativo com teste de vazamento verde;
- nenhum ambiente de teste aponta para o banco da produção.

**Onda 2 — Ligar o que existe.**
- S.1, S.2, S.4, S.5 (linhas de serviço; o renomear S.3 vai junto);
- R (racionalização);
- B (cadastro e importação);
- P (anotações, contexto herdado, linha do tempo);
- I (manutenção remota, horas, Auditor → tarefa, incidente);
- Q.1–Q.3 e Q.5 (git, CI, gate de produção);
- D núcleo: D.1, D.2, D.7, D.8, D.10;
- O.1–O.3;
- E.1 e E.4.

Saída da Onda 2: um serviço de cada linha percorreu o fluxo com evidência e documento, e o
Marcelo supervisionou pela linha do tempo.

**Onda 3 — Garantir e aprender.**
- Missão completa M.1a–M.1l e M.2–M.4 (sobre a extensão do Projeto);
- D restante (manual, identidade visual, auditoria de documentação);
- C restante;
- E restante;
- G (evals, lições, verificador, parada global, fila de decisões, laço de autoaperfeiçoamento, objetivos).

Regra das ondas: nada da Onda 2 começa antes de a Onda 1 sair. A exceção é o documento dos sete
sistemas (M.0), que só depende de leitura.

### 0.2 Decisões: padrões adotados

Das 17 decisões da seção 9, as que têm recomendação passam a valer **como padrão revisável**. O
Marcelo só precisa responder estas três para começar:

1. **Começar a Onda 1** como está em 0.1.
2. **Primeira missão:** pequena e real, para provar o caminho. Sugestão: o controle de contexto C.0+C.1
   (linha de base da memória dos agentes e política na Foundation), que tem orquestrador (Athos),
   executores (Mnemosyne, Themis), documentador (Scriba) e critérios verificáveis. O plano integrado
   inteiro como missão fica para depois, quando o caminho estiver provado.
3. **Quem implementa a Onda 1:** o Claude Code (esta sessão) faz C.2, Q.4, V-a e o MCP mínimo, com
   revisão de outro agente, porque a capacidade de os agentes conduzirem o trabalho é justamente o que
   a Onda 1 prova.

## 1. Objetivo

Todo trabalho do ecossistema passa por um único caminho rastreável, seja ele implementação, manutenção
de sistema, serviço em estação ou servidor de cliente, documentação, incidente ou missão:

```
Darckware (site, chat da Lara, portal) ─┐
Entrada ──► Service Factory ──► Messages ──► Agente ──► Evidência ──► Documento ──► Aceite
(pedido,     (Produto/Versão/     (único       (Hermes ou  (git/file/db/  (DocLink)     (Marcelo ou
 ticket,      Projeto/Fase/        executor)    externo)    execução                   delegação)
 check,       Tarefa)                                       remota)
 missão)
                     ▲                                                          │
                     └──── Operação 24x7 vigia, cobra e escala ◄────────────────┘
                           Agent Activity mostra tudo em tempo real
```

### 1.1 Princípio de uso: o agente opera, o Marcelo supervisiona e dá contexto

O Service Factory é **operado pelos agentes** pelo MCP `forgehub`: eles criam o planejamento, as
tarefas e as dependências, despacham, registram evidência e documentos e fecham as fases. O Marcelo
não precisa operar o módulo. Ele:
- **monitora** o que os agentes fizeram (linha do tempo, Cockpit, Agent Activity);
- **decide** o que é dele (fila única de decisões);
- **acrescenta contexto**: anotações e documentos em qualquer nível (produto, versão, projeto, fase,
  tarefa, missão), que passam a acompanhar automaticamente toda tarefa abaixo daquele nível.

Consequências para o plano:
- toda ação da tela tem uma ferramenta MCP equivalente;
- toda ação de agente é auditada com o nome do agente;
- a anotação do Marcelo é a camada de maior precedência do contexto (Fase C, camada 1);
- **regra de uso:** trabalho com entrega (código, documento, manutenção, serviço) é tarefa do Software
  Factory; o Messages é o executor e o canal de conversa entre agentes, não o lugar de registrar
  trabalho. Uma Task solta no Messages só para pergunta, aviso ou algo que não deixa entrega.

### 1.2 Para que serve o Service Factory

É o centro de gestão do desenvolvimento. O que ele gerencia, onde isso já existe e o que falta:

| O Marcelo precisa | Já existe | Falta | Tarefas |
|---|---|---|---|
| **Documentação** do projeto organizada e com estado (rascunho, em revisão, aprovado) | Concepção gera `PRD.md`, `SPEC-TECNOLOGIA.md`, `SCREEN-TEMPLATES.md`, `DESIGN-SYSTEM.md` (padrão 18 da Foundation) e copia para `docs/` do projeto; Artefatos; `DocLink`; Pipelines | Conjunto completo de documentos por projeto, estado de cada um, documento obrigatório por estágio | D.1–D.5, D.7, D.11 |
| **Manual do sistema** (uso e operação) | Telas e regras de negócio no Escopo | Manual gerado e atualizado a cada versão | D.9 |
| **Controle das tarefas** | Planejamento, tarefas, dependências, status, evidência, Cockpit | Linha do tempo e supervisão | P.5, P.6 |
| **Distribuição das demandas entre os agentes** | Atribuição, membros do projeto por tipo de solução, despacho pelo Messages | Sugestão de agente por skill/carta, MCP completo | I.11, P.1 |
| **Pasta do projeto organizada e descritiva** | Navegador de arquivos do projeto; cópia dos documentos da Concepção para `docs/` | Estrutura padrão (padrão 19), índice, guia para agentes, verificação de divergência entre a pasta e o Service Factory | D.7, D.10, D.11 |
| **Administrar e auditar** o desenvolvimento | Governança, `AuditEvent`, aprovações, fechamento de versão | Completude da documentação por projeto, auditoria de quem mudou o quê | D.11, P.5 |
| **Identidade visual:** design system, logomarca, cores, tipografia, ícones, templates de tela, protótipos | Concepção gera `DESIGN-SYSTEM.md` e `SCREEN-TEMPLATES.md`; MCP salva protótipo HTML de tela; padrão 02 da Foundation (UI e design system); o Darckware tem homologação de design própria | Logomarca e ativos guardados no projeto, tokens de design aplicáveis no código, homologação antes de implementar tela | D.12, D.13 |
| **Contexto do projeto para os agentes:** escopo, banco, deploy, metodologia, specs | Escopo e telas; modelo de banco derivado (ERD); Deploy; padrões 01–19 da stack | Um **contrato do projeto** que declara metodologia, specs e padrões adotados, banco, ambientes de deploy, e vai junto em todo despacho | D.8, P.4 |

### 1.3 De Software Factory a Service Factory

O módulo deixa de ser só a fábrica de software e passa a ser a **fábrica de todos os serviços** do
ecossistema: desenvolvimento, sustentação de sistemas, manutenção de estações e servidores, suporte
ao cliente, infraestrutura, documentação, marketing e captação, e missões.

**O que muda e o que não muda:**
- **A regra central do ForgeHub continua** (todo trabalho rastreável até produto, versão, projeto,
  planejamento, dono, status e auditoria). O que se generaliza é o significado:
  - **Produto** passa a ser *o que é atendido*: um sistema, um serviço ou o parque de TI de um cliente;
  - **Versão** passa a ser *o ciclo*: a versão do software, ou o período e contrato do serviço (ex.: `2026.4`, `Contrato 2026`).
- **Linhas de serviço (catálogo):** cada linha define o próprio fluxo (estágios do pipeline),
  os documentos obrigatórios, o tipo de evidência, os agentes padrão (pelas cartas), o prazo (SLA) e
  a ligação com o contrato do Darckware.
- **O fluxo de 6 etapas atual** (Concepção, Telas e regras, Banco e ERD, Projetos e backlog, Gate de
  governança, Fechamento de versão) **continua igual**: vira o fluxo da linha "Desenvolvimento de
  software". As outras linhas têm fluxos mais curtos.
- **Nada quebra por baixo:** rotas (`/api/v1/factory`, `/projects`, `/tasks`), tabelas e ferramentas
  MCP mantêm os nomes. Muda o que se lê na tela, na documentação, nas skills e na Foundation.

**Linhas de serviço iniciais (proposta):**

| Linha | Exemplos | Fluxo (estágios) | Evidência típica | Agentes padrão | Contrato Darckware |
|---|---|---|---|---|---|
| **Desenvolvimento de software** | Sistema novo, evolução, site | As 6 etapas atuais + homologação de design (D.13) | `git:` + CI + documento | Porthus, Aramis, Dartan | desenvolvimento |
| **Sustentação de sistemas** | Correção, atualização, dependências | Triagem → correção → verificação → registro | `git:` ou `host_execution` | Daedalus (pedido), Aramis | suporte_horas |
| **Manutenção de estações e servidores** | Script, configuração, acesso remoto | Pedido → autorização (máquinas/scripts) → execução → verificação → registro de atendimento | `host_execution` + horas | Hephaestus, Aegis, agente delegado | suporte_horas |
| **Suporte ao cliente** | Ticket, dúvida, demanda | Triagem → atendimento → resposta aprovada → encerramento | e-mail aprovado + horas | Lara (triagem), dono da área | suporte_horas |
| **Infraestrutura e operação** | VPS, backup, rede, segurança, deploy | Detecção → ação → verificação → runbook | `host_execution` / `db:` + runbook | Hephaestus, Aegis | interno |
| **Documentação e conhecimento** | Manual, KB, Foundation | Rascunho → revisão → publicação | `file:` + artefato | Scriba, Mnemosyne, Athos | interno |
| **Marketing e captação** | Campanha, conteúdo do site, análise de mercado | Proposta → aprovação → execução → medição pelo funil | artefato + métrica do funil (E.4) | Kairos, Lara | interno |
| **Missões** | Objetivo que atravessa várias linhas | Planejamento → fases → consolidação | resultado consolidado | Athos (coordenador) | — |
| **Incidentes** | Sistema fora do ar, falha crítica | Detecção → contenção → correção → pós-incidente | evidência + relatório | Hephaestus + dono | — |

### Fase S — Service Factory (antes da Fase B, depois da V)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| S.1 | **Catálogo de linhas de serviço** (tabela): nome, descrição, template de pipeline (R.2), documentos obrigatórios, tipos de evidência aceitos, agentes padrão, SLA, tipo de contrato Darckware, visível ao cliente | Aramis | V | As 9 linhas iniciais cadastradas; cada projeto pertence a uma linha |
| S.2 | **Generalizar o modelo sem quebrar:** `products.kind` (`software`, `service`, `infrastructure`, `client_it`); `project_type` passa de `creation`/`maintenance` para os tipos das linhas; o fluxo de 6 etapas só é exigido na linha de software | Aramis | S.1 | Migration com backfill (projetos atuais = Desenvolvimento); 107 testes atuais seguem verdes |
| S.3 | **Renomear para Service Factory** na tela (seção do menu, i18n pt-BR/en/es), no `CLAUDE.md`, nos documentos, na skill `forgehub` e na Foundation (pelo Athos); rotas, tabelas e ferramentas MCP mantêm o nome | Dartan + Scriba + Athos | S.2 | Nenhum "Software Factory" visível; nenhuma integração quebrada |
| S.4 | **Cockpit por linha de serviço:** árvore Linha → Produto/Serviço → Projeto, filtros por cliente e interno, indicadores por linha (abertos, atrasados, fora do SLA, horas) | Dartan + Aramis | S.1 | Celular; números batem com as tarefas |
| S.5 | **Abrir trabalho pela linha:** "Novo serviço" escolhe a linha e já cria o projeto com pipeline, documentos obrigatórios e agentes padrão; o mesmo pelo MCP | Aramis + Dartan | S.1, P.1 | Projeto novo nasce completo para a linha escolhida |
| S.6 | **Ligação com o Darckware:** contrato `suporte_horas` → linhas de suporte e manutenção, `desenvolvimento` → linha de software; o portal do cliente mostra os serviços em andamento por linha (E.2) | Aramis | S.1, E.1 | Horas e serviços do cliente batem nos dois lados |
| S.7 | **Validação por linha:** o roteiro da Fase V ganha um fluxo curto por linha (um atendimento de manutenção, um ticket, um incidente simulado, um documento) | Claude Code + agente | S.5 | Relatório por linha |

### 1.4 Missão = projeto no Service Factory: o que os agentes conseguem hoje

Para um grupo de agentes executar uma missão, ela precisa existir como projeto no Service Factory.
O projeto é onde eles gerenciam as atividades, a documentação e a distribuição das tarefas. Análise
das ferramentas MCP de 24/10:

| O grupo precisa | Hoje pelo MCP | Lacuna |
|---|---|---|
| Registrar a missão como projeto | Só pelo caminho de software novo: `create_conception_idea` (cria produto, conceito, blueprint) → aprovação do conceito → `authorize_project_delivery`. Pesado e errado para uma missão interna | **Criar projeto interno** sob um produto/versão existente, na linha "Missões", com objetivo e critério de sucesso |
| Ter onde registrar (produto e ciclo) | Não há produto real cadastrado, só dados de teste | Produto "Ecossistema Foundation" com versão `2026.4` (B.1) |
| Definir participantes e papéis | `ProjectAgentMembership` existe (13 registros), mas no módulo de Orquestração e sem ferramenta MCP | Ferramenta para gerenciar membros. **Atenção:** a R.1 aposenta a Orquestração e precisa preservar o `ProjectAgentMembership` |
| Quebrar em fases e tarefas | `create_planning_item`, `create_project_task` | — |
| Ordenar as tarefas | Não há ferramenta de dependência | `add_task_dependency` |
| Distribuir as tarefas | `release_planning_for_execution` só grava o agente no item; não cria a atribuição da tarefa nem despacha | `assign_task` e `dispatch_task` (a rota já existe) |
| Acompanhar | `list_project_tasks`, `update_task_status` | Linha do tempo (P.5) |
| Provar a entrega | Só pela resposta do Messages | `report_task_execution` com evidência |
| Documentar o projeto | `save_concept_document` (só no conceito) | Documento ligado ao projeto/fase/tarefa (`DocLink` + artefato) e a pasta `docs/missions/<slug>/` |
| Receber o seu contexto | — | Anotações (P.2) e contexto herdado no despacho (P.4) |

### Fase M0 — Caminho rápido: a primeira missão como projeto (logo após a V-a)

Antes do módulo completo de Missão (M.1), o grupo já pode trabalhar numa missão registrada como
projeto, por convenção. A camada de Missão vem depois e se apoia nesses mesmos projetos.

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| M0.1 | Produto "Ecossistema Foundation" (interno, sem cliente) com versão `2026.4` | Claude Code (via API), Marcelo confirma | V-a | Aparece no Cockpit |
| M0.2 | Ferramentas MCP mínimas para o grupo: `create_internal_project` (produto/versão, linha, objetivo, critérios de aceite, orquestrador, pasta), `manage_project_members` (com função), `submit_project_plan` (Plano do projeto para aprovação), `add_task_dependency`, `assign_task`, `dispatch_task`, `report_task_execution` (evidência), `attach_project_document` (`DocLink`) | Aramis, Porthus revisa | V-a | Um agente cria e conduz um projeto de missão inteiro pelo MCP |
| M0.3 | **Convenção de missão** até a M.1: projeto do tipo missão; o primeiro planning item é "Objetivo e critérios de aceite" (um critério por linha, cada um com a tarefa e a evidência que o comprovam); fases = planning items; orquestrador = Athos (`coordinator`); executores, verificadores, planejador e documentador como membros do projeto com a função; `BRIEF.md` e documentos em `docs/missions/<slug>/` com `00-INDICE.md`; plano no Plano do projeto, aprovado pelo Marcelo antes de despachar; toda tarefa termina com `STATUS: DONE` e evidência | Athos (Foundation) + Scriba | M0.2 | Convenção publicada na skill `forgehub` e na Foundation |
| M0.4 | **Skill "como conduzir uma missão"** na skill compartilhada `forgehub`: registrar, planejar, distribuir, acompanhar, documentar, consolidar | Athos + Claude Code | M0.3 | Os agentes seguem o mesmo roteiro |
| M0.5 | **Primeira missão real:** o próprio plano integrado, registrado como projeto de missão (fases do plano = planning items, tarefas = tarefas), com o Athos coordenando e você acompanhando e anotando | Athos | M0.4 | O avanço do plano é visto no Cockpit, não em documento solto |

A M.1 (módulo completo) passa a acrescentar o que a convenção não cobre: campos próprios de missão,
consolidação automática, contexto por destinatário (M.2) e a tela `/missions`.

### 1.5 Pipeline de ponta a ponta: Missão → Service Factory → Operação 24x7 → Atividades dos Agentes

**A Missão é a garantia de que o serviço foi concluído.** Ela define o que é "concluído", controla e
monitora a execução, e só se encerra quando cada critério está comprovado. Os outros três componentes
executam e observam. Ninguém além da Missão declara um serviço terminado.

```
 MISSÃO (garantia)          SERVICE FACTORY (gestão)       OPERAÇÃO 24x7 (vigilância)    ATIVIDADES DOS AGENTES (visão)
 ─────────────────          ────────────────────────       ──────────────────────────    ──────────────────────────────
 1 Abertura ───────────────► 2 Planejamento
   objetivo, critérios        projetos por linha,
   de aceite, prazo,          fases, tarefas,
   coordenador                dependências, docs,
        ▲                     agentes
        │                          │
        │                          ▼
        │                     3 Execução ─────────────────► vigia prazos, falhas,  ──► tempo real de cada agente,
        │                       despacho pelo Messages,       bloqueios; cobra,          rotina e execução, com a
        │                       STATUS + evidência            escala, pergunta           origem (missão/projeto/tarefa)
        │                          │                               │                          │
        │                          ▼                               ▼                          ▼
 5 Verificação ◄──────────── 4 Entrega por tarefa ◄────── sinais de saúde ◄─────────── eventos e indicadores
   cada critério × evidência   evidência verificada,
   documentação aprovada       documento registrado
        │
        ▼
 6 Aceite e encerramento ──► lições (G.7) e melhoria
   cliente (portal) e Marcelo
```

**Estágios, responsáveis e gates**

| # | Estágio | Componente | Entra | Sai | Gate para avançar |
|---|---|---|---|---|---|
| 1 | **Abertura** | Missão | Pedido do Marcelo, ticket/proposta do cliente, proposta da retrospectiva | Objetivo, **critérios de aceite** (cada um verificável), prazo, coordenador, linhas de serviço, orçamento | Marcelo aprova (ou delegação) |
| 2 | **Planejamento** | Service Factory | Missão aprovada | Projeto(s) por linha com pipeline da linha, fases, tarefas, dependências, documentos obrigatórios, agentes; **cada critério de aceite ligado às tarefas que o cumprem** | Coordenador confirma que todo critério tem tarefa; Marcelo aprova o plano (até o nível M1) |
| 3 | **Execução** | Service Factory + Messages | Tarefa pronta (dependências concluídas) | Despacho com contexto (contrato, anotações, missão); resultado com `STATUS` e evidência | `STATUS: DONE` |
| 4 | **Entrega por tarefa** | Service Factory | Resultado da execução | Evidência verificada (`git:`/CI, `host_execution`, `file:`, `db:`), documento registrado; `PARTIAL`/`BLOCKED` voltam à execução com motivo | Evidência verificada + documento do estágio |
| — | **Vigilância contínua** (estágios 3 e 4) | Operação 24x7 | Sinais de todas as tarefas da missão | Cobrança ao agente, reatribuição, pergunta ao Marcelo, escalada ao coordenador | — |
| — | **Visibilidade contínua** | Atividades dos Agentes | Eventos de execução, rotinas, telemetria | Quem está fazendo o quê, para qual missão, e há quanto tempo | — |
| 5 | **Verificação** | Missão | Tarefas entregues | Cada critério de aceite marcado como cumprido, com a evidência que prova; verificador independente (G.5) quando o tipo exige | **Todos** os critérios comprovados; nenhum documento obrigatório pendente |
| 6 | **Aceite e encerramento** | Missão | Verificação completa | Resultado consolidado, documento final, aceite do cliente no portal (se houver) e do Marcelo; lições registradas | Aceite explícito; sem aceite, a missão volta ao estágio que falhou |

**Como a Missão monitora (o "controle da execução")**

A missão calcula continuamente a própria **saúde** a partir das tarefas dos seus projetos, e a mostra
como um semáforo:

| Sinal | Fonte | Vira alerta quando |
|---|---|---|
| Avanço por critério de aceite | tarefas ligadas a cada critério | um critério não tem tarefa, ou nenhuma tarefa dele avançou em N dias |
| Prazo | datas das tarefas × prazo da missão | caminho crítico passa do prazo |
| Bloqueios e falhas | `blocked`, `PARTIAL`, `BLOCKED`, falha no Messages | qualquer bloqueio > 24 h, ou 2 falhas na mesma tarefa |
| Evidência pendente | tarefas `reported` sem verificação | entrega sem prova > 24 h |
| Documentação | documentos obrigatórios do pipeline | estágio concluído sem documento |
| Rotinas e agentes | Operação 24x7 e Atividades dos Agentes | agente da missão degradado, rotina de vigilância perdida |
| Custo | ForgeRouter e horas (Q.7) | consumo acima do orçamento |
| Cliente | portal Darckware (E.2/E.3) | ajuste pedido ou aceite pendente |

Cada alerta vai para quem age:
- ao **coordenador**, como tarefa de triagem;
- ao **Marcelo**, pela fila de decisões (G.11), só quando a decisão é dele;
- ao **agente responsável**, como cobrança pela Operação 24x7.

A saúde da missão aparece no Cockpit, no briefing do Athos e no painel da própria missão.

**Regras do pipeline**
1. Só a Missão declara um serviço concluído. Tarefa `done` e fase concluída são etapas, não o fim.
2. Todo critério de aceite precisa de evidência verificável. Critério sem prova não fecha.
3. Todo trabalho de missão passa pelo Service Factory. Execução fora dele não conta para a missão.
4. A Operação 24x7 nunca encerra nada: ela cobra, reatribui e escala.
5. As Atividades dos Agentes nunca decidem nada: elas mostram, com a origem de cada execução.
6. Falha em qualquer estágio volta ao estágio anterior, com motivo registrado. Nada é apagado.

### 1.6 Papéis, contexto e validação na missão

#### Papéis (nomeados na abertura da missão)

Reaproveitam o vocabulário único de funções que já existe (`PROJECT_AGENT_ROLES`, usado por membros
de projeto, agentes e canais). Nada de lista nova.

| Papel na missão | Função existente | Quantos | Quem (padrão) | Faz | Nunca faz |
|---|---|---|---|---|---|
| **Patrocinador / aprovador** | — (pessoa) | 1 | Marcelo | Aprova abertura, plano, documentos-chave e aceite final; anota | — |
| **Orquestrador** | `coordinator` | exatamente 1 | Athos | Planeja com o planejador, distribui, acompanha a saúde, resolve bloqueios, consolida | Executar código (é agente Hermes); verificar a própria consolidação |
| **Planejador** | `planner` | 0–1 | Atlas | Monta o plano (fases, tarefas, dependências, critérios × tarefas) | Aprovar o próprio plano |
| **Executores** | `developer`, `designer`, `data_engineer`, `architect`, `release_manager`, `compliance`, `knowledge_management` | 1 ou mais | Por linha e carta: código só Aramis, Porthus, Dartan | Executam as tarefas e entregam evidência | Verificar a própria entrega |
| **Verificadores** | `reviewer`, `qa`, `security_reviewer` | 1 ou mais | Porthus (código), Aegis (segurança), outro agente da área | Comprovam entregas e critérios de aceite | Verificar o que eles mesmos executaram |
| **Documentador** | `documentation` | 1 | Scriba | Mantém o brief, os documentos obrigatórios e o resultado final | Aprovar o próprio documento |

**Regras checadas automaticamente ao nomear:**
- exatamente um orquestrador;
- código só com executor de runtime externo;
- verificador nunca é o executor da mesma tarefa;
- o papel respeita o "nunca faz" da carta do agente;
- o agente está ativo e com canal saudável;
- há limite de missões simultâneas por orquestrador e de carga por executor.

#### Contexto da missão (o "brief")

Um documento único, versionado, `docs/missions/<slug>/BRIEF.md`, registrado como Artefato. Contém:
- objetivo;
- histórico e motivação;
- escopo e fora de escopo;
- critérios de aceite;
- restrições;
- decisões já tomadas;
- referências: contrato do projeto (D.8), documentos do produto, Foundation, Base de Conhecimento;
- riscos;
- glossário;
- papéis.

O brief é a base do contexto enviado em cada despacho, junto com as anotações do Marcelo (P.4) e os
itens de contexto filtrados por destinatário (M.2). Mudou o brief? Sai uma nova versão, os membros são
avisados e as próximas tarefas já recebem a versão nova.

#### Validação do plano

O plano da missão usa o **Plano do projeto que já existe** (`ProjectPlan`: rascunho → aprovado →
baseline → substituído) e o **change request** para mudanças depois da baseline.

1. **Checagem automática**, antes de pedir aprovação:
   - todo critério de aceite tem tarefa;
   - toda tarefa tem papel e agente compatíveis;
   - as dependências não formam ciclo;
   - o caminho crítico cabe no prazo;
   - todo documento obrigatório tem dono;
   - toda entrega tem verificador;
   - o orçamento cabe;
   - os riscos estão listados.
2. **Revisão:** o orquestrador revisa o que o planejador montou.
3. **Aprovação:** o Marcelo aprova, e o plano vira baseline. **A aprovação do plano autoriza a execução
   das tarefas daquela baseline.** Não é preciso aprovar tarefa por tarefa, o que concilia com a regra
   dos canais "a execução real fica com o Marcelo" (`CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md` §3.3).
4. **Depois da baseline:** só por change request aprovado. Mudança de prazo, escopo ou critério reabre a validação.

#### Validação da documentação

- **Ciclo por documento:** autor → revisão por outro agente → aprovação. Os estados seguem o padrão 18
  da Foundation (rascunho, em revisão, aprovado), mapeados nos estados do Artefato
  (`draft`, `submitted`, `approved`) e das versões (`draft`, `final`, `superseded`).
- **Documentos-chave aprovados pelo Marcelo:** brief, escopo/PRD, plano, resultado final. Os demais são
  aprovados pelo verificador ou pelo documentador.
- **Checagem automática:** cabeçalho com estado/dono/data, links válidos, nenhum segredo, nenhum nome
  ou id interno em documento visível ao cliente.
- **Regra:** a missão só passa da verificação (estágio 5) com todos os documentos obrigatórios aprovados.

#### Lacunas encontradas

| # | Lacuna | Tarefa |
|---|---|---|
| 1 | Os papéis existem por projeto (`ProjectAgentMembership`), mas não por tarefa: não há verificador nomeado por entrega | M.1e |
| 2 | Nenhuma regra é checada ao nomear (independência, runtime de código, "nunca faz" da carta, carga) | M.1e |
| 3 | O orquestrador não recebe autoridade sobre o projeto; a delegação pode ser limitada a projeto, mas nada a concede | M.1f |
| 4 | Não há substituto quando o orquestrador fica indisponível | M.1f |
| 5 | Não existe o brief da missão nem o seu ciclo de versão e validação | M.1g |
| 6 | O Plano do projeto existe (1 registro) mas não é usado; não há checagem automática do plano | M.1h |
| 7 | A independência na revisão de documentos não é exigida; não há checagem automática de documento | M.1i |
| 8 | A missão não ganha um canal de coordenação, embora canais já aceitem projeto e membros com função | M.1j |
| 9 | O agente não tem como perguntar "qual é o meu papel e as minhas tarefas nesta missão" pelo MCP | M.1k |
| 10 | A regra dos canais "execução real só com o Marcelo" não diz como fica numa missão com plano aprovado | Resolvida acima (aprovação da baseline autoriza as tarefas dela); registrar na Foundation (M.1l) |

## 2. Componentes existentes e papel no conjunto

| Componente | Papel no conjunto | Estado |
|---|---|---|
| **Service Factory** (Produto, Versão, Concepção, Mapa do Sistema, Escopo, Planejamento, Tarefas, Governança, Fechamento de Versão, Cockpit) | **Registro e gestão** de todo trabalho: o que, por quê, quem, em que ordem, com que evidência | Construído, 107 testes automatizados verdes, **sem uso real** (só 4 projetos de teste) |
| **Messages** (+ Incubação) | **Único executor**: fila, teto por agente, prazo, `STATUS: DONE`, reprocesso, retorno | Em produção |
| **Operação 24x7** (cartas, rotinas, dúvidas, Evolução) | **Vigilância e iniciativa**: rotinas, triagem, briefing, autonomia A0/A1/A2 | Em produção; só 3 de 18 rotinas ligadas |
| **Auditor / Crons** | **Detecção**: checks com dono; check falho → Task | Em produção (Task solta no Messages) |
| **Agent Activity** | **Tempo real**: estado dos agentes, timeline, replay, alertas | Em produção; externos só aparecem quando rodam; não mostra rotinas |
| **Acesso Remoto** (máquinas, scripts, execuções, delegações, "Pedir ao agente") | **Execução de manutenção** em estações e servidores pelo Tailscale | Em produção; tarefa do Messages autoriza o agente |
| **Clientes (Darckware)** no ForgeHub (`client_ops.py`: leads, conversões, cadastros, tickets, demandas, e-mails, contratos, horas, informe mensal, "criar projeto") | **Operação do cliente**: origem do trabalho e consumo da franquia | Em produção; ainda **não** cobre os projetos propostos ao cliente, a analytics do site nem as conversas da Lara |
| **Docs** (`/docs` + `DocLink`) | **Registro documental** ligado a produto, versão, projeto, fase e tarefa | Em produção; nada obriga o vínculo |
| **Governança** (`Approval`, `AuthorityDelegation`, `AuditEvent`) | **Aceite e autoridade** | Em produção |
| **Deploy / System Control** | Entrega e operação da infraestrutura | Em produção |
| **Canais / Workspace** | Conversa que pode virar tarefa (`:dispatch-task`) | Em produção |
| **Pessoal (Maia)** | Trabalho pessoal do Marcelo; fora do Service Factory | Em produção (sem ligação, por desenho) |
| **Hermes** | Runtime dos agentes: perfis, gateway único, canais (Telegram, WhatsApp), skills, cron, memória | Em produção |
| **ForgeRouter** | Camada de modelos: roteamento, fallback, custo (free e pagos); os runtimes externos usam o modelo nativo | Em produção (projeto próprio) |
| **ForgeVault** | Segredos e credenciais: só pelo host-bridge, conta de serviço por finalidade | Em produção |
| **Tailscale** | Rede: acesso da VPS a todas as estações e servidores (direto ou por sub-rede), base da manutenção remota | Em produção |
| **RustDesk** | Acesso remoto assistido (tela) às estações, quando o SSH não basta ou o atendimento é visual | Em produção |
| **Darckware** | **Porta de entrada na internet para captar clientes**: site institucional com analytics, chat da Lara, leads, orçamento, conversão em cliente, portal do cliente (tickets, demandas, contratos, equipe, projetos propostos para aprovação) e a fila de e-mails aprovados. "Darckware guarda, ForgeHub opera" | Em produção (repositório próprio) |
| **Missão** | **Objetivo** acima de projetos: coordena agentes e contexto | Proposta (`2026-10-24-missao-design.md`) |

### 2.1 Outros componentes já existentes (inventário completo, 24/10)

Levantamento de todos os módulos (`backend/app/api/routes/*`) com o uso real no banco. Cada um tem
uma decisão no conjunto, para não haver dois caminhos para a mesma coisa.

| Componente | Uso real | Decisão | Tarefa |
|---|---|---|---|
| **Pipelines** (estágios, templates, artefatos obrigatórios, gates — SPEC 6.2) | 0 pipelines, 1 template | **Reaproveitar** como as fases de cada tipo de projeto: um template por tipo (implementação, sustentação, serviço, missão), com os documentos obrigatórios de cada estágio. Substitui a "tarefa de documentação" inventada | R.2, D.1 |
| **Artefatos** versionados (SPEC 4.7) | 7 artefatos, 7 versões | **Reaproveitar** como o registro formal de cada entrega documental (versão, autor, estágio); o `DocLink` aponta o arquivo | D.2 |
| **Execution Waves / Work Packages / runner** (`execution.py`) | 0 ondas, 0 pacotes | **Aposentar**: é um segundo executor e contraria "Messages é o único executor". O card simulado do Cockpit sai junto | R.1 |
| **Orquestração** (`orchestration.py`) | despacho direto já retirado (410) | **Aposentar** o restante, mantendo só o que o Cockpit ainda lê | R.1 |
| **Progresso governado** (`progress.py`: checkpoints, recuperação, conclusão de estágio) | 0 checkpoints | **Avaliar na validação**: se a conclusão de estágio do Pipeline cobre, aposentar; senão, fundir no Pipeline | V.13, R.3 |
| **Plano do projeto, baseline, change request, WBS** (`project.py`) | 1 plano, 0 baselines, 0 CRs, 0 nós | **Validar** (V.14). Change request passa a ser o caminho para mudar o escopo de versão publicada | V.14 |
| **Gerar via IA** (`ai_draft.py`, nas 5 fases) | — | **Validar** (V.15) | V.15 |
| **Scripts e agendamentos de manutenção** (`host_script.py`) | 18 scripts, 0 agendamentos, 24 execuções | **Integrar**: execução agendada registra evidência na tarefa recorrente do projeto Sustentação; falha abre tarefa para o dono | I.10 |
| **Máquinas e grupos** (`server.py`, `host_group.py`) | 22 máquinas, 1 grupo | **Integrar**: grupo de máquinas ↔ cliente Darckware ↔ projeto de serviço; tarefa de manutenção escolhe máquinas do grupo | I.2 |
| **Deploy** (`deploy.py`) + **Releases** (`product.py`) | 19 instalações, 0 releases | **Integrar**: publicar versão cria a Release e a liga às instalações implantadas; o Deploy mostra a versão em produção | D.6 |
| **Tools dos agentes** (`tool.py`), **skills**, **catálogo MCP** (`mcp_catalog.py`) | 21 tools, 10 MCP | **Integrar** no planejamento: `TaskRequiredSkill` já existe; sugerir o agente pelas skills/tools e pela carta | I.11 |
| **Auditor** (`audit.py`), **Crons/Scripts** (`cron_scripts.py`, `foundation_script.py`) | 59 checks, 79 scripts de cron, 37 scripts Foundation | **Integrar**: check falho → Sustentação (I.7); script órfão ou cron falho → tarefa para o dono | I.7, I.12 |
| **Backup externo, System Control, Hindsight, ForgeRouter** | em uso | **Integrar** as falhas como trabalho: backup falho, disco cheio, provedor de modelo com erro → tarefa no Sustentação do produto | I.12 |
| **Notificações** (`notifications.py`) | 1027 | **Manter como caixa única**: todo evento novo do conjunto chega aqui com dedupe por `event_key` | todas |
| **Foundation docs**, **Knowledge Base** (`vault.py`), **Docs** | em uso | **Destinos da documentação**: projeto → `/docs`; regra/política → Foundation (pelo Athos); conhecimento → KB (pelo Scriba/Mnemosyne) | D.3 |
| **Canais, Chat, Workspace, Terminal, Explorer, Navegador compartilhado** | em uso | Ferramentas do operador; Canal → tarefa em I.8; o resto fica fora do fluxo | I.8 |
| **Usuários, perfis, TOTP** | em uso | Cada tela nova (Missões, Sustentação) ganha a chave de permissão do módulo | M.1, B.3 |
| **Database, Systemstats, Tool versions, System info, Remote access (túnel)** | em uso | Utilitários; fora do fluxo de trabalho | — |
| **Pessoal (Maia)** | em uso | Fora do Service Factory por desenho (vida pessoal) | — |

## 3. Tipos de trabalho e como cada um entra

| Tipo | Entrada | Onde fica no Service Factory | Evidência de conclusão |
|---|---|---|---|
| **Implementação** | Concepção/escopo, missão, pedido do Marcelo | Produto do sistema → versão em desenvolvimento → projeto da evolução | `git:<sha>` + teste, documento da fase |
| **Manutenção de sistema** (corretiva, preventiva, atualização) | Check do Auditor, rotina, incidente, pedido | Produto do sistema → versão em produção → **projeto permanente "Sustentação"** | `git:` ou `host_execution` + documento/runbook |
| **Serviço em estação/servidor de cliente** | Ticket ou demanda Darckware, "Pedir ao agente" | Produto interno "Serviços de Manutenção" → projeto por ticket/demanda (já existe `:create-project`), com o cliente | `host_execution` (todas as máquinas `ok`) + horas lançadas no Darckware |
| **Infraestrutura interna** (VPS, servidores próprios) | Rotina do Hephaestus/Aegis, check | Produto "Ecossistema Foundation" → projeto "Sustentação" | `host_execution` ou `db:` + runbook |
| **Documentação** | Fase concluída, missão, rotina do Scriba | Tarefa `documentation` dentro do projeto que gerou | `file:` + `DocLink` |
| **Missão** | Marcelo ou agente (rascunho) | Projeto interno (sem cliente) da missão | Fases concluídas + resultado consolidado |

Projetos internos não têm cliente (`darckware_client_id` vazio). Só o serviço a cliente carrega o
cliente, herdado do ticket ou da demanda.

## 4. Mapa de interligações

`✅` já existe · `🔶` existe em parte · `❌` falta. A coluna "Tarefa" aponta a linha do plano (seção 6).

| De → Para | Ligação | Estado | Tarefa |
|---|---|---|---|
| ProjectTask → Messages | `POST /tasks/{id}/dispatch` cria a Task e despacha | ✅ | validar (V) |
| Messages → ProjectTask | resultado → `TaskExecution` `reported` → evidência verificada | ✅ | validar (V) |
| `STATUS: DONE` → TaskExecution | `PARTIAL`/`BLOCKED` devem refletir na tarefa | 🔶 | I.3 |
| Aprovação → despacho | aprovar `project_task` despacha | ✅ | validar (V) |
| ProjectTask → Acesso Remoto | a Task despachada autoriza `run_maintenance_script`, mas sem limitar máquinas/scripts | 🔶 | I.4 |
| Execução remota → evidência | `db:host_execution:<id>` não é aceito; sucesso por máquina não é verificado | ❌ | I.5 |
| Execução remota → ProjectTask | `host_executions.agent_demand_id` existe; falta mostrar na tarefa | 🔶 | I.5 |
| Ticket/demanda Darckware → Projeto | `:create-project` | ✅ | validar (V) |
| Tarefa de cliente → horas Darckware | lançar horas ao concluir a tarefa | ❌ | I.6 |
| Check do Auditor → trabalho | cria Task solta no Messages | 🔶 | I.7 (tarefa no projeto Sustentação do dono) |
| Incubação → planejamento | promover ideia a Planning Item | 🔶 | I.8 |
| Canal → tarefa | `:dispatch-task` cria AgentDemand | 🔶 | I.8 (opção de criar ProjectTask) |
| Tarefa/fase → documento | `DocLink` existe, não é obrigatório | 🔶 | D.1–D.3 |
| Publicar versão → notas | `release_notes` existe, sem geração | 🔶 | D.4 |
| Rotina → Agent Activity | rotinas não aparecem | ❌ | A.2 |
| Agente externo → Agent Activity | só aparece rodando | 🔶 | A.1 |
| Service Factory → Agent Activity | a execução não mostra tarefa/projeto | 🔶 | A.3 |
| Service Factory → Operação 24x7 | triagem/briefing não olham tarefas de projeto | ❌ | O.1–O.3 |
| Tudo → Evolução | métricas só de rotinas | 🔶 | O.4 |
| Missão → tudo | nova camada | ❌ | M.* (spec da Missão) |
| Anotação/contrato → despacho | anotações e contrato do projeto no corpo da tarefa | ❌ | P.4, D.8 |
| Projeto proposto (Darckware) → Service Factory | aprovação no portal cria o projeto | ❌ | E.1 |
| Service Factory → pasta do projeto | só a cópia dos documentos da Concepção | 🔶 | D.7, D.10 |
| Tarefa de código → git/PR/CI | evidência `git:<sha>` sem branch, PR nem CI | 🔶 | Q.1–Q.3 |
| Release → Deploy | releases não usadas | ❌ | D.6, Q.5 |
| Hindsight/KB/Foundation → ForgeHub | edição de KB e Foundation; Hindsight só status | 🔶 | C.4 |

## 5. Agent Activity: acompanhar todas as rotinas e monitorar todos os agentes

Hoje: estado ao vivo dos agentes Hermes pela telemetria, agentes externos só enquanto há um despacho
rodando, alertas, timeline e replay. Rotinas e cartas ficam só em `/operations`.

Alvo:
1. **Todos os agentes sempre no quadro**, os 13 das cartas, Hermes e externos. Um externo parado
   aparece "ocioso", nunca some. Para cada agente:
   - estado (executando, pensando, aguardando, ocioso, degradado);
   - canal Telegram e gateway;
   - próxima rotina e última execução;
   - fila no Messages;
   - orçamento do dia usado (execuções e custo).
2. **Rotinas na timeline:** cada ocorrência é um bloco na faixa do agente, com cor por desfecho
   (agendada, rodando, concluída, falhou, perdida, pulada por orçamento). Uma ocorrência perdida gera
   alerta. A grade mostra também as próximas 24 h.
3. **Ligação com o trabalho:** cada execução mostra a origem (rotina, ProjectTask com projeto e fase,
   missão, ticket, execução remota) e leva até ela com um clique.
4. **Saúde por agente:** taxa de `DONE` na primeira tentativa (7 dias), falhas, reprocessos, rotinas
   perdidas e dúvidas sem resposta. É o que a Evolução já mede, agora visível por agente.
5. **Alertas novos:** rotina perdida, agente sem rotina ligada há mais de N dias quando a carta prevê
   rotina, tarefa de projeto parada além do prazo, execução remota com falha.

Princípio mantido: o ForgeHub não lê o banco de nenhum runtime. Tudo vem do que já é dele (Messages,
rotinas, cartas, execuções remotas) e da telemetria que os runtimes enviam.

## 6. Plano de implementação (conjunto completo)

Ordem: **validar o Service Factory primeiro**, racionalizar o que está duplicado, ligar os componentes nele, depois a Missão.
Cada linha vira uma ProjectTask com dependência (`TaskDependency`) no projeto interno "Plano
integrado" (produto ForgeHub), assim que a Fase V estiver aprovada. Quem escreve não revisa o próprio
código: Porthus revisa Aramis e Dartan.

### Fase V — Validação do Service Factory (agente opera, Marcelo acompanha, Claude Code corrige)

Base automatizada: 107 testes do Service Factory passando em 24/10 (e2e, cockpit, MCP, escopo, versão,
tarefas, evidência, aprovação governada, produto, projeto, backlog, governança). Falta o uso real.

A validação tem duas passadas, para não depender de algo que ainda não existe:
- **V-a, pela tela/API:** o roteiro abaixo inteiro, com o Marcelo acompanhando e o Claude Code
  corrigindo os defeitos.
- **V-b, um agente pelo MCP:** o mesmo roteiro, só com as ferramentas que o MCP já tem. O que o
  agente não conseguir fazer vira a lista exata da P.1.

| # | Roteiro | Resultado esperado |
|---|---|---|
| V.1 | Criar produto interno (sem cliente) e versão no Cockpit | Aparece na árvore; produto nunca fica sem versão |
| V.2 | Concepção → submeter → decidir | Gate de aprovação respeitado |
| V.3 | Mapa do Sistema: elementos, relações, validar | Validação aponta inconsistências |
| V.4 | Autorizar planejamento da entrega | Projetos, membros e tarefas criados com responsável |
| V.5 | Planejamento: Planning Items, tarefas, dependências | Tarefa com predecessor aberto não despacha (409) |
| V.6 | Despachar tarefa a um agente | Mensagem no Messages, execução registrada, `STATUS: DONE` → `reported` → evidência verificada |
| V.7 | Aprovação de `project_task` | Aprovar despacha; falha vira notificação |
| V.8 | Ligar documento à tarefa e à fase (Docs) | Aparece nos dois lados |
| V.9 | Fechar versão | Bloqueia com tarefa aberta; trava escopo/telas/planejamento depois de publicada |
| V.10 | Cockpit e Telemetria | Fases, custo por projeto, telemetria por agente coerentes |
| V.11 | Ticket Darckware → "Criar projeto" | Projeto com cliente e origem; idempotente |
| V.12 | Celular (390 px) nas telas acima | Sem corte nem rolagem lateral |
| V.13 | Pipeline do projeto: estágios, artefatos obrigatórios, gate; e o Progresso governado | Estágio não conclui sem artefato; definir se o Progresso é redundante |
| V.14 | Plano do projeto, baseline, change request e WBS | Baseline congela; change request altera o escopo com aprovação |
| V.15 | "Gerar via IA" nas fases | Rascunho gerado, nunca aplicado sem revisão |

Cada defeito encontrado vira tarefa no projeto "Validação do Service Factory" e é corrigido antes da
Fase I. Entregável: relatório da validação (documento ligado ao projeto) com o que passou e o que foi corrigido.

### Fase P — Agentes operam o Service Factory; Marcelo supervisiona e anota (seção 1.1)

Hoje o MCP já cobre: listar e ler projetos, planning items, tarefas, telas e ERD; criar ideia de
concepção, documento de conceito, escopo, telas, modelo de banco, planning item e tarefa; atualizar
status de tarefa; reportar bloqueio de governança; liberar execução; criar e publicar versão; e a
manutenção remota. **Não existe** anotação nas entidades do Service Factory.

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| P.1 | **Completar o MCP** para o ciclo inteiro sem a tela, a partir da lista da V-b: dependências, atribuição, despacho, relatar execução com evidência, atualizar planning item e estágio do pipeline, change request, anexar documento/artefato (`DocLink`), criar item no Sustentação, ler a linha do tempo | Aramis | V-b, R.2 | Um agente percorre o roteiro da Fase V inteiro só pelo MCP |
| P.2 | **Anotações** (`annotations`, polimórfica como `AuditEvent`): em produto, versão, projeto, fase, tarefa, missão, máquina e cliente; tipos `instrução`, `contexto`, `decisão`, `correção`, `observação`; autor (Marcelo ou agente); fixar; validade; anexos por `DocLink` (upload vai para `/docs`). Agente nunca edita nem apaga anotação do Marcelo | Aramis | V | Testes de permissão; histórico auditado |
| P.3 | **Painel "Anotações e documentos"** reutilizável em todas as telas de detalhe do Service Factory, da Missão e do Agent Activity; escrever em Markdown, anexar arquivo, fixar; pelo celular também | Dartan | P.2 | 390 px; `ConfirmDialog` para arquivar |
| P.4 | **Contexto herdado no despacho:** ao despachar uma tarefa, o corpo inclui as anotações ativas da tarefa e dos níveis acima (missão → projeto → versão → produto), em ordem de precedência (instrução do Marcelo primeiro), resumidas e com os documentos citados; MCP `get_task_context` devolve o mesmo pacote | Aramis | P.2, C.2 | Teste: anotação do projeto chega a toda tarefa do projeto; anotação privada respeita o escopo da Fase C |
| P.5 | **Linha do tempo por projeto/missão:** tudo o que os agentes fizeram (criações, mudanças de status, despachos, execuções, evidências, documentos, execuções remotas), filtrável por agente, com "o que mudou desde a sua última visita" | Aramis + Dartan | P.1 | Toda ação de agente aparece com autor e link |
| P.6 | **Visão de supervisão** no Cockpit: o que espera o Marcelo (G.11), o que travou, o que os agentes mudaram nas últimas 24 h, e anotar com um toque a partir de qualquer item | Dartan | P.5, G.11 | Celular; um toque leva do item à anotação |
| P.7 | **Anotação vira conhecimento:** promover uma anotação para documento do projeto, Base de Conhecimento ou Foundation, por tarefa (Scriba/Mnemosyne/Athos, Fase C) | Aramis | P.2, C.3 | Promoção registrada; a anotação aponta o destino |
| P.9 | **Anotar pelo Telegram:** o Marcelo dita uma anotação ou instrução para um projeto/tarefa ("anota no projeto X: ...") ao Athos ou à Maia, que registram pelo MCP com ele como autor | Aramis + Athos (skill) | P.2 | Anotação aparece no projeto com origem Telegram |
| P.8 | Agentes também anotam (`observação`, `decisão`) quando algo for útil para o próximo agente ou para o Marcelo; skill `forgehub` ensina quando anotar e quando abrir tarefa | Aramis + Athos (skill) | P.2 | Skill atualizada; anotações de agente distinguíveis das do Marcelo |

### Fase R — Racionalização (um caminho para cada coisa)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| R.1 | Aposentar Execution Waves/Work Packages/runner e o restante da Orquestração (rotas 410, telas e card simulado do Cockpit removidos; tabelas vazias removidas por migration), **preservando o `ProjectAgentMembership`** (membros do projeto, usados pela Missão e pela autorização de entrega), que passa para o domínio de projeto | Aramis + Dartan | V | Nenhuma rota de execução fora do Messages; membros do projeto intactos; testes ajustados |
| R.2 | Templates de Pipeline por tipo de projeto (implementação, sustentação, serviço, missão) com estágios e artefatos obrigatórios | Atlas (conteúdo) + Aramis | V.13 | Projeto novo recebe o pipeline do seu tipo |
| R.3 | Progresso governado: fundir no Pipeline ou aposentar, conforme V.13 | Aramis | V.13 | Uma só noção de "estágio concluído" |
| R.4 | Revisão | Porthus | R.1–R.3 | Aprovação registrada |

### Fase B — Base cadastral

| # | Tarefa | Dono | Aceite |
|---|---|---|---|
| B.1 | Produtos a partir dos repositórios reais em `/root/project`: Ecossistema Foundation (inclui Hermes, Tailscale, RustDesk), ForgeHub, ForgeRouter, ForgeVault, Darckware, CoreTI, Duplica, SAEDAS, FileNest, OsintKey, Marketing, Serviços de Manutenção; internos sem cliente, os de cliente com o cliente; versão em produção de cada um | Atlas, Marcelo aprova a lista | No Cockpit; interno marcado |
| B.2 | Projeto permanente "Sustentação" por produto (manutenção corretiva, preventiva, atualização) | Atlas | Um por produto, sem cliente |
| B.3 | Marcar "Interno" na tela e no Cockpit para projeto sem cliente | Dartan | Visível na lista e no detalhe |
| B.4 | **Importar o estado atual** de cada produto: pasta e repositório (`working_directory_path`, remoto git), documentos existentes (`docs/`, `CLAUDE.md`, specs e planos), pendências abertas (`docs/PENDENCIAS.md`, Messages em aberto, Incubação) como planning items, e o que está em produção (Deploy) | Atlas + Scriba, Marcelo revisa | O Service Factory reflete o que existe hoje, não começa vazio |

### Fase I — Interligações de execução

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| I.1 | Tipo de item `maintenance` e `service` no planejamento (além dos atuais) | Aramis | V | Migration do CHECK; filtros na tela |
| I.2 | Tarefa de manutenção com **máquinas e scripts autorizados** (mesmo registro do "Pedir ao agente"), preenchidos na tarefa | Aramis + Dartan | I.1 | Agente fora das máquinas/scripts da tarefa → 403 |
| I.3 | `PARTIAL`/`BLOCKED` do Messages → ProjectTask `blocked` com motivo; `DONE` segue para verificação | Aramis | V | Testes dos três desfechos |
| I.4 | Despacho de tarefa de manutenção traz as máquinas e a instrução no corpo (como "Pedir ao agente") | Aramis | I.2 | Corpo inclui ids e `message_number` |
| I.5 | Evidência `host_execution:<id>`: verificada só se todas as máquinas terminaram `ok`; execuções aparecem na tarefa | Aramis | I.2 | Execução com uma máquina falha → evidência `failed` |
| I.6 | Tarefa de projeto de cliente concluída → lançar horas no Darckware (mesma regra do `:resolve`, minutos obrigatórios) | Aramis | B.1 | Horas aparecem na franquia; auditadas |
| I.7 | Check do Auditor falho → tarefa no projeto Sustentação do produto do dono (dedupe por check), não Task solta | Aramis | B.2 | Check verde fecha a tarefa com evidência |
| I.8 | Incubação "promover" e Canal `:dispatch-task` com opção de criar Planning Item/ProjectTask | Aramis + Dartan | V | Origem registrada na tarefa |
| I.10 | Agendamento de script de manutenção → tarefa recorrente no Sustentação: cada execução vira evidência; falha abre tarefa para o dono | Aramis | B.2, I.5 | Execução agendada aparece na tarefa; falha gera tarefa |
| I.11 | Sugestão de responsável no planejamento pelas skills/tools/MCP do agente e pela carta (`TaskRequiredSkill`) | Aramis + Dartan | V | Tarefa mostra agentes compatíveis |
| I.12 | Falhas operacionais viram trabalho no Sustentação do produto: cron/script órfão, backup externo, disco, provedor ForgeRouter, Hindsight | Aramis | B.2 | Dedupe por fonte; fecha sozinha quando a fonte volta ao normal |
| I.13 | **Incidente:** tipo de item `incident` com severidade; incidente crítico fura o silêncio noturno do Telegram, abre tarefa no Sustentação para o dono, e só fecha com causa, correção, evidência e relatório pós-incidente (documento da fase e lição na G.7) | Aramis + Hephaestus | I.7 | Incidente simulado percorre o fluxo inteiro |
| I.9 | Revisão | Porthus | I.1–I.8, I.10–I.13 | Aprovação registrada |

### Fase D — Documentação, manual e pasta do projeto

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| D.1 | Documentos obrigatórios vêm do estágio do Pipeline do projeto (R.2); cada um gera uma tarefa `documentation` (Scriba por padrão) | Aramis | R.2 | Estágio sem o documento não conclui |
| D.2 | Documento entregue = Artefato versionado + `DocLink` ao arquivo em `/docs/<produto>/<projeto>/`; fase só vai a `done` com os artefatos do estágio | Aramis | D.1 | Teste: fase não fecha sem artefato |
| D.3 | Manutenção e serviço geram registro de atendimento (o quê, onde, evidência, horas) ligado à tarefa e, no cliente, ao ticket | Aramis | I.5, I.6 | Registro visível no projeto e no Darckware |
| D.4 | Publicar versão gera notas da versão a partir das tarefas e documentos | Aramis | D.2 | `release_notes` preenchido; revisável antes de publicar |
| D.5 | Aba "Documentos" no projeto e na fase (artefatos, versões, arquivos) | Dartan | D.2 | Celular; link para o Docs |
| D.7 | **Estrutura padrão da pasta do projeto** (padrões 18 e 19 da Foundation), mantida pelo Service Factory em `<working_directory_path>/docs/`: `00-INDICE.md` (mapa com estado de cada documento), `PRD.md`, `ESCOPO.md` (telas e regras), `BANCO-DE-DADOS.md` (modelo e ERD derivados), `DEPLOY.md` (ambientes, instalações, como publicar e reverter), `METODOLOGIA.md` (padrões e specs adotados, D.8), `SPEC-TECNOLOGIA.md`, `adr/` (decisões), `design/` (D.12), `MANUAL/` (D.9), `CHANGELOG.md` (notas de cada versão, D.4). Cada arquivo tem cabeçalho com estado, dono e data | Aramis + Scriba (conteúdo) | D.2, R.2 | Projeto novo nasce com a estrutura; o índice reflete o estado real |
| D.8 | **Contrato do projeto:** no Service Factory, por projeto, declara metodologia, padrões da stack adotados (com versão e estado de cada um), stack técnica, design system e identidade visual (D.12), banco, ambientes de deploy e restrições; gera `METODOLOGIA.md` e vai junto em todo despacho de tarefa do projeto (com as anotações, P.4) | Aramis + Dartan | P.4 | Tarefa despachada cita o contrato; mudar o contrato exige anotação ou aprovação |
| D.9 | **Manual do sistema** por versão: gerado a partir do escopo (telas, regras, fluxos), revisado pelo Scriba e publicado em `docs/MANUAL/` e no portal do cliente quando for projeto de cliente (E.2) | Scriba + Aramis | D.7 | Publicar versão sem manual atualizado pede confirmação explícita |
| D.10 | **Guia para os agentes na pasta** (`AGENTS.md`/`CLAUDE.md` do projeto), gerado do contrato, das anotações fixadas e da estrutura, para que Claude Code, Codex e agy leiam o contexto ao abrir a pasta | Aramis | D.8, P.2 | Guia atualizado a cada mudança do contrato; seção gerada delimitada (o resto do arquivo não é tocado) |
| D.11 | **Tela "Documentação do projeto"** e auditoria: documentos exigidos × existentes, estado (rascunho/em revisão/aprovado), última atualização × última mudança de código, divergência entre a pasta e o Service Factory; check no Auditor por projeto | Aramis + Dartan | D.7 | Documento desatualizado ou divergente aparece na tela e vira tarefa |
| D.12 | **Identidade visual do projeto** no Service Factory, materializada em `docs/design/`: logomarca (variações horizontal, vertical, símbolo, monocromática, fundo claro e escuro, em SVG e PNG), favicon e ícone de app; paleta de cores com tokens claro/escuro e contraste verificado (WCAG AA); tipografia; ícones; tom de voz; `DESIGN-SYSTEM.md` (componentes, espaçamentos, estados); `SCREEN-TEMPLATES.md`; protótipos de tela (o MCP já salva HTML); e um arquivo de tokens aplicável no código (variáveis CSS / tema Tailwind do padrão 02) | Dartan + Aramis (upload e geração) | D.7 | Projeto com tela não libera tarefa de UI sem identidade aprovada; contraste reprovado aparece na tela |
| D.13 | **Homologação de design** como estágio do pipeline (R.2) antes de implementar telas: o Marcelo aprova logomarca, paleta e protótipos; tarefas de UI despachadas ao Dartan levam os tokens, a logomarca e o protótipo aprovado no contexto; no produto Darckware vale também a homologação própria (`docs/CONTROLE_DE_DESENVOLVIMENTO.md` e skill `darckware-design`) | Dartan + Porthus (revisão) | D.12, R.2, P.4 | Tela implementada diferente do protótipo aprovado é apontada na revisão |
| D.6 | Publicar versão cria a Release, liga às instalações do Deploy e mostra a versão em produção | Aramis + Dartan | D.4 | Deploy exibe a versão; release com notas |

### Fase Q — Qualidade, ambientes e entrega do código

Lacuna encontrada na revisão: não há CI, não há branch/worktree por tarefa (dois agentes podem editar o
mesmo repositório ao mesmo tempo) e não há ambiente de homologação (o `dev.sh` usa o mesmo banco da
produção). Para os agentes desenvolverem com segurança e o Marcelo auditar, cada entrega de código
precisa de um caminho fixo até a produção.

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| Q.1 | **Git por tarefa:** toda tarefa de código roda num worktree/branch próprio (`task/<numero>-<slug>`), commits citam o número da tarefa, e a entrega é um PR ligado à tarefa (evidência `git:` passa a apontar o PR/merge) | Porthus (desenho) + Aramis | V | Dois agentes no mesmo repositório não se atropelam; toda mudança no `main` vem de PR ligado a tarefa |
| Q.2 | **Trava por repositório e área:** o despacho não manda duas tarefas que mexem no mesmo repositório e na mesma área ao mesmo tempo sem worktree separado | Aramis | Q.1 | Teste de concorrência |
| Q.3 | **CI por repositório** (padrões 08 e 10 da Foundation): testes, lint, build, varredura de segurança (Aegis) e verificação de migrations; resultado anexado à tarefa | Aramis + Aegis | Q.1 | PR sem CI verde não pode ser aceito |
| Q.4 | **Ambiente de homologação** por produto (banco separado, URL própria, dados de teste), usado pelos agentes para testar e pelos evals (G.6); o `dev.sh` deixa de apontar para o banco de produção | Hephaestus + Aramis | B.1 | Nenhum teste de agente toca dado de produção |
| Q.5 | **Gate de produção:** deploy só com CI verde, revisão (Porthus), homologação aprovada e, para produção, aprovação do Marcelo ou delegação; o Hephaestus executa; rollback documentado e testado; a Release (D.6) registra o que subiu | Hephaestus + Aramis | Q.3, Q.4, D.6 | Deploy fora do gate é apontado pelo Auditor |
| Q.6 | **Segredos por projeto** no ForgeVault (variáveis de ambiente por ambiente), referenciados no contrato do projeto (D.8), nunca no repositório nem no contexto | Aramis + Aegis | D.8 | Varredura não encontra segredo em repositório |
| Q.7 | **Custo por projeto:** orçamento por projeto/missão; consumo de ForgeRouter e horas de agente somados no projeto; alerta ao passar do limite (os runtimes externos sem custo medido aparecem como "não medido", nunca zero) | Aramis | O.4 | Projeto acima do orçamento gera alerta e decisão |

### Fase A — Agent Activity completo (seção 5)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| A.1 | Quadro com todos os agentes das cartas (externos sempre presentes) + saúde de canal/gateway | Aramis (API) + Dartan | — | 13 agentes sempre visíveis |
| A.2 | Rotinas na timeline (passado e próximas 24 h) com desfecho; alerta de rotina perdida | Aramis + Dartan | A.1 | Ocorrência perdida aparece e alerta |
| A.3 | Origem de cada execução (rotina, tarefa/projeto, missão, ticket, execução remota) com link | Aramis + Dartan | I.5 | Clique leva à origem |
| A.4 | Indicadores por agente (DONE na 1ª tentativa, falhas, reprocessos, rotinas perdidas, dúvidas) | Aramis + Dartan | A.2 | Coerentes com a Evolução |
| A.5 | Alertas novos (agente sem rotina, tarefa parada, execução remota falha) | Aramis | A.2 | Dedupe por evento |

### Fase O — Operação 24x7 sobre o conjunto

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| O.1 | Triagem do Athos cobre tarefas de projeto paradas, bloqueadas, sem evidência e prazos | Athos (instruções) + Aramis (dados) | I.3 | Itens listados com link |
| O.2 | Briefing matinal com projetos, sustentação, serviços abertos e missões | Athos + Aramis | O.1 | Mostra o que precisa do Marcelo |
| O.3 | Rotinas do Scriba (fase sem documento), Atlas (dependências travadas) e Hephaestus/Aegis (manutenção preventiva via Sustentação) ligadas | Athos, Marcelo aprova | D.2, B.2 | Rodando dentro do orçamento |
| O.4 | Evolução mede projetos e manutenção: lead time, retrabalho, DONE na 1ª, documentação em dia, horas de serviço | Aramis | D.3 | Tendência semanal |

### Fase E — Captação de clientes (Darckware como porta de entrada)

**O funil inteiro passa a ser rastreável** do primeiro acesso ao site até a entrega e a renovação:

```
Visita ao site ──► Conversa com a Lara ──► Lead ──► Orçamento / projeto proposto ──► Aprovação no portal
 (analytics)        (chat do site)          (CRM)     (versão publicada ao cliente)      (vira contrato)
                                                                                              │
Renovação / novo projeto ◄── Informe mensal ◄── Horas na franquia ◄── Entrega aprovada ◄── Projeto no Service Factory
 (Kairos, Lara)               (e-mail aprovado)    (Darckware)          (portal do cliente)    (execução pelos agentes)
```

Regras mantidas: o Darckware guarda os dados do cliente e o ForgeHub opera. Nenhum e-mail sai sem
aprovação. A Lara não contata cliente por rotina. O cliente nunca vê nome interno, id interno nem valor
que não seja dele.

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| E.1 | **Projeto proposto ao cliente ↔ Service Factory:** ao publicar um projeto proposto no Darckware, o ForgeHub registra a oportunidade; quando o cliente aprova a versão (vira contrato de desenvolvimento), o ForgeHub cria o projeto do Service Factory com cliente, escopo da versão aprovada e origem `proposal` (novo valor em `darckware_origin_type`), idempotente | Aramis (ForgeHub) + Aramis/Darckware (evento) | V, B.1 | Aprovação no portal gera exatamente um projeto, com o escopo aprovado |
| E.2 | **Acompanhamento no portal:** o cliente vê o andamento do projeto (fases concluídas, próxima entrega, documentos publicáveis) a partir de um resumo enviado pelo ForgeHub, sem ids nem nomes internos | Aramis + Dartan (Darckware) | E.1, D.2 | Resumo aprovado antes de publicar; nada interno vaza (teste) |
| E.3 | **Entrega aprovada pelo cliente:** fechar uma fase/versão do projeto de cliente pede o aceite do cliente no portal (mesmo mecanismo de aprovar/pedir ajuste); pedido de ajuste vira change request no Service Factory | Aramis + Dartan | E.2, V.14 | Ajuste pedido no portal aparece como change request |
| E.4 | **Funil no ForgeHub:** visitas (analytics), conversas da Lara, leads, propostas, conversões e tempo até a primeira resposta — no Dashboard/Clientes, no briefing do Athos e na Evolução | Aramis + Dartan | — | Números batem com o Darckware; sem dado pessoal na agregação |
| E.5 | **Conversas da Lara no site:** sessão de chat ligada ao lead (já existe `link-conversation` no Darckware) e visível na ficha do cliente no ForgeHub; resumo por conversa, nunca o texto bruto no contexto de outros agentes (Fase C) | Aramis | C.1 | Lara e ForgeHub mostram a mesma ligação; teste de não vazamento |
| E.6 | **Rotinas comerciais:** ligar a rotina do pipeline comercial interno da Lara e a de mercado/marketing do Kairos, alimentadas pelo funil (E.4); propostas de campanha e de conteúdo do site viram projeto no produto Darckware | Athos (rotinas), Marcelo aprova | E.4, O.3 | Rodando dentro do orçamento; nenhum contato automático com cliente |
| E.7 | **Site como produto:** mudanças no site do Darckware entram como projeto no produto Darckware do Service Factory, respeitando a homologação de design do próprio Darckware (`docs/CONTROLE_DE_DESENVOLVIMENTO.md` e a skill `darckware-design`) | Dartan + Porthus (revisão) | B.1 | Toda mudança no site tem tarefa, evidência e homologação |
| E.8 | **Segurança e LGPD da porta de entrada:** checks do Aegis para a exposição pública do Darckware (já há allow-list do Tailscale no catálogo v2) e da Themis para os dados de lead e de cliente (retenção, consentimento, autorização de contato) | Aegis + Themis | C.1 | Checks no Auditor; falha vira tarefa no Sustentação do Darckware |
| E.9 | **Eventos do Darckware no fluxo único** (G.2): novo lead, conversa abandonada, proposta aprovada, ticket aberto, franquia perto do limite | Aramis | G.2 | Cada evento dispara a ação certa (tarefa, notificação ou rotina) |

### Fase C — Controle de contexto do ecossistema

**O que é:** memória dos agentes, Hindsight (memória estendida), Base de Conhecimento e Foundation
governados como um sistema só: o que cada camada guarda, quem pode ler, o que prevalece num conflito,
quanto tempo vale, e prova de que um agente não recebe o que não devia.

**Base já existente (não reinventar):**
- Foundation `36_governance/agent-memory-model.md` e `COLLECTIVE_MEMORY_ARCHITECTURE.md` definem as camadas;
- `KNOWLEDGE_ARCHITECTURE.md` define o fluxo de promoção da KB;
- o diagnóstico do Athos (#39778, 24/10) traz a matriz de riscos, a classificação, a precedência e um plano por fases.

O que falta é **controle**: hoje o ForgeHub só edita a Foundation, a KB e os arquivos de perfil, e do
Hindsight só vê status, restart e log.

**As camadas e a ordem de precedência** (diagnóstico #39778, §6.4):

| # | Camada | Onde vive | Dono | Escreve | Validade |
|---|---|---|---|---|---|
| 1 | Instrução atual do Marcelo | conversa/tarefa | Marcelo | — | a da tarefa |
| 2 | Estado real | sistemas (ForgeHub, máquinas, deploy) via ferramenta | cada sistema | — | sempre atual |
| 3 | **Foundation** (canônica) | `/root/memory/foundation` | Athos | Athos, por tarefa revisada | versionada |
| 4 | Identidade do agente | `SOUL.md`, `AGENTS.md`, `IDENTITY.md`, `TOOLS.md` | Athos + Marcelo (A2) | só por mudança A2 | versionada |
| 5 | Documentação de projeto | `/docs` + Artefatos (Service Factory) | dono do projeto | tarefas `documentation` | versionada |
| 6 | **Base de Conhecimento** | `knowledge_base/<agente>/`, `shared/approved/` | cada agente; Mnemosyne/Scriba revisam | o agente (inbox) → revisão → publicação | revisão periódica |
| 7 | **Hindsight** (memória estendida) | bancos `hermes` (coletivo) e `maia` (privado) | Mnemosyne | retenção automática, com tags e redação | TTL por tipo |
| 8 | **Memória nativa** | `memories/MEMORY.md` (2.200 caracteres), `USER.md` (1.375) | o agente | o agente | curta, revisada |
| 9 | Resumo de sessão | compactação do Hermes | — | — | a sessão |

Classificação de todo item (diagnóstico §6.1): `public`, `internal`, `confidential`, `personal` (só a
Maia), `secret` (nunca guardado). Confiabilidade (§6.3): `canonical`, `verified`, `reviewed`,
`observed`, `inferred`, `stale`. Só os três primeiros alimentam conhecimento compartilhado.

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| C.0 | **Linha de base** (fase 0 do diagnóstico): matriz por perfil com memória nativa (uso × limite), banco e modos do Hindsight (`auto_retain`, `auto_recall`, `recall_budget`, tags), hook ativo, pasta da KB, compactação e limite real de contexto por rota | Mnemosyne (levantamento) + Aramis (coleta automática) | — | Matriz gerada sem nenhum segredo; vira a primeira aba da tela C.4 |
| C.1 | **Política de classificação e retenção** na Foundation (`36_governance/MEMORY_CLASSIFICATION_AND_RETENTION.md`): classes, tipos, TTL, proveniência, confiabilidade, precedência, redação, consumidores, regras Maia/Lara. Complementa os documentos existentes, sem duplicar | Athos (Foundation) + Themis (LGPD) | C.0 | Aprovada pelo Marcelo; exemplos de permitido e proibido |
| C.2 | **Isolamento da recuperação (P0):** `knowledge_cycle.py` passa a ler só a KB do próprio agente e `shared/approved/`, respeita `allowed_consumers`, rejeita documento sem metadados; primeiro em modo observação (registra o que seria excluído) | Porthus (código) + Mnemosyne (valida) | C.1 | Testes: Lara nunca recebe nota pessoal da Maia; Maia nunca recebe histórico de cliente; conteúdo não aprovado não entra no prompt |
| C.3 | **Compartilhamento controlado Maia ↔ Lara** (e entre quaisquer agentes): `shared/approved/<consumidores>/`, fluxo candidato → revisão → publicação versionada; pasta privada da Maia na KB | Mnemosyne + Scriba | C.2 | Uma regra comercial não sensível chega à Lara; nenhuma conversa bruta é compartilhada |
| C.4 | **Tela "Contexto"** no ForgeHub (Agentes & IA), com abas: **Agentes** (matriz C.0 viva, alerta de memória perto do limite); **Hindsight** (bancos, estatísticas, crescimento, busca por tag/agente/classe, histórico de uma memória, marcar `stale`/substituída, exportar — pela API do Hindsight via host-bridge); **Base de Conhecimento** (fila de revisão do `inbox/`, documentos sem metadados, publicação em `shared/approved`); **Foundation** (o editor atual, com histórico de versões e quem mudou); **Conflitos** (o mesmo fato com valores diferentes entre camadas) | Aramis (API) + Dartan (tela) | C.0 | Celular; nenhuma ação apaga sem `ConfirmDialog`; Hindsight nunca recebe escrita fora das ações listadas |
| C.5 | **Metadados obrigatórios** na KB e na Foundation (front matter: classificação, dono, consumidores, validade, confiabilidade, origem, revisão) + verificador | Scriba (conteúdo) + Aramis (verificador) | C.1 | Documento novo sem metadados é apontado na tela e no Auditor |
| C.6 | **Governança do Hindsight por perfil:** revisar `bank_id`, `auto_retain`, `recall_budget`, `retain_tags` (agente, domínio, classe, tipo) e `retain_source`; redação antes de reter; Maia segue no banco `maia` | Mnemosyne + Porthus (config) | C.1 | Teste: informação pessoal retida fica só no `maia`; a Lara não a recupera |
| C.7 | **Checks do Auditor** para contexto: memória nativa > 90% do limite, documento sem metadados, crescimento anormal de banco, teste de vazamento entre agentes (rodado semanalmente), Foundation alterada fora de tarefa | Aramis + Aegis | C.2, C.5 | Check falho vira tarefa no Sustentação (I.7) para o dono da camada |
| C.8 | **Compactação e limite de contexto** (fase 5 do diagnóstico): medir perda real, então ajustar `protect_last_n` de Maia e Lara, `threshold_tokens`, pruning e o limite de recall por perfil | Mnemosyne + Porthus | C.0 | Sessão longa compacta sem perder identidade; nada passa do limite do modelo em silêncio |
| C.9 | **Saneamento** (fase 6 do diagnóstico, aprovação separada): deduplicar o Hindsight (25.080 fatos no `hermes`), marcar fatos antigos, promover os verificados, arquivar candidatos | Mnemosyne | C.6, C.7 | Relatório antes e depois; nada apagado sem exportação prévia |
| C.10 | **Ligações com o resto do plano:** o contexto da Missão (M.2) promove itens para estas camadas por tarefa (Mnemosyne → Hindsight, Scriba → KB, Athos → Foundation); os evals (G.6) incluem testes de recuperação de memória; o Agent Activity mostra recall/retenção por agente | Aramis | M.2, G.6, A.3 | Toda promoção tem tarefa, revisão e registro |

Ordem dentro da frente: C.0 → C.1 → C.2 (P0, o maior risco atual) → C.3/C.5/C.6 → C.4 → C.7 → C.8 → C.9.
C.0 e C.1 podem começar já, em paralelo à validação do Service Factory.

### Fase M — Missão (spec `2026-10-24-missao-design.md`)

| # | Tarefa | Depende |
|---|---|---|
| M.0 | Documento dos sete sistemas (Hermes, ForgeHub, ForgeRouter, ForgeVault, Tailscale, RustDesk, Darckware). O isolamento do `knowledge_cycle.py` e a pasta da Maia passaram para a Fase C (C.2, C.3) | — (pode correr em paralelo desde já) |
| M.1 | Núcleo como **extensão do Projeto** (seção 0, problema 4): `project_type = mission`, critérios de aceite (M.1a), papéis (M.1e), brief (M.1g), consolidação; tela `/missions` como uma visão filtrada dos projetos de missão; MCP | Onda 1 + Onda 2 |
| M.1a | **Critérios de aceite** da missão (tabela própria): cada critério com descrição verificável, tarefas que o cumprem, evidência que o prova, quem verifica e estado (`aberto`, `em andamento`, `comprovado`, `reprovado`) | M.1 |
| M.1b | **Saúde da missão** (seção 1.5): semáforo calculado dos sinais (critérios, prazo, bloqueios, evidência, documentação, agentes, custo, cliente), com alerta ao coordenador, ao agente ou ao Marcelo conforme o caso | M.1a, A.3, O.1 |
| M.1c | **Gates do pipeline da missão** (estágios 1–6) como pipeline da linha "Missões" (R.2): abertura aprovada, plano com todo critério coberto, verificação completa, aceite explícito; falha volta ao estágio anterior | M.1a, R.2 |
| M.1e | **Papéis por missão e por tarefa:** membros com função (vocabulário existente) e, por tarefa, executor e verificador; checagem automática das regras ao nomear (seção 1.6) | M.1 |
| M.1f | **Autoridade do orquestrador:** ao nomear, concede uma `AuthorityDelegation` limitada ao projeto da missão (criar, atribuir, despachar, propor change request), com risco máximo da missão; revogada no encerramento; substituto definido (padrão: Atlas, depois o Marcelo) quando o orquestrador fica indisponível | M.1e |
| M.1g | **Brief da missão:** gerado na abertura, versionado como Artefato, validado antes do planejamento; mudança gera versão nova, aviso aos membros e contexto atualizado no despacho | M.1, P.4 |
| M.1h | **Validação do plano:** plano da missão como `ProjectPlan` gerado das fases, tarefas, papéis e critérios; checagem automática (seção 1.6); revisão do orquestrador; aprovação do Marcelo vira baseline; change request depois disso | M.1a, M.1e |
| M.1i | **Validação da documentação:** autor ≠ revisor exigido; estados do padrão 18; documentos-chave aprovados pelo Marcelo; checagem automática (cabeçalho, links, segredos, nomes internos em documento de cliente) | D.2, M.1e |
| M.1j | **Canal da missão:** canal de coordenação criado com o projeto e os membros com suas funções (canais já suportam isso) | M.1e |
| M.1k | **MCP por papel:** `get_my_mission_role`, minhas tarefas, o que espera minha verificação, o brief vigente | M.1e, M.1g |
| M.1l | **Foundation:** registrar os papéis, a regra "aprovação da baseline autoriza as tarefas dela" e a validação de plano e documentação (pelo Athos) | M.1h, M.1i |
| M.1d | **Painel da missão:** o pipeline com o estágio atual, os critérios e suas provas, a saúde, a linha do tempo (P.5), as anotações (P.3) e os agentes em atividade agora | M.1b, M.1c |
| M.2 | Contexto da missão por destinatário, com testes de vazamento; promove itens para as camadas da Fase C | M.1, C.2 |
| M.3 | Missão na Operação 24x7 e no Agent Activity | M.1, A.3, O.1 |
| M.4 | Autonomia M1 (coordenador propõe o plano) | M.2, O.4 |

### Regra transversal — o sistema se documenta a cada fase

Toda fase só fecha quando:
- a skill compartilhada `forgehub` e as skills dos agentes afetados ensinam as ferramentas e os
  processos novos;
- o `CLAUDE.md` do ForgeHub está atualizado;
- a Foundation (pelo Athos) registra o que mudou de processo.

É o que mantém os agentes alinhados com o sistema, que eles mesmos vão manter e evoluir
(Marcelo, 24/10: "atualizar as skills dos sistemas porque o próprio sistema pode fazer manutenção e
novas implementações").

### Ordem e paralelismo

```
Trilho principal:
V-a ──► M0 (primeira missão como projeto) ──► V-b ──► S ──► R ──► B ──► P.1/P.2 ──► I ──► Q ──► D ──► P.3–P.6 ──► M.1 ──► M.2 ──► M.4 ──► G

Começam já, em paralelo:
A.1/A.2 ──► A.3–A.5 (após I.5)
C.0 ──► C.1 ──► C.2 ──► C.3/C.5/C.6 ──► C.4 ──► C.7 ──► C.8 ──► C.9
M.0 (documento dos sete sistemas)
E.4 (funil)

Depois das dependências:
E.1 ──► E.2 ──► E.3 (após V, B e D) · E.5–E.9
O.1–O.4 (após I.3 e D.2) ──► M.3
P.7/P.8/P.9 (após C.3)
```

## 7. Rumo à inteligência operacional própria ("nossa AGI")

### 7.1 O que é realista

Nenhuma integração de sistemas produz uma AGI geral, e o plano não promete isso. O que dá para
construir com Hermes, ForgeHub, ForgeRouter, ForgeVault, Tailscale, RustDesk e Darckware é uma **organização de
agentes autônoma e que melhora sozinha**:
- recebe objetivos;
- planeja e executa com evidência;
- mantém sistemas e máquinas;
- aprende com o resultado;
- melhora o próprio software, dentro de limites que o Marcelo controla.

O plano até a seção 6 cobre o **corpo** desse sistema: executar, registrar, vigiar e coordenar. A
análise abaixo mostra o que ainda falta para que ele **aprenda, se avalie e se corrija** de forma
mensurável e segura.

### 7.2 O que já existe e o que falta

| Capacidade | Já existe | Falta | Fase |
|---|---|---|---|
| Agir no mundo | Messages, Acesso Remoto (Tailscale/RustDesk), Deploy, MCP, tools | — | — |
| Planejar | Service Factory, Missão (proposta), cartas | Hierarquia de objetivos acima das missões | G.1 |
| Perceber | Telemetria, Auditor, notificações, Messages, canais, Darckware (site, chat, leads, portal) | Um fluxo único de eventos que dispare iniciativa | G.2 |
| Lembrar | Hindsight, KB, Foundation, `MEMORY.md` | Controle das camadas com precedência, proveniência e isolamento | **Fase C** |
| Conhecer o próprio ambiente | Blueprints, máquinas, deploy, checks, scripts — em telas separadas | Um mapa único do ecossistema (o que existe, depende de quê, quem é dono) | G.4 |
| Verificar o próprio trabalho | `STATUS: DONE`, evidência `git:`/`file:`/`db:`, revisão do Porthus | Verificação independente do resultado por tipo de tarefa (não só "existe") | G.5 |
| **Medir a própria capacidade** | Evolução mede operação (falhas, prazos) | **Avaliações de capacidade (evals)**: tarefas-padrão por agente e domínio, repetidas, com nota. Sem isso não há como saber se uma mudança de modelo, skill ou prompt melhorou ou piorou | G.6 |
| **Aprender com o resultado** | Hindsight retém conversa; curator de skills; Evolução registra mudanças | **Lições estruturadas**: cada falha ou retrabalho gera uma lição com causa e evidência, que vira proposta de skill, carta ou rotina, avaliada pelos evals antes de valer | G.7 |
| **Melhorar o próprio software** | Retrospectiva propõe; A2 vai ao Marcelo | O laço completo: proposta → Missão → projeto → implementação pelos externos → evals → deploy → medição, de ponta a ponta | G.8 |
| Escolher o modelo certo | ForgeRouter (roteamento, fallback) | Seleção guiada pelos evals por tipo de tarefa — **no projeto ForgeRouter**, não no ForgeHub | G.9 (fora) |
| Segurança da autonomia | A0/A1/A2, delegações, redação de segredos, "dados não são instruções" | **Parada global** (pausar toda autonomia, ou a de um agente, num toque), orçamento de autonomia, testes de injeção de prompt vindos de WhatsApp/e-mail/web, registro de toda ação autônoma reversível | G.10 |
| Decisões do Marcelo | Aprovações, dúvidas, A2, incubação, aceite de missão — em telas diferentes | **Uma fila única de decisões**, com resumo e recomendação, também no Telegram | G.11 |
| Continuidade | Backup externo funcionando (38 execuções `ok`), gateway único | Recuperação testada do estado dos agentes (perfis, memória, banco) | G.12 |

### 7.3 Fase G — Capacidade de aprender (depois de M.1)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| G.1 | **Objetivos** (trimestrais, com métrica) acima das missões: toda missão serve a um objetivo; o briefing mostra o avanço | Aramis + Dartan | M.1 | Missão sem objetivo só como exceção explícita |
| G.2 | **Fluxo de eventos**: normalizar o que já chega (checks, alertas, Messages, tickets, telemetria, execuções remotas) num registro único que a triagem e as regras de iniciativa consomem | Aramis | A.5 | Toda iniciativa automática cita o evento que a disparou |
| G.3 | Coberto pela **Fase C** (controle de contexto) | — | — | — |
| G.4 | **Mapa do ecossistema**: sistemas, máquinas (Tailscale), serviços, deploys, checks, donos e dependências num grafo consultável por MCP | Aramis + Dartan | B.1 | Um agente responde "o que depende do X e quem é o dono" pelo MCP |
| G.5 | **Verificador por tipo de tarefa**: código (testes + revisão), manutenção (estado da máquina depois), documentação (artefato revisado); agente diferente do executor | Porthus + Aramis | I.5, D.2 | Tarefa só fica `done` com verificação do tipo |
| G.6 | **Evals de capacidade**: conjunto de tarefas-padrão por agente e domínio (seguras e repetíveis, em ambiente de teste), rodadas por rotina semanal e a cada mudança de modelo, skill ou prompt; nota histórica no Agent Activity | Porthus (desenho) + Aramis | A.4 | Toda mudança A1/A2 de agente mostra a nota antes e depois |
| G.7 | **Lições**: falha, `PARTIAL`, reprocesso ou rejeição de revisão → lição (causa, evidência, recomendação) → proposta de skill/carta/rotina → avaliada por G.6 → aplicada pelo nível de autonomia | Aramis + Athos | G.6 | Lição repetida não gera proposta duplicada; nenhuma skill muda sem eval |
| G.8 | **Laço de autoaperfeiçoamento do software**: proposta A2 aprovada vira Missão automaticamente, com projeto, tarefas para os externos, evals e medição pós-deploy | Aramis | G.6, M.1 | Uma melhoria percorre o laço inteiro com registro em cada etapa |
| G.9 | Seleção de modelo guiada por evals | projeto **ForgeRouter** | G.6 | Fora deste plano; o ForgeHub só fornece as notas |
| G.10 | **Segurança da autonomia**: parada global e por agente; orçamento de ações autônomas; suíte de injeção de prompt (WhatsApp, e-mail, web, documento); toda ação autônoma com desfazer ou registro de irreversível | Porthus + Aegis | A.1 | Parada testada; suíte verde antes de subir qualquer nível M |
| G.11 | **Fila única de decisões** do Marcelo (aprovações, A2, dúvidas, aceite de missão, incubação madura), na tela e no Telegram | Aramis + Dartan | O.2 | Nenhuma decisão pendente fora da fila |
| G.12 | **Recuperação testada** do estado dos agentes (perfis Hermes, memória, banco do ForgeHub) a partir do backup externo | Hephaestus (rotina) + Aramis | backup externo (já funcionando) | Teste de restauração trimestral registrado |

### 7.4 Níveis de autonomia revistos

Os níveis M0–M3 da Missão passam a exigir os itens da Fase G:

| Nível | Exige |
|---|---|
| M1 (coordenador propõe o plano) | G.10 (parada global) e G.11 (fila de decisões) |
| M2 (tarefas de baixo risco sem aprovação item a item) | G.5 (verificador) e G.6 (evals) com nota estável por 30 dias |
| M3 (o sistema propõe missões) | G.1, G.2, G.7 e G.8 funcionando; suíte de segurança G.10 verde |

### 7.5 Ordem

```
... M.1 ──► G.10 ──► G.11 ──► G.5 ──► G.6 ──► G.7 ──► G.8
             G.1, G.2, G.3, G.4, G.12 em paralelo, conforme as dependências da tabela
```

## 8. Lacunas encontradas na revisão do plano (24/10)

| # | Lacuna | Onde foi tratada |
|---|---|---|
| 1 | A validação pelo agente dependia de ferramentas MCP que só viriam depois (ciclo) | V dividida em V-a (tela/API) e V-b (MCP); a V-b gera a lista da P.1 |
| 2 | Não havia regra de quando usar tarefa do Service Factory e quando usar Task do Messages | Regra em 1.1 |
| 3 | Sem git por tarefa, sem PR, sem CI, sem trava de repositório | Q.1–Q.3 |
| 4 | Sem ambiente de homologação; `dev.sh` e produção dividem o banco | Q.4 |
| 5 | Deploy sem gate formal nem rollback testado | Q.5 |
| 6 | Segredos de cada projeto fora do contrato do projeto | Q.6 |
| 7 | Custo e orçamento por projeto/missão | Q.7 |
| 8 | "Incidente" estava no objetivo mas sem fluxo | I.13 |
| 9 | O Service Factory começaria vazio: faltava importar projetos, documentos e pendências atuais | B.4 |
| 10 | Produtos reais ausentes da lista (Duplica, SAEDAS, FileNest, OsintKey, Marketing, Hermes) | B.1 |
| 11 | Anotar exigia a tela; o Marcelo também supervisiona pelo Telegram | P.9 |
| 12 | Skills, `CLAUDE.md` e Foundation não acompanhavam cada fase | Regra transversal antes da ordem |
| 13 | Numeração (faltava a seção 7) e diagrama de ordem com dependências invertidas | Corrigidos |

**Riscos que continuam abertos e precisam de acompanhamento:**
- **Tamanho do plano.** São mais de 100 tarefas. Sem disciplina de uma tarefa pequena por vez, com
  `STATUS: DONE` e evidência, ele repete o que aconteceu com a Missão. O próprio plano vira o primeiro
  projeto do Service Factory e é acompanhado por ele.
- ~~Backup externo sem snapshot~~ — corrigido: o backup externo roda com sucesso (38 execuções `ok`). Falta o teste de restauração (G.12).
- **Só 3 de 18 rotinas ligadas:** a Operação 24x7 só vigia de fato quando as rotinas da O.3 forem ligadas.
- **Dependência do ForgeRouter** para a seleção de modelo (G.9), que está fora deste plano.

## 9. Decisões (padrões adotados; ver 0.2)

As recomendações abaixo valem como padrão revisável. Só as três de 0.2 bloqueiam o início.

1. Aposentar Execution Waves/Work Packages e o restante da Orquestração (R.1), que estão sem uso e
   duplicam o Messages como executor.
2. Fase V: pelo princípio 1.1, a validação natural é **um agente operando o Service Factory pelo
   MCP** com o roteiro acima, com você acompanhando, anotando e revisando o relatório; o Claude Code
   corrige os defeitos. Alternativa: você na tela.
3. Produtos internos da Fase B (lista proposta) e "Sustentação" permanente por produto.
4. Serviço a cliente: projeto por ticket/demanda (como o `:create-project` já faz, recomendado) ou um
   projeto por cliente com uma fase por ticket.
5. Horas: lançar no Darckware na conclusão da tarefa (recomendado) ou só manualmente.
6. A.1/A.2 e M.0 podem começar já, em paralelo à validação: autoriza?
7. As decisões da spec da Missão (coordenador, quem cria, dono da documentação).
8. Fase C: aprovar que C.0 (linha de base) e C.1 (política na Foundation, pelo Athos) comecem já, e
   que C.2 (isolamento do `knowledge_cycle.py`) seja feito pelo Porthus em modo observação primeiro.
9. Fase P: anotações em todos os níveis do Service Factory, herdadas no despacho das tarefas, e o MCP
   completo para os agentes operarem o módulo sem a tela.
10. Fase E (Darckware): projeto aprovado pelo cliente no portal vira projeto no Service Factory
   automaticamente (E.1), e o funil (E.4) pode começar já.
11. Fase Q: git por tarefa com PR, CI por repositório, ambiente de homologação separado e gate de
    produção com rollback (Q.1–Q.5).
12. **Service Factory (seção 1.3, Fase S):** confirmar o nome, as 9 linhas de serviço iniciais e a
    generalização (Produto = o que é atendido; Versão = o ciclo), mantendo rotas e tabelas.
13. **Papéis e validação (seção 1.6):** orquestrador, planejador, executores, verificadores e
    documentador nomeados na missão; aprovação da baseline do plano autoriza as tarefas dela;
    documentos-chave (brief, escopo, plano, resultado) aprovados por você.
14. **Pipeline (seção 1.5):** a Missão como garantia de conclusão — só ela declara um serviço
    concluído, com critérios de aceite comprovados um a um, saúde monitorada e aceite explícito.
15. **M0:** registrar já a primeira missão como projeto (o próprio plano integrado), com as
    ferramentas MCP mínimas e a convenção de missão, logo após a validação pela tela/API.
16. B.4: importar o estado atual dos produtos (pastas, documentos, pendências) antes de começar.
17. Fase G: aprovar a ideia dos **evals de capacidade** (G.6) e da **parada global** (G.10) como
   pré-requisitos para subir qualquer nível de autonomia.
