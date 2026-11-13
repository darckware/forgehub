/**
 * Mission executions screen (Plano Integrado M0.7,
 * docs/architecture/MISSION_EXECUTIONS_SCREEN_SPEC.md).
 *
 * Reads: GET /api/v1/missions, /missions/{id}/executions, /missions/{id}/timeline.
 * Every write goes to the existing guarded route -- the board's
 * allowed_actions/blocked_actions are the backend's dry run of those guards,
 * and the UI never re-derives eligibility.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/** SSE is not built in M0.7: the board polls (spec §9 "SSE drop → 15 s polling"). */
export const BOARD_POLL_MS = 15_000;

export const EXECUTION_STATES = [
  "cancelled", "done_proven", "done_historical", "uncertain", "running", "queued", "scheduled",
  "changes_requested", "awaiting_review", "evidence_failed", "reported", "failed", "blocked", "ready", "not_ready",
] as const;
export type ExecutionState = (typeof EXECUTION_STATES)[number];

const agentRef = z.object({ agent_id: z.string(), name: z.string() });
const blockedAction = z.object({ action: z.string(), reason: z.string(), message: z.string().optional() }).passthrough();

export const missionTaskSchema = z.object({
  task_id: z.string(),
  number: z.number().nullable(),
  title: z.string(),
  status: z.string(),
  topo_index: z.number(),
  depends_on: z.array(z.object({ task_id: z.string(), number: z.number().nullable(), status: z.string() })),
  executor: agentRef.nullable(),
  reviewer: agentRef.nullable(),
  reviewer_is_executor: z.boolean(),
  review: z.object({
    review_id: z.string(), status: z.string(), decided: z.boolean(), feedback: z.string().nullable(),
  }).passthrough().nullable(),
  reviewer_candidates: z.array(agentRef.extend({ eligible: z.boolean(), reason: z.string().optional() })),
  executor_candidates: z.array(agentRef),
  execution_state: z.string(),
  queued_reason: z.string().nullable(),
  missing: z.array(z.string()),
  blocking: z.array(z.number().nullable()),
  returned_reason: z.string().nullable(),
  execution: z.object({
    execution_id: z.string().nullable(),
    attempt: z.number().nullable(),
    status: z.string().nullable(),
    summary: z.string().nullable(),
    demand_id: z.string().nullable(),
    demand_number: z.number().nullable(),
    dispatch_status: z.string().nullable(),
    dispatch_error: z.string().nullable(),
    agent_run_id: z.string().nullable(),
    scheduled_at: z.string().nullable(),
    dispatched_at: z.string().nullable(),
    deadline_at: z.string().nullable(),
    elapsed_seconds: z.number().nullable(),
    attempts: z.number().nullable(),
    retry_limit: z.number().nullable(),
  }).nullable(),
  attempts: z.array(z.object({ execution_id: z.string(), attempt: z.number(), status: z.string() }).passthrough()),
  evidence: z.array(z.object({
    ref: z.string(),
    verified: z.boolean().nullable(),
    verified_by: z.string().nullable(),
    reviewed_by: z.object({ name: z.string(), status: z.string() }).nullable(),
  }).passthrough()),
  baseline_status: z.string(),
  context: z.object({
    version: z.string().nullable(), dispatched_at: z.string().nullable(), stale: z.boolean(),
    stale_reasons: z.array(z.string()),
  }).passthrough().nullable(),
  skills: z.array(z.object({
    skill_id: z.string(), name: z.string(), approved: z.boolean(), executor_has: z.boolean(), reviewer_has: z.boolean(),
  })),
  targets: z.array(z.object({ kind: z.string(), key: z.string() }).passthrough()),
  conflicts: z.array(z.string()),
  allowed_actions: z.array(z.string()),
  blocked_actions: z.array(blockedAction),
});
export type MissionTask = z.infer<typeof missionTaskSchema>;

export const missionConflictSchema = z.object({
  id: z.string(),
  kind: z.string(),
  severity: z.enum(["blocking", "warning"]),
  target: z.string().nullable(),
  tasks: z.array(z.number().nullable()),
  detail: z.string(),
}).passthrough();
export type MissionConflict = z.infer<typeof missionConflictSchema>;

