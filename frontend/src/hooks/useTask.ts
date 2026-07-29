import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Task domain (see docs/SPEC.md 4.5 Task Domain):
 *   project_tasks, task_dependencies, task_required_skills,
 *   task_assignments, task_executions
 *
 * Primary entity: ProjectTask. A ProjectTask represents a planned task or
 * subtask (subtasks use parent_task_id relationships) split out from a
 * PlanningItem (PRD.md 5.9). Each ProjectTask carries a nested list of
 * TaskExecution records (PRD.md 5.10) -- every real execution attempt by an
 * agent, sub-agent, human, or system is tracked separately, and a task can
 * have multiple executions (failed, retried, verified, completed) per
 * SPEC.md 5.4 / 6.4.
 *
 * Backend contract: /api/v1/tasks (list/create/get/update/delete).
 */

export const TASK_STATUSES = [
  "planned",
  "ready",
  "assigned",
  "in_progress",
  "blocked",
  "done",
  "deployed",
  "cancelled",
] as const;

export type TaskStatus = (typeof TASK_STATUSES)[number];

export const TASK_PRIORITIES = ["low", "medium", "high", "critical"] as const;
export type TaskPriority = (typeof TASK_PRIORITIES)[number];

export const EXECUTION_STATUSES = [
  "pending",
  "running",
  "blocked",
  "paused",
  "reconciling",
  "recovering",
  "failed",
  "retried",
  "verified",
  "completed",
] as const;

export const EXECUTOR_TYPES = ["agent", "sub_agent", "human", "system"] as const;

export type ExecutionStatus = (typeof EXECUTION_STATUSES)[number];
export type ExecutorType = (typeof EXECUTOR_TYPES)[number];

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

