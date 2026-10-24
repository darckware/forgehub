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

## Fase S — Service Factory (antes da Fase B, depois da V)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| S.1 | **Catálogo de linhas de serviço** (tabela): nome, descrição, template de pipeline (R.2), documentos obrigatórios, tipos de evidência aceitos, agentes padrão, SLA, tipo de contrato Darckware, visível ao cliente | Aramis | V | As 9 linhas iniciais cadastradas; cada projeto pertence a uma linha |
| S.2 | **Generalizar o modelo sem quebrar:** `products.kind` (`software`, `service`, `infrastructure`, `client_it`); `project_type` passa de `creation`/`maintenance` para os tipos das linhas; o fluxo de 6 etapas só é exigido na linha de software | Aramis | S.1 | Migration com backfill (projetos atuais = Desenvolvimento); 107 testes atuais seguem verdes |
| S.3 | **Renomear para Service Factory** na tela (seção do menu, i18n pt-BR/en/es), no `CLAUDE.md`, nos documentos, na skill `forgehub` e na Foundation (pelo Athos); rotas, tabelas e ferramentas MCP mantêm o nome | Dartan + Scriba + Athos | S.2 | Nenhum "Software Factory" visível; nenhuma integração quebrada |
| S.4 | **Cockpit por linha de serviço:** árvore Linha → Produto/Serviço → Projeto, filtros por cliente e interno, indicadores por linha (abertos, atrasados, fora do SLA, horas) | Dartan + Aramis | S.1 | Celular; números batem com as tarefas |
| S.5 | **Abrir trabalho pela linha:** "Novo serviço" escolhe a linha e já cria o projeto com pipeline, documentos obrigatórios e agentes padrão; o mesmo pelo MCP | Aramis + Dartan | S.1, P.1 | Projeto novo nasce completo para a linha escolhida |
| S.6 | **Ligação com o Darckware:** contrato `suporte_horas` → linhas de suporte e manutenção, `desenvolvimento` → linha de software; o portal do cliente mostra os serviços em andamento por linha (E.2) | Aramis | S.1, E.1 | Horas e serviços do cliente batem nos dois lados |
| S.7 | **Validação por linha:** o roteiro da Fase V ganha um fluxo curto por linha (um atendimento de manutenção, um ticket, um incidente simulado, um documento) | Claude Code + agente | S.5 | Relatório por linha |

---
[← Índice](README.md)
