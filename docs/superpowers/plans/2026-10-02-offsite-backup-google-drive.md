# Backup externo da VPS no Google Drive — Especificação e Plano

**Data:** 2026-10-02
**Status:** Aprovado na direção (Marcelo: backup de todo o `/root` no Google Drive da conta marcelodarck@gmail.com, com Google One). Prioridade sobre o plano de Auditoria/Cron.
**Responsável operacional:** Athos (script no perfil, `hermes cron`, registrado no ForgeHub).

## Objetivo

Se a VPS for perdida, deve ser possível reconstruí-la numa máquina nova com **apenas duas coisas**: login na conta Google e a senha do repositório de backup. Ficam cobertos todos os projetos, a configuração do Hermes e seus perfis, os runtimes externos (Claude Code, Codex, agy, OpenClaw), os bancos de dados de todas as aplicações e a configuração do sistema.

## Situação atual

- O único backup é `backup_hermes_root.sh`: um tar semanal de `/root/.hermes` + `/root/memory`, gravado **na própria VPS** (`/root/backup/hermes-root`). Se o disco se perder, ele se perde junto.
- Nenhum banco de aplicação tem dump: forgehub, forgerouter, hindsight, forgevault (guarda as chaves), darckware e coreti.
- `/root` ocupa 38 GB. Cerca de 18 GB são caches regeneráveis (`.npm` 9,9 GB, `.cache` 4,6 GB, `.nuget` 1,3 GB, `node_modules`, venvs). O conteúdo útil fica em ~19 GB, ou 10–13 GB compactados.
- `/root/db/*-postgres` são os diretórios de dados **vivos** do forgehub/forgerouter/hindsight. Copiar esses arquivos com o banco rodando gera cópia inconsistente; o dump é a fonte restaurável.
- O Hermes usa vários SQLite com WAL (`state.db`, `cron/executions.db`, `sqlite-foundation`). Uma cópia a quente pode pegar um estado intermediário.

## Desenho

### Ferramentas

- **restic 0.16** (apt do Ubuntu 24.04): backup incremental, deduplicado, compactado e **criptografado no cliente**. Cada execução vira um snapshot restaurável por data.
- **rclone** (apt) como transporte para o Google Drive: `restic -r rclone:gdrive:vps-backup/restic`.
- O Google só armazena blobs cifrados. Sem a senha do restic, o conteúdo é ilegível, inclusive para quem tiver acesso à conta.

### O que entra

`/root` inteiro e `/etc`, mais três artefatos gerados antes de cada execução, dentro de `/root/backup/offsite-staging/` (o que faz com que entrem no snapshot):

1. **Dumps Postgres** das 6 instâncias (`forgehub_postgres`, `hindsight_postgres`, `forgerouter_postgres`, `forgevault-postgres-1`, `darckware-postgres`, `coreti_postgres`): `pg_dumpall --globals-only` + `pg_dump` por banco em **formato texto sem compressão**. O restic deduplica e compacta melhor texto estável do que um `-Fc` já comprimido, então dumps diários quase iguais custam pouco espaço.
2. **Snapshots SQLite** via `sqlite3 <db> ".backup <destino>"` para os bancos conhecidos do Hermes (online e consistente).
3. **Estado do sistema** para reconstruir a máquina: `apt-mark showmanual`, `dpkg --get-selections`, `snap list`, `npm -g ls --depth=0`, `pip freeze` do venv do hermes-agent, `docker ps -a` / `docker compose ls` / `docker image ls`, `systemctl list-unit-files --state=enabled` (sistema e usuário), `crontab -l`, versão do kernel e do Hermes.

### O que fica de fora (regenerável ou inconsistente)

`.npm`, `.cache`, `.nuget`, `go/pkg/mod`, `**/node_modules`, `**/.venv`, `**/venv`, `**/venvs`, `**/__pycache__`, `**/.next`, `**/bin/Debug`, `**/obj`, `.local/share/Trash`, `/root/backup/hermes-root` (substituído por este backup), os dados vivos `/root/db/*-postgres/*` (os dumps cobrem; o `docker-compose.yml` entra) e os arquivos SQLite vivos que têm snapshot próprio. A lista fica num `excludes.txt` versionado junto ao script, para ser auditável. Só sai o que é comprovadamente regenerável.

