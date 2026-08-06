import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export const RUNTIME_TYPES = ["claude", "codex", "agy"] as const;
export const FORGEROUTER_ROUTING_GROUPS = [
  "auto", "simple", "standard", "complex", "reasoning", "vision", "audio", "code",
] as const;
export const PROJECT_AGENT_ROLES = [
  "coordinator", "planner", "architect", "designer", "developer",
  "data_engineer", "qa", "security_reviewer", "reviewer", "release_manager",
  // 2026-08-05, see docs/architecture/CHANNEL_AGENT_ROLES_AND_ORCHESTRATION.md
  // -- same shared vocabulary now also used by Agent.default_role and
  // ChatChannelMember.role.
  "documentation",
] as const;
export const LOOP_PHASES = ["documentation", "planning", "implementation", "testing", "review"] as const;

export interface AgentRuntimeProfile {
  id: string;
  agent_id?: string | null;
  sub_agent_id?: string | null;
  name: string;
  runtime_type: typeof RUNTIME_TYPES[number];
  model_ref: string;
  routing_group: typeof FORGEROUTER_ROUTING_GROUPS[number];
  purpose: string;
  intelligence_level: number;
  max_budget_usd?: number | null;
  is_default: boolean;
  is_active: boolean;
}

export interface ForgeRouterVirtualModel {
  id: string;
  routing_group: typeof FORGEROUTER_ROUTING_GROUPS[number];
  description: string;
  is_recommended_default: boolean;
}

export interface ProjectAgentMembership {
  id: string;
  project_id: string;
  agent_id?: string | null;
  sub_agent_id?: string | null;
  role: typeof PROJECT_AGENT_ROLES[number];
  status: string;
  responsibilities?: string | null;
  allowed_runtimes?: string[] | null;
  allocation_percent: number;
  can_review: boolean;
  can_approve: boolean;
}

export interface ProjectLoopPolicy {
  id: string;
  project_id: string;
  name: string;
  phase: typeof LOOP_PHASES[number];
  producer_membership_id: string;
  reviewer_membership_id: string;
  producer_runtime_profile_id: string;
  reviewer_runtime_profile_id: string;
  max_iterations: number;
  min_review_score: number;
  requires_human_approval: boolean;
  auto_dispatch: boolean;
  is_active: boolean;
}

export interface EligibleMembership {
  membership: ProjectAgentMembership;
  eligible: boolean;
  reasons: string[];
}

export interface TaskAssignment {
  id: string;
  task_id: string;
  agent_id?: string | null;
  sub_agent_id?: string | null;
  membership_id?: string | null;
  status: string;
}

export interface DispatchedExecution {
  execution_id: string;
  run_id: string;
  status: string;
  runtime_type: string;
  model_ref: string;
  loop_iteration: number;
}

export interface ExecutionReview {
  id: string;
  execution_id: string;
  reviewer_membership_id: string;
  status: string;
  score?: number | null;
  feedback?: string | null;
  evidence_ref?: string | null;
  runtime_session_ref?: string | null;
}

const ROOT = "/api/v1/orchestration";

export function useForgeRouterVirtualModels() {
  return useQuery({
    queryKey: ["forgerouter-virtual-models"],
    queryFn: () => apiClient.get<ForgeRouterVirtualModel[]>(`${ROOT}/forgerouter-models`),
  });
}

export function useRuntimeProfiles(agentId?: string) {
  return useQuery({
    queryKey: ["runtime-profiles", agentId ?? "all"],
    queryFn: () => apiClient.get<AgentRuntimeProfile[]>(
      `${ROOT}/runtime-profiles${agentId ? `?agent_id=${agentId}` : ""}`
    ),
  });
}

export function useCreateRuntimeProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiClient.post<AgentRuntimeProfile>(`${ROOT}/runtime-profiles`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runtime-profiles"] }),
  });
}

export function useProjectMemberships(projectId?: string) {
  return useQuery({
    queryKey: ["project-memberships", projectId ?? ""],
    queryFn: () => apiClient.get<ProjectAgentMembership[]>(`${ROOT}/projects/${projectId}/memberships`),
    enabled: Boolean(projectId),
  });
}

