# M0.R — dossiê de preparação, 03/11/2026

**NÃO APTO PARA PUBLICAÇÃO:** revisão independente e aprovação de Marcelo pendentes; a sequência de parada e migrations requer decisão e revisão antes da ativação. Nenhuma publicação ou escrita em produção foi feita nesta preparação.

## Conteúdo exato

Base implantada informada: `027ee0e`; develop final: `afef230ebe71d7bdbba60e4e544db3fba5377182`; worktree de pacote: merge `8a712a4`, com backend, frontend, host-bridge e compose idênticos à develop. O backup foi tirado do banco em uso. O frontend em execução é `sha256:b9348ce8ca4bfcea9ef3c5885a8edafa821839aac4bba325083e7a502c238132`, embora `forgehub-frontend:latest` seja `sha256:4d3267d2338c7f0c361bf0758d37021c7ba19221c632747d4d01206bf3c7ae44`. O backend em execução é `sha256:497121be1132e3080e40123e5c8071b7b689a735f63000fc9ea3c3de0a80dc38`.

Destaques: `ae7de6d` corrige duplicação de contatos WhatsApp estrangeiros de 11 dígitos; `cde2b28` corrige o texto do botão “Manter dúvida”; M0.4 adiciona instruções versionadas e ensaio completo de missão. `MISSION_TOOLS_ENABLED` tem padrão false; a publicação não deve ligá-la. Confirme a configuração real no momento da publicação, sem divulgar segredos.

### Commits (`git log --oneline 027ee0e..afef230ebe71d7bdbba60e4e544db3fba5377182`)

```text
afef230 test(host-exec): order the stored task lookup; plan: T.4a done
896250a Merge feat/t4a-linux-target: isolated Linux SSH test target (T.4a)
43f5af6 test(bridge): install-key test follows the ForgeVault-only key design
118ca2f docs(plan): C.2a developed
7390b52 Tests: use seeded Linux targets
6c69241 Tests: add isolated Linux SSH target
15b06a3 docs(plan): M0.4 developed
9827810 Merge feat/m0-4-mission-rehearsal: M0 versioned instructions and full rehearsal (M0.4)
2b471f2 docs(missions): name DEPLOYED_WITHOUT_RELEASE in the executor steps
cde2b28 fix(operations): the question cancel dialog's dismiss reads "Manter dúvida"
ea3809d docs(plan): B0 runs at M0.R preparation with a fresh backup
00eb345 Missions: rehearse review and completion
6d702b2 docs(plan): C.2a and C.2.R to Dartan, Aramis reviews
156a40c Missions: rehearse dispatch and executor report
e815c41 Missions: rehearse planning through activation
5ee94fc Missions: exercise rehearsal document attachment
52a632a docs(plan): M0.3 done
ae7de6d fix(personal): one contact per foreign 11-digit WhatsApp number
0aa186c Missions: start M0 rehearsal
7fe30a9 docs(plan): technical work to Aramis/Dartan; Hermes keeps docs and simple tasks
8b597bc docs(plan): T.6 done; record the Software Factory group's current labels
41ebfff chore(vault): record the deployed per-profile ForgeHub Vault token helper
d83723b Merge main into develop: MESSAGES_EXTERNAL_MCP.md from the production release line
94ba5b4 Merge develop into main: test suite green, create_task fix, Onda 1 matrix
d7ce5d7 Merge fix/test-suite-green: backend suite green on the test database; create_task keyword call
3c7c2b4 test: whole backend suite green on the isolated test database
5388f49 fix(conversions): call create_task with keyword arguments
349cde9 Merge develop into main (via release/terminal-notes)
b318c99 docs(plano-integrado): record Onda 1 progress in the task matrix
c2bdfba Merge fix/ecosystem-scripts-no-secret: no production credential in registration scripts
ccaa748 Merge feat/m0-7-executions-screen + feat/m0-8-orchestrator-cycle: mission executions screen and orchestrator cycle (M0.7, M0.8)
4114e03 fix(scripts): no production credential in the ecosystem registration scripts
f214f5a fix(mission): M0.8 orchestrator owns failed mission tasks; finish cycle tests
43b89b7 feat(mission): orchestrator decision cycle through 24x7 Operations (Plano Integrado M0.8)
a6999a9 fix(mission): M0.7 action input inline, modal only confirms
e3cc84d feat(mission): minimal mission executions screen and environment releases (Plano Integrado M0.7)
a6952f0 Terminal: show controls and session name in workspace
10b7b83 Terminal: persist names and session notes
5422029 Auth: extend session to eight hours
f4a10d3 Messages: validate linked failure checks
dc01d46 Messages: preserve failed attempts with linked checks
cbb8014 feat(agents): autonomous_runs, dispatched runs without permission prompts
65cd068 Messages: include deployed migration ancestry
d580c96 Messages: load MCP for external runs on main
f436eed Merge develop into main
43d7674 Merge develop into main
d010d25 Merge pull request #2 from marcelodarckferreira/develop
5bd13ed Merge pull request #1 from marcelodarckferreira/develop
```