### Agenda e retenção

- Diário às **02:30** (America/Sao_Paulo), antes do `docker-daily-cleanup` (04:30) e sem cruzar com o `hermes-weekly-backup` de domingo 03:00.
- `restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 12`, com `--prune` só aos domingos (o prune reescreve pacotes e é a parte cara).
- `restic check` sem dados diariamente. Aos domingos, `restic check --read-data-subset=5%` baixa e verifica uma amostra real.

### Segredos

- **Senha do restic:** gerada na VPS e mostrada uma única vez para o Marcelo guardar no gerenciador de senhas. Fica em `/root/.config/restic/password` (0600) só para as execuções automáticas. Sem a cópia externa, o backup é irrecuperável. Este é o ponto crítico do desenho.
- **Token do Google:** obtido **inteiramente pela VPS**, sem instalar nada no computador do Marcelo (decisão dele). O `rclone authorize "drive"` roda na VPS e gera a URL de consentimento; o Marcelo abre essa URL no navegador (computador ou celular) e autoriza. O Google então redireciona para `http://127.0.0.1:53682/?code=...`, endereço que na máquina dele não abre. Ele copia essa URL da barra de endereço e cola na sessão, e a VPS a entrega ao próprio listener do rclone, que troca o código pelo token. O token é gravado em `/root/.config/rclone/rclone.conf` (0600). Escopo `drive.file`: o rclone só enxerga os arquivos que ele mesmo criou, não o restante do Drive.
- Opcional, também só pelo navegador: um **OAuth client próprio** no Google Cloud Console. O client compartilhado do rclone tem limite de taxa global e pode deixar o primeiro envio mais lento. Dá para começar sem ele e trocar depois, reautorizando.
- Nada disso entra no git. Os dois arquivos estão em `/root/.config`, então também vão (cifrados) para o snapshot. Numa VPS nova basta reautorizar o Google e digitar a senha.

### Falha e observabilidade

- O script termina com código ≠ 0 em qualquer falha (dump, snapshot SQLite, backup, check). O cron do Athos marca erro, e isso já alimenta o ECO-022 e o alerta de cron do Agent Activity.
- A cada execução, grava `/root/backup/offsite-staging/last_run.json` (início, fim, snapshot id, bytes adicionados, resultado do check, sem segredo). É a evidência do novo check de auditoria.
- Entrega do resultado ao Marcelo pelo canal configurado do job (`deliver`) só em falha. Sucesso diário fica só no log, para não virar ruído.

## Tarefas

### Tarefa 1: Instalação e autorização do Google Drive

- [ ] `apt install restic rclone sqlite3` na VPS; conferir `restic version` ≥ 0.16 (compressão).
- [ ] Na VPS, `rclone authorize "drive"` (escopo `drive.file`) em background, aguardando no listener local `127.0.0.1:53682`, e entregar ao Marcelo a URL de consentimento.
- [ ] Marcelo abre a URL no navegador, autoriza com marcelodarck@gmail.com e cola na sessão a URL `http://127.0.0.1:53682/?code=...` em que o navegador parar.
- [ ] Na VPS, `curl` nessa URL contra o listener local. O rclone imprime o token, que é gravado no remote. Nada é instalado no computador do Marcelo.
- [ ] Criar o remote `gdrive` (`scope = drive.file`) e validar com `rclone mkdir gdrive:vps-backup` + `rclone lsd gdrive:`.

### Tarefa 2: Repositório restic e custódia da senha

- [ ] Gerar a senha (`openssl rand -base64 32`), gravar em `/root/.config/restic/password` (0600) e mostrá-la ao Marcelo uma única vez.
- [ ] **Bloqueante:** Marcelo confirma que salvou a senha fora da VPS. Só depois se segue.
- [ ] `restic init -r rclone:gdrive:vps-backup/restic` e `restic cat config` para confirmar a versão 2 do repositório (com compressão).

### Tarefa 3: Script `backup_offsite_root.sh` (Athos)

