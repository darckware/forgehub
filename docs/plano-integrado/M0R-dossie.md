# M0.R — dossiê de preparação, 03/11/2026

**NÃO APTO PARA PUBLICAÇÃO:** revisão de Dartan e aprovação de Marcelo pendentes; o bridge em execução usa código antigo sem a rota e o critério de contagem não passou. Nenhuma publicação ou escrita em produção foi feita nesta preparação. Este roteiro é proposta incompleta: fechar os bloqueios e obter aprovação ao conteúdo exato antes de executar.

## Conteúdo exato

Base implantada informada: `027ee0e`; develop e worktree ensaiados: `15b06a33439e8e76fbce68b1300ff4c6cf424db4`. O backup foi tirado do banco em uso. O frontend em execução é `sha256:b9348ce8ca4bfcea9ef3c5885a8edafa821839aac4bba325083e7a502c238132`, embora `forgehub-frontend:latest` seja `sha256:4d3267d2338c7f0c361bf0758d37021c7ba19221c632747d4d01206bf3c7ae44`. O backend em execução é `sha256:497121be1132e3080e40123e5c8071b7b689a735f63000fc9ea3c3de0a80dc38`.

Destaques: `ae7de6d` corrige duplicação de contatos WhatsApp estrangeiros de 11 dígitos; `cde2b28` corrige o texto do botão “Manter dúvida”; M0.4 adiciona instruções versionadas e ensaio completo de missão. `MISSION_TOOLS_ENABLED` tem padrão false; a publicação não deve ligá-la. Confirme a configuração real no momento da publicação, sem divulgar segredos.

### Commits (`git log --oneline 027ee0e..develop`)

```text
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

### Diff (`git diff --stat 027ee0e develop`)

```text
 CLAUDE.md                                          |    2 +-
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
 backend/app/core/config.py                         |    6 +
 backend/app/core/conversions.py                    |    2 +-
 backend/app/core/demand_dispatch_guard.py          |    5 +
 backend/app/core/demand_failure_check.py           |   19 +
 backend/app/core/mission.py                        |   15 +-
 backend/app/core/mission_board.py                  | 1013 +++++++++++++++++++
 backend/app/core/mission_cycle.py                  |  883 +++++++++++++++++
 backend/app/db/models/__init__.py                  |    8 +
 backend/app/db/models/demand.py                    |    5 +
 backend/app/db/models/environment.py               |   56 ++
 backend/app/db/models/mission.py                   |    7 +
 backend/app/db/models/mission_cycle.py             |  166 ++++
 backend/app/db/models/operations.py                |    5 +
 backend/app/main.py                                |   41 +-
 backend/app/mcp/factory_server.py                  |   91 ++
 backend/app/tests/conftest.py                      |   64 ++
 backend/app/tests/test_agent_activity.py           |    9 +-
 backend/app/tests/test_audit_incidents.py          |   27 +-
 backend/app/tests/test_client_ops.py               |    7 +
 backend/app/tests/test_host_enrollment.py          |   12 +-
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
 backend/app/tests/test_software_factory_e2e.py     |   30 +-
 backend/app/tests/test_task_baseline_guard.py      |   21 +-
 backend/app/tests/test_task_governed_approval.py   |   52 +-
 backend/pytest.ini                                 |    1 +
 .../tests_unit/test_agent_availability_patterns.py |  110 +++
 .../test_direct_demand_origin_migration.py         |    8 +-
 .../tests_unit/test_personal_group_capture_api.py  |    3 +-
 .../test_personal_group_capture_migration.py       |    3 +-
 docs/architecture/MESSAGES_EXTERNAL_MCP.md         |   13 +
 .../architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md |    4 +
 .../MISSION_ORCHESTRATOR_CYCLE_SPEC.md             |   10 +
 docs/missions/INSTRUCOES-M0.md                     |   39 +
 docs/plano-integrado/03-service-factory.md         |    2 +
 docs/plano-integrado/07-fases-de-implementacao.md  |   24 +-
 docs/plano-integrado/12-primeira-onda.md           |   30 +-
 docs/plano-integrado/onda1-tarefas.json            |  133 +--
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
 scripts/forgehub_vault_token.py                    |    2 +-
 scripts/link_agents_to_systems.py                  |    7 +-
 scripts/migrate_forgehub_vault_profiles.py         |  148 +++
 scripts/register_ecosystem_systems.py              |    7 +-
 .../tests/test_migrate_forgehub_vault_profiles.py  |   45 +
 scripts/validate-integrated-plan.py                |    3 +-
 108 files changed, 9564 insertions(+), 312 deletions(-)
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

