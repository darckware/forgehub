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
- `forgevault.darckware.net` responde **200 para requisição anônima**: o Cloudflare Access exigido pela documentação não está ativo. O serviço guarda as chaves do ecossistema.
- Checks falhando hoje: ECO-004 (Lara sem `AGENTS.md`), ECO-022 (`foundation-clear`), ECO-039 (`/etc/docker/daemon.json` ausente / rotação de logs), ECO-040/041 (runtime de voz).
- Nenhum banco de aplicação tem dump, e o único backup fica na própria VPS.

## Fases

### Fase 0 — Proteção imediata (risco de perda ou exposição)

| # | Item | Plano | Depende de |
|---|---|---|---|
| 0.1 | Backup externo: instalação, autorização Google, repositório, script, primeira execução e teste de restauração (A, Tarefas 1–5) | A | Token do `rclone authorize` e confirmação da senha (Marcelo) |
| 0.2 | ✅ Remediações perigosas da Auditoria: gateways por perfil, containers aposentados, scripts inexistentes (B, Tarefa 1). Migração aplicada; deploy do backend pendente para o guard valer em produção | B | — |
| 0.3 | ForgeVault atrás do Cloudflare Access (política no painel Zero Trust; validar `curl` anônimo → 302/403) | este roteiro | Acesso do Marcelo ao painel Cloudflare |
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

### Fase 4 — Continuidade dos agentes

Pedido do Marcelo: agentes ociosos o dia todo, à espera de solicitação. A ideia é dar a cada agente funções de continuidade recorrentes, coordenadas por uma tela de controle e com comunicação entre eles pelo Messages.

- Começa por uma especificação (C), reaproveitando o que já existe: Messages como único executor, Incubação, `hermes cron` por perfil e Agent Activity como painel de execução.
- Depende das Fases 1–2: as primeiras funções de continuidade naturais são justamente as rotinas que a Auditoria v2 e o backup tornam verificáveis, como cada responsável de check atuar quando o check falha.
- Questão a decidir na especificação: estender a tela Agent Activity ou criar uma tela de controle própria.

## Decisões pendentes do Marcelo

1. Autorizar o Google Drive pelo navegador: abrir a URL gerada pela VPS e colar a URL de retorno, sem instalar nada (Fase 0.1).
2. Confirmação de que a senha do backup foi guardada fora da VPS (Fase 0.1).
3. Aprovação do catálogo v2: allow-list de portas (ECO-047), limite de falhas do Messages (ECO-054) e destino do perfil `prometheus` (Fase 1.3).
4. Manter ou aposentar o `hermes-weekly-backup` local depois do backup externo (Fase 1.1).
5. Ativar o Cloudflare Access no ForgeVault (Fase 0.3).

## Ordem de execução nesta sessão

1. Commit dos documentos de planejamento.
2. **B, Tarefa 1** (remediações), enquanto as decisões 1 e 2 não chegam. É a única frente da Fase 0 sem dependência externa.
3. A, Tarefas 1–5, assim que o token chegar.
4. Seguir as Fases 1 → 2 → 3, atualizando os status acima.