### Diff (`git diff --stat 027ee0e afef230ebe71d7bdbba60e4e544db3fba5377182`)

```text
 .gitignore                                         |    1 +
 CLAUDE.md                                          |    5 +-
 .../f2d7a4c9e1b6_m0_8_orchestrator_cycle.py        |  155 +++
 .../f3a9c6d1b8e2_m0_7_environment_releases.py      |   51 +
 backend/app/api/routes/agent_availability.py       |  112 +++
 backend/app/api/routes/demand.py                   |   17 +
 backend/app/api/routes/environment.py              |  130 +++
 backend/app/api/routes/mission.py                  |    4 +
 backend/app/api/routes/mission_board.py            |  144 +++
 backend/app/api/routes/mission_cycle.py            |  857 +++++++++++++++++
 backend/app/api/routes/mission_task.py             |   14 +-
 backend/app/api/routes/operations.py               |   28 +-
 backend/app/api/routes/personal_contacts.py        |   19 +-
 backend/app/api/routes/task.py                     |   20 +-
 backend/app/api/schemas/environment.py             |   36 +
 backend/app/api/schemas/mission_cycle.py           |  175 ++++
 backend/app/core/agent_availability.py             |  197 ++++
 backend/app/core/agent_questions.py                |   43 +
 backend/app/core/config.py                         |   11 +
 backend/app/core/conversions.py                    |    2 +-
 backend/app/core/demand_dispatch_guard.py          |    5 +
 backend/app/core/demand_failure_check.py           |   19 +
 backend/app/core/mission.py                        |   15 +-
 backend/app/core/mission_board.py                  | 1013 +++++++++++++++++++
 backend/app/core/mission_cycle.py                  |  883 +++++++++++++++++
 backend/app/core/test_integration_policy.py        |    9 +
 backend/app/db/models/__init__.py                  |    8 +
 backend/app/db/models/demand.py                    |    5 +
 backend/app/db/models/environment.py               |   56 ++
 backend/app/db/models/mission.py                   |    7 +
 backend/app/db/models/mission_cycle.py             |  166 ++++
 backend/app/db/models/operations.py                |    5 +
 backend/app/main.py                                |   41 +-
 backend/app/mcp/factory_server.py                  |   91 ++
 backend/app/scripts/seed_test_database.py          |    1 +
 backend/app/tests/conftest.py                      |   64 ++
 backend/app/tests/fixtures/integration_stub.py     |   42 +-
 backend/app/tests/test_agent_activity.py           |    9 +-
 backend/app/tests/test_audit_incidents.py          |   27 +-
 backend/app/tests/test_client_ops.py               |    7 +
 backend/app/tests/test_host_enrollment.py          |   12 +-
 backend/app/tests/test_host_execution.py           |    3 +-
 backend/app/tests/test_host_preparation.py         |   25 +-
 backend/app/tests/test_host_rotation.py            |  170 ++--
 backend/app/tests/test_mcp_catalog.py              |    7 +-
 backend/app/tests/test_mission_base.py             |    6 +
 backend/app/tests/test_mission_board.py            |  451 +++++++++
 backend/app/tests/test_mission_cycle.py            | 1014 ++++++++++++++++++++
 backend/app/tests/test_mission_mcp.py              |   18 +-
 backend/app/tests/test_mission_plan_approval.py    |   18 +-
 backend/app/tests/test_mission_planning_records.py |   11 +-
 backend/app/tests/test_mission_rehearsal_m0.py     |  264 +++++
 backend/app/tests/test_personal_contacts.py        |   22 +
 backend/app/tests/test_product.py                  |    8 +-
 backend/app/tests/test_project.py                  |    6 +-
 backend/app/tests/test_project_mcp.py              |   13 +-
 backend/app/tests/test_seed_test_database.py       |    6 +-
 backend/app/tests/test_software_factory_e2e.py     |   30 +-
 backend/app/tests/test_t4a_linux_target.py         |  189 ++++
 backend/app/tests/test_task_baseline_guard.py      |   21 +-
 backend/app/tests/test_task_governed_approval.py   |   52 +-
 backend/pytest.ini                                 |    1 +
 .../tests_unit/test_agent_availability_patterns.py |  110 +++
 .../test_direct_demand_origin_migration.py         |    8 +-
 .../tests_unit/test_personal_group_capture_api.py  |    3 +-
 .../test_personal_group_capture_migration.py       |    3 +-
 backend/tests_unit/test_test_integration_policy.py |    9 +
 docs/architecture/MESSAGES_EXTERNAL_MCP.md         |   13 +
 .../architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md |    4 +
 .../MISSION_ORCHESTRATOR_CYCLE_SPEC.md             |   10 +
 docs/missions/INSTRUCOES-M0.md                     |   39 +
 docs/plano-integrado/03-service-factory.md         |    2 +
 docs/plano-integrado/07-fases-de-implementacao.md  |   24 +-
 docs/plano-integrado/12-primeira-onda.md           |   30 +-
 docs/plano-integrado/T4a-alvo-linux.md             |   13 +
 docs/plano-integrado/onda1-tarefas.json            |  137 +--
 frontend/src/App.tsx                               |    4 +
 frontend/src/components/layout/navSections.ts      |    2 +
 frontend/src/components/missions/MissionAction.tsx |  132 +++
 .../components/missions/MissionConflictsBanner.tsx |   51 +
 .../missions/MissionEnvironmentsStrip.tsx          |   43 +
 .../components/missions/MissionExecutionsBoard.tsx |  166 ++++
 .../components/missions/MissionPlanningView.tsx    |  114 +++
 .../src/components/missions/MissionStateChip.tsx   |   43 +
 .../src/components/missions/MissionTaskDetail.tsx  |  133 +++
 .../src/components/missions/MissionTaskRow.tsx     |  149 +++
 .../src/components/missions/MissionTimeline.tsx    |   28 +
 frontend/src/components/missions/missionFormat.ts  |   44 +
 .../hooks/useMissionExecutionsViewModel.test.ts    |  108 +++
 .../src/hooks/useMissionExecutionsViewModel.ts     |  254 +++++
 frontend/src/hooks/useMissions.ts                  |  300 ++++++
 frontend/src/hooks/useProject.ts                   |    2 +
 frontend/src/i18n/locales/en/cockpit.json          |    2 +-
 frontend/src/i18n/locales/en/common.json           |    1 +
 frontend/src/i18n/locales/en/missions.json         |  209 ++++
 frontend/src/i18n/locales/en/operations.json       |    2 +-
 frontend/src/i18n/locales/es/cockpit.json          |    2 +-
 frontend/src/i18n/locales/es/common.json           |    1 +
 frontend/src/i18n/locales/es/missions.json         |  209 ++++
 frontend/src/i18n/locales/es/operations.json       |    2 +-
 frontend/src/i18n/locales/pt-BR/cockpit.json       |    2 +-
 frontend/src/i18n/locales/pt-BR/common.json        |    1 +
 frontend/src/i18n/locales/pt-BR/missions.json      |  209 ++++
 frontend/src/i18n/locales/pt-BR/operations.json    |    2 +-
 frontend/src/pages/cockpit/index.tsx               |    9 +
 frontend/src/pages/missions/[id].test.tsx          |  197 ++++
 frontend/src/pages/missions/[id].tsx               |   35 +
 frontend/src/pages/missions/index.test.tsx         |   53 +
 frontend/src/pages/missions/index.tsx              |  126 +++
 frontend/src/pages/operations/index.tsx            |    2 +-
 frontend/src/test/fixtures/missionBoard.ts         |   66 ++
 host-bridge/tests/test_server_key_install.py       |    9 +-
 scripts/forgehub_vault_token.py                    |    2 +-
 scripts/link_agents_to_systems.py                  |    7 +-
 scripts/migrate_forgehub_vault_profiles.py         |  148 +++
 scripts/register_ecosystem_systems.py              |    7 +-
 .../tests/test_migrate_forgehub_vault_profiles.py  |   45 +
 scripts/validate-integrated-plan.py                |    3 +-
 test-env/docker-compose.yml                        |   19 +
 test-env/gateway-nginx.conf                        |    4 +
 test-env/init-env.sh                               |    8 +
 test-env/linux-target/.dockerignore                |    1 +
 test-env/linux-target/Dockerfile                   |    6 +
 123 files changed, 9882 insertions(+), 326 deletions(-)
```

