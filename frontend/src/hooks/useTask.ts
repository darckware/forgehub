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

export const taskDependencySchema = z.object({
  id: z.string(),
  task_id: z.string(),
  depends_on_task_id: z.string(),
});

export type TaskDependency = z.infer<typeof taskDependencySchema>;

export const taskRequiredSkillSchema = z.object({
  id: z.string(),
  task_id: z.string(),
  skill_id: z.string(),
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
  planning_item_id: z.string().nullable().optional(),
  change_request_id: z.string().nullable().optional(),
  project_id: z.string().nullable().optional(),
  parent_task_id: z.string().nullable().optional(),
  policy_id: z.string().nullable().optional(),
  title: z.string(),
  description: z.string().nullable().optional(),
  status: z.enum(TASK_STATUSES).default("planned"),
  priority: z.enum(TASK_PRIORITIES).default("medium"),
  estimated_cost: z.number().nullable().optional(),
  due_date: z.string().nullable().optional(),
  kanboard_task_id: z.number().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  executions: z.array(taskExecutionSchema).nullable().optional(),
});

export type ProjectTask = z.infer<typeof projectTaskSchema>;

export const projectTaskKanboardSyncSchema = projectTaskSchema.extend({
  kanboard_url: z.string().nullable().optional(),
});

export type ProjectTaskKanboardSync = z.infer<typeof projectTaskKanboardSyncSchema>;

// Base object (no refine) so .partial() can be derived from it.
const _taskBaseSchema = z.object({
  title: z.string().min(1, "Title is required").max(200, "Title is too long"),
  description: z.string().max(2000, "Description is too long").optional().or(z.literal("")),
  project_id: z.string().optional().or(z.literal("")),
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
  due_date: z.string().optional().or(z.literal("")),
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

export function useSyncTaskToKanboard(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<ProjectTaskKanboardSync>(`/api/v1/tasks/${id}/sync-kanboard`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
      queryClient.invalidateQueries({ queryKey: taskKeys.detail(id) });
    },
  });
}

export function usePullKanboard(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiClient.post<ProjectTask>(`/api/v1/tasks/${taskId}/pull-kanboard`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
      queryClient.invalidateQueries({ queryKey: taskKeys.detail(taskId) });
    },
  });
}

export function useKanboardCleanup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      apiClient.post<{ closed: number; skipped: number; errors: string[] }>(
        `/api/v1/tasks/kanboard-cleanup?project_id=${projectId}`,
        {}
      ),
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
