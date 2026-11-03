# Componentes e interligações

**Inventário histórico de 24/10:** números e marcações de implementação precisam ser revalidados por V; não certificam o estado atual. Modelo vigente em 04, tarefas em 07.

## Componentes existentes e papel no conjunto

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
| **Missão** | **Objetivo** acima de projetos: coordena agentes e contexto | Proposta ([missao-especificacao.md](missao-especificacao.md)) |

## Outros componentes já existentes (inventário completo, 24/10)

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
| **Canais, Chat, Workspace, Terminal, Explorer** | em uso | Ferramentas do operador; Canal → tarefa em I.8 | I.8 |
| **Navegador do Workspace** (`workspace_browser.py`: rotinas, testes em segundo plano, macros, sites avulsos) | parado; 0 rotinas, 0 testes, 0 macros | **Evoluir** para o serviço de navegação dos agentes, com sessões isoladas, modo teste e modo internet | Fase N ([11](11-navegador-dos-agentes.md)) |
| **Usuários, perfis, TOTP** | em uso | Cada tela nova (Missões, Sustentação) ganha a chave de permissão do módulo | M.1, B.3 |
| **Database, Systemstats, Tool versions, System info, Remote access (túnel)** | em uso | Utilitários; fora do fluxo de trabalho | — |
| **Pessoal (Maia)** | em uso | Fora do Service Factory por desenho (vida pessoal) | — |

## Tipos de trabalho e como cada um entra

| Tipo | Entrada | Onde fica no Service Factory | Evidência de conclusão |
|---|---|---|---|
| **Implementação** | Concepção/escopo, missão, pedido do Marcelo | Produto do sistema → versão em desenvolvimento → projeto da evolução | `git:<sha>` + teste, documento da fase |
| **Manutenção de sistema** (corretiva, preventiva, atualização) | Check do Auditor, rotina, incidente, pedido | Produto do sistema → versão em produção → **projeto permanente "Sustentação"** | `git:` ou `host_execution` + documento/runbook |
| **Serviço em estação/servidor de cliente** | Ticket ou demanda Darckware, "Pedir ao agente" | Produto interno "Serviços de Manutenção" → projeto por ticket/demanda (já existe `:create-project`), com o cliente | `host_execution` (todas as máquinas `ok`) + horas lançadas no Darckware |
| **Infraestrutura interna** (VPS, servidores próprios) | Rotina do Hephaestus/Aegis, check | Produto "Ecossistema Foundation" → projeto "Sustentação" | `host_execution` ou `db:` + runbook |
| **Documentação** | Fase concluída, missão, rotina do Scriba | Tarefa `documentation` dentro do projeto que gerou | `file:` + `DocLink` |
| **Missão** | Marcelo ou agente (rascunho) | Projeto de coordenação interno no Ecossistema Foundation, ligado aos projetos executores | Critérios de todos os projetos vinculados comprovados + dossiê + aceite independente |

Projetos internos não têm cliente (`darckware_client_id` vazio). Só o serviço a cliente carrega o
cliente, herdado do ticket ou da demanda.

## Mapa de interligações

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
| Missão → tudo | nova camada | ❌ | M.* (contrato 04, planejamento 07) |
| Anotação/contrato → despacho | anotações e contrato do projeto no corpo da tarefa | ❌ | P.4, D.8 |
| Projeto proposto (Darckware) → Service Factory | aprovação no portal cria o projeto | ❌ | E.1 |
| Service Factory → pasta do projeto | só a cópia dos documentos da Concepção | 🔶 | D.7, D.10 |
| Tarefa de código → git/PR/CI | evidência `git:<sha>` sem branch, PR nem CI | 🔶 | Q.1–Q.3 |
| Release → Deploy | releases não usadas | ❌ | D.6, Q.5 |
| Hindsight/KB/Foundation → ForgeHub | edição de KB e Foundation; Hindsight só status | 🔶 | C.4 |

---
[← Índice](README.md)
