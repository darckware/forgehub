# Auditor, Cron e Monitoramento do Athos — Plano de Implementação

> **Para agentes:** implemente este plano tarefa por tarefa. Cada tarefa termina com verificação independente e commit.

**Revisão 2 (2026-10-02):** o plano original (`889245d`) foi conferido contra o código, o banco `forgehub` e o host antes de qualquer implementação. A seção "Conferência" registra o que mudou e por quê; as tarefas abaixo já refletem a correção.

**Objetivo:** remover remediações perigosas ou quebradas da Auditoria, substituir o catálogo por uma lista atualizada para os módulos atuais do ecossistema (catálogo v2), expor a saúde real do cron semanal do Athos, retirar o fallback do catálogo central de scripts e renovar as telas Auditor e Cron em `pt-BR`, `en` e `es`.

**Arquitetura:** o ForgeHub continua sendo a fonte de persistência dos checks e runs. A lógica nova fica em módulos puros sob `backend/app/core/` (não existe `app/services/` neste backend), testáveis sem banco nem rede. O monitor do Athos reaproveita o loader de stores de cron que `foundation.py` já tem, em vez de um segundo parser de `jobs.json`. A correção do runtime Hermes e dos jobs externos é uma etapa operacional controlada, fora do código versionado.

**Tecnologias:** FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest/pytest-asyncio, React 18, TypeScript, TanStack Query, Zod, React Testing Library, i18next e Tailwind/shadcn.

**Especificação:** `docs/superpowers/specs/2026-10-02-auditor-cron-athos-monitoring-design.md` (ver a seção "Revisão 2026-10-02").

## Conferência do plano original (2026-10-02)

| Item do plano original | Estado real encontrado | Decisão |
|---|---|---|
| Aposentar checks obsoletos com `lifecycle_status` | `company.audit_checks` tem exatamente `ECO-001`…`ECO-041`, iguais ao `CHECKS` de `checklist_verifier.py`. O único aposentado é o ECO-021. O catálogo, porém, não cobre ForgeVault, Darckware, CoreTI, acesso remoto, backups de banco, restart policy, telemetria, Messages nem os perfis kairos/lara/prometheus | Sem coluna nova (`enabled=false` + motivo basta). Tarefa 2 vira o **catálogo v2** (decisão do Marcelo) |
| Remediações | Fora do plano original, embora a especificação cite `weekly_backup.sh`. ECO-005/ECO-020 reiniciam `hermes-gateway-<perfil>.service`, units que não existem desde o gateway multiplex (a política só permite `systemctl --user restart hermes-gateway`). ECO-010/ECO-012 usam `company_postgres`/`foundation_postgres`, aposentados em 2026-09-04. ECO-012 aponta para um `.sql` inexistente. ECO-024 chama `weekly_backup.sh`, que não existe (o real é `backup_hermes_root.sh`) e tem timeout de 55 s. ECO-040/ECO-041 chamam `repair_voice_runtime.sh`, que não existe | Nova Tarefa 1, prioritária |
| Criar saúde `ok/error/overdue/never_ran/off` e erro de store nos Crons | `CronJobOut.health` e `store_errors` já existem em `foundation.py` | A Tarefa 4 adiciona só `script_state` e `is_audit_job` |
| Fallback central | Confirmado: `crons/index.tsx:329,350` envia `location: "central"`; `foundation.py:1186` aceita `central/main/profile`; `company.cron_scripts` tem 2 linhas com `location='main'` | Mantido, mais a reconciliação dessas 2 linhas |
| `foundation-clear` falha por `ruamel.yaml` | Erro de 2026-09-27. Hoje o venv `/usr/local/lib/hermes-agent/venv` importa `ruamel`, e jobs do mesmo worker rodam OK (memory-maintenance em 2026-10-02 20:30) | Só validar com uma execução manual |
| `daily_hermes_update_check` deve tratar `update --check` como diagnóstico | A causa é uma falha real: `cannot lock ref 'refs/remotes/origin/main'` no checkout do Hermes, ou seja, o `fetch` está quebrado. O `doctor` já é advisory | Reparar a ref git. O script continua tratando falha de `update --check` como erro |
| Traduções `pt-BR` e `en` | `SUPPORTED_UI_LANGUAGES = ["en", "pt-BR", "es"]`. `es` não tem `auditor.json` nem `crons.json` | Incluir `es` nas Tarefas 5 e 6 |
| `backend/app/services/*.py` | O diretório não existe. Módulos puros vivem em `backend/app/core/` | Usar `app/core/` |