**Arquivos (host, perfil Athos):** `/root/.hermes/profiles/athos/scripts/backup_offsite_root.sh` e `/root/.hermes/profiles/athos/scripts/backup_offsite_root.excludes`

- [ ] Cabeçalho `#` descritivo (lido pelo sync do ForgeHub), `set -euo pipefail` e `flock` próprio.
- [ ] Etapa de staging: limpa `offsite-staging/`, gera os dumps Postgres (usuário e banco lidos de cada container, nunca hardcoded), os snapshots SQLite e o estado do sistema. Qualquer dump vazio ou com erro aborta antes do upload.
- [ ] `restic backup /root /etc --exclude-file=... --tag daily --one-file-system`, seguido de forget, prune aos domingos e check, conforme o desenho.
- [ ] Grava `last_run.json` e imprime um resumo de uma linha (snapshot, tamanho adicionado, duração).
- [ ] `bash -n` e `shellcheck` (se disponível) passam.

### Tarefa 4: Primeira execução (manual)

- [ ] Rodar o script manualmente em background (o primeiro envio tem ~10–13 GB e pode levar horas), acompanhando o log.
- [ ] Conferir `restic snapshots`, `restic stats --mode raw-data` e `restic check`.
- [ ] Rodar de novo e confirmar que o incremental é pequeno e rápido.

### Tarefa 5: Teste de restauração (critério de aceite)

- [ ] `restic restore latest --target /tmp/restore-test --include /root/.hermes/profiles/athos --include /root/project/forgehub/.env` e comparar com o original.
- [ ] Restaurar o dump do `forgevault` num container Postgres temporário e contar as tabelas e linhas principais.
- [ ] Abrir um snapshot SQLite restaurado com `sqlite3 ... "pragma integrity_check"`.
- [ ] Apagar o diretório de teste e o container temporário.

### Tarefa 6: Agendamento e registro

- [ ] `hermes cron` no perfil athos: job `backup-offsite-root`, `30 2 * * *`, `no_agent` (script), entrega só em falha. Conferir que o timeout do worker comporta uma execução incremental (e o prune de domingo).
- [ ] `POST /api/v1/scripts/sync` no ForgeHub e conferir a linha (`agent=athos`, `category=maintenance`).
- [ ] Decidir com o Marcelo o destino do `hermes-weekly-backup` local: manter como restauração rápida local ou aposentar.

### Tarefa 7: Runbook de recuperação de desastre

**Arquivo:** `docs/runbooks/offsite-backup-restore.md` (versionado, sem segredos)

- [ ] Do zero numa VPS nova: instalar restic/rclone, `rclone config` com reautorização do Google, `restic snapshots` com a senha do gerenciador.
- [ ] Ordem de restauração: `/etc` (seletivo: units, cloudflared, headscale) → `/root` → Docker e redes (`foundation_network`) → `docker compose up` de cada aplicação com banco vazio → importação dos dumps → serviços systemd (bridge, gateway Hermes de usuário) → validação com o Auditor do ForgeHub.
- [ ] Como restaurar um arquivo ou pasta isolada de uma data específica (o uso mais comum).

### Tarefa 8: Integração com a Auditoria

- [ ] No catálogo v2 (`2026-10-02-auditor-cron-athos-monitoring.md`, Tarefa 2): o **ECO-046** (dumps de banco) passa a verificar os dumps gerados por este script dentro de `last_run.json`. Entra um novo check **ECO-058 — backup externo**: último snapshot com menos de 36 h, `restic check` OK na última execução e repositório alcançável. Responsável: hephaestus.
- [ ] Atualizar a seção "Catálogo v2" da especificação da Auditoria com o ECO-058.

### Tarefa 9: Controle na tela System Control

Marcelo pediu que o backup externo seja acompanhado e acionado pela tela System Control, ao lado dos cards de Backups locais e Docker. Segue o mesmo padrão: proxy pelo host-bridge, sem tabela própria e com o par ViewModel (§21).

**Arquivos:**
- Modificar: `backend/app/api/routes/system_control.py`
- Criar: `backend/app/tests/test_system_control_offsite_backup.py`
- Criar: `frontend/src/pages/system-control/OffsiteBackupCard.tsx`
- Criar: `frontend/src/hooks/useOffsiteBackupViewModel.ts`
- Modificar: `frontend/src/pages/system-control/index.tsx`
- Modificar/criar: `frontend/src/i18n/locales/{pt-BR,en,es}/` (namespace da tela)
- Modificar: `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`