export const environmentEntrySchema = z.object({
  environment: z.string(),
  target: z.string(),
  source: z.string(),
  commit_sha: z.string().optional(),
  branch: z.string().nullable().optional(),
  released_at: z.string().optional(),
  released_by: z.string().optional(),
  task_number: z.number().nullable().optional(),
});
export type EnvironmentEntry = z.infer<typeof environmentEntrySchema>;

const planningItem = z.object({
  item_id: z.string(), text: z.string(), origin: z.string().nullable(), disposition: z.string().nullable(),
  reason: z.string().nullable(), needs_decision: z.boolean(), decision: z.string().nullable(),
}).passthrough();

export const planningViewSchema = z.object({
  stages: z.array(z.string()),
  current: z.string().nullable(),
  status: z.string(),
  unmet: z.array(z.object({ code: z.string(), message: z.string().optional() }).passthrough()),
  not_evaluated: z.array(z.object({ code: z.string() }).passthrough()),
  layers: z.array(z.object({ layer: z.string(), reviewed: z.boolean(), waived: z.boolean() })).default([]),
  reviews: z.array(z.object({
    review_id: z.string(), kind: z.string(), layer: z.string(), reviewer: agentRef.nullable(), summary: z.string().nullable(),
  }).passthrough()).default([]),
  items: z.array(planningItem).default([]),
  pending_decisions: z.array(planningItem.extend({ can_decide: z.boolean(), blocked_reason: z.string().nullable() })).default([]),
});
export type PlanningView = z.infer<typeof planningViewSchema>;

/** Mission phases (docs/architecture/MISSION_PHASES_PLAN.md): ordered executor
 * projects; planning items may run in parallel, tasks of one item in sequence. */
export const PHASE_STATUSES = [
  "planned", "in_progress", "homologating", "awaiting_approval", "approved", "returned",
] as const;
export type PhaseStatus = (typeof PHASE_STATUSES)[number];

export const missionPhaseTaskSchema = z.object({
  task_id: z.string(),
  number: z.number().nullable(),
  title: z.string(),
  status: z.string(),
  position: z.number().nullable(),
  assignee_name: z.string().nullable(),
  depends_on: z.array(z.number()).default([]),
});

export const missionPhaseSchema = z.object({
  phase_id: z.string(),
  position: z.number(),
  name: z.string(),
  objective: z.string().nullable(),
  phase_status: z.string(),
  executor_project_id: z.string(),
  executor_project_name: z.string().nullable(),
  homologator: agentRef.nullable(),
  homologation_verdict: z.string().nullable(),
  homologation_summary: z.string().nullable(),
  homologation_evidence: z.string().nullable(),
  homologated_at: z.string().nullable(),
  decided_by: z.string().nullable(),
  decided_at: z.string().nullable(),
  decision_reason: z.string().nullable(),
  planning_items: z.array(z.object({
    planning_item_id: z.string(),
    title: z.string(),
    position: z.number().nullable(),
    status: z.string(),
    sequenced: z.boolean(),
    tasks: z.array(missionPhaseTaskSchema),
  })).default([]),
}).passthrough();
export type MissionPhase = z.infer<typeof missionPhaseSchema>;

export const missionBoardSchema = z.object({
  mission: z.object({
    project_id: z.string(),
    name: z.string(),
    state: z.string(),
    paused_from_state: z.string().nullable(),
    planning_stage: z.string().nullable(),
    priority: z.number(),
    row_version: z.number(),
    orchestrator: z.object({ id: z.string(), name: z.string().nullable() }),
    deadline_at: z.string().nullable(),
    paused: z.boolean(),
    product_registration_pending: z.boolean().optional().default(false),
    working_directory_path: z.string().nullable().optional(),
    baseline: z.object({ id: z.string(), name: z.string().nullable().optional(), approved_at: z.string().nullable(), superseded: z.boolean() }).passthrough().nullable(),
    allowed_actions: z.array(z.string()),
    blocked_actions: z.array(blockedAction),
  }),
  phases: z.array(missionPhaseSchema).optional().default([]),
  tasks: z.array(missionTaskSchema),
  conflicts: z.array(missionConflictSchema),
  environments: z.array(environmentEntrySchema),
  planning: planningViewSchema.nullable(),
  viewer: z.object({ principal_type: z.string(), is_admin: z.boolean(), can_act: z.boolean() }),
  generated_at: z.string(),
});
export type MissionBoard = z.infer<typeof missionBoardSchema>;