## Restrições globais

- Os checks canônicos são os do catálogo v2 (`ECO-001`…`ECO-057`, sem o ECO-021 aposentado), executados por `/root/.hermes/profiles/athos/scripts/checklist_verifier.py --check ECO-NNN`. IDs aposentados nunca são reutilizados.
- A agenda canônica do job do Athos é `0 19 * * 0`, com nome `ecosystem-weekly-audit` e script `ecosystem_weekly_audit.sh`.
- O endpoint interno continua protegido por `X-Bridge-Token` e registra `requested_by=cron`.
- Migrações já aplicadas não são editadas: correções de dados entram como nova revisão, no padrão de `6bd92eeab902_remove_kanboard_from_audit_remediation.py`.
- Nenhuma remediação pode reiniciar gateways por perfil, iniciar um segundo gateway ou usar `kill`/`--force` (Foundation `52_policies/hermes-gateway-operations.md`).
- O frontend não pode resolver scripts por `central`, `main` ou outro catálogo legado.
- Toda chave i18n nova existe em `pt-BR`, `en` e `es`.
- Nenhum segredo pode entrar em código, documentação versionada, logs de teste ou commit.
- O deploy somente ocorre depois de backend, frontend e operações Hermes serem verificados.

## Foco de revisão

- Remediação que referencia unit, container ou script inexistente: `test_remediation_problems_*` e `test_remediate_refuses_broken_command`.
- Catálogo do ForgeHub divergente do verificador ou ID aposentado reutilizado: `test_catalog_matches_verifier` e `test_retired_ids_are_never_reused`.
- Store do Athos ausente, corrompido, duplicado ou com agenda divergente: `test_athos_monitor_*`.
- Job saudável com check falho, que deve aparecer como scheduler saudável e checklist degradado: `test_status_separates_scheduler_from_check_result`.
- Script ausente no perfil e fallback central ainda ativo: `test_cron_job_reports_profile_script_state` e `test_script_content_rejects_legacy_location`.
- Respostas antigas sem os novos campos e estados de erro do frontend: testes de parsing dos hooks e testes de página com mocks de erro.

---

### Tarefa 1: Sanear as remediações da Auditoria

**Arquivos:**
- Criar: `backend/app/core/audit_remediation.py`
- Criar: `backend/alembic/versions/<revision>_fix_stale_audit_remediations.py` (down_revision = head atual, `b3d8f1a6c2e9` na conferência)
- Modificar: `backend/app/api/routes/audit.py`
- Criar: `backend/app/tests/test_audit_remediation.py`

**Interfaces:**
- `remediation_problems(command: str, *, script_exists: Callable[[str], bool] = os.path.exists) -> list[str]`, função pura que retorna os motivos de recusa:
  - referência a container aposentado (`company_postgres`, `foundation_postgres`);
  - `hermes-gateway-<perfil>.service` ou `hermes gateway run`/`--force`/`kill` sobre o gateway;
  - `bash <caminho>` ou `python3 <caminho>` cujo arquivo não existe;
  - redirecionamento `< <arquivo>` inexistente.
- `POST /checks/{id}/remediate` responde `409` com a lista de problemas antes de executar qualquer coisa.
- `POST /checks` e `PATCH /checks/{id}` respondem `422` quando o `remediation_command` enviado tem problema estrutural (container/unit aposentado). Script inexistente é avaliado só na execução, porque o host pode ganhar o arquivo depois.

**Correção de dados (migração):**

| Check | Novo `remediation_command` | Observação |
|---|---|---|
| ECO-005 | o único restart permitido pela política (`systemctl --user restart hermes-gateway`, com o ambiente de usuário necessário ao rodar como root pelo bridge) | Antes de gravar, confirmar no host se a unit é de sistema ou de usuário e testar o comando com `systemctl ... is-active` |
| ECO-020 | igual ao ECO-005 (o ticker do cron roda dentro do gateway) | |
| ECO-010 | `docker start forgehub_postgres hindsight_postgres forgerouter_postgres` + espera `pg_isready` em cada um | `start` é no-op para container já em execução, então não derruba banco saudável |
| ECO-012 | `NULL` | O `.sql` referenciado não existe. Descrição passa a orientar escalada manual |
| ECO-024 | `bash /root/.hermes/profiles/athos/scripts/backup_hermes_root.sh` | Mesmo script do job `hermes-weekly-backup`. `timeout_seconds` sobe para 600 |
| ECO-040, ECO-041 | `NULL` | `repair_voice_runtime.sh` não existe. Escalar até um script de reparo ser criado pelo Athos (pendência registrada) |

