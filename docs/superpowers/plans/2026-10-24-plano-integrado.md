# Plano integrado — todos os componentes do ForgeHub interligados

**Data:** 2026-10-24
**Status:** proposta para aprovação do Marcelo
**Pedidos do Marcelo (24/10):**
- "integrar a missão com operação 24x7 e software factory, para gerenciar as tarefas e registro das implementações e da documentação"
- "o projeto criado não precisa ter um cliente associado, podendo ser um projeto interno"
- "eu ainda preciso validar o software factory, que ainda não foi testado. Esse módulo foi criado para o gerenciamento da implementação dos sistemas. O software factory também pode ser utilizado para manutenção de sistema e execução de serviços de manutenção, pois a VPN Tailscale possui o acesso a todas as estações de trabalho e servidores"
- "preciso adicionar no planejamento da implementação em um conjunto completo, interligando todos os componentes criados"
- "a tela de atividades dos agentes precisa acompanhar todas as rotinas e monitorar todos os agentes"

**Documentos ligados:** `docs/superpowers/specs/2026-10-24-missao-design.md` (frente Missão),
`docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md` (Operação 24x7),
`docs/superpowers/plans/2026-10-02-roadmap-geral.md` (roadmap anterior),
`docs/architecture/REMOTE_MAINTENANCE_PLAN.md` (manutenção remota).

## 1. Objetivo

Todo trabalho do ecossistema passa por um único caminho rastreável, seja ele implementação, manutenção
de sistema, serviço em estação ou servidor de cliente, documentação, incidente ou missão:

```
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
| **Clientes (Darckware)** (tickets, demandas, horas, informe mensal, "criar projeto") | **Serviço ao cliente**: origem do trabalho e consumo da franquia | Em produção; já cria Projeto a partir de ticket/demanda |
| **Docs** (`/docs` + `DocLink`) | **Registro documental** ligado a produto, versão, projeto, fase e tarefa | Em produção; nada obriga o vínculo |
| **Governança** (`Approval`, `AuthorityDelegation`, `AuditEvent`) | **Aceite e autoridade** | Em produção |
| **Deploy / System Control** | Entrega e operação da infraestrutura | Em produção |
| **Canais / Workspace** | Conversa que pode virar tarefa (`:dispatch-task`) | Em produção |
| **Pessoal (Maia)** | Trabalho pessoal do Marcelo; fora do Software Factory | Em produção (sem ligação, por desenho) |
| **ForgeRouter / ForgeVault / Hermes** | Modelos, segredos e runtime dos agentes | Em produção |
| **Missão** | **Objetivo** acima de projetos: coordena agentes e contexto | Proposta (`2026-10-24-missao-design.md`) |

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

Ordem: **validar o Software Factory primeiro**, depois ligar os componentes nele, depois a Missão.
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

Cada defeito encontrado vira tarefa no projeto "Validação do Software Factory" e é corrigido antes da
Fase I. Entregável: relatório da validação (documento ligado ao projeto) com o que passou e o que foi corrigido.

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
| I.9 | Revisão | Porthus | I.1–I.8 | Aprovação registrada |

### Fase D — Documentação obrigatória

| # | Tarefa | Dono | Depende | Aceite |
|---|---|---|---|---|
| D.1 | Toda fase (Planning Item) ganha tarefa `documentation` (Scriba por padrão) | Aramis | V | Fase sem ela não fecha |
| D.2 | Fase só vai a `done` com documento ligado por `DocLink`; pastas `/docs/<produto>/<projeto>/` | Aramis | D.1 | Teste: fase não fecha sem vínculo |
| D.3 | Manutenção e serviço geram registro de atendimento (o quê, onde, evidência, horas) ligado à tarefa e, no cliente, ao ticket | Aramis | I.5, I.6 | Registro visível no projeto e no Darckware |
| D.4 | Publicar versão gera notas da versão a partir das tarefas e documentos | Aramis | D.2 | `release_notes` preenchido; revisável antes de publicar |
| D.5 | Aba "Documentos" no projeto e na fase | Dartan | D.2 | Celular; link para o Docs |

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

### Fase M — Missão (spec `2026-10-24-missao-design.md`)

| # | Tarefa | Depende |
|---|---|---|
| M.0 | Documento dos quatro sistemas; `knowledge_cycle.py` restrito à pasta do agente; pasta privada da Maia | — (pode correr em paralelo desde já) |
| M.1 | Núcleo: missão = projeto interno + coordenação, participantes, consolidação, tela `/missions`, MCP | V, B, D |
| M.2 | Controle de contexto por destinatário, com testes de vazamento | M.1 |
| M.3 | Missão na Operação 24x7 e no Agent Activity | M.1, A.3, O.1 |
| M.4 | Autonomia M1 (coordenador propõe o plano) | M.2, O.4 |

### Ordem e paralelismo

```
V ──► B ──► I ──► D ──► M.1 ──► M.2 ──► M.4
            │      │      │
            │      └──► O ┴──► M.3
A.1/A.2 (em paralelo desde já) ──► A.3–A.5 (após I.5)
M.0 (em paralelo desde já)
```

## 7. Decisões pendentes do Marcelo

1. Começar pela **Fase V** com você validando na tela e o Claude Code acompanhando e corrigindo os
   defeitos, ou a validação ser feita por um agente com o roteiro acima e você revisa o relatório.
2. Produtos internos da Fase B (lista proposta) e "Sustentação" permanente por produto.
3. Serviço a cliente: projeto por ticket/demanda (como o `:create-project` já faz, recomendado) ou um
   projeto por cliente com uma fase por ticket.
4. Horas: lançar no Darckware na conclusão da tarefa (recomendado) ou só manualmente.
5. A.1/A.2 e M.0 podem começar já, em paralelo à validação: autoriza?
6. As decisões da spec da Missão (coordenador, quem cria, dono da documentação).
