# Planejamento geral — Ecossistema ForgeHub/Hermes (a partir de 2026-10-02)

**Objetivo central (Marcelo, 2026-10-02):** auditoria e monitoramento do ecossistema, com os agentes ativos em produção 24x7, cada um com funções estabelecidas, rotinas diárias, comunicação entre eles, dúvidas tiradas com o Marcelo pelo Telegram, e o sistema se aperfeiçoando sozinho. As frentes A (backup) e B (auditoria) são a base desse objetivo: a auditoria vira o que os agentes vigiam e o backup é uma das rotinas monitoradas.

Roteiro mestre que ordena os planos detalhados e as pendências soltas levantadas na passagem do Codex para o Claude Code. Cada frente tem um plano próprio; este documento só define **ordem, dependências e decisões pendentes**. Atualize o status aqui no mesmo commit em que uma frente avança.

## Planos detalhados

| Plano | Arquivo |
|---|---|
| A. Backup externo no Google Drive | `docs/superpowers/plans/2026-10-02-offsite-backup-google-drive.md` |
| B. Auditor, Cron e monitoramento do Athos (revisão 2) | `docs/superpowers/plans/2026-10-02-auditor-cron-athos-monitoring.md` |
| B'. Especificação da Auditoria + catálogo v2 | `docs/superpowers/specs/2026-10-02-auditor-cron-athos-monitoring-design.md` |
| C. Operação 24x7 dos agentes + autoaperfeiçoamento (**objetivo central**) | `docs/superpowers/specs/2026-10-02-agent-operations-24x7-design.md` (proposta) |

## Estado em 2026-10-02

- Nada da implementação de A, B ou C começou. O working tree só tem estes documentos.
- O incidente do reboot de 2026-10-02 já foi corrigido pelo Codex: todos os containers estão com `restart: unless-stopped`/`always`. Mas as alterações de compose em **darckware (9), forgevault (1), coreti (21), forgerouter (3) arquivos** continuam **sem commit** nos respectivos repositórios.
- ~~`forgevault.darckware.net` sem Cloudflare Access~~ — **não é falha** (Marcelo: "o sistema tem login e dois fatores"). O 200 anônimo era só a tela de login (SPA); a API responde 401 sem credencial e `/mcp` não é alcançável pelo domínio público (POST → 405, fallback da SPA). Verificado em 2026-10-02.
- Checks falhando hoje: ECO-004 (Lara sem `AGENTS.md`), ECO-022 (`foundation-clear`), ECO-039 (`/etc/docker/daemon.json` ausente / rotação de logs), ECO-040/041 (runtime de voz).
- Nenhum banco de aplicação tem dump, e o único backup fica na própria VPS.

## Fases

### Fase 0 — Proteção imediata (risco de perda ou exposição)

| # | Item | Plano | Depende de |
|---|---|---|---|
| 0.1 | Backup externo: instalação, autorização Google, repositório, script, primeira execução e teste de restauração (A, Tarefas 1–5) | A | Token do `rclone authorize` e confirmação da senha (Marcelo) |
| 0.2 | ✅ Remediações perigosas da Auditoria: gateways por perfil, containers aposentados, scripts inexistentes (B, Tarefa 1). Migração aplicada; deploy do backend pendente para o guard valer em produção | B | — |
| 0.3 | ~~Cloudflare Access no ForgeVault~~ — descartado: ForgeVault tem login próprio com 2FA; API 401 e `/mcp` fora do domínio público confirmados | — | — |
| 0.4 | Commitar as correções de `restart` nos repositórios darckware, forgevault, coreti e forgerouter, depois de revisar cada diff (podem conter trabalho não relacionado) | este roteiro | Revisão do diff |

### Fase 1 — Observabilidade confiável

| # | Item | Plano |
|---|---|---|
| 1.1 | Agendamento do backup externo, registro no ForgeHub e runbook de recuperação (A, Tarefas 6–7) | A |
| 1.2 | Correção operacional dos jobs do Athos: ref git do Hermes, `foundation-clear`, smoke test (B, Tarefa 7) | B |
| 1.3 | Catálogo v2 da Auditoria, com ECO-042…058 (B, Tarefa 2), depois da aprovação da lista | B / B' |
| 1.4 | Monitor do cron semanal do Athos (B, Tarefa 3) | B |
| 1.5 | Estado dos scripts dos crons e fim do catálogo central (B, Tarefa 4) | B |

### Fase 2 — Telas

| # | Item | Plano |
|---|---|---|
| 2.1 | Card de backup externo no System Control (A, Tarefa 9) | A |
| 2.2 | Tela Auditor em pt-BR/en/es (B, Tarefa 5) | B |
| 2.3 | Tela Cron em pt-BR/en/es (B, Tarefa 6) | B |
| 2.4 | Verificação integrada, deploy e push (B, Tarefa 8) | B |

### Fase 3 — Saneamento que o catálogo v2 vai expor

Itens que vão falhar na primeira execução do catálogo v2. Cada um vira tarefa curta, com o check como critério de aceite:

- `AGENTS.md` (e demais arquivos obrigatórios) da Lara (ECO-004/043).
- Política de logs do Docker em `/etc/docker/daemon.json` (ECO-039).
- Runtime de voz: modelo Piper `pt_BR-jeff-medium`, gravador para a CLI, `stt.enabled` da Lara, e um script de reparo para ECO-040/041.
- Perfil `prometheus`: registrar como agente ou aposentar (ECO-044).
- `hooks.outbound` nos perfis Hermes que não enviam telemetria (ECO-053).

### Fase 1b — Perfis e skills (base das cartas de funções)

- Descrições de todos os agentes (ForgeHub `agents.description` e profile files) e as qualidades distintas de Aramis, Porthus e Dartan nos respectivos perfis.
- Por agente Hermes: análise da função, criação das skills da função, arquivamento das skills criadas por agentes sem uso ou obsoletas (`curator archive`, recuperável) e opt-out das bundled fora da função, com snapshot antes.

### Fase 4 — Continuidade dos agentes

Pedido do Marcelo: agentes ociosos o dia todo, à espera de solicitação. A ideia é dar a cada agente funções de continuidade recorrentes, coordenadas por uma tela de controle e com comunicação entre eles pelo Messages.

- Começa por uma especificação (C), reaproveitando o que já existe: Messages como único executor, Incubação, `hermes cron` por perfil e Agent Activity como painel de execução.
- Depende das Fases 1–2: as primeiras funções de continuidade naturais são justamente as rotinas que a Auditoria v2 e o backup tornam verificáveis, como cada responsável de check atuar quando o check falha.
- Questão a decidir na especificação: estender a tela Agent Activity ou criar uma tela de controle própria.

## Decisões aprovadas (Marcelo, 2026-10-02: "aprovado")

| # | Decisão | Valor adotado |
|---|---|---|
| 1 | Senha do backup fora da VPS | Marcelo copia `RESTIC_VPS_BACKUP_PASSWORD` do ForgeVault para o Gerenciador de Senhas do Google (**confirmação ainda pendente**) |
| 2 | Primeiro envio do backup | Continua com o client compartilhado do rclone (lento por `rateLimitExceeded`, sem perda); OAuth client próprio fica opcional |
| 3 | Executor das rotinas | Messages (cobre agentes Hermes e externos) |
| 4 | Tela | `/operations` nova, separada do Agent Activity |
| 5 | Orçamento diário por agente | 24 execuções e US$ 2,00/dia (Athos e Hephaestus: US$ 5,00); editável na tela e ajustável pelo autoaperfeiçoamento só no nível A2 |
| 6 | Catálogo inicial de rotinas | Aprovado como está na especificação |
| 7 | Autonomia e avaliação | A0/A1/A2 como especificado; janela de avaliação de 7 dias |
| 8 | Silêncio no Telegram | 23:00–07:00, só urgências (falha de backup, serviço fora do ar, segurança); o resto entra no briefing das 08:00 |
| 9 | Catálogo v2 da Auditoria | Aprovado. Allow-list de portas: só `127.0.0.1`/`[::1]`, mais o Darckware no IP Tailscale `100.105.235.114` (3000, 8020). Limite do Messages: no máximo 20% de falhas em 7 dias. `prometheus` continua estacionado (`gateway.parked`), sem registro como agente; ECO-044 o ignora enquanto estiver estacionado |
| 10 | Cloudflare Access no ForgeVault | **Descartado** (login próprio + 2FA). O ECO-048 passa a verificar que a API do ForgeVault recusa anônimos (401) e que `/mcp` não responde pelo domínio público |
| 11 | Skills | Arquivar as criadas por agentes sem uso ou obsoletas, desligar por perfil as genéricas fora da função, criar as skills de cada função. A lista por agente é apresentada antes de arquivar |
| 12 | Perfis | Registrar as qualidades distintas de cada agente externo no perfil e melhorar as descrições de todos |

## Decisões pendentes do Marcelo (histórico)

1. Autorizar o Google Drive pelo navegador: abrir a URL gerada pela VPS e colar a URL de retorno, sem instalar nada (Fase 0.1).
2. Confirmação de que a senha do backup foi guardada fora da VPS (Fase 0.1).
3. Aprovação do catálogo v2: allow-list de portas (ECO-047), limite de falhas do Messages (ECO-054) e destino do perfil `prometheus` (Fase 1.3).
4. Manter ou aposentar o `hermes-weekly-backup` local depois do backup externo (Fase 1.1).
5. ~~Cloudflare Access no ForgeVault~~ (descartado).

## Ordem de execução nesta sessão

1. Commit dos documentos de planejamento.
2. **B, Tarefa 1** (remediações), enquanto as decisões 1 e 2 não chegam. É a única frente da Fase 0 sem dependência externa.
3. A, Tarefas 1–5, assim que o token chegar.
4. Seguir as Fases 1 → 2 → 3, atualizando os status acima.