O `downgrade` restaura os valores anteriores literalmente.

- [ ] **Passo 1: testes falhando.** `test_remediation_problems_flags_retired_containers`, `..._flags_per_profile_gateway_units`, `..._flags_missing_script`, `..._accepts_current_commands`, `test_remediate_refuses_broken_command` (rota com `_execute_command` simulado: nunca chamado quando há problema) e `test_create_check_rejects_retired_target`.
- [ ] **Passo 2:** `cd backend && .venv/bin/pytest app/tests/test_audit_remediation.py -q`. Esperado: falha.
- [ ] **Passo 3:** implementar `core/audit_remediation.py` e o guard na rota.
- [ ] **Passo 4:** validar no host o comando de restart do gateway (só `is-active`, sem reiniciar) e escrever a migração.
- [ ] **Passo 5:** `.venv/bin/pytest app/tests/test_audit_remediation.py app/tests/test_audit.py -q`, `.venv/bin/ruff check app` e `.venv/bin/alembic upgrade head`. Depois, consultar `company.audit_checks` e confirmar que `remediation_problems` retorna vazio para toda remediação não nula.
- [ ] **Passo 6: commit.** `Audit: drop remediations that target retired units and missing scripts`

### Tarefa 2: Catálogo de auditoria v2

Lista completa, lacunas e justificativas: especificação, seção "Catálogo v2". **Esta tarefa só começa depois que o Marcelo aprovar a lista.**

**Arquivos versionados:**
- Criar: `backend/app/core/audit_catalog.py`
- Criar: `backend/alembic/versions/<revision>_audit_catalog_v2.py`
- Modificar: `backend/app/api/routes/audit.py` (docstring: `forgehub-audit-checklist` passa a `ecosystem-weekly-audit`)
- Criar: `backend/app/tests/test_audit_catalog.py`

**No host, fora do repositório (propriedade do Athos):**
- `/root/.hermes/profiles/athos/scripts/checklist_verifier.py`: novas funções `ECO-042`…`ECO-057` e escopo revisto de ECO-007/009/010/017/019/039
- `audit.foundation_checklist` (hindsight_postgres): novas linhas `[ECO-NNN]` e ECO-021 `retired`

**Interfaces:**
- `CANONICAL_AUDIT_CHECKS: dict[str, CheckSpec]` (nome, categoria, perfil, descrição, timeout) e `RETIRED_AUDIT_CHECKS = {"ECO-021": "<motivo>"}`, a única fonte para a migração e os testes.
- `verifier_check_names(source: str) -> set[str]` extrai via `ast` as chaves do dict `CHECKS` do verificador, sem importá-lo.
- Migração de dados: insere os checks novos (command `python3 .../checklist_verifier.py --check ECO-NNN`, remediação nula até existir um script de reparo validado pela Tarefa 1), atualiza descrições dos checks com escopo revisto e mantém ECO-021 `enabled=false`. É idempotente (`ON CONFLICT (name) DO UPDATE`) e o `downgrade` remove só as linhas novas sem runs.

- [ ] **Passo 1: aprovação da lista** (IDs, responsáveis, allow-list do ECO-047, limite do ECO-054, destino dos dumps do ECO-046, decisão sobre o perfil prometheus).
- [ ] **Passo 2: testes falhando.** `test_catalog_v2_ids_are_contiguous_and_unique`, `test_retired_ids_are_never_reused`, `test_catalog_matches_verifier` (lê o verificador do host; `skip` se ausente), `test_db_catalog_matches_canonical`.
- [ ] **Passo 3: verificador no host.** Snapshot do arquivo, implementação das funções novas no estilo das existentes (só leitura, `Result` com motivo legível), `python3 -m py_compile` e `--check ECO-0NN` para cada novo check. Registrar o resultado inicial de cada um (falhas esperadas viram pendência).
- [ ] **Passo 4:** inserir as linhas novas em `audit.foundation_checklist` e retirar o ECO-021, preservando o log histórico.
- [ ] **Passo 5:** implementar `core/audit_catalog.py` e a migração. Rodar `.venv/bin/pytest app/tests/test_audit_catalog.py app/tests/test_audit.py -q`, `ruff` e `alembic upgrade head`.
- [ ] **Passo 6:** `POST /api/v1/audit/run` e conferir que ECO-025 aceita o novo total e que cada check novo grava um run.
- [ ] **Passo 7: commit.** `Audit: catalog v2 covering current ecosystem modules`