**Contrato:**
- `GET /api/v1/system-control/offsite-backup` (usuário autenticado) responde `{ state, last_run, snapshots, repository, job }`:
  - `last_run`: conteúdo de `last_run.json` (início, fim, duração, snapshot id, bytes adicionados, resultado do check, erro);
  - `snapshots`: `restic snapshots --json` (data, id curto, tags, tamanho), os 30 mais recentes;
  - `repository`: tamanho total (`restic stats --mode raw-data`) e uso do Drive (`rclone about gdrive:`), com cache de 10 min, pois ambos consultam o Google;
  - `job`: saúde do cron `backup-offsite-root` do Athos, reaproveitando o loader de crons de `foundation.py`;
  - `state`: `healthy` (snapshot < 36 h e check OK), `stale`, `failed`, `auth_required` (rclone sem token válido) ou `not_configured`.
- `POST /api/v1/system-control/offsite-backup:run` (admin) dispara o **mesmo** job pelo caminho de `POST /foundation/crons/{job_id}/run`. Não existe um segundo executor, e o `flock` do script impede duas execuções simultâneas (`409` se já houver uma em andamento).
- Os comandos `restic`/`rclone` são montados no backend como constantes, sem entrada do usuário. Senha e token nunca saem do host: o bridge executa com `RESTIC_PASSWORD_FILE` e a resposta não inclui nenhum dos dois. Bridge ou Google inalcançável vira `state` degradado com motivo, nunca um falso "saudável".

**Interface:**
- Card "Backup externo (Google Drive)": selo de estado, último backup (quando, duração, quanto foi enviado), próxima execução, tamanho do repositório e cota do Drive, lista de snapshots e botão "Fazer backup agora" com `ConfirmDialog` e `Loader2`.
- `auth_required` mostra o procedimento de reautorização pelo navegador (URL gerada na VPS, colar a URL de retorno) e o link do runbook. Integrar esse fluxo ao próprio card fica para a fase 2.
- Layout de celular conforme o CLAUDE.md. Texto em pt-BR, en e es.

**Fase 2 (fora deste plano, decidir depois):** navegar por um snapshot e restaurar um arquivo ou pasta para `/root/restore/<data>/`, nunca sobrescrevendo no lugar, com `AuditEvent`. A restauração completa continua sendo do runbook.

- [ ] **Passo 1: testes backend falhando.** `test_offsite_status_healthy`, `test_offsite_status_stale_and_failed`, `test_offsite_status_auth_required`, `test_offsite_status_bridge_down_is_degraded`, `test_offsite_run_requires_admin`, `test_offsite_response_never_contains_secrets` (bridge simulado).
- [ ] **Passo 2:** implementar as rotas. Rodar `pytest` e `ruff`.
- [ ] **Passo 3: testes de página falhando.** `rendersHealthyState`, `rendersAuthRequiredInstructions`, `confirmsBeforeRunNow`, `rendersInSpanish`.
- [ ] **Passo 4:** implementar a ViewModel e o card. Rodar `npm test -- --run`, `npm run build` e conferir visualmente em 390px e 1440px.
- [ ] **Passo 5: commit.** `System Control: show and trigger off-site Google Drive backup`

## Critérios de aceite

1. Existe um snapshot diário no Google Drive, cifrado, cobrindo `/root` e `/etc` com as exclusões documentadas.
2. Todos os 6 Postgres têm dump consistente em cada snapshot.
3. A restauração de amostra (Tarefa 5) funciona, incluindo o banco do ForgeVault.
4. A senha está confirmada fora da VPS, e o runbook permite reconstruir a máquina só com conta Google e senha.
5. Uma falha do backup aparece como erro de cron e na Auditoria (ECO-058).
6. Nenhum segredo em git, log ou saída de cron.
7. A tela System Control mostra o estado do backup externo, os snapshots e a cota, e permite disparar um backup sob confirmação, sem expor senha ou token.
