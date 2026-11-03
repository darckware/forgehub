# Service Factory: linhas de serviço

## De Software Factory a Service Factory

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

## Abertura de um novo projeto (sistema ou serviço)

Marcelo, 24/10: "e a abertura de um novo projeto do sistema ou serviço". Abrir um projeto é o
"começar" do lado do Service Factory. Ele precisa sair da abertura **pronto para os agentes
trabalharem**, sem que alguém tenha de montar as peças à mão depois.

### Quem abre e por onde entra

| Origem | Exemplo | Quem abre |
|---|---|---|
| Pedido do Marcelo | Sistema novo, evolução, serviço interno | O Marcelo, ou um agente a pedido dele (em rascunho) |
| Cliente (Darckware) | Projeto proposto aprovado no portal (E.1), ticket ou demanda (`:create-project`) | Automático a partir do Darckware |
| Operação | Check do Auditor, incidente, rotina | Automático, no projeto Sustentação do produto (já existente) |
| Missão | Uma missão que precisa de um projeto novo numa linha | O orquestrador da missão |

### O termo de abertura

Todo projeto novo nasce com um **termo de abertura**: `docs/TERMO-DE-ABERTURA.md` na pasta do
projeto, registrado como Artefato. Modelo em [modelos/TERMO-DE-ABERTURA.md](modelos/TERMO-DE-ABERTURA.md).
Ele responde, numa página:
- o quê e por quê (objetivo, problema, resultado esperado);
- para quem (interno ou cliente, contrato do Darckware);
- qual linha de serviço e qual produto/sistema é atendido;
- escopo e fora de escopo;
- critérios de aceite iniciais;
- prazo e orçamento;
- responsáveis (orquestrador, executores, verificadores, documentador);
- riscos conhecidos;
- e, para sistema, a base técnica: stack, banco, ambientes, repositório.

Numa missão, o termo de abertura e o brief são o mesmo documento: o brief é o termo de abertura da missão.

### O que a abertura cria automaticamente

| Item | Sistema (linha Desenvolvimento) | Serviço (demais linhas) |
|---|---|---|
| Produto e versão/ciclo | Produto do sistema (novo ou existente) + versão em desenvolvimento | Produto atendido (sistema, serviço ou parque de TI do cliente) + ciclo/contrato |
| Projeto | Na linha, com o pipeline da linha (R.2) e os documentos obrigatórios | Idem |
| Termo de abertura | Rascunho preenchido com o que já se sabe; aprovação do Marcelo (ou do cliente, se for de cliente) | Idem |
| Papéis | Membros do projeto com função, a partir dos agentes padrão da linha e das cartas | Idem |
| Pasta do projeto | Estrutura padrão de `docs/` (D.7): índice, PRD, escopo, banco, deploy, metodologia, decisões, design, manual, histórico | Estrutura reduzida: termo, registro de atendimento, runbook, histórico |
| Contrato do projeto | Metodologia, padrões da stack adotados, stack, design system, banco, ambientes (D.8) | Contrato de serviço: SLA, horas, máquinas e scripts autorizados, contatos |
| Guia para os agentes | `AGENTS.md`/`CLAUDE.md` do projeto (D.10) | Idem, reduzido |
| Repositório | Repositório git (remoto), branch padrão, CI inicial (Q.1, Q.3) | Não se aplica (salvo automações do serviço) |
| Área de teste | Banco e ambiente de teste do sistema (Fase T) | Máquina de teste quando há scripts novos |
| Segredos | Ambiente do projeto no ForgeVault (teste e produção), sem segredo no repositório (Q.6) | Credenciais do serviço no ForgeVault |
| Deploy | Registro no Deploy e destino de produção (D.6, Q.5) | Não se aplica |
| Identidade visual | Pasta `design/` e homologação de design antes das telas (D.12, D.13) | Não se aplica |
| Cliente | Ligação com o cliente e o contrato no Darckware (E.1, S.6), quando houver | Idem, com horas da franquia |
| Canal | Canal de coordenação com os membros (opcional) | Idem |

### Gate de abertura

O projeto sai de `rascunho` e libera a primeira tarefa só quando:
1. o termo de abertura está aprovado (pelo Marcelo, e pelo cliente quando o projeto é dele);
2. os papéis estão nomeados sem violar as regras;
3. a pasta, o contrato do projeto e, para sistema, o repositório e a área de teste existem;
4. o primeiro planejamento (fases e tarefas iniciais) está registrado.

É o mesmo princípio da Missão ("pronta"), aplicado a cada projeto.

## Fase S — Service Factory (antes da Fase B, depois da V)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| S.1 | **Catálogo de linhas de serviço** (tabela): nome, descrição, template de pipeline (R.2), documentos obrigatórios, tipos de evidência aceitos, agentes padrão, SLA, tipo de contrato Darckware, visível ao cliente | Aramis | V | As 9 linhas iniciais cadastradas; cada projeto pertence a uma linha |
| S.2 | **Generalizar o modelo sem quebrar:** `products.kind` (`software`, `service`, `infrastructure`, `client_it`); `project_type` passa de `creation`/`maintenance` para os tipos das linhas; o fluxo de 6 etapas só é exigido na linha de software | Aramis | S.1 | Migration com backfill (projetos atuais = Desenvolvimento); 107 testes atuais seguem verdes |
| S.3 | **Renomear para Service Factory** na tela (seção do menu, i18n pt-BR/en/es), no `CLAUDE.md`, nos documentos, na skill `forgehub` e na Foundation (pelo Athos); rotas, tabelas e ferramentas MCP mantêm o nome | Dartan + Scriba + Athos | S.2 | Nenhum "Software Factory" visível; nenhuma integração quebrada |
| S.4 | **Cockpit por linha de serviço:** árvore Linha → Produto/Serviço → Projeto, filtros por cliente e interno, indicadores por linha (abertos, atrasados, fora do SLA, horas) | Dartan + Aramis | S.1 | Celular; números batem com as tarefas |
| S.5 | **Abrir trabalho pela linha:** "Novo serviço" escolhe a linha e já cria o projeto com pipeline, documentos obrigatórios e agentes padrão; o mesmo pelo MCP | Aramis + Dartan | S.1, P.1 | Projeto novo nasce completo para a linha escolhida |
| S.6 | **Ligação com o Darckware:** contrato `suporte_horas` → linhas de suporte e manutenção, `desenvolvimento` → linha de software; o portal do cliente mostra os serviços em andamento por linha (E.2) | Aramis | S.1, E.1 | Horas e serviços do cliente batem nos dois lados |
| S.8 | **Abertura padrão de projeto** (sistema ou serviço): termo de abertura gerado e aprovado, produto e versão/ciclo, pipeline da linha, papéis, pasta padrão, contrato do projeto, guia para os agentes, e para sistema também repositório com CI, área de teste, ambiente no ForgeVault e registro no Deploy; gate de abertura antes da primeira tarefa; pela tela ("Novo projeto") e pelo MCP (`open_project`) | Aramis + Dartan, Porthus revisa | S.5, D.7, D.8, D.10, Q.1, T.2 | Um sistema e um serviço abertos do zero ficam prontos para os agentes sem passo manual |
| S.7 | **Validação por linha:** o roteiro da Fase V ganha um fluxo curto por linha (um atendimento de manutenção, um ticket, um incidente simulado, um documento) | Claude Code + agente | S.5 | Relatório por linha |

---
[← Índice](README.md)