### Migrations ensaiadas

- `a6d1c3e8f402`: aceita status de tarefa `in_review`.
- `b9e4d2a7c615`: itens imutáveis de baseline e ambientes alvo de execução.
- `d3f7a1c9e2b5`: recibos de idempotência de comandos de agentes.
- `c5a8e2f71d04`: registros de planejamento de missões.
- `e8c4b2d9a7f1`: aprovação governada de plano, dependências únicas e skills.
- `b9f246c18a73`: merge das linhagens de terminal e planejamento.
- `f3a9c6d1b8e2`: publicações por ambiente M0.7.
- `f2d7a4c9e1b6`: ciclo de orquestração M0.8.

## Evidências e limites

Dump `/root/backup/forgehub-m0r-2026-11-03/forgehub.dump`: SHA-256 `18312d9bcd75806ff2765f8407705a568804e6cade5aca68082165fe5a6043f9`; diretório 700, dump 600. Revisão inicial `a4d238b759c1`. Restauração `pg_restore --no-owner --exit-on-error` em rede interna isolada: 2,464 s (após uma tentativa prematura durante a inicialização falhar com socket indisponível); upgrade: 3,161 s, `f2d7a4c9e1b6 (head)`. Tempos de comandos, sem preparo de infraestrutura; não representam RTO total.

