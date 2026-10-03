# Auditor, Cron e Monitoramento do Athos — Plano de Implementação

> **Para agentes:** use a subskill `superpowers:executing-plans` para implementar este plano tarefa por tarefa. Cada tarefa termina com verificação independente e commit.

**Objetivo:** alinhar o catálogo da Auditoria ao verificador canônico, expor a saúde real do cron semanal do Athos, retirar referências descontinuadas e renovar as telas Auditor e Cron.

**Arquitetura:** o ForgeHub continuará sendo a fonte de persistência dos checks e runs. Um serviço pequeno, testável por caminho de store, inspecionará o job semanal do perfil Athos e será incorporado ao endpoint existente `/api/v1/audit/status`; o frontend consumirá esse contrato e o endpoint de Crons sem criar outro scheduler. A correção do runtime Hermes e dos jobs externos será executada como etapa operacional controlada, fora do código versionado.

**Tecnologias:** FastAPI, SQLAlchemy async, Alembic, Pydantic, pytest/pytest-asyncio, React 18, TypeScript, TanStack Query, Zod, React Testing Library, i18next e Tailwind/shadcn.

**Especificação:** `docs/superpowers/specs/2026-10-02-auditor-cron-athos-monitoring-design.md`

## Restrições globais

- Os checks canônicos são `ECO-001` a `ECO-041`, executados por `/root/.hermes/profiles/athos/scripts/checklist_verifier.py`.
- A agenda canônica do job do Athos é `0 19 * * 0`, com nome `ecosystem-weekly-audit` e script `ecosystem_weekly_audit.sh`.
- O endpoint interno continua protegido por `X-Bridge-Token` e registra `requested_by=cron`.
- Checks ou funções aposentados não podem entrar em novas execuções; runs históricos permanecem consultáveis.
- O frontend não pode resolver scripts por `central`, `main` ou outro catálogo legado.
- Nenhum segredo pode entrar em código, documentação versionada, logs de teste ou commit.
- O deploy somente ocorre depois de backend, frontend e operações Hermes serem verificados.

## Foco de revisão

- Check `ECO-*` aposentado ainda sendo enviado para `/run-internal`; teste em `test_run_all_excludes_retired_checks`.
- Store Athos ausente, corrompido, duplicado ou com agenda divergente; testes em `test_athos_monitor_*`.
- Job saudável com check falho, que deve aparecer como scheduler saudável e checklist degradado; teste em `test_status_separates_scheduler_from_check_result`.
- Script ausente no perfil e fallback central ainda ativo; testes em `test_cron_job_reports_profile_script_state` e `test_script_content_rejects_legacy_location`.
- Respostas antigas sem os novos campos e estados de erro do frontend; testes de parsing dos hooks e testes de página com mocks de erro.

---

### Tarefa 1: Ciclo de vida e reconciliação do catálogo de Auditoria

**Arquivos:**
- Criar: `backend/app/services/audit_catalog.py`
- Criar: `backend/alembic/versions/<revision>_add_audit_check_lifecycle.py`
- Modificar: `backend/app/db/models/audit.py`
- Modificar: `backend/app/api/schemas/audit.py`
- Modificar: `backend/app/api/routes/audit.py`
- Modificar: `backend/app/tests/test_audit.py`
- Testar: `backend/app/tests/test_audit_catalog.py`

**Interfaces:**
- Produz `CANONICAL_AUDIT_CHECK_NAMES`, `is_canonical_audit_check(name: str) -> bool` e `retired_reason_for(name: str) -> str | None`.
- `AuditCheck` passa a expor `lifecycle_status: Literal["active", "retired"]` e `retired_reason: str | None`.
- `AuditCheckOut` e `AuditCheckUpdate` carregam os mesmos campos; `AuditStatusOut` passa a incluir `retired`.
- `_run_enabled_checks` considera somente `enabled == true` e `lifecycle_status == "active"`.

- [ ] **Passo 1: escrever os testes falhando**
  - `test_canonical_catalog_contains_exactly_41_checks` verifica `ECO-001`…`ECO-041`.
  - `test_run_all_excludes_retired_checks` cria um check ativo e um aposentado, chama `POST /api/v1/audit/run` com `_execute_check` simulado e confirma que apenas o ativo é executado.
  - `test_retired_check_preserves_run_history` confirma que uma atualização de ciclo de vida não apaga `AuditCheckRun`.
  - `test_status_counts_retired_separately` verifica os novos contadores.