### Tarefa 3: Monitor do cron semanal do Athos

**Arquivos:**
- Criar: `backend/app/core/athos_audit_monitor.py`
- Modificar: `backend/app/api/schemas/audit.py`
- Modificar: `backend/app/api/routes/audit.py`
- Criar: `backend/app/tests/test_athos_audit_monitor.py`
- Modificar: `backend/app/tests/test_audit.py`
- Modificar: `docs/screens/auditor.md`

**Interfaces:**
- `inspect_athos_audit_job(jobs: list[CronJobOut], store_errors: list[CronStoreErrorOut], last_cron_run_at: datetime | None, now: datetime) -> AthosAuditMonitorOut`, função pura. A rota a alimenta com `foundation._list_cron_jobs()`/`_cron_store_errors()` (filtrando `profile == "athos"`) e com o último `AuditCheckRun.created_at` de `requested_by="cron"`.
- `AthosAuditMonitorOut`: `state` (`healthy|degraded|failed|not_configured`), `job_id`, `job_name`, `script`, `schedule`, `enabled`, `health`, `last_run_at`, `last_status`, `next_run_at`, `last_cron_run_at`, `issues: list[str]`.
- Regras: `not_configured` quando não há job; `degraded` para duplicado, agenda/script divergente, desabilitado, `health=overdue` ou último run cron com mais de 8 dias; `failed` para `last_status=error` ou store do Athos com erro de parse.
- `AuditStatusOut.athos_monitor: AthosAuditMonitorOut | None`. Os campos existentes não mudam, e falha ao ler o store vira `failed` com motivo, nunca 500.

- [ ] **Passo 1: testes unitários falhando.** `test_athos_monitor_healthy_for_canonical_job`, `..._missing_or_duplicate_job`, `..._schedule_script_and_disabled_drift`, `..._failed_on_error_status_or_store_error`, `..._marks_stale_audit`.
- [ ] **Passo 2:** implementar o serviço e integrar em `/api/v1/audit/status`. Adicionar `test_status_separates_scheduler_from_check_result` (job OK + um check `fail` resulta em monitor `healthy` e `fail >= 1`).
- [ ] **Passo 3:** `.venv/bin/pytest app/tests/test_athos_audit_monitor.py app/tests/test_audit.py -q` e `ruff`.
- [ ] **Passo 4:** corrigir `docs/screens/auditor.md` (catálogo v2, ECO-021 aposentado, `ecosystem-weekly-audit`, bloco de monitoramento).
- [ ] **Passo 5: commit.** `Audit: expose Athos scheduler health`

### Tarefa 4: Estado dos scripts dos crons e fim do catálogo central

**Arquivos:**
- Criar: `backend/app/core/cron_script_state.py`
- Criar: `backend/alembic/versions/<revision>_reconcile_legacy_cron_script_rows.py`
- Modificar: `backend/app/api/routes/foundation.py`
- Modificar: `backend/app/api/routes/cron_scripts.py` (docstrings/comentários que ainda descrevem o central como ativo)
- Criar: `backend/app/tests/test_cron_operational_state.py`
- Modificar: `frontend/src/hooks/useFoundationCrons.ts`
- Modificar: `frontend/src/hooks/useFoundationScripts.ts`

**Interfaces:**
- `classify_script(path: Path | None) -> Literal["ok", "missing", "broken", "none"]` (`none` = job sem script; `broken` = symlink quebrado ou sem permissão de leitura).
- `CronJobOut` ganha `script_state` e `is_audit_job` (`profile == "athos" and name == "ecosystem-weekly-audit"`). O `deprecated` do plano original foi descartado: o único caso (`cron-worker-smoke-test`) sai do store na Tarefa 7.
- `GET /api/v1/foundation/scripts/{location}/{name}/content` aceita só perfil real; `central`, `main` e `profile` respondem `404`.
- Migração: as 2 linhas `company.cron_scripts.location='main'` são remapeadas para o perfil cujo `scripts/` contém o arquivo; se nenhum contiver, são removidas. Antes, conferir que nenhuma FK aponta para elas.
- `fetchScriptContentWithFallback` deixa de existir; os chamadores usam `fetchScriptContent({ location: job.profile, name: job.script })`.

