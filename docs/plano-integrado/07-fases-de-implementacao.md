# Fases de implementação


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

### Fase M — Missão ([missao-especificacao.md](missao-especificacao.md))

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

---
[← Índice](README.md)