- [ ] **Passo 2: executar a suíte nova para confirmar a falha**
  - Rodar `cd backend && .venv/bin/pytest app/tests/test_audit_catalog.py app/tests/test_audit.py -q`.
  - Esperado: falha por campos/serviço ainda inexistentes.
- [ ] **Passo 3: implementar o catálogo e o ciclo de vida**
  - Criar a constante canônica e a validação de nomes `ECO-001`…`ECO-041`.
  - Adicionar colunas com default `active`; a migração marca como `retired` somente nomes `ECO-NNN` fora do conjunto canônico, preservando checks customizados e runs existentes.
  - Atualizar schemas, serialização e filtros da rota; execução individual de check aposentado retorna `409` com motivo claro.
  - Manter `DELETE` compatível para checks customizados sem histórico; a UI usará aposentadoria para checks canônicos.
- [ ] **Passo 4: executar os testes para confirmar a passagem**
  - Rodar o mesmo comando do Passo 2 e `cd backend && .venv/bin/ruff check app`.
  - Esperado: todos os testes e lint passam.
- [ ] **Passo 5: revisar a migração contra o head atual**
  - Rodar `cd backend && .venv/bin/alembic upgrade head` em ambiente de teste e confirmar que a migração é idempotente em catálogo já existente.
- [ ] **Passo 6: commit**
  - `git add backend/app/services/audit_catalog.py backend/alembic/versions backend/app/db/models/audit.py backend/app/api/schemas/audit.py backend/app/api/routes/audit.py backend/app/tests/test_audit.py backend/app/tests/test_audit_catalog.py`
  - `git commit -m "Audit: retire obsolete checks without losing evidence"`

### Tarefa 2: Monitor testável do cron semanal do Athos

**Arquivos:**
- Criar: `backend/app/services/athos_audit_monitor.py`
- Modificar: `backend/app/api/schemas/audit.py`
- Modificar: `backend/app/api/routes/audit.py`
- Modificar: `backend/app/tests/test_audit.py`
- Criar: `backend/app/tests/test_athos_audit_monitor.py`
- Modificar: `docs/screens/auditor.md`

**Interfaces:**
- `inspect_athos_audit_job(store_path: Path, now: datetime | None = None) -> AthosAuditMonitorOut` lê somente o store fornecido, sem acessar banco ou rede.
- `AthosAuditMonitorOut` contém `state` (`healthy|degraded|failed|not_configured`), `profile`, `job_id`, `job_name`, `script`, `schedule`, `enabled`, `last_run_at`, `last_status`, `next_run_at` e `message`.
- `AuditStatusOut.athos_monitor` usa o tipo acima; `last_run_at` legado continua representando o último run geral.

- [ ] **Passo 1: escrever testes unitários falhando**
  - `test_athos_monitor_healthy_for_canonical_job` usa store temporário com um job correto e estado recente.
  - `test_athos_monitor_detects_missing_or_duplicate_job` cobre `not_configured` e `degraded`.
  - `test_athos_monitor_detects_schedule_script_and_failure_drift` cobre agenda, script, disabled e `last_status=error`.
  - `test_athos_monitor_marks_stale_audit` cobre ausência de execução há mais de oito dias.
- [ ] **Passo 2: executar os testes para confirmar a falha**
  - Rodar `cd backend && .venv/bin/pytest app/tests/test_athos_audit_monitor.py -q`.
  - Esperado: falha por módulo e schema inexistentes.
- [ ] **Passo 3: implementar o serviço**
  - Usar `Path("/profiles/athos/cron/jobs.json")` como default de produção e injeção de caminho nos testes.
  - Não considerar falha de um check individual como falha do scheduler; o monitor mede configuração, despacho e existência de execução cron.
  - Usar o último `AuditCheckRun.created_at` com `requested_by="cron"` para a idade da auditoria.
- [ ] **Passo 4: integrar no endpoint `/api/v1/audit/status`**
  - Adicionar o bloco `athos_monitor` sem remover campos existentes.
  - Adicionar `test_status_separates_scheduler_from_check_result`, simulando job executado com um check falho.