export const missionCriterionSchema = z.object({
  id: z.string(), code: z.string(), statement: z.string(), verification_method: z.string(),
  status: z.enum(["open", "proven", "failed"]), verifier_agent_id: z.string().nullable(),
  verifier_is_marcelo: z.boolean(), evidence_ref: z.string().nullable(), task_ids: z.array(z.string()),
});
export type MissionCriterion = z.infer<typeof missionCriterionSchema>;

export function useMissionCriteria(projectId: string | undefined) {
  return useQuery({
    queryKey: ["mission-criteria", projectId],
    queryFn: async () => z.array(missionCriterionSchema).parse(
      await apiClient.get(`/api/v1/missions/${projectId}/criteria`),
    ),
    enabled: Boolean(projectId),
  });
}

export function useCreateMissionCriterion(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      code: string; statement: string; verification_method: string; task_ids: string[];
      verifier_agent_id?: string; verifier_is_marcelo?: boolean; idempotency_key: string;
    }) => apiClient.post(`/api/v1/missions/${projectId}/criteria`, body),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["mission-criteria", projectId] });
      queryClient.invalidateQueries({ queryKey: ["mission-board", projectId] });
      queryClient.invalidateQueries({ queryKey: ["missions"] });
    },
  });
}

export const missionSummarySchema = z.object({
  project_id: z.string(),
  name: z.string(),
  state: z.string(),
  priority: z.number(),
  orchestrator: z.object({ id: z.string(), name: z.string().nullable() }),
  deadline_at: z.string().nullable(),
  remaining_seconds: z.number().nullable(),
  progress: z.object({ done_proven: z.number(), total: z.number() }),
  running: z.number(),
  queued: z.number(),
  awaiting_review: z.number(),
  uncertain: z.number(),
  conflicts: z.number(),
  warnings: z.number(),
  last_decision: z.object({ event_type: z.string(), actor: z.string().nullable(), at: z.string().nullable() }).nullable(),
});
export type MissionSummary = z.infer<typeof missionSummarySchema>;

export const missionListSchema = z.object({
  items: z.array(missionSummarySchema),
  total: z.number(),
  page: z.number(),
  page_size: z.number(),
  contested_agents: z.array(z.object({
    agent_id: z.string(), name: z.string(),
    missions: z.array(z.object({ project_id: z.string(), name: z.string(), priority: z.number() })),
    winner_project_id: z.string(),
  })),
});
export type MissionList = z.infer<typeof missionListSchema>;

export interface MissionFilters {
  states: string[];
  q: string;
  hasConflicts: boolean;
  hasUncertain: boolean;
}

export function useMissions(filters: MissionFilters) {
  return useQuery({
    queryKey: ["missions", filters],
    queryFn: async () => missionListSchema.parse(await apiClient.get("/api/v1/missions", {
      params: {
        state: filters.states.length ? filters.states.join(",") : undefined,
        q: filters.q.trim() || undefined,
        has_conflicts: filters.hasConflicts || undefined,
        has_uncertain: filters.hasUncertain || undefined,
      },
    })),
    refetchInterval: BOARD_POLL_MS,
  });
}

export function useMissionBoard(projectId: string | undefined) {
  return useQuery({
    queryKey: ["mission-board", projectId],
    enabled: Boolean(projectId),
    queryFn: async () => missionBoardSchema.parse(await apiClient.get(`/api/v1/missions/${projectId}/executions`)),
    refetchInterval: BOARD_POLL_MS,
    retry: false,
  });
}