export function useCreateProjectMembership(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiClient.post<ProjectAgentMembership>(`${ROOT}/projects/${projectId}/memberships`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project-memberships", projectId] }),
  });
}

/** Inverse of useProjectMemberships -- which projects is this agent
 * actually on (2026-08-05, Software Factory visibility fix: backs the
 * agent detail page's "Projetos ativos" section, which didn't exist
 * before). */
export function useAgentMemberships(agentId?: string) {
  return useQuery({
    queryKey: ["agent-memberships", agentId ?? ""],
    queryFn: () => apiClient.get<ProjectAgentMembership[]>(`${ROOT}/agents/${agentId}/memberships`),
    enabled: Boolean(agentId),
  });
}

export function useProjectLoopPolicies(projectId?: string) {
  return useQuery({
    queryKey: ["project-loop-policies", projectId ?? ""],
    queryFn: () => apiClient.get<ProjectLoopPolicy[]>(`${ROOT}/projects/${projectId}/loop-policies`),
    enabled: Boolean(projectId),
  });
}

export function useCreateProjectLoopPolicy(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiClient.post<ProjectLoopPolicy>(`${ROOT}/projects/${projectId}/loop-policies`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["project-loop-policies", projectId] }),
  });
}

export function useEligibleMemberships(taskId?: string) {
  return useQuery({
    queryKey: ["eligible-memberships", taskId ?? ""],
    queryFn: () => apiClient.get<EligibleMembership[]>(`${ROOT}/tasks/${taskId}/eligible-memberships`),
    enabled: Boolean(taskId),
  });
}

export function useTaskAssignments(taskId?: string) {
  return useQuery({
    queryKey: ["task-assignments", taskId ?? ""],
    queryFn: () => apiClient.get<TaskAssignment[]>(`/api/v1/tasks/${taskId}/assignments`),
    enabled: Boolean(taskId),
  });
}

export function useCreateTaskAssignment(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiClient.post<TaskAssignment>(`/api/v1/tasks/${taskId}/assignments`, { task_id: taskId, ...payload }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task-assignments", taskId] });
      qc.invalidateQueries({ queryKey: ["tasks", taskId] });
    },
  });
}

export function useDispatchTask(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      apiClient.post<DispatchedExecution>(`${ROOT}/tasks/${taskId}/dispatch`, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["task-executions", taskId] });
      qc.invalidateQueries({ queryKey: ["tasks", taskId] });
    },
  });
}

export function useRefreshExecution(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (executionId: string) =>
      apiClient.post<Record<string, unknown>>(`${ROOT}/executions/${executionId}/refresh`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task-executions", taskId] }),
  });
}

export function useDispatchExecutionReview(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (executionId: string) =>
      apiClient.post<ExecutionReview>(`${ROOT}/executions/${executionId}/dispatch-review`, {}),
    onSuccess: (_data, executionId) => {
      qc.invalidateQueries({ queryKey: ["execution-reviews", executionId] });
      qc.invalidateQueries({ queryKey: ["task-executions", taskId] });
    },
  });
}

export function useExecutionReviews(executionId?: string) {
  return useQuery({
    queryKey: ["execution-reviews", executionId ?? ""],
    queryFn: () => apiClient.get<ExecutionReview[]>(`${ROOT}/executions/${executionId}/reviews`),
    enabled: Boolean(executionId),
  });
}

export function useRefreshExecutionReview(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewId }: { reviewId: string; executionId: string }) =>
      apiClient.post<ExecutionReview>(`${ROOT}/reviews/${reviewId}/refresh`, {}),
    onSuccess: (_data, { executionId }) => {
      qc.invalidateQueries({ queryKey: ["execution-reviews", executionId] });
      qc.invalidateQueries({ queryKey: ["task-executions", taskId] });
    },
  });
}

export function useDecideExecutionReview(taskId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewId, executionId: _executionId, status, feedback }: { reviewId: string; executionId: string; status: "approved" | "changes_requested"; feedback: string }) =>
      apiClient.patch<ExecutionReview>(`${ROOT}/reviews/${reviewId}`, { status, feedback }),
    onSuccess: (_data, { executionId }) => {
      qc.invalidateQueries({ queryKey: ["execution-reviews", executionId] });
      qc.invalidateQueries({ queryKey: ["task-executions", taskId] });
    },
  });
}