- [ ] **Passo 5: executar testes e lint**
  - Rodar `cd backend && .venv/bin/pytest app/tests/test_athos_audit_monitor.py app/tests/test_audit.py -q` e `cd backend && .venv/bin/ruff check app`.
- [ ] **Passo 6: atualizar documentação da tela**
  - Corrigir `docs/screens/auditor.md` para `ECO-001`…`ECO-041`, `ecosystem-weekly-audit` e o bloco de monitoramento.
- [ ] **Passo 7: commit**
  - `git add backend/app/services/athos_audit_monitor.py backend/app/api/schemas/audit.py backend/app/api/routes/audit.py backend/app/tests/test_athos_audit_monitor.py backend/app/tests/test_audit.py docs/screens/auditor.md`
  - `git commit -m "Audit: expose Athos scheduler health"`

### Tarefa 3: Estado dos scripts e remoção do catálogo central

**Arquivos:**
- Criar: `backend/app/services/cron_script_state.py`
- Modificar: `backend/app/api/routes/foundation.py`
- Modificar: `backend/app/api/routes/cron_scripts.py`
- Modificar: `backend/app/api/schemas` somente se o contrato compartilhado exigir
- Criar: `backend/app/tests/test_cron_operational_state.py`
- Modificar: `frontend/src/hooks/useFoundationCrons.ts`
- Modificar: `frontend/src/hooks/useFoundationScripts.ts`

**Interfaces:**
- `CronJobOut` passa a incluir `script_state: Literal["ok", "missing", "broken", "none"]`, `is_audit_job: bool` e `deprecated: bool`.
- `GET /api/v1/foundation/scripts/{location}/{name}/content` aceita somente um perfil real; localizações `central`, `main` e `profile` respondem `404`.
- `fetchScriptContentWithFallback` é substituída por resolução de um único `ScriptLocationRef` do perfil do job.

- [ ] **Passo 1: escrever testes falhando**
  - `test_cron_job_reports_profile_script_state` cobre script existente, ausente e symlink quebrado.
  - `test_audit_job_is_tagged` verifica nome, perfil e script canônicos.
  - `test_script_content_rejects_legacy_location` garante que o catálogo central não volta por compatibilidade.
- [ ] **Passo 2: executar os testes para confirmar a falha**
  - Rodar `cd backend && .venv/bin/pytest app/tests/test_cron_operational_state.py -q`.
  - Esperado: falha pelos novos campos e regra de resolução.
- [ ] **Passo 3: implementar o estado operacional**
  - Extrair a classificação de script para serviço puro, reutilizável pela rota e pelos testes.
  - Derivar `is_audit_job` de `profile == "athos"` e `name == "ecosystem-weekly-audit"`; derivar `deprecated` apenas para `cron-worker-smoke-test` até sua remoção operacional.
  - Remover busca em diretórios centrais da rota de conteúdo e atualizar comentários/documentação que ainda afirmam que o catálogo central está ativo.
- [ ] **Passo 4: atualizar contratos TypeScript**
  - Ajustar Zod para os campos novos e remover candidatos `central` dos hooks.
- [ ] **Passo 5: executar backend e frontend checks**
  - Rodar `cd backend && .venv/bin/pytest app/tests/test_cron_operational_state.py -q`.
  - Rodar `cd frontend && npm test -- --run` e `cd frontend && npm run build`.
- [ ] **Passo 6: commit**
  - `git add backend/app/services/cron_script_state.py backend/app/api/routes/foundation.py backend/app/api/routes/cron_scripts.py backend/app/tests/test_cron_operational_state.py frontend/src/hooks/useFoundationCrons.ts frontend/src/hooks/useFoundationScripts.ts`
  - `git commit -m "Crons: remove legacy central script resolution"`

### Tarefa 4: Renovação da tela Auditor e seus contratos de tradução

**Arquivos:**
- Modificar: `frontend/src/pages/auditor/index.tsx`
- Modificar: `frontend/src/hooks/useAudit.ts`
- Modificar: `frontend/src/i18n/locales/pt-BR/auditor.json`
- Modificar: `frontend/src/i18n/locales/en/auditor.json`
- Criar: `frontend/src/pages/auditor/index.test.tsx`

**Interfaces:**
- `useAuditStatus()` expõe `athos_monitor` e `retired` com defaults compatíveis para respostas antigas.
- A página exibe quatro blocos: resumo, monitor Athos, filtros do checklist e evidência.
- O filtro de ciclo de vida usa `active|retired`; checks aposentados não exibem executar ou remediar.