`rowcounts-prod.txt` e `rowcounts-restore.txt` no diretório do backup contêm estimativas estatísticas, frequentemente diferentes. As contagens exatas das 10 maiores segundo a estatística de produção estão nos arquivos `rowcounts-exact-prod-top10.txt` e `rowcounts-exact-restore-top10.txt`: 9 bateram; `personal_contact_messages` era 2727 na produção consultada depois do dump e 2724 na cópia. Marcelo confirmou 2724 linhas com `created_at < 2026-11-03 11:22:53-03`, início do dump; outras quatro chegaram depois por WhatsApp. A cópia coincide com o snapshot: validação concluída. A consulta anterior de 2727 ocorreu antes da chegada de todas as quatro.

Smoke na cópia migrada, sem workers e só em rede interna: `/health` retornou `{"status":"ok"}`; SELECT `id, target_environment` em `company.project_tasks` retornou uma linha; `run_task_failure_pass` executou uma vez sem erro. A função captura exceções individuais de notificação internamente, portanto saída sem erro não prova que toda notificação possível funcionaria. Não houve integração externa.

`alembic downgrade a4d238b759c1`: exit 0, 2,789 s, mas deixou **duas** heads `a4d238b759c1` e `e8c4b2d9a7f1` por causa do merge; não reverteu as migrations da outra linhagem. Não se exercitou a recusa de `b9e4d2a7c615` por missão ativa. Rollback principal: restauração do dump numa segunda base, 2,864 s, revisão `a4d238b759c1`; não é RTO completo. Containers e rede de quarentena removidos, imagem de ensaio preservada.

