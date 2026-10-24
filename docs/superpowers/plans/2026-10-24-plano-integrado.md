# Plano integrado — todos os componentes do ForgeHub interligados

**Data:** 2026-10-24
**Status:** proposta para aprovação do Marcelo
**Pedidos do Marcelo (24/10):**
- "integrar a missão com operação 24x7 e software factory, para gerenciar as tarefas e registro das implementações e da documentação"
- "o projeto criado não precisa ter um cliente associado, podendo ser um projeto interno"
- "eu ainda preciso validar o software factory, que ainda não foi testado. Esse módulo foi criado para o gerenciamento da implementação dos sistemas. O software factory também pode ser utilizado para manutenção de sistema e execução de serviços de manutenção, pois a VPN Tailscale possui o acesso a todas as estações de trabalho e servidores"
- "preciso adicionar no planejamento da implementação em um conjunto completo, interligando todos os componentes criados"
- "a tela de atividades dos agentes precisa acompanhar todas as rotinas e monitorar todos os agentes"
- "o Darckware precisa ser adicionado, ele é minha ponte com a internet para captação de cliente no nosso ecossistema"
- "queria adicionar o controle do contexto: memória dos agentes, Hindsight (memória estendida), base de conhecimento e a documentação da Foundation"

**Documentos ligados:** `docs/superpowers/specs/2026-10-24-missao-design.md` (frente Missão),
`docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md` (Operação 24x7),
`docs/superpowers/plans/2026-10-02-roadmap-geral.md` (roadmap anterior),
`docs/architecture/REMOTE_MAINTENANCE_PLAN.md` (manutenção remota).

## 1. Objetivo

Todo trabalho do ecossistema passa por um único caminho rastreável, seja ele implementação, manutenção
de sistema, serviço em estação ou servidor de cliente, documentação, incidente ou missão:

```
Darckware (site, chat da Lara, portal) ─┐
Entrada ──► Software Factory ──► Messages ──► Agente ──► Evidência ──► Documento ──► Aceite
(pedido,     (Produto/Versão/     (único       (Hermes ou  (git/file/db/  (DocLink)     (Marcelo ou
 ticket,      Projeto/Fase/        executor)    externo)    execução                   delegação)
 check,       Tarefa)                                       remota)
 missão)
                     ▲                                                          │
                     └──── Operação 24x7 vigia, cobra e escala ◄────────────────┘
                           Agent Activity mostra tudo em tempo real
```

## 2. Componentes existentes e papel no conjunto

| Componente | Papel no conjunto | Estado |
|---|---|---|
| **Software Factory** (Produto, Versão, Concepção, Mapa do Sistema, Escopo, Planejamento, Tarefas, Governança, Fechamento de Versão, Cockpit) | **Registro e gestão** de todo trabalho: o que, por quê, quem, em que ordem, com que evidência | Construído, 107 testes automatizados verdes, **sem uso real** (só 4 projetos de teste) |
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
| **Pessoal (Maia)** | Trabalho pessoal do Marcelo; fora do Software Factory | Em produção (sem ligação, por desenho) |
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
| **Pessoal (Maia)** | em uso | Fora do Software Factory por desenho (vida pessoal) | — |

## 3. Tipos de trabalho e como cada um entra

| Tipo | Entrada | Onde fica no Software Factory | Evidência de conclusão |
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
| Software Factory → Agent Activity | a execução não mostra tarefa/projeto | 🔶 | A.3 |
| Software Factory → Operação 24x7 | triagem/briefing não olham tarefas de projeto | ❌ | O.1–O.3 |
| Tudo → Evolução | métricas só de rotinas | 🔶 | O.4 |
| Missão → tudo | nova camada | ❌ | M.* (spec da Missão) |

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

Ordem: **validar o Software Factory primeiro**, racionalizar o que está duplicado, ligar os componentes nele, depois a Missão.
Cada linha vira uma ProjectTask com dependência (`TaskDependency`) no projeto interno "Plano
integrado" (produto ForgeHub), assim que a Fase V estiver aprovada. Quem escreve não revisa o próprio
código: Porthus revisa Aramis e Dartan.