export const taskExecutionSchema = z.object({
  id: z.string(),
  task_id: z.string(),
  assignment_id: z.string().nullable().optional(),
  runtime_profile_id: z.string().nullable().optional(),
  loop_policy_id: z.string().nullable().optional(),
  parent_execution_id: z.string().nullable().optional(),
  attempt_number: z.number().int().optional(),
  executor_type: z.string().nullable().optional(),
  runtime_type: z.string().nullable().optional(),
  runtime_session_ref: z.string().nullable().optional(),
  work_package_id: z.string().nullable().optional(),
  adapter_version: z.string().nullable().optional(),
  process_ref: z.string().nullable().optional(),
  exit_code: z.number().nullable().optional(),
  loop_iteration: z.number().int().default(1),
  status: z.enum(EXECUTION_STATUSES).default("pending"),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  outcome_summary: z.string().nullable().optional(),
  evidence_ref: z.string().nullable().optional(),
  actual_cost: z.number().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type TaskExecution = z.infer<typeof taskExecutionSchema>;

export const executionCreateSchema = z.object({
  executor_type: z.enum(EXECUTOR_TYPES).default("agent"),
  status: z.enum(EXECUTION_STATUSES).default("pending"),
  started_at: z.string().optional().or(z.literal("")),
  finished_at: z.string().optional().or(z.literal("")),
  outcome_summary: z.string().max(2000).optional().or(z.literal("")),
  evidence_ref: z.string().max(500).optional().or(z.literal("")),
  actual_cost: z
    .union([z.coerce.number(), z.literal("")])
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
});

export type ExecutionCreateInput = z.infer<typeof executionCreateSchema>;

export const DEPENDENCY_TYPES = [
  "finish_to_start",
  "start_to_start",
  "finish_to_finish",
  "start_to_finish",
] as const;
export type DependencyType = (typeof DEPENDENCY_TYPES)[number];

export const taskDependencySchema = z.object({
  id: z.string(),
  task_id: z.string(),
  depends_on_task_id: z.string(),
  dependency_type: z.enum(DEPENDENCY_TYPES).default("finish_to_start"),
});

export type TaskDependency = z.infer<typeof taskDependencySchema>;

export const taskRequiredSkillSchema = z.object({
  id: z.string(),
  task_id: z.string(),
  skill_id: z.string(),
  is_mandatory: z.boolean().default(true),
  minimum_proficiency: z.string().nullable().optional(),
});

export type TaskRequiredSkill = z.infer<typeof taskRequiredSkillSchema>;

export const taskAssignmentSchema = z.object({
  id: z.string(),
  task_id: z.string(),
  agent_id: z.string().nullable().optional(),
  sub_agent_id: z.string().nullable().optional(),
  assigned_at: z.string().optional(),
});

export type TaskAssignment = z.infer<typeof taskAssignmentSchema>;

export const projectTaskSchema = z.object({
  id: z.string(),
  // Server-assigned display number (#1, #2, ...) -- a real Postgres
  // IDENTITY column (see ProjectTask.number's docstring backend-side),
  // always set from creation.
  number: z.number(),
  planning_item_id: z.string().nullable().optional(),
  change_request_id: z.string().nullable().optional(),
  // Computed by the backend (task.py's _attach_project_ids) from whichever
  // of planning_item_id/change_request_id this task traces back to -- a
  // task has no project_id column of its own. Read-only: never send this
  // back on create/update, the backend silently ignores it there (it used
  // to be sent from here too, which is why every task looked unlinked from
  // its project on screen -- fixed 2026-07-16).
  project_id: z.string().nullable().optional(),
  // Computed by the backend (core/task_health.py's compute_health_map) --
  // "ok" | "overdue" (deadline passed, never executed) | "stalled"
  // (execution stuck pending/running) | "failed" (latest execution
  // failed). Never sent on create/update.
  health: z.enum(["ok", "overdue", "stalled", "failed"]).default("ok"),
  parent_task_id: z.string().nullable().optional(),
  policy_id: z.string().nullable().optional(),
  title: z.string(),
  description: z.string().nullable().optional(),
  status: z.enum(TASK_STATUSES).default("planned"),
  priority: z.enum(TASK_PRIORITIES).default("medium"),
  estimated_cost: z.number().nullable().optional(),
  // "Due date" in the UI -- maps to the backend's planned_end_date (there
  // is no separate due_date column; sending "due_date" was silently
  // dropped, same phantom-field bug as project_id, fixed alongside it).
  planned_end_date: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  executions: z.array(taskExecutionSchema).nullable().optional(),
});

export type ProjectTask = z.infer<typeof projectTaskSchema>;

// Base object (no refine) so .partial() can be derived from it. No
// project_id here on purpose -- it's derived server-side (see
// projectTaskSchema above), never a real column, so it must never be part
// of what the create/edit form submits.
const _taskBaseSchema = z.object({
  title: z.string().min(1, "Title is required").max(200, "Title is too long"),
  description: z.string().max(2000, "Description is too long").optional().or(z.literal("")),
  planning_item_id: z.string().optional().or(z.literal("")),
  change_request_id: z.string().optional().or(z.literal("")),
  parent_task_id: z.string().optional().or(z.literal("")),
  policy_id: z.string().optional().or(z.literal("")),
  status: z.enum(TASK_STATUSES).default("planned"),
  priority: z.enum(TASK_PRIORITIES).default("medium"),
  estimated_cost: z
    .union([z.coerce.number(), z.literal("")])
    .optional()
    .transform((v) => (v === "" || v === undefined ? undefined : Number(v))),
  planned_end_date: z.string().optional().or(z.literal("")),
});

// Payload schemas (what the create/edit form submits).
export const taskCreateSchema = _taskBaseSchema.refine(
  (d) => Boolean(d.planning_item_id) || Boolean(d.change_request_id),
  {
    message: "At least one of Planning item or Change request must be set",
    path: ["planning_item_id"],
  }
);

export type TaskCreateInput = z.infer<typeof taskCreateSchema>;

export const taskUpdateSchema = _taskBaseSchema.partial();
export type TaskUpdateInput = z.infer<typeof taskUpdateSchema>;

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const taskKeys = {
  all: ["tasks"] as const,
  detail: (id: string) => ["tasks", id] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useTasks(planningItemId?: string) {
  return useQuery({
    queryKey: planningItemId ? ["tasks", "by-planning-item", planningItemId] : taskKeys.all,
    queryFn: () =>
      apiClient.get<ProjectTask[]>(
        planningItemId ? `/api/v1/tasks?planning_item_id=${planningItemId}` : "/api/v1/tasks"
      ),
  });
}

export function useTasksByChangeRequest(changeRequestId: string | undefined) {
  return useQuery({
    queryKey: ["tasks", "by-change-request", changeRequestId ?? ""],
    queryFn: () =>
      apiClient.get<ProjectTask[]>(`/api/v1/tasks?change_request_id=${changeRequestId}`),
    enabled: Boolean(changeRequestId),
  });
}

export function useTasksByPolicy(policyId: string | undefined) {
  return useQuery({
    queryKey: ["tasks", "by-policy", policyId ?? ""],
    queryFn: () =>
      apiClient.get<ProjectTask[]>(`/api/v1/tasks?policy_id=${policyId}`),
    enabled: Boolean(policyId),
  });
}

export function useTask(id: string | undefined) {
  return useQuery({
    queryKey: taskKeys.detail(id ?? ""),
    queryFn: () => apiClient.get<ProjectTask>(`/api/v1/tasks/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: TaskCreateInput) => apiClient.post<ProjectTask>("/api/v1/tasks", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}

export function useUpdateTask(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    // Backend only exposes PATCH /api/v1/tasks/{id} (no PUT route).
    mutationFn: (payload: TaskUpdateInput) => apiClient.patch<ProjectTask>(`/api/v1/tasks/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
      queryClient.invalidateQueries({ queryKey: taskKeys.detail(id) });
    },
  });
}

export function useDeleteTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`/api/v1/tasks/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
    },
  });
}


export function useCreateExecution(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ExecutionCreateInput) =>
      apiClient.post<TaskExecution>(`/api/v1/tasks/${taskId}/executions`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.detail(taskId) });
    },
  });
}

export function useTaskExecutions(taskId: string | undefined) {
  return useQuery({
    queryKey: ["task-executions", taskId ?? ""],
    queryFn: () => apiClient.get<TaskExecution[]>(`/api/v1/tasks/${taskId}/executions`),
    enabled: Boolean(taskId),
  });
}

// ---------------------------------------------------------------------------
// TaskDependency -- blocks a task's completion until each depends_on_task_id
// is "done" (see task.py's _ensure_dependencies_satisfied). Not surfaced
// anywhere in the UI before 2026-07-16 despite backing a real business rule.
// ---------------------------------------------------------------------------

export function useTaskDependencies(taskId: string | undefined) {
  return useQuery({
    queryKey: ["task-dependencies", taskId ?? ""],
    queryFn: () => apiClient.get<TaskDependency[]>(`/api/v1/tasks/${taskId}/dependencies`),
    enabled: Boolean(taskId),
  });
}

export function useCreateTaskDependency(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { depends_on_task_id: string; dependency_type?: DependencyType }) =>
      apiClient.post<TaskDependency>(`/api/v1/tasks/${taskId}/dependencies`, {
        task_id: taskId,
        ...payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-dependencies", taskId] });
    },
  });
}

export function useDeleteTaskDependency(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (dependencyId: string) =>
      apiClient.delete<void>(`/api/v1/tasks/${taskId}/dependencies/${dependencyId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-dependencies", taskId] });
    },
  });
}

