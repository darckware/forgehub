import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

// z.coerce.number() turns "" into 0 (JS `Number("") === 0`), which would
// silently store an explicit zero for fields the user left blank. Treat
// blank/missing as genuinely absent instead.
const optionalNumber = z.preprocess(
  (value) => (value === "" || value === null || value === undefined ? undefined : value),
  z.coerce.number().optional()
);

/**
 * Project domain (see docs/SPEC.md 4.2 Project Domain):
 *   projects, project_plans, plan_baselines, change_requests
 *
 * Project is the primary entity. It is linked to a product version and
 * carries a nested ProjectPlan (scope/schedule/baseline/estimates).
 */

export const PROJECT_STATUSES = [
  "planned",
  "active",
  "on_hold",
  "completed",
  "cancelled",
] as const;

export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

export const PROJECT_PLAN_STATUSES = ["draft", "approved", "baselined", "superseded"] as const;
export type ProjectPlanStatus = (typeof PROJECT_PLAN_STATUSES)[number];

export const CHANGE_REQUEST_STATUSES = ["pending", "approved", "rejected", "applied"] as const;
export type ChangeRequestStatus = (typeof CHANGE_REQUEST_STATUSES)[number];

export const projectPlanSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  name: z.string(),
  scope_summary: z.string().nullable().optional(),
  estimated_start_date: z.string().nullable().optional(),
  estimated_end_date: z.string().nullable().optional(),
  estimated_cost: z.number().nullable().optional(),
  status: z.enum(PROJECT_PLAN_STATUSES),
  approved_at: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type ProjectPlan = z.infer<typeof projectPlanSchema>;

export const projectPlanCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  scope_summary: z.string().optional().or(z.literal("")),
  estimated_start_date: z.string().optional().or(z.literal("")),
  estimated_end_date: z.string().optional().or(z.literal("")),
  estimated_cost: optionalNumber,
});

export type ProjectPlanCreateInput = z.infer<typeof projectPlanCreateSchema>;