## Pacote revisado na rodada 4

`/root/.forgehub/releases/m0r-afef230/`: cópia do bridge da worktree, overrides, scripts e `release.json`. Imagens reconstruídas com cache: `forgehub-backend:m0r-afef230` (3,294 s; `sha256:89163dd70794b2619d255f63330878c3a92d94260f829934661a2f9258317256`) e `forgehub-frontend:m0r-afef230` (2,009 s; `sha256:af69998f2de43d730236ba7ac28d2162393e31b6051957cab7ebe2d5967b6a2b`). Tempos de relógio desta execução, não previsões para build sem cache. Teste do bridge: 123 passaram em 16,26 s. Backend essencial: 30 passaram em 26,97 s, com duas advertências de descontinuação; executado com o ambiente isolado de teste carregado após inicializar as referências de segurança. `bash -n` passou.

SHA-256: `activate.sh` `6ac086ff9489f8d0fa7aa312caaef9655626392aeace7598f655775f66a491ae`; `rollback.sh` `da5be23512a08413b3850f57f923f510cc33c34d452eabc582541086cbee4f11`.

O dump das 11:22, usado no ensaio de restauração, continua conferido por `sha256sum -c`. A ativação cria sempre um novo dump verificado após parar o backend e registra seu caminho em `backup-path.txt`. A proteção de falha reinicia o backend anterior caso a migration não termine. O smoke exige leitura autenticada da API e frontend com HTTP 200, além das verificações existentes.

Em DRY_RUN despachos em voo produzem aviso e o ensaio continua; em execução real continuam impedindo a operação. O rollback seco usa o dump conhecido quando ainda não existe o ponteiro de uma ativação real; execução real continua exigindo o ponteiro e `CONFIRM_RESTORE=yes`.

### Ensaio completo de ativação (stdout e stderr)

```text
dispatches=1
WARN: 1 dispatch(es) in flight — a real activation would abort here
/root/backup/forgehub-m0r-2026-11-03/forgehub.dump: OK
image available: 497121be1132
image available: b9348ce8ca4b
image available: forgehub-backend:m0r-afef230
image available: forgehub-frontend:m0r-afef230
DRY_RUN: docker tag 497121be1132 forgehub-backend:pre-m0r
DRY_RUN: docker tag b9348ce8ca4b forgehub-frontend:pre-m0r
DRY_RUN: docker compose -p forgehub stop forgehub-backend
DRY_RUN: create fresh custom pg_dump and SHA256SUMS in /root/backup/forgehub-pre-m0r-20261103-115518
DRY_RUN: record rollback dump /root/backup/forgehub-pre-m0r-20261103-115518/forgehub.dump in /root/.forgehub/releases/m0r-afef230/backup-path.txt
version before:
a4d238b759c1
DRY_RUN: POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5433 alembic upgrade head
DRY_RUN: show version after migration
DRY_RUN: docker compose -p forgehub -f docker-compose.yml -f /root/.forgehub/releases/m0r-afef230/compose.override.yml up -d --no-build forgehub-backend forgehub-frontend
DRY_RUN: wait for and check /health
DRY_RUN: /usr/bin/python3 /root/.hermes/scripts/forgehub_vault_token.py athos /bin/sh -c 'curl -fsS -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $FORGEHUB_AGENT_TOKEN" "http://127.0.0.1:8000/api/v1/tasks?limit=1"' (expect 200)
DRY_RUN: curl -fsS -o /dev/null -w "%{http_code}" http://127.0.0.1:4173/ (expect 200)
DRY_RUN: write systemd drop-in WorkingDirectory=/root/.forgehub/releases/m0r-afef230/host-bridge
DRY_RUN: systemctl daemon-reload
DRY_RUN: systemctl restart forgehub-chat-bridge
DRY_RUN: check bridge evidence endpoint with systemd token (secret withheld)
DRY_RUN: wait 900 seconds; verify Task failure poll failed count is 0
DRY_RUN: verify database version f2d7a4c9e1b6
DRY_RUN: write /root/.forgehub/releases/m0r-afef230/activated-at.txt
```