### Fase V — Validação do Software Factory (Marcelo + Claude Code)

Base automatizada: 107 testes do Software Factory passando em 24/10 (e2e, cockpit, MCP, escopo, versão,
tarefas, evidência, aprovação governada, produto, projeto, backlog, governança). Falta o uso real pela tela.

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

Cada defeito encontrado vira tarefa no projeto "Validação do Software Factory" e é corrigido antes da
Fase I. Entregável: relatório da validação (documento ligado ao projeto) com o que passou e o que foi corrigido.

### Fase R — Racionalização (um caminho para cada coisa)

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| R.1 | Aposentar Execution Waves/Work Packages/runner e o restante da Orquestração (rotas 410, telas e card simulado do Cockpit removidos; tabelas vazias removidas por migration) | Aramis + Dartan | V | Nenhuma rota de execução fora do Messages; testes ajustados |
| R.2 | Templates de Pipeline por tipo de projeto (implementação, sustentação, serviço, missão) com estágios e artefatos obrigatórios | Atlas (conteúdo) + Aramis | V.13 | Projeto novo recebe o pipeline do seu tipo |
| R.3 | Progresso governado: fundir no Pipeline ou aposentar, conforme V.13 | Aramis | V.13 | Uma só noção de "estágio concluído" |
| R.4 | Revisão | Porthus | R.1–R.3 | Aprovação registrada |

### Fase B — Base cadastral

| # | Tarefa | Dono | Aceite |
|---|---|---|---|
| B.1 | Produtos internos sem cliente: Ecossistema Foundation, ForgeHub, ForgeRouter, ForgeVault, Darckware, CoreTI, Serviços de Manutenção; versão em produção de cada um | Atlas, Marcelo aprova | No Cockpit como "Interno" |
| B.2 | Projeto permanente "Sustentação" por produto (manutenção corretiva, preventiva, atualização) | Atlas | Um por produto, sem cliente |
| B.3 | Marcar "Interno" na tela e no Cockpit para projeto sem cliente | Dartan | Visível na lista e no detalhe |

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
| I.9 | Revisão | Porthus | I.1–I.8, I.10–I.12 | Aprovação registrada |

### Fase D — Documentação obrigatória

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| D.1 | Documentos obrigatórios vêm do estágio do Pipeline do projeto (R.2); cada um gera uma tarefa `documentation` (Scriba por padrão) | Aramis | R.2 | Estágio sem o documento não conclui |
| D.2 | Documento entregue = Artefato versionado + `DocLink` ao arquivo em `/docs/<produto>/<projeto>/`; fase só vai a `done` com os artefatos do estágio | Aramis | D.1 | Teste: fase não fecha sem artefato |
| D.3 | Manutenção e serviço geram registro de atendimento (o quê, onde, evidência, horas) ligado à tarefa e, no cliente, ao ticket | Aramis | I.5, I.6 | Registro visível no projeto e no Darckware |
| D.4 | Publicar versão gera notas da versão a partir das tarefas e documentos | Aramis | D.2 | `release_notes` preenchido; revisável antes de publicar |
| D.5 | Aba "Documentos" no projeto e na fase (artefatos, versões, arquivos) | Dartan | D.2 | Celular; link para o Docs |
| D.6 | Publicar versão cria a Release, liga às instalações do Deploy e mostra a versão em produção | Aramis + Dartan | D.4 | Deploy exibe a versão; release com notas |

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
Renovação / novo projeto ◄── Informe mensal ◄── Horas na franquia ◄── Entrega aprovada ◄── Projeto no Software Factory
 (Kairos, Lara)               (e-mail aprovado)    (Darckware)          (portal do cliente)    (execução pelos agentes)