`rowcounts-prod.txt` e `rowcounts-restore.txt` no diretório do backup contêm estimativas estatísticas, frequentemente diferentes. As contagens exatas das 10 maiores segundo a estatística de produção estão nos arquivos `rowcounts-exact-prod-top10.txt` e `rowcounts-exact-restore-top10.txt`: 9 bateram; `personal_contact_messages` era 2727 na produção consultada depois do dump e 2724 na cópia. Atividade concorrente pode explicar, mas isso não comprova igualdade no instante do snapshot. Critério solicitado **falhou**; investigar e repetir validação com snapshot consistente antes da aprovação.

Smoke na cópia migrada, sem workers e só em rede interna: `/health` retornou `{"status":"ok"}`; SELECT `id, target_environment` em `company.project_tasks` retornou uma linha; `run_task_failure_pass` executou uma vez sem erro. A função captura exceções individuais de notificação internamente, portanto saída sem erro não prova que toda notificação possível funcionaria. Não houve integração externa.

`alembic downgrade a4d238b759c1`: exit 0, 2,789 s, mas deixou **duas** heads `a4d238b759c1` e `e8c4b2d9a7f1` por causa do merge; não reverteu as migrations da outra linhagem. Não se exercitou a recusa de `b9e4d2a7c615` por missão ativa. Rollback principal: restauração do dump numa segunda base, 2,864 s, revisão `a4d238b759c1`; não é RTO completo. Containers e rede de quarentena removidos, imagem de ensaio preservada.

## Bloqueio do bridge e roteiro proposto

Em 03/11 o serviço estava ativo, mas `POST /v1/evidence/verify` retornou 404. `systemctl show` revelou `WorkingDirectory=/root/.forgehub/releases/autonomy-e043f37/host-bridge`; seu `app.py` não contém o router de evidence. Reiniciar o serviço como está não carrega o código da worktree. É necessário planejar e revisar a publicação da versão correta do bridge e seu rollback, inclusive preservação dos processos, antes de uma sequência exata poder ser aprovada. Não executar os comandos seguintes enquanto isso não estiver resolvido. Alterações subsequentes exigem nova revisão e aprovação do conteúdo exato.

Após resolver o bloqueio, validar que a árvore usada para build continua no hash aprovado, não contém alterações e que o backup validado é adequado à janela. O snapshot envelhece: restaurá-lo perde gravações posteriores. Coordenar suspensão de todos os escritores, inclusive workers externos, antes de qualquer restauração. A sequência abaixo é um esqueleto de publicação, não uma autorização:

```bash
cd /root/project/forgehub
[ "$(git rev-parse HEAD)" = 15b06a33439e8e76fbce68b1300ff4c6cf424db4 ] && test -z "$(git status --porcelain)"
sha256sum -c /root/backup/forgehub-m0r-2026-11-03/SHA256SUMS
docker tag forgehub-backend:latest forgehub-backend:pre-m0r-2026-11-03
docker tag sha256:b9348ce8ca4bfcea9ef3c5885a8edafa821839aac4bba325083e7a502c238132 forgehub-frontend:pre-m0r-2026-11-03
# BLOQUEIO: publicar e validar o código correto do bridge conforme procedimento ainda não definido.
systemctl restart forgehub-chat-bridge
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8910/v1/evidence/verify)
[ "$code" != 404 ] && [ "$code" != 000 ] || { echo 'Bridge indisponível ou rota ausente'; exit 1; }
docker compose build forgehub-backend forgehub-frontend
docker compose run --rm --no-deps -e BACKGROUND_WORKERS_ENABLED=false forgehub-backend alembic current
docker compose run --rm --no-deps -e BACKGROUND_WORKERS_ENABLED=false forgehub-backend alembic upgrade head
docker compose run --rm --no-deps -e BACKGROUND_WORKERS_ENABLED=false forgehub-backend alembic current
docker compose up -d --build forgehub-backend forgehub-frontend
curl -fsS http://127.0.0.1:8000/health
# Com JWT de administrador obtido pelo operador e sem expô-lo em logs:
curl -fsS -H "Authorization: Bearer $FORGEHUB_SMOKE_JWT" http://127.0.0.1:8000/api/v1/tasks > /dev/null
curl -fsS -H "Authorization: Bearer $FORGEHUB_SMOKE_JWT" http://127.0.0.1:8000/api/v1/demands > /dev/null
docker logs --since 35m forgehub-backend 2>&1 | grep -F 'Task failure poll failed' || true
```

O `!=404` é apenas teste de presença de rota; fazer também POST autenticado válido com credencial do bridge, verificar resposta sem revelar token, abrir a tela de tarefas e Messages autenticado, e observar pelo menos um ciclo de 30 minutos sem falha. O comando de logs acima é ponto de partida, não prova imediata de ausência futura. Confirmar tags pelo ID em execução imediatamente antes de marcar; `latest` pode ter mudado. Parar se qualquer pré-condição falhar.

## Rollback proposto — requer procedimento operacional revisado

Downgrade ensaiado não é reversão completa; restauração do dump é o rollback principal e perde alterações após seu snapshot. Antes de qualquer comando: parar todos os escritores e sessões da base, verificar checksum, obter aprovação expressa para perda de dados e confirmar usuários/conexões e dependências. A restauração completa destrói a base existente. O procedimento abaixo é ilustrativo e precisa ser validado para os consumidores e privilégios reais antes de aprovação:

```bash
cd /root/project/forgehub
sha256sum -c /root/backup/forgehub-m0r-2026-11-03/SHA256SUMS
docker compose stop forgehub-frontend forgehub-backend
# Após parar TODOS os demais escritores; opcional, pode falhar ou deixar duas heads:
docker compose run --rm --no-deps -e BACKGROUND_WORKERS_ENABLED=false forgehub-backend alembic downgrade a4d238b759c1
# Com conexões encerradas e aprovação de perda de dados:
docker exec forgehub_postgres dropdb -U foundation --if-exists forgehub
docker exec forgehub_postgres createdb -U foundation forgehub
docker exec -i forgehub_postgres pg_restore -U foundation --no-owner --exit-on-error -d forgehub < /root/backup/forgehub-m0r-2026-11-03/forgehub.dump
docker exec forgehub_postgres psql -U foundation -d forgehub -Atc 'select version_num from company.alembic_version'
docker tag forgehub-backend:pre-m0r-2026-11-03 forgehub-backend:latest
docker tag forgehub-frontend:pre-m0r-2026-11-03 forgehub-frontend:latest
docker compose up -d --no-build forgehub-backend forgehub-frontend
```

Se downgrade falhar, seguir para restauração somente após verificar o estado e a autorização; não presumir que falha signifique ausência de alterações. Rollback do bridge depende do procedimento ainda não definido. Validar saúde, login e fluxos após restaurar.

## Janela e riscos

Não há estimativa confiável de indisponibilidade: a soma das medições não inclui preparo, parada de escritores, build, bridge, deploy, validação e tráfego concorrente. Planejar janela após ensaio completo do procedimento corrigido. O backend antigo já apresenta falhas de leitura de tarefas até a migração; migração e troca de imagem não são atômicas. Backup e contagens foram medidos com produção ativa; há risco de perda de dados entre snapshot e eventual rollback. Builds `--build` podem não ser reproduzíveis por dependências externas; fixar e aprovar artefatos antes de produção.