- [ ] **Passo 1: escrever testes de página falhando**
  - `rendersAthosMonitorAndSeparatesSchedulerFromCheckFailure` verifica monitor `healthy` com contador de checks falhos.
  - `rendersRetiredChecksWithoutRunActions` verifica o estado aposentado e ausência do botão de execução.
  - `rendersMonitorErrorAndRetryState` verifica erro de status sem quebrar o checklist carregado.
  - `usesPortugueseTranslationKeys` verifica título, ações e estados via namespace `auditor`.
- [ ] **Passo 2: executar os testes para confirmar a falha**
  - Rodar `cd frontend && npm test -- --run src/pages/auditor/index.test.tsx`.
  - Esperado: falha porque a página ainda não consome monitor, ciclo de vida ou i18n.
- [ ] **Passo 3: implementar o contrato do hook**
  - Adicionar schemas Zod para `athos_monitor` e `lifecycle_status`; manter defaults somente para campos opcionais de compatibilidade.
- [ ] **Passo 4: reorganizar a página**
  - Usar `useTranslation("auditor")` em todos os textos visíveis.
  - Adicionar cards de resumo e monitor, filtros por categoria/perfil/ciclo de vida e link `/crons` para o job Athos.
  - Manter execução, histórico, remediação e escalada existentes, condicionando ações a checks ativos.
- [ ] **Passo 5: completar traduções e acessibilidade**
  - Adicionar chaves equivalentes em `pt-BR` e `en`, labels/aria-labels para estados e ações.
- [ ] **Passo 6: executar testes e build**
  - Rodar `cd frontend && npm test -- --run src/pages/auditor/index.test.tsx` e `cd frontend && npm run build`.
- [ ] **Passo 7: commit**
  - `git add frontend/src/pages/auditor/index.tsx frontend/src/hooks/useAudit.ts frontend/src/i18n/locales/pt-BR/auditor.json frontend/src/i18n/locales/en/auditor.json frontend/src/pages/auditor/index.test.tsx`
  - `git commit -m "Auditor: show Athos monitoring and lifecycle state"`

### Tarefa 5: Renovação da tela Cron e estados de erro acionáveis

**Arquivos:**
- Modificar: `frontend/src/pages/crons/index.tsx`
- Modificar: `frontend/src/i18n/locales/pt-BR/crons.json`
- Modificar: `frontend/src/i18n/locales/en/crons.json`
- Criar: `frontend/src/pages/crons/index.test.tsx`

**Interfaces:**
- A tabela usa `script_state`, `is_audit_job` e `deprecated` do hook.
- A página mantém as mutações existentes e mostra erros inline, sem `window.alert`.
- O conteúdo de arquivo recebe somente `{ location: job.profile, name: job.script }`.

- [ ] **Passo 1: escrever testes de página falhando**
  - `rendersHealthSummaryAndAuditBadge` verifica contagens e identificação do job Athos.
  - `rendersMissingScriptAsBrokenWithoutCentralFallback` verifica diagnóstico e ausência de chamada para `central`.
  - `showsRunErrorInline` verifica erro de execução no DOM.
  - `opensDeleteConfirmationDialog` verifica uso do `ConfirmDialog`.
- [ ] **Passo 2: executar os testes para confirmar a falha**
  - Rodar `cd frontend && npm test -- --run src/pages/crons/index.test.tsx`.
  - Esperado: falha por textos, estado e fluxos atuais.
- [ ] **Passo 3: implementar o resumo e a tabela atualizada**
  - Usar `useTranslation("crons")`, cards para `ok/error/overdue/never_ran/off`, badge especial do job de auditoria e indicação de script quebrado/descontinuado.
  - Retirar candidatos e comentários de catálogo central.
- [ ] **Passo 4: trocar alertas nativos por estados da interface**
  - Controlar confirmação de exclusão com `ConfirmDialog` e mostrar erros de run/reset/update/delete em um aviso no card.
- [ ] **Passo 5: completar traduções e verificar comportamento**
  - Adicionar chaves nos dois idiomas e executar `cd frontend && npm test -- --run src/pages/crons/index.test.tsx && npm run build`.