- [ ] **Passo 1: testes falhando.** `test_cron_job_reports_profile_script_state` (existente, ausente, symlink quebrado, sem script), `test_audit_job_is_tagged`, `test_script_content_rejects_legacy_location`.
- [ ] **Passo 2:** implementar o backend e a migração. Rodar `.venv/bin/pytest app/tests/test_cron_operational_state.py app/tests/test_cron_scripts_sync.py app/tests/test_foundation_script.py -q`, `ruff` e `alembic upgrade head`.
- [ ] **Passo 3:** ajustar os schemas Zod (campos novos opcionais com default, para tolerar resposta antiga) e remover o fallback dos hooks.
- [ ] **Passo 4:** `cd frontend && npm test -- --run && npm run build`.
- [ ] **Passo 5: commit.** `Crons: report script state and remove legacy central resolution`

### Tarefa 5: Renovação da tela Auditor (pt-BR, en, es)

**Arquivos:**
- Modificar: `frontend/src/pages/auditor/index.tsx`
- Criar: `frontend/src/hooks/useAuditorViewModel.ts` (padrão §21, se a página continuar com estado assíncrono coordenado)
- Modificar: `frontend/src/hooks/useAudit.ts`
- Modificar: `frontend/src/i18n/locales/pt-BR/auditor.json`, `frontend/src/i18n/locales/en/auditor.json`
- Criar: `frontend/src/i18n/locales/es/auditor.json`
- Criar: `frontend/src/pages/auditor/index.test.tsx`
- Modificar: `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` (marcar a tela)

**Interfaces:**
- `useAuditStatus()` expõe `athos_monitor` (opcional; resposta antiga renderiza "monitor indisponível").
- A página tem quatro blocos: resumo (ativos/saudáveis/falhos/nunca executados/desabilitados), monitor Athos (com link `/crons`), checklist com filtros por categoria/perfil/estado, e evidência.
- O botão "Remediar" não aparece quando `remediation_command` é nulo. O `409` da Tarefa 1 aparece inline com os motivos.
- Layout conforme a seção de celular do CLAUDE.md (`PageHeader`, `grid-cols-1 md:grid-cols-N`, tabela com scroll).

- [ ] **Passo 1: testes falhando.** `rendersAthosMonitorAndSeparatesSchedulerFromCheckFailure`, `hidesRemediateWhenNoCommand`, `showsRemediationRefusalInline`, `rendersMonitorErrorWithoutBreakingChecklist`, `rendersInSpanish` (troca o idioma para `es` e confere título e ações).
- [ ] **Passo 2:** `cd frontend && npm test -- --run src/pages/auditor/index.test.tsx`. Esperado: falha.
- [ ] **Passo 3:** implementar o hook, a ViewModel e a página com `useTranslation("auditor")` em todo texto visível.
- [ ] **Passo 4:** completar as chaves nos três idiomas, com aria-labels para estados e ações.
- [ ] **Passo 5:** testes da página, `npm run build`, verificação visual em 390px e 1440px.
- [ ] **Passo 6: commit.** `Auditor: show Athos monitoring and safe remediation state`

### Tarefa 6: Renovação da tela Cron (pt-BR, en, es)

**Arquivos:**
- Modificar: `frontend/src/pages/crons/index.tsx`
- Modificar: `frontend/src/i18n/locales/pt-BR/crons.json`, `frontend/src/i18n/locales/en/crons.json`
- Criar: `frontend/src/i18n/locales/es/crons.json`
- Criar: `frontend/src/pages/crons/index.test.tsx`
- Modificar: `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`

**Interfaces:**
- Resumo de saúde (`ok/error/overdue/never_ran/off`), banner de `store_errors`, badge do job de auditoria (`is_audit_job`) e indicação de script `missing/broken`.
- `window.confirm` vira `ConfirmDialog`, e `window.alert` vira aviso inline no card.
- O conteúdo do arquivo é buscado só com `{ location: job.profile, name: job.script }`.

