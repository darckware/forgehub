import type { MissionBoard, MissionPhase, MissionTask } from "@/hooks/useMissions";

/** Fictitious mission board (M0.7 tests): one task per §1 point. */
export function missionTask(overrides: Partial<MissionTask> = {}): MissionTask {
  return {
    task_id: "t-ready", number: 9001, title: "Matriz por perfil", status: "assigned", topo_index: 0,
    depends_on: [], executor: { agent_id: "a-porthus", name: "Porthus" }, reviewer: null, reviewer_is_executor: false,
    review: null, reviewer_candidates: [{ agent_id: "a-dartan", name: "Dartan", eligible: true }],
    executor_candidates: [{ agent_id: "a-porthus", name: "Porthus" }, { agent_id: "a-aramis", name: "Aramis" }],
    execution_state: "ready", queued_reason: null, missing: [], blocking: [], returned_reason: null,
    execution: null, attempts: [], evidence: [], baseline_status: "current", context: null, skills: [],
    targets: [{ kind: "worktree", key: "/srv/m07/wt" }], conflicts: [],
    allowed_actions: ["dispatch", "schedule", "assign"],
    blocked_actions: [
      { action: "request_review", reason: "EXECUTION_NOT_VERIFIED", message: "" },
      { action: "return", reason: "EXECUTION_NOT_FOUND", message: "" },
    ],
    ...overrides,
  };
}

export function missionBoard(overrides: Partial<MissionBoard> = {}): MissionBoard {
  const now = new Date().toISOString();
  return {
    mission: {
      project_id: "m07-mission", name: "m07 Política de memória", state: "active", paused_from_state: null,
      planning_stage: null, priority: 50, row_version: 3, orchestrator: { id: "a-athos", name: "Athos" },
      deadline_at: new Date(Date.now() + 3 * 86400_000).toISOString(), paused: false,
      product_registration_pending: false, working_directory_path: null,
      baseline: { id: "b-1", name: "baseline 1", approved_at: now, superseded: false },
      allowed_actions: ["pause", "cancel"],
      blocked_actions: [{ action: "resume", reason: "MISSION_TRANSITION_NOT_ALLOWED", message: "" }],
    },
    phases: [],
    tasks: [
      missionTask(),
      missionTask({
        task_id: "t-running", number: 9002, title: "Política C.1 rascunho", execution_state: "running",
        executor: { agent_id: "a-aramis", name: "Aramis" }, reviewer: { agent_id: "a-aramis", name: "Aramis" },
        reviewer_is_executor: true, depends_on: [{ task_id: "t-ready", number: 9001, status: "done" }],
        execution: {
          execution_id: "e-2", attempt: 2, status: "running", summary: null, demand_id: "d-2", demand_number: 41634,
          dispatch_status: "running", dispatch_error: null, agent_run_id: "run-2", scheduled_at: null,
          dispatched_at: new Date(Date.now() - 21 * 60_000).toISOString(),
          deadline_at: new Date(Date.now() + 24 * 60_000).toISOString(), elapsed_seconds: 1260, attempts: 1, retry_limit: 3,
        },
        evidence: [{ ref: "git:0123456789abcdef", verified: true, verified_by: "evidence-check", reviewed_by: null }],
        context: { version: "abc123def456", dispatched_at: now, stale: true, stale_reasons: ["task_changed"] },
        skills: [{ skill_id: "s-1", name: "python", approved: true, executor_has: true, reviewer_has: false }],
        allowed_actions: [],
        blocked_actions: [
          { action: "dispatch", reason: "TASK_RUN_IN_FLIGHT", message: "" },
          { action: "request_review", reason: "REVIEWER_IS_EXECUTOR", message: "" },
        ],
        conflicts: ["C-1"],
      }),
    ],
    conflicts: [{ id: "C-1", kind: "same_worktree", severity: "blocking", target: "/srv/m07/wt", tasks: [9001, 9002], detail: "held by #41634" }],
    environments: [
      { environment: "test", target: "forgehub", source: "recorded", commit_sha: "6e8fce4aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", released_at: now, released_by: "Hephaestus", task_number: 9007 },
      { environment: "production", target: "forgehub", source: "no_record" },
    ],
    planning: null,
    viewer: { principal_type: "user", is_admin: true, can_act: true },
    generated_at: now,
    ...overrides,
  };
}

/** A fictitious mission phase (MISSION_PHASES_PLAN.md). */
export function missionPhase(overrides: Partial<MissionPhase> = {}): MissionPhase {
  return {
    phase_id: "ph-1", position: 1, name: "Estrutura", objective: "Navegação e design system, sem regras de negócio",
    phase_status: "planned", executor_project_id: "p-ph-1", executor_project_name: "m07 · Fase 1 · Estrutura",
    homologator: null, homologation_verdict: null, homologation_summary: null, homologation_evidence: null,
    homologated_at: null, decided_by: null, decided_at: null, decision_reason: null,
    planning_items: [{
      planning_item_id: "pi-1", title: "Menu e rotas", position: 1, status: "new", sequenced: true,
      tasks: [
        { task_id: "pt-1", number: 9101, title: "Layout base", status: "done", position: 1, assignee_name: "Porthus", depends_on: [] },
        { task_id: "pt-2", number: 9102, title: "Rotas", status: "assigned", position: 2, assignee_name: "Aramis", depends_on: [9101] },
      ],
    }],
    ...overrides,
  };
}