export const planBaselineSchema = z.object({
  id: z.string(),
  project_plan_id: z.string(),
  name: z.string(),
  scope_snapshot: z.string().nullable().optional(),
  cost_snapshot: z.number().nullable().optional(),
  end_date_snapshot: z.string().nullable().optional(),
  frozen_at: z.string(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type PlanBaseline = z.infer<typeof planBaselineSchema>;

export const planBaselineCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
});

export type PlanBaselineCreateInput = z.infer<typeof planBaselineCreateSchema>;

export const changeRequestSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  plan_baseline_id: z.string().nullable().optional(),
  title: z.string(),
  justification: z.string().nullable().optional(),
  affects_scope: z.boolean(),
  affects_schedule: z.boolean(),
  affects_cost: z.boolean(),
  adds_features: z.boolean(),
  removes_features: z.boolean(),
  introduces_critical_bug_fix: z.boolean(),
  changes_agents: z.boolean(),
  changes_skills: z.boolean(),
  changes_architecture: z.boolean(),
  changes_security: z.boolean(),
  schedule_delta_days: z.number().nullable().optional(),
  cost_delta: z.number().nullable().optional(),
  requested_by: z.string().nullable().optional(),
  status: z.enum(CHANGE_REQUEST_STATUSES),
  decided_at: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type ChangeRequest = z.infer<typeof changeRequestSchema>;

export const CHANGE_REQUEST_IMPACT_FLAGS = [
  { key: "affects_scope", label: "Affects scope" },
  { key: "affects_schedule", label: "Affects schedule" },
  { key: "affects_cost", label: "Affects cost" },
  { key: "adds_features", label: "Adds features" },
  { key: "removes_features", label: "Removes features" },
  { key: "introduces_critical_bug_fix", label: "Critical bug fix" },
  { key: "changes_agents", label: "Changes agents" },
  { key: "changes_skills", label: "Changes skills" },
  { key: "changes_architecture", label: "Changes architecture" },
  { key: "changes_security", label: "Changes security" },
] as const satisfies readonly { key: keyof ChangeRequest; label: string }[];

export const changeRequestCreateSchema = z
  .object({
    title: z.string().min(1, "Title is required").max(255),
    justification: z.string().optional().or(z.literal("")),
    plan_baseline_id: z.string().optional().or(z.literal("")),
    affects_scope: z.boolean().default(false),
    affects_schedule: z.boolean().default(false),
    affects_cost: z.boolean().default(false),
    adds_features: z.boolean().default(false),
    removes_features: z.boolean().default(false),
    introduces_critical_bug_fix: z.boolean().default(false),
    changes_agents: z.boolean().default(false),
    changes_skills: z.boolean().default(false),
    changes_architecture: z.boolean().default(false),
    changes_security: z.boolean().default(false),
    schedule_delta_days: optionalNumber,
    cost_delta: optionalNumber,
    requested_by: z.string().optional().or(z.literal("")),
  })
  .refine(
    (values) =>
      CHANGE_REQUEST_IMPACT_FLAGS.some((flag) => values[flag.key as keyof typeof values]),
    { message: "Select at least one impact flag", path: ["affects_scope"] }
  );

export type ChangeRequestCreateInput = z.infer<typeof changeRequestCreateSchema>;

export const changeRequestUpdateSchema = z.object({
  title: z.string().min(1).max(255).optional(),
  justification: z.string().optional(),
  plan_baseline_id: z.string().optional(),
  affects_scope: z.boolean().optional(),
  affects_schedule: z.boolean().optional(),
  affects_cost: z.boolean().optional(),
  adds_features: z.boolean().optional(),
  removes_features: z.boolean().optional(),
  introduces_critical_bug_fix: z.boolean().optional(),
  changes_agents: z.boolean().optional(),
  changes_skills: z.boolean().optional(),
  changes_architecture: z.boolean().optional(),
  changes_security: z.boolean().optional(),
  schedule_delta_days: z.number().optional(),
  cost_delta: z.number().optional(),
  requested_by: z.string().optional(),
  status: z.enum(CHANGE_REQUEST_STATUSES).optional(),
});

export type ChangeRequestUpdateInput = z.infer<typeof changeRequestUpdateSchema>;

export const projectSchema = z.object({
  id: z.string(),
  name: z.string().min(1, "Name is required"),
  description: z.string().nullable().optional(),
  product_version_id: z.string().nullable().optional(),
  status: z.enum(PROJECT_STATUSES).default("planned"),
  working_directory_path: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type Project = z.infer<typeof projectSchema>;

// Payload schemas (what the create/edit form submits).
export const projectCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(200, "Name is too long"),
  description: z.string().max(2000, "Description is too long").optional().or(z.literal("")),
  product_version_id: z.string().min(1, "Product version is required"),
  status: z.enum(PROJECT_STATUSES).default("planned"),
  working_directory_path: z.string().max(1024, "Path is too long").optional().or(z.literal("")),
});

export type ProjectCreateInput = z.infer<typeof projectCreateSchema>;

export const projectUpdateSchema = projectCreateSchema.partial();
export type ProjectUpdateInput = z.infer<typeof projectUpdateSchema>;

// ---------------------------------------------------------------------------
// ProjectStructureNode
// ---------------------------------------------------------------------------

export const STRUCTURE_NODE_TYPES = [
  "folder",
  "module",
  "component",
  "screen",
  "table",
  "stored_procedure",
] as const;

export type StructureNodeType = (typeof STRUCTURE_NODE_TYPES)[number];

export const structureNodeSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  parent_node_id: z.string().nullable().optional(),
  name: z.string(),
  node_type: z.enum(STRUCTURE_NODE_TYPES),
  path: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  is_locked: z.boolean().default(false),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type StructureNode = z.infer<typeof structureNodeSchema>;

export const structureNodeCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  node_type: z.enum(STRUCTURE_NODE_TYPES),
  parent_node_id: z.string().optional().or(z.literal("")),
  path: z.string().max(1024).optional().or(z.literal("")),
  description: z.string().optional().or(z.literal("")),
  is_locked: z.boolean().optional().default(false),
});

export type StructureNodeCreateInput = z.infer<typeof structureNodeCreateSchema>;

export const structureNodeUpdateSchema = structureNodeCreateSchema.partial();
export type StructureNodeUpdateInput = z.infer<typeof structureNodeUpdateSchema>;

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const projectKeys = {
  all: ["projects"] as const,
  detail: (id: string) => ["projects", id] as const,
};

export const projectPlanKeys = {
  byProject: (projectId: string) => ["projects", projectId, "plans"] as const,
};

export const planBaselineKeys = {
  byProject: (projectId: string) => ["projects", projectId, "baselines"] as const,
};