export const timelineSchema = z.object({
  items: z.array(z.object({
    id: z.string(), event_type: z.string(), actor: z.string().nullable(), at: z.string(),
    task_number: z.number().nullable(), payload: z.record(z.string(), z.unknown()),
  })),
  next_before: z.string().nullable(),
});
export type MissionTimeline = z.infer<typeof timelineSchema>;

export function useMissionTimeline(projectId: string | undefined, taskId?: string | null) {
  return useQuery({
    queryKey: ["mission-timeline", projectId, taskId ?? null],
    enabled: Boolean(projectId),
    queryFn: async () => timelineSchema.parse(await apiClient.get(`/api/v1/missions/${projectId}/timeline`, {
      params: { task_id: taskId ?? undefined, limit: 50 },
    })),
  });
}

/** Every action the screen offers, each bound to its existing guarded route. */
export type MissionActionKind =
  | "dispatch" | "schedule" | "assign" | "request_review" | "return"
  | "pause" | "resume" | "cancel" | "decide_item";

export interface MissionActionInput {
  kind: MissionActionKind;
  taskId?: string;
  executionId?: string | null;
  agentId?: string;
  reason?: string;
  scheduledAt?: string;
  itemId?: string;
  decision?: string;
  toState?: string | null;
  rowVersion?: number;
}

function idempotencyKey(): string {
  const random = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `ui-m07-${random}`;
}

/** Route and body per action. Exported for tests: no action has a path of its own. */
export function actionRequest(projectId: string, input: MissionActionInput): { path: string; body: Record<string, unknown> } {
  const base = `/api/v1/missions/${projectId}`;
  switch (input.kind) {
    case "dispatch":
      return { path: `/api/v1/tasks/${input.taskId}/dispatch`, body: {} };
    case "schedule":
      return { path: `/api/v1/tasks/${input.taskId}/dispatch`, body: { scheduled_at: input.scheduledAt } };
    case "assign":
      return { path: `${base}/tasks/${input.taskId}:assign`,
        body: { agent_id: input.agentId, reason: input.reason, idempotency_key: idempotencyKey() } };
    case "request_review":
      return { path: `${base}/tasks/${input.taskId}:request-review`,
        body: { execution_id: input.executionId, reviewer_agent_id: input.agentId, idempotency_key: idempotencyKey() } };
    case "return":
      return { path: `${base}/tasks/${input.taskId}:return`,
        body: { execution_id: input.executionId, reason: input.reason, idempotency_key: idempotencyKey() } };
    case "pause":
    case "resume":
    case "cancel":
      return { path: `${base}:transition`,
        body: { to: input.toState, reason: input.reason || null, expected_row_version: input.rowVersion } };
    case "decide_item":
      return { path: `${base}/review-items/${input.itemId}:decide`, body: { decision: input.decision, reason: input.reason } };
  }
}

export function useMissionAction(projectId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: MissionActionInput) => {
      const { path, body } = actionRequest(projectId ?? "", input);
      return apiClient.post(path, body);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["mission-board", projectId] });
      queryClient.invalidateQueries({ queryKey: ["mission-timeline", projectId] });
      queryClient.invalidateQueries({ queryKey: ["missions"] });
    },
  });
}

/** One phase write (create/update/delete/reorder/approve/return), each to its own guarded route. */
export interface MissionPhaseRequest {
  method: "POST" | "PATCH" | "DELETE";
  path: string;
  body?: Record<string, unknown>;
}

/** Marcelo's pending mission decisions (Pessoal → Tarefas dos agentes). Kept
 * here so phase mutations can refresh it without an import cycle. */
export const missionDecisionsKey = ["mission-pending-decisions"] as const;

export function useMissionPhaseMutation(projectId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ method, path, body }: MissionPhaseRequest) => {
      const url = `/api/v1/missions/${projectId}${path}`;
      if (method === "PATCH") return apiClient.patch(url, body);
      if (method === "DELETE") return apiClient.delete(url);
      return apiClient.post(url, body);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["mission-board", projectId] });
      queryClient.invalidateQueries({ queryKey: ["mission-timeline", projectId] });
      queryClient.invalidateQueries({ queryKey: missionDecisionsKey });
    },
  });
}