- [ ] **Passo 6: commit**
  - `git add frontend/src/pages/crons/index.tsx frontend/src/i18n/locales/pt-BR/crons.json frontend/src/i18n/locales/en/crons.json frontend/src/pages/crons/index.test.tsx`
  - `git commit -m "Crons: surface operational health and retire legacy actions"`

### Tarefa 6: Correção operacional dos jobs Hermes do Athos

**Arquivos versionados:**
- Criar: `docs/runbooks/auditor-cron-recovery.md`
- Atualizar: `docs/PENDENCIAS.md` somente com evidência final e itens remanescentes

**Arquivos no host, fora do repositório:**
- `/root/.hermes/profiles/athos/scripts/daily_hermes_update_check.py`
- `/root/.hermes/profiles/athos/cron/jobs.json`
- runtime Hermes que atende o worker de cron

- [ ] **Passo 1: registrar um snapshot seguro do store**
  - Copiar `jobs.json` para um arquivo de backup fora do repositório, sem imprimir prompts, tokens ou destinos privados.
- [ ] **Passo 2: reparar o runtime Hermes pelo mecanismo suportado**
  - Executar `hermes pm repair` ou o procedimento equivalente indicado pelo próprio Hermes; confirmar que o mesmo runtime do scheduler importa `ruamel.yaml`.
- [ ] **Passo 3: tornar o relatório diário não destrutivo**
  - Alterar o script para que `doctor` e `update --check` sejam diagnósticos; o retorno será erro somente quando o próprio script não conseguir produzir o relatório.
  - Executar o script com `python3` e verificar código zero sem imprimir segredos.
- [ ] **Passo 4: remover o smoke test descontinuado**
  - Confirmar que `cron-worker-smoke-test` não é referenciado pelo verificador nem por outro job; remover usando o comando de cron suportado ou editar o store com lock atômico.
- [ ] **Passo 5: executar os três jobs de validação**
  - Rodar `foundation-clear`, `daily_hermes_update_check` e `ecosystem-weekly-audit` manualmente.
  - Confirmar `last_status=ok`, logs recentes e, no terceiro job, runs persistidos com `requested_by=cron`.
- [ ] **Passo 6: documentar evidência**
  - Registrar horário, job, código de saída e resultado resumido no runbook; omitir conteúdo de prompts e tokens.
- [ ] **Passo 7: commit**
  - `git add docs/runbooks/auditor-cron-recovery.md docs/PENDENCIAS.md`
  - `git commit -m "Ops: document Athos audit cron recovery"`

### Tarefa 7: Verificação integrada, deploy e entrega

**Arquivos:**
- Modificar somente se necessário: `docs/PENDENCIAS.md`, documentação de telas ou runbook

- [ ] **Passo 1: executar verificações backend**
  - `cd backend && .venv/bin/pytest app/tests/test_audit.py app/tests/test_audit_catalog.py app/tests/test_athos_audit_monitor.py app/tests/test_cron_operational_state.py -q`
  - `cd backend && .venv/bin/ruff check app`
- [ ] **Passo 2: executar verificações frontend**
  - `cd frontend && npm test -- --run src/pages/auditor/index.test.tsx src/pages/crons/index.test.tsx`
  - `cd frontend && npm run build`
- [ ] **Passo 3: conferir contrato implantado**
  - Verificar `GET /api/v1/audit/status`, `GET /api/v1/audit/checks` e `GET /api/v1/foundation/crons` com os campos novos.
  - Confirmar que `/api/v1/audit/run-internal` rejeita token inválido e aceita somente o token configurado.
- [ ] **Passo 4: executar o deploy**
  - `scripts/deploy.sh api web`
  - Acompanhar health checks e confirmar que backend e frontend estão servindo a mesma revisão.
- [ ] **Passo 5: smoke test funcional**
  - Abrir Auditor e confirmar cards de resumo, monitor Athos, filtros e histórico.
  - Abrir Crons e confirmar resumo, script quebrado sem fallback central e erro inline.
  - Executar um check manual não destrutivo e confirmar novo run `manual`.
- [ ] **Passo 6: revisão final do diff**
  - `git diff --check`, `git status --short --branch` e revisão de arquivos alterados para garantir ausência de segredo.
- [ ] **Passo 7: commit final e push**
  - Se houver alterações de verificação/documentação pendentes, `git add -A && git commit -m "Audit: finish cron and Athos monitoring"`.
  - `git push origin develop`.