```

Regras mantidas: o Darckware guarda os dados do cliente e o ForgeHub opera. Nenhum e-mail sai sem
aprovação. A Lara não contata cliente por rotina. O cliente nunca vê nome interno, id interno nem valor
que não seja dele.

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| E.1 | **Projeto proposto ao cliente ↔ Software Factory:** ao publicar um projeto proposto no Darckware, o ForgeHub registra a oportunidade; quando o cliente aprova a versão (vira contrato de desenvolvimento), o ForgeHub cria o projeto do Software Factory com cliente, escopo da versão aprovada e origem `proposal` (novo valor em `darckware_origin_type`), idempotente | Aramis (ForgeHub) + Aramis/Darckware (evento) | V, B.1 | Aprovação no portal gera exatamente um projeto, com o escopo aprovado |
| E.2 | **Acompanhamento no portal:** o cliente vê o andamento do projeto (fases concluídas, próxima entrega, documentos publicáveis) a partir de um resumo enviado pelo ForgeHub, sem ids nem nomes internos | Aramis + Dartan (Darckware) | E.1, D.2 | Resumo aprovado antes de publicar; nada interno vaza (teste) |
| E.3 | **Entrega aprovada pelo cliente:** fechar uma fase/versão do projeto de cliente pede o aceite do cliente no portal (mesmo mecanismo de aprovar/pedir ajuste); pedido de ajuste vira change request no Software Factory | Aramis + Dartan | E.2, V.14 | Ajuste pedido no portal aparece como change request |
| E.4 | **Funil no ForgeHub:** visitas (analytics), conversas da Lara, leads, propostas, conversões e tempo até a primeira resposta — no Dashboard/Clientes, no briefing do Athos e na Evolução | Aramis + Dartan | — | Números batem com o Darckware; sem dado pessoal na agregação |
| E.5 | **Conversas da Lara no site:** sessão de chat ligada ao lead (já existe `link-conversation` no Darckware) e visível na ficha do cliente no ForgeHub; resumo por conversa, nunca o texto bruto no contexto de outros agentes (Fase C) | Aramis | C.1 | Lara e ForgeHub mostram a mesma ligação; teste de não vazamento |
| E.6 | **Rotinas comerciais:** ligar a rotina do pipeline comercial interno da Lara e a de mercado/marketing do Kairos, alimentadas pelo funil (E.4); propostas de campanha e de conteúdo do site viram projeto no produto Darckware | Athos (rotinas), Marcelo aprova | E.4, O.3 | Rodando dentro do orçamento; nenhum contato automático com cliente |
| E.7 | **Site como produto:** mudanças no site do Darckware entram como projeto no produto Darckware do Software Factory, respeitando a homologação de design do próprio Darckware (`docs/CONTROLE_DE_DESENVOLVIMENTO.md` e a skill `darckware-design`) | Dartan + Porthus (revisão) | B.1 | Toda mudança no site tem tarefa, evidência e homologação |
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
| 5 | Documentação de projeto | `/docs` + Artefatos (Software Factory) | dono do projeto | tarefas `documentation` | versionada |
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
C.0 e C.1 podem começar já, em paralelo à validação do Software Factory.

### Fase M — Missão (spec `2026-10-24-missao-design.md`)

| # | Tarefa | Depende |
|---|---|---|
| M.0 | Documento dos sete sistemas (Hermes, ForgeHub, ForgeRouter, ForgeVault, Tailscale, RustDesk, Darckware). O isolamento do `knowledge_cycle.py` e a pasta da Maia passaram para a Fase C (C.2, C.3) | — (pode correr em paralelo desde já) |
| M.1 | Núcleo: missão = projeto interno + coordenação, participantes, consolidação, tela `/missions`, MCP | V, B, D |
| M.2 | Contexto da missão por destinatário, com testes de vazamento; promove itens para as camadas da Fase C | M.1, C.2 |
| M.3 | Missão na Operação 24x7 e no Agent Activity | M.1, A.3, O.1 |
| M.4 | Autonomia M1 (coordenador propõe o plano) | M.2, O.4 |

### Ordem e paralelismo

```
V ──► R ──► B ──► I ──► D ──► M.1 ──► M.2 ──► M.4
            │      │      │
            │      └──► O ┴──► M.3