// ---------------------------------------------------------------------------
// TaskRequiredSkill -- gates who counts as "eligible" in the Governed CLI
// execution card (see useOrchestration's useEligibleMemberships /
// _member_skill_ids on the backend). Create + list only; the backend has
// no delete endpoint for this sub-resource.
// ---------------------------------------------------------------------------

export function useTaskRequiredSkills(taskId: string | undefined) {
  return useQuery({
    queryKey: ["task-required-skills", taskId ?? ""],
    queryFn: () => apiClient.get<TaskRequiredSkill[]>(`/api/v1/tasks/${taskId}/required-skills`),
    enabled: Boolean(taskId),
  });
}

export function useCreateTaskRequiredSkill(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { skill_id: string; is_mandatory?: boolean; minimum_proficiency?: string }) =>
      apiClient.post<TaskRequiredSkill>(`/api/v1/tasks/${taskId}/required-skills`, {
        task_id: taskId,
        ...payload,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task-required-skills", taskId] });
      // Eligibility (Governed CLI execution card) is computed from required
      // skills -- keep it in sync with a fresh required-skills row.
      queryClient.invalidateQueries({ queryKey: ["eligible-memberships", taskId] });
    },
  });
}

/** Despacha a task pelo processo de Mensagens.
 *
 * Decisão do Marcelo (2026-07-26): toda tarefa é executada pelo canal de
 * mensagens -- este hook não fala com nenhum runner, ele chama
 * POST /api/v1/tasks/{id}/dispatch, que cria a mensagem vinculada
 * (origin_type="task") e a entrega ao mesmo dispatch que o Messages já usa
 * para comunicação entre agentes. Invalida também a lista de mensagens,
 * já que a chamada cria uma. */
export interface TaskInboxDispatch {
  task_id: string;
  task_status: string;
  demand_id: string;
  demand_number: number;
  target_agent_id: string;
  dispatch_status: string | null;
  agent_run_id: string | null;
}

export function useDispatchTask(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { target_agent_id?: string; command_text?: string; requires_response?: boolean } = {}) =>
      apiClient.post<TaskInboxDispatch>(`/api/v1/tasks/${taskId}/dispatch`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.detail(taskId) });
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
      queryClient.invalidateQueries({ queryKey: ["demands"] });
    },
  });
}