- [ ] **Passo 1: testes falhando.** `rendersHealthSummaryAndAuditBadge`, `rendersMissingScriptWithoutCentralFallback` (garante que nenhuma chamada usa `central`), `showsRunErrorInline`, `opensDeleteConfirmationDialog`, `rendersInSpanish`.
- [ ] **Passo 2:** `cd frontend && npm test -- --run src/pages/crons/index.test.tsx`. Esperado: falha.
- [ ] **Passo 3:** implementar o resumo, a tabela, o `ConfirmDialog`, os erros inline e as chaves i18n nos três idiomas.
- [ ] **Passo 4:** testes, `npm run build`, verificação visual em 390px e 1440px.
- [ ] **Passo 5: commit.** `Crons: surface operational health and retire native dialogs`

### Tarefa 7: Correção operacional dos jobs Hermes do Athos

Usar a skill `hermes-ecosystem-repair` antes de tocar em `/root/.hermes`.

**Arquivos versionados:**
- Criar: `docs/runbooks/auditor-cron-recovery.md`
- Atualizar: `docs/PENDENCIAS.md`, só com evidência final e itens remanescentes (script de reparo de voz para ECO-040/041, migração SQL do ECO-012, os 5 checks que falham hoje)

**No host, fora do repositório:**
- checkout git do Hermes (ref `refs/remotes/origin/main` travada)
- `/root/.hermes/profiles/athos/cron/jobs.json`

- [ ] **Passo 1:** snapshot de `jobs.json` fora do repositório, sem imprimir prompts, tokens ou destinos.
- [ ] **Passo 2: reparar a ref do Hermes.** Diagnosticar o `cannot lock ref 'refs/remotes/origin/main'` (ref solta divergente da `packed-refs` ou lock órfão) e corrigir pelo caminho suportado (`git fetch --prune` / `git remote prune origin`, removendo só um `*.lock` órfão confirmado). Confirmar com `hermes update --check` (código 0 ou "update available") **sem** aplicar update.
- [ ] **Passo 3:** executar `daily_hermes_update_check` manualmente e confirmar `last_status=ok`. O script não é alterado: falha de `update --check` continua sendo erro real.
- [ ] **Passo 4:** executar `foundation-clear` manualmente e confirmar que o worker não reproduz o `ModuleNotFoundError: ruamel`. Se reproduzir, rodar `hermes pm repair` e repetir.
- [ ] **Passo 5:** confirmar que `cron-worker-smoke-test` (já `enabled=false`) não é referenciado por outro job ou script e removê-lo com o comando de cron do Hermes.
- [ ] **Passo 6:** executar `ecosystem-weekly-audit` manualmente e confirmar runs novos com `requested_by=cron`, ECO-022 OK e o monitor da Tarefa 3 em `healthy`.
- [ ] **Passo 7:** registrar no runbook horário, job, código de saída e resultado resumido, sem prompts nem tokens.
- [ ] **Passo 8: commit.** `Ops: document Athos audit cron recovery`

### Tarefa 8: Verificação integrada, deploy e entrega

- [ ] **Passo 1: backend.** `cd backend && .venv/bin/pytest app/tests/test_audit.py app/tests/test_audit_remediation.py app/tests/test_audit_catalog.py app/tests/test_athos_audit_monitor.py app/tests/test_cron_operational_state.py app/tests/test_cron_scripts_sync.py app/tests/test_foundation_script.py -q` e `.venv/bin/ruff check app`.
- [ ] **Passo 2: frontend.** `cd frontend && npm test -- --run && npm run build`.
- [ ] **Passo 3: contrato.** `GET /api/v1/audit/status` (com `athos_monitor`), `GET /api/v1/audit/checks` e `GET /api/v1/foundation/crons` (com `script_state`/`is_audit_job`). `/api/v1/audit/run-internal` rejeita token inválido. `GET /foundation/scripts/central/x/content` retorna 404.
- [ ] **Passo 4: deploy.** `scripts/deploy.sh api web`, acompanhando os health checks.
- [ ] **Passo 5: smoke test.** Auditor: resumo, monitor, filtros, histórico e idioma `es`. Crons: resumo, script quebrado sem fallback, erro inline e `ConfirmDialog`. Executar um check manual não destrutivo e confirmar o run `manual`.
- [ ] **Passo 6: revisão final.** `git diff --check`, `git status --short --branch` e conferência de ausência de segredo.
- [ ] **Passo 7: push.** `git push origin develop`.