### Ensaio completo de rollback (stdout e stderr)

```text
dispatches=1
WARN: 1 dispatch(es) in flight — a real activation would abort here
DRY_RUN: activation backup pointer absent; rehearsing with /root/backup/forgehub-m0r-2026-11-03/forgehub.dump
/root/backup/forgehub-m0r-2026-11-03/forgehub.dump: OK
DRY_RUN: docker compose -p forgehub -f docker-compose.yml -f /root/.forgehub/releases/m0r-afef230/rollback.override.yml stop forgehub-backend forgehub-frontend
DRY_RUN: pg_restore --clean --if-exists --no-owner --exit-on-error from /root/backup/forgehub-m0r-2026-11-03/forgehub.dump into production forgehub
DRY_RUN: docker compose -p forgehub -f docker-compose.yml -f /root/.forgehub/releases/m0r-afef230/rollback.override.yml up -d --no-build forgehub-backend forgehub-frontend
DRY_RUN: write systemd drop-in WorkingDirectory=/root/.forgehub/releases/autonomy-e043f37/host-bridge
DRY_RUN: systemctl daemon-reload
DRY_RUN: systemctl restart forgehub-chat-bridge
DRY_RUN: wait for and check /health
```

### Janela e ponto pendente

O upgrade isolado medido levou 3,161 s. A janela requerida é parada do backend + ~3,161 s de migrations + subida/health do backend e frontend + reinício do bridge; esses demais tempos não foram medidos, portanto não há estimativa numérica confiável do total. O monitoramento posterior aguarda 900 s adicionais; builds são prévios à janela. O backend é parado antes do novo dump e da migration; o frontend permanece no ar sem API até a subida e o health. Não presumir que os ~3 s sejam indisponibilidade total. O rollback restaura o dump e perde gravações posteriores: coordenar e parar todos os escritores; o downgrade não é rollback.

### Itens para aprovação de Marcelo, após revisão independente

1. Commit `afef230ebe71d7bdbba60e4e544db3fba5377182`, imagens e hashes dos scripts acima, após revisão independente do pacote revisado.
2. Janela coordenada, ausência de despachos em voo e backup novo e verificado após parar o backend.
3. Aplicação das oito migrations em produção e troca das imagens de backend e frontend, conforme sequência revisada.
4. Alteração do drop-in e reinício do bridge, verificação de saúde e monitoramento de 900 s; não habilitar `MISSION_TOOLS_ENABLED`.
5. Plano de contingência por restauração do dump, com todos os escritores parados e perda das gravações posteriores ao snapshot reconhecida; a restauração exige confirmação explícita no momento (`CONFIRM_RESTORE=yes`).

Revisão independente e autorização de Marcelo permanecem pendentes. Nenhuma ativação real foi executada.