export const changeRequestKeys = {
  byProject: (projectId: string) => ["projects", projectId, "change-requests"] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useProjects() {
  return useQuery({
    queryKey: projectKeys.all,
    queryFn: () => apiClient.get<Project[]>("/api/v1/projects"),
  });
}

export function useProject(id: string | undefined) {
  return useQuery({
    queryKey: projectKeys.detail(id ?? ""),
    queryFn: () => apiClient.get<Project>(`/api/v1/projects/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectCreateInput) => apiClient.post<Project>("/api/v1/projects", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

export function useUpdateProject(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    // Backend only exposes PATCH /api/v1/projects/{id} (no PUT route).
    mutationFn: (payload: ProjectUpdateInput) => apiClient.patch<Project>(`/api/v1/projects/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectKeys.all });
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(id) });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`/api/v1/projects/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// ProjectPlan hooks
// ---------------------------------------------------------------------------

export function useProjectPlans(projectId: string | undefined) {
  return useQuery({
    queryKey: projectPlanKeys.byProject(projectId ?? ""),
    queryFn: () => apiClient.get<ProjectPlan[]>(`/api/v1/projects/${projectId}/plans`),
    enabled: Boolean(projectId),
  });
}

export function useCreateProjectPlan(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectPlanCreateInput) =>
      apiClient.post<ProjectPlan>(`/api/v1/projects/${projectId}/plans`, {
        ...payload,
        scope_summary: payload.scope_summary || undefined,
        estimated_start_date: payload.estimated_start_date || undefined,
        estimated_end_date: payload.estimated_end_date || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectPlanKeys.byProject(projectId) });
    },
  });
}

export function useApproveProjectPlan(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) =>
      apiClient.post<ProjectPlan>(`/api/v1/projects/plans/${planId}/approve`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectPlanKeys.byProject(projectId) });
    },
  });
}

// ---------------------------------------------------------------------------
// PlanBaseline hooks
// ---------------------------------------------------------------------------

export function usePlanBaselines(projectId: string | undefined) {
  return useQuery({
    queryKey: planBaselineKeys.byProject(projectId ?? ""),
    queryFn: () => apiClient.get<PlanBaseline[]>(`/api/v1/projects/${projectId}/baselines`),
    enabled: Boolean(projectId),
  });
}

export function useCreatePlanBaseline(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PlanBaselineCreateInput & { project_plan_id: string }) =>
      apiClient.post<PlanBaseline>(`/api/v1/projects/${projectId}/baselines`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: planBaselineKeys.byProject(projectId) });
      queryClient.invalidateQueries({ queryKey: projectPlanKeys.byProject(projectId) });
    },
  });
}

// ---------------------------------------------------------------------------
// ChangeRequest hooks
// ---------------------------------------------------------------------------

export function useChangeRequests(projectId: string | undefined) {
  return useQuery({
    queryKey: changeRequestKeys.byProject(projectId ?? ""),
    queryFn: () => apiClient.get<ChangeRequest[]>(`/api/v1/projects/${projectId}/change-requests`),
    enabled: Boolean(projectId),
  });
}

export function useCreateChangeRequest(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ChangeRequestCreateInput) =>
      apiClient.post<ChangeRequest>(`/api/v1/projects/${projectId}/change-requests`, {
        ...payload,
        justification: payload.justification || undefined,
        plan_baseline_id: payload.plan_baseline_id || undefined,
        requested_by: payload.requested_by || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: changeRequestKeys.byProject(projectId) });
    },
  });
}

export function useUpdateChangeRequest(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: ChangeRequestUpdateInput }) =>
      apiClient.patch<ChangeRequest>(`/api/v1/projects/change-requests/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: changeRequestKeys.byProject(projectId) });
    },
  });
}

export function useDeleteChangeRequest(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (crId: string) =>
      apiClient.delete(`/api/v1/projects/change-requests/${crId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: changeRequestKeys.byProject(projectId) });
    },
  });
}

// ---------------------------------------------------------------------------
// ProjectStructureNode hooks
// ---------------------------------------------------------------------------

export const structureNodeKeys = {
  byProject: (projectId: string) => ["projects", projectId, "structure-nodes"] as const,
};

export function useStructureNodes(projectId: string | undefined) {
  return useQuery({
    queryKey: structureNodeKeys.byProject(projectId ?? ""),
    queryFn: () => apiClient.get<StructureNode[]>(`/api/v1/projects/${projectId}/structure-nodes`),
    enabled: Boolean(projectId),
  });
}

export function useCreateStructureNode(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: StructureNodeCreateInput) =>
      apiClient.post<StructureNode>(`/api/v1/projects/${projectId}/structure-nodes`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: structureNodeKeys.byProject(projectId) });
    },
  });
}

export function useUpdateStructureNode(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ nodeId, payload }: { nodeId: string; payload: StructureNodeUpdateInput }) =>
      apiClient.patch<StructureNode>(`/api/v1/projects/structure-nodes/${nodeId}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: structureNodeKeys.byProject(projectId) });
    },
  });
}

export function useDeleteStructureNode(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (nodeId: string) =>
      apiClient.delete<void>(`/api/v1/projects/structure-nodes/${nodeId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: structureNodeKeys.byProject(projectId) });
    },
  });
}
