# M0 — Minimal mission executions screen

**Status:** proposed (M0.SPEC). Decided by Marcelo on 2026-10-29 (`09-lacunas-e-decisoes.md`):
anticipated from M.1 because running Onda 1 through ad-hoc messages and monitors left the
orchestrator unable to manage executions. Part of [MCP_MISSION_TOOLS_SPEC.md](MCP_MISSION_TOOLS_SPEC.md);
labels **[EXISTS file:line]** / **[PROPOSED]** / **[EXTEND]** as defined there (§0.1). Proposed slice:
M0.7 (open decision D-M0-1).

The screen **shows and routes actions**; it decides nothing by itself (04 "Regras do pipeline" 5).
Every button calls an existing guarded route or a proposed route that reuses the same guards — there
is no screen-only shortcut.

## 1. Questions the screen must answer (the seven points)

| # | Question | Where on screen | Data source |
|---|---|---|---|
| 1 | Which tasks exist, in what order, what each depends on | Task list ordered topologically, dependency chips; "Grafo" toggle | `project_tasks`, `task_dependencies` [backend/app/db/models/task.py:61,189] via §3.2 |
| 2 | Who executes and who reviews each; author = reviewer block visible | Executor and Reviewer columns; red "Revisor = executor" badge and disabled review action | assignment → membership [backend/app/db/models/task.py:225], designated reviewer, `TaskExecutionReview` [backend/app/db/models/orchestration.py:216] |
| 3 | State of each execution (queued, running for how long and until when, awaiting review, refused, done-proven, uncertain) | State column with elapsed/deadline | `AgentDemand` (`scheduled_at`, `dispatched_at`, `dispatch_deadline_at`, `dispatch_status`, `agent_run_id`) [backend/app/db/models/demand.py:381,434,426,395], `TaskExecution.status` [backend/app/db/models/task.py:316], review status |
| 4 | Evidence delivered (commit, file, test, message) and whether verified by someone other than the executor | Evidence cell: each ref with verification icon and "verificado por" | `TaskExecution.evidence_ref` + `verify_evidence` result [backend/app/core/task_evidence.py:140], review `evidence_ref`/reviewer |
| 5 | Conflicts between executions (same worktree/branch/production target; publishing a branch that does not contain production) | Conflict banner at top + row badges | §5 |
| 6 | What is published in each environment (test/production) and from which commit | Environments strip | `environment_releases` [PROPOSED] §6 |
| 7 | Actions allowed to the orchestrator and to Marcelo (dispatch, request review, refuse with reason, accept) through existing routes and guards | Row action menu + mission header actions, driven by backend-computed `allowed_actions`/`blocked_actions` | §7 |

## 2. Placement and navigation

- Route **`/missions`** (list) and **`/missions/:projectId`** (detail, tab "Execuções") [PROPOSED,
  frontend]. M.1 later adds tabs to the same route (brief, criteria, critiques, dossier) — no second
  screen (M0.SPEC §10).
- Sidebar: Software Factory section, entry "Missões" after Cockpit (`navSections.ts`
  [EXISTS frontend/src/components/layout/navSections.ts:91 for Cockpit]), gated by module `product`
  like the Cockpit; also reachable from Cmd/Ctrl+K (same `NAV_SECTIONS`).
- Cockpit product → project row links to `/missions/:projectId` when `project_type='mission'`.

## 3. Backend routes

### 3.1 Reused as-is

| Purpose | Route |
|---|---|
| Live state of each executor (executing/thinking/waiting/idle) | `GET /api/v1/agent-activity/stream` (SSE) [EXISTS backend/app/api/routes/agent_activity.py:250]; fallback `GET /api/v1/agent-activity?project_id=` [:179] |
| Message history of one execution | `GET /api/v1/demands/{id}/history` [EXISTS backend/app/api/routes/demand.py:1199] |
| Operator decisions on the underlying message (investigate/confirm inactive/authorize retry/archive) | `POST /api/v1/demands/{id}/decision` [EXISTS backend/app/api/routes/demand.py:1190] |
| Dispatch status detail | `GET /api/v1/demands/{id}/dispatch-status` [EXISTS backend/app/api/routes/demand.py:2369] |
| Reviews of an execution | `GET /api/v1/orchestration/executions/{id}/reviews` [EXISTS backend/app/api/routes/orchestration.py:481] |
| Review decision by the reviewer agent | `PATCH /api/v1/orchestration/reviews/{id}` [EXISTS backend/app/api/routes/orchestration.py:496] (with M0.6a fixes) |
| Plan/acceptance decisions by Marcelo | `POST /api/v1/governed/approval-requests/{id}:decide` [EXISTS backend/app/api/routes/governed_approval.py:64] (+ M0 branches) |
| Mission audit trail | `GET /api/v1/governance/audit-events?...` [EXISTS backend/app/api/routes/governance.py:234] |