A.1/A.2 (em paralelo desde já) ──► A.3–A.5 (após I.5)
M.0 (em paralelo desde já)
E.4 (em paralelo desde já) · E.1 ──► E.2 ──► E.3 (após V e D) · E.5–E.9 conforme dependências
C.0 ──► C.1 ──► C.2 ──► C.3/C.5/C.6 ──► C.4 ──► C.7 ──► C.8 ──► C.9 (começa já, em paralelo)
```

## 8. Rumo à inteligência operacional própria ("nossa AGI")

### 8.1 O que é realista

Nenhuma integração de sistemas produz uma AGI geral, e o plano não promete isso. O que dá para
construir com Hermes, ForgeHub, ForgeRouter, ForgeVault, Tailscale, RustDesk e Darckware é uma **organização de
agentes autônoma e que melhora sozinha**:
- recebe objetivos;
- planeja e executa com evidência;
- mantém sistemas e máquinas;
- aprende com o resultado;
- melhora o próprio software, dentro de limites que o Marcelo controla.

O plano até a seção 7 cobre o **corpo** desse sistema: executar, registrar, vigiar e coordenar. A
análise abaixo mostra o que ainda falta para que ele **aprenda, se avalie e se corrija** de forma
mensurável e segura.

### 8.2 O que já existe e o que falta

| Capacidade | Já existe | Falta | Fase |
|---|---|---|---|
| Agir no mundo | Messages, Acesso Remoto (Tailscale/RustDesk), Deploy, MCP, tools | — | — |
| Planejar | Software Factory, Missão (proposta), cartas | Hierarquia de objetivos acima das missões | G.1 |
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
| Continuidade | Backup externo (pendente de snapshot), gateway único | Recuperação testada do estado dos agentes (perfis, memória, banco) | G.12 |

### 8.3 Fase G — Capacidade de aprender (depois de M.1)

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
| G.12 | **Recuperação testada** do estado dos agentes (perfis Hermes, memória, banco do ForgeHub) a partir do backup externo | Hephaestus (rotina) + Aramis | backup externo com snapshot | Teste de restauração trimestral registrado |

### 8.4 Níveis de autonomia revistos

Os níveis M0–M3 da Missão passam a exigir os itens da Fase G:

| Nível | Exige |
|---|---|
| M1 (coordenador propõe o plano) | G.10 (parada global) e G.11 (fila de decisões) |
| M2 (tarefas de baixo risco sem aprovação item a item) | G.5 (verificador) e G.6 (evals) com nota estável por 30 dias |
| M3 (o sistema propõe missões) | G.1, G.2, G.7 e G.8 funcionando; suíte de segurança G.10 verde |

### 8.5 Ordem

```
... M.1 ──► G.10 ──► G.11 ──► G.5 ──► G.6 ──► G.7 ──► G.8
             G.1, G.2, G.3, G.4, G.12 em paralelo, conforme as dependências da tabela
```

## 9. Decisões pendentes do Marcelo

1. Aposentar Execution Waves/Work Packages e o restante da Orquestração (R.1), que estão sem uso e
   duplicam o Messages como executor.
2. Começar pela **Fase V** com você validando na tela e o Claude Code acompanhando e corrigindo os
   defeitos, ou a validação ser feita por um agente com o roteiro acima e você revisa o relatório.
3. Produtos internos da Fase B (lista proposta) e "Sustentação" permanente por produto.
4. Serviço a cliente: projeto por ticket/demanda (como o `:create-project` já faz, recomendado) ou um
   projeto por cliente com uma fase por ticket.
5. Horas: lançar no Darckware na conclusão da tarefa (recomendado) ou só manualmente.
6. A.1/A.2 e M.0 podem começar já, em paralelo à validação: autoriza?
7. As decisões da spec da Missão (coordenador, quem cria, dono da documentação).
8. Fase C: aprovar que C.0 (linha de base) e C.1 (política na Foundation, pelo Athos) comecem já, e
   que C.2 (isolamento do `knowledge_cycle.py`) seja feito pelo Porthus em modo observação primeiro.
9. Fase E (Darckware): projeto aprovado pelo cliente no portal vira projeto no Software Factory
   automaticamente (E.1), e o funil (E.4) pode começar já.
10. Fase G: aprovar a ideia dos **evals de capacidade** (G.6) e da **parada global** (G.10) como
   pré-requisitos para subir qualquer nível de autonomia.