`GET /api/v1/demands/agent-work` [EXISTS backend/app/api/routes/demand.py:843] is the agent-centric queue (Pessoal → Tarefas
dos agentes). It is **reused for its logic, not its shape**: the mission board calls
`work_item()`/`allowed_actions` from `core/demand_management.py` [EXISTS :55,113] for the demand part
of each row, so the action availability for a message is computed in one place. The board needs a
task-centric, mission-scoped aggregate the agent-work list cannot express (dependencies, reviews,
evidence, conflicts, environments), hence §3.2.

### 3.2 Proposed

| Route | Returns | Auth |
|---|---|---|
| `GET /api/v1/missions?state=&orchestrator_id=&agent_id=&has_conflicts=&q=&page=&page_size=` | mission summaries (§8) | `demands.view` (`authorize_action` [backend/app/core/deps.py:59]); agent `agt_` sees only missions where it is a member |
| `GET /api/v1/missions/{project_id}/executions` | the board (§4) | same; non-member agent → 404 |
| `GET /api/v1/missions/{project_id}/timeline?before=&limit=` | decisions and transitions (AuditEvent `entity_type in (mission, project_task, task_execution)` for the mission's tasks) | same |
| `GET /api/v1/missions/{project_id}/stream` | SSE, pushes the board snapshot ~0.3 s after a change to any of its tasks/demands/reviews and every 15 s; same in-process broadcaster pattern as `core/agent_activity_stream.py` | same |
| action routes | §7 | per action |

Board response (abridged):

```json
{
  "mission": {"project_id": "…", "name": "…", "state": "active", "priority": 50,
              "orchestrator": {"id": "…", "name": "Athos"}, "deadline_at": "…", "paused": false,
              "baseline": {"id": "…", "content_hash": "…", "approved_at": "…"},
              "allowed_actions": ["pause"], "blocked_actions": [{"action": "accept", "reason": "AC-2 open"}]},
  "tasks": [{
    "task_id": "…", "number": 9001, "title": "…", "topo_index": 0,
    "depends_on": [{"task_id": "…", "number": 9000, "status": "done"}],
    "executor": {"agent_id": "…", "name": "Porthus", "live": "executing"},
    "reviewer": {"agent_id": "…", "name": "Dartan"},
    "reviewer_is_executor": false,
    "execution_state": "running",
    "execution": {"execution_id": "…", "attempt": 2, "demand_id": "…", "demand_number": 41634,
                  "agent_run_id": "…", "dispatched_at": "…", "deadline_at": "…", "scheduled_at": null,
                  "elapsed_seconds": 1260},
    "evidence": [{"ref": "git:abc123", "verified": true, "verified_by": "evidence-check",
                  "reviewed_by": {"name": "Dartan", "status": "approved"}}],
    "baseline_status": "current",
    "targets": [{"kind": "worktree", "key": "/root/project/forgehub/.claude/worktrees/m0-spec"}],
    "conflicts": ["C-1"],
    "allowed_actions": ["request_review"], "blocked_actions": [{"action": "dispatch", "reason": "TARGET_BUSY"}]
  }],
  "conflicts": [{"id": "C-1", "kind": "same_worktree", "tasks": [9001, 9003], "severity": "blocking", "detail": "…"}],
  "environments": [{"environment": "production", "target": "forgehub", "commit_sha": "…", "branch": "…",
                    "released_at": "…", "released_by": "Hephaestus", "task_number": 9007, "source": "recorded"}],
  "generated_at": "…"
}
```

`allowed_actions`/`blocked_actions` are computed by the backend for the **caller** (Marcelo vs
orchestrator agent vs other) by dry-running the same guard functions the action routes call
(`assert_task_baseline_current`, completion guard, `reserve_dispatch` admission checks without taking
the lock). The UI never re-derives eligibility.

## 4. Execution state model (one value per task, computed server-side)

Precedence top-down — the first matching rule wins:

| State (`execution_state`) | pt-BR label | Rule | Shows |
|---|---|---|---|
| `cancelled` | Cancelada | task `cancelled` | reason |
| `done_proven` | Concluída comprovada | task done/deployed **and** latest execution `verified` **and** approved review by reviewer ≠ executor | evidence + reviewer |
| `done_historical` | Concluída sem prova (histórica) | task done/deployed without the above (pre-M0.6a) | grey; never counted as proof for a criterion |
| `uncertain` | Incerta | demand `requires_reconciliation` [backend/app/core/demand_workflow.py:24] | run id, "investigar / confirmar inativa" (Marcelo) |
| `running` | Rodando | demand `dispatched`/`running` | elapsed since `dispatched_at`, deadline `dispatch_deadline_at`; amber at 80 % of deadline, red past it |
| `queued` | Na fila | demand with `scheduled_at <= now`, not dispatched; reason from last admission refusal (`capacity`, `agent_busy`, `TARGET_BUSY`, `dependencies`, `baseline`, `mission_paused`) | reason chip |
| `scheduled` | Agendada | `scheduled_at > now` | time + the decision that scheduled it (cycle spec) |
| `changes_requested` | Recusada / devolvida | latest review `changes_requested` or `rejected`, or task returned (`mission_task_returned`) | reason |
| `awaiting_review` | Aguardando revisão | latest execution `verified`, no decided review (pending review shows reviewer) | reviewer, waiting time |
| `evidence_failed` | Prova recusada | latest execution `failed` by evidence verification | which ref failed |
| `reported` | Relatada (verificando prova) | latest execution `reported` | evidence list |
| `failed` | Falhou | demand `failed` with known error | error, attempts `n/retry_limit` |
| `blocked` | Bloqueada | task `blocked` or dependency not done | blocking tasks |
| `ready` | Pronta | dependencies done, baseline current, assigned, not dispatched | — |
| `not_ready` | Não pronta | otherwise (unassigned, no baseline, waiting dependencies) | what is missing |

Timer source of truth is the server (`elapsed_seconds` at `generated_at`); the client only advances
it locally between snapshots.

## 5. Conflict detection

Computed on every board build (and across **all** active missions plus non-mission in-flight demands,
since the 28/10 incident involved work outside any mission):

| Kind | Detected when | Severity |
|---|---|---|
| `same_worktree` | two in-flight/queued items whose normalized `working_path`/`worktree` target is equal | blocking (serialized by `reserve_dispatch` for mission tasks, §4.3 of the main spec) |
| `same_branch` | two items declare the same `branch:` target | blocking |
| `same_publish_target` | two items declare the same `publish:<env>:<target>` | blocking |
| `publish_missing_production` | a task declaring `publish:production:<target>` has a candidate commit (from its evidence `git:` or declared branch head) that does **not** contain the last recorded production commit for that target (`git merge-base --is-ancestor <prod_sha> <candidate>` run through the host-bridge `/v1/exec` [EXISTS, already called by backend/app/api/routes/system_control.py:181]) | blocking for dispatch of that task; shown red |
| `production_unknown` | a `publish:production:*` target has no `environment_releases` row | warning: "produção sem registro — não é possível verificar" (never inferred) |
| `reviewer_is_executor` | §4 rule 2 | blocking for review/accept |
| `delegation_revoked_during_run` | a run is in flight but the actor's delegation was revoked | warning |

A git check that cannot run (bridge down, repo missing) yields `unknown`, never "no conflict".

## 6. Environments strip [PROPOSED table `environment_releases`]

| Column | Note |
|---|---|
| id, environment (`test`,`production` CHECK), target (e.g. `forgehub`), commit_sha (40 hex), branch, released_at, released_by (principal name), task_id (nullable FK), evidence_ref, source (`recorded`,`imported`) | `UNIQUE(environment, target, released_at)` |

Written by `POST /api/v1/environments/releases` [PROPOSED] (Hephaestus' publication gate or the
publishing task's report with a `publish:` evidence; Marcelo). Read: latest row per
`(environment, target)`. The existing on-host convention `/root/.forgehub/releases/<name>-<sha>/`
(observed, not an API) may be imported once with `source='imported'`; the strip labels imported rows.
Without a row the strip shows "sem registro" — the build/container is **not** read as proof of what
was released (12 §10 "sem inferir release do build").

## 7. Actions

Every action: confirmation dialog (`ConfirmDialog` [EXISTS frontend/src/components/ui/confirm-dialog.tsx]),
required reason where marked, button `disabled` + `Loader2` while pending, result toast, board refetch.
Backend-computed availability (§3.2). Each action writes an AuditEvent with the human or agent
principal (main spec §0.5) and appears in the timeline.

| Action | Who (M0) | Route | Guards it cannot skip |
|---|---|---|---|
| Despachar agora | Marcelo; orchestrator agent (`planning.execution.manage`) via MCP | `POST /api/v1/tasks/{id}/dispatch` [EXISTS backend/app/api/routes/task.py:946, EXTEND] | baseline M0.6b, mission state, dependencies, assignment, target serialization, capacity |
| Agendar | same | same with `scheduled_at` [EXTEND] | same at start time |
| Reatribuir (motivo) | Marcelo; orchestrator (`mission.orchestrate`) | `POST /api/v1/missions/{p}/tasks/{t}:assign` [PROPOSED, main spec §5.5] | eligibility, reviewer ≠ executor, nothing in flight |
| Pedir revisão | Marcelo; orchestrator | `POST /api/v1/missions/{p}/tasks/{t}:request-review` [PROPOSED §5.11] | execution verified, reviewer independent and `can_review` |
| Recusar / devolver (motivo) | Marcelo; orchestrator not the executor; reviewer via its review | `POST /api/v1/missions/{p}/tasks/{t}:return` [PROPOSED §5.12]; reviewer: `PATCH /orchestration/reviews/{id}` [EXISTS] | reason required |
| Marcar concluída | — (no button) | completion happens only when the guard passes after an approved independent review; the screen shows "aguardando revisão" instead | M0.6a |
| Investigar / confirmar inativa / autorizar nova tentativa | Marcelo (admin) | `POST /api/v1/demands/{id}/decision` [EXISTS backend/app/api/routes/demand.py:1190] | typed run id; attempt budget never reset |
| Decidir critério | criterion verifier; Marcelo | `POST /api/v1/missions/{p}/criteria/{id}:decide` [PROPOSED main §8] | verifier ≠ executor |
| Aprovar plano (baseline) | Marcelo only | `:decide` on the `project_plan` request [EXISTS route, EXTEND] | human_only, hash match |
| Aceitar missão | Marcelo only | `:decide` on the `mission_dossier` request [EXISTS route, EXTEND] | main spec §8 |
| Pausar / retomar / cancelar | Marcelo; orchestrator may pause only when blocked | `POST /api/v1/missions/{p}:transition` [PROPOSED] | main spec §3 |
| Desfazer / travar decisão do ciclo | Marcelo | cycle spec §5 | — |

## 8. Mission list (`/missions`)

Columns: priority, name, state, orchestrator, progress (`done_proven`/total), running now, queued,
awaiting review, uncertain, conflicts, deadline (remaining, paused time excluded), last decision.
Filters: state (multi), orchestrator, agent (missions where an agent executes or reviews), "com
conflitos", "com incertas", text search. Default sort: state group (active first) then priority then
deadline. A "Agentes disputados" panel lists agents with queued work in more than one mission and
which mission wins by priority (cycle spec §6.1).

## 9. Frontend structure, states and layout

- Files [PROPOSED]: `frontend/src/pages/missions/index.tsx`, `pages/missions/[id].tsx`,
  `components/missions/MissionExecutionsBoard.tsx`, `MissionTaskRow.tsx`, `MissionConflictsBanner.tsx`,
  `MissionEnvironmentsStrip.tsx`, `MissionTimeline.tsx`; hooks `hooks/useMissions.ts` (TanStack Query,
  Zod schemas) and `hooks/useMissionExecutionsViewModel.ts` (§21 ViewModel: `status: "loading" |
  "ready" | "empty" | "error" | "confirming" | "submitting"`, selected task, pending action, SSE
  connection state). Tick the screen in `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` in the
  same change. i18n keys in pt-BR/en/es.
- **Loading:** skeleton rows (header, strip, 6 rows); SSE "conectando…" indicator.
- **Empty:** no missions → text + "Nova missão" only for Marcelo (creation through `POST /missions`);
  mission without tasks → "Plano sem tarefas" with link to Planejamento; no baseline → banner "Plano
  não aprovado — nenhuma tarefa pode ser despachada".
- **Partial:** a failed sub-source (agent-activity stream, git ancestry check, environments) shows that
  block as "indisponível" with retry; the rest renders. Never a false all-clear (e.g. conflicts
  `unknown` ≠ none).
- **Error:** 404 (not a member / not found) → `NotFoundState`; 403 → permission message; 5xx →
  `ErrorState` with retry. SSE drop → falls back to 15 s polling with a "ao vivo pausado" chip.
- **1440 px:** header (name, state, priority, orchestrator, deadline, actions) → conflicts banner →
  environments strip → table (#, task, depends on, executor, reviewer, state + timer, evidence,
  actions) with a right-hand detail panel for the selected row (executions/attempts, reviews, evidence,
  message history link, timeline filtered to the task).
- **390 px:** `PageHeader` stacks; conflicts banner collapses to a count chip that expands; environments
  strip becomes a horizontally scrollable card row; the table becomes a card list (one card per task:
  number + title, state chip with timer, executor → reviewer line, evidence count, "…" action menu);
  selecting a card shows the detail full-width with a `md:hidden` back bar (split-screen rule,
  `usePhoneListDetail`); action buttons `max-md:h-auto max-md:whitespace-normal`; inputs `text-base`
  below `md`. Desktop classes unchanged; phone behavior only in `max-md:` variants (CLAUDE.md mobile
  rules).

```
1440 px
┌ Missões › C.0+C.1 Política de memória ────────────── ativa · prioridade 50 · Athos · prazo 3d 4h ┐
│ [Pausar] [Pedir aceite]                                                                           │
├ ⚠ 1 conflito: #9001 e #9003 no mesmo worktree …/m0-spec — #9003 aguarda                            │
├ Ambientes: teste forgehub @ 6e8fce4 (28/10 21:10, Hephaestus) · produção forgehub @ f5f5a6c (sem    │
│   tarefa, importado)                                                                               │
├────┬───────────────────────┬──────────┬──────────┬──────────┬──────────────────┬───────────┬──────┤
│ #  │ Tarefa                │ Depende  │ Executor │ Revisor  │ Estado           │ Provas    │      │
│9000│ Inventário C.0        │ —        │ Mnemosyne│ Dartan   │ Concluída ✓prova │ db:… ✓ Rv │ …    │
│9001│ Matriz por perfil     │ 9000 ✓   │ Porthus● │ Dartan   │ Rodando 21m/45m  │ —         │ …    │
│9003│ Política C.1 rascunho │ 9001 …   │ Athos    │ Mnemosyne│ Na fila: worktree│ —         │ …    │
│9004│ Revisão segurança     │ 9003     │ Aegis    │ Aegis ⚠  │ Não pronta       │ —         │ …    │
└────┴───────────────────────┴──────────┴──────────┴──────────┴──────────────────┴───────────┴──────┘
                                    (⚠ Revisor = executor: revisão bloqueada)

390 px
┌ C.0+C.1 Política…   ativa ┐
│ ⚠ 1 conflito ▸            │
│ [teste 6e8fce4][prod f5f… ▸│
│┌─────────────────────────┐│
││#9001 Matriz por perfil  ││
││Rodando 21m de 45m       ││
││Porthus → Dartan   ⋯     ││
│└─────────────────────────┘│
│┌─────────────────────────┐│
││#9003 Política C.1       ││
││Na fila · worktree ocupado││
│└─────────────────────────┘│
└───────────────────────────┘
```

## 10. Permissions summary

| Role | Sees | Can act |
|---|---|---|
| Marcelo (admin) | all missions | every action in §7 |
| Operator without admin, module `product` | missions list and boards (read) | none in M0 |
| Orchestrator agent (via MCP, `agt_`) | missions where it is coordinator | dispatch, schedule, reassign, request review, return, pause-when-blocked (delegated keys) |
| Executor/reviewer agent (MCP) | its own role/tasks (`get_my_mission_role`) | report its execution; decide its own review |

## 11. Planned tests

Backend `backend/app/tests/test_mission_board.py`:

| Test | Proves |
|---|---|
| `test_board_state_precedence` | each §4 state from fixture rows; uncertain beats running; historical done never `done_proven` |
| `test_reviewer_equals_executor_flag` | flag set and `request_review`/accept blocked |
| `test_conflict_same_worktree_and_branch_and_publish` | each kind detected across two missions and a non-mission demand |
| `test_publish_missing_production_commit` | ancestry false → blocking; bridge unavailable → `unknown`, not clear |
| `test_environments_never_inferred` | no row → "sem registro"; imported rows labeled |
| `test_allowed_actions_match_guards` | every action listed as allowed succeeds on its route; every blocked one fails with the same code |
| `test_non_member_agent_404` | agent outside the mission gets 404 on board and timeline |
| `test_actions_audited_with_principal` | each action produces an AuditEvent with the caller |
| `test_stream_pushes_after_change` | SSE emits a new snapshot after a demand/review change |

Frontend (Vitest + RTL) `frontend/src/pages/missions/index.test.tsx`, `[id].test.tsx`,
`hooks/useMissionExecutionsViewModel.test.ts`: loading/empty/partial/error renders; action dialog
requires reason; button disabled while pending; blocked action shows backend reason; phone layout
(card list + back bar) at 390 px and table at 1440 px (viewport mocks); i18n keys exist in pt-BR/en/es.
Playwright (test environment only, T.2 frontend `127.0.0.1:4174`, seeded fixtures): open a mission,
dispatch a ready task with the simulated runner (T.3), see it running, then queued conflict for a second
task on the same worktree.
