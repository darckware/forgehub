import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Backlog domain (see docs/SPEC.md 4.4 Backlog Domain / PRD.md 5.8, 6.1, 6.2):
 *   planning_items, feature_requests, bug_reports, version_scope_items, triage_decisions
 *
 * PlanningItem is the primary entity. FeatureRequest and BugReport are
 * specializations of a PlanningItem, distinguished by `item_type` and
 * carrying type-specific fields (severity/environment for bugs,
 * acceptance criteria for features). VersionScopeItem links a planning
 * item into a target product version's scope; TriageDecision records the
 * outcome of triaging a bug/feature into (or out of) scope.
 *
 * Backend contract: /api/v1/planning-items (list/create/get/update/delete).
 */

export const PLANNING_ITEM_TYPES = [
  "feature",
  "bug",
  "hotfix",
  "improvement",
  "technical_debt",
  "refactoring",
  "security_fix",
  "research",
  "documentation",
] as const;

export type PlanningItemType = (typeof PLANNING_ITEM_TYPES)[number];

export const PLANNING_ITEM_STATUSES = [
  "new",
  "triaged",
  "scoped",
  "in_progress",
  "blocked",
  "done",
  "rejected",
] as const;

export type PlanningItemStatus = (typeof PLANNING_ITEM_STATUSES)[number];

export const PLANNING_ITEM_PRIORITIES = ["low", "medium", "high", "critical"] as const;

export type PlanningItemPriority = (typeof PLANNING_ITEM_PRIORITIES)[number];

export const BUG_SEVERITIES = ["low", "medium", "high", "critical"] as const;

export type BugSeverity = (typeof BUG_SEVERITIES)[number];

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

export const featureRequestSchema = z.object({
  id: z.string(),
  planning_item_id: z.string(),
  acceptance_criteria: z.string().nullable().optional(),
  requested_by: z.string().nullable().optional(),
  business_value: z.string().nullable().optional(),
});

export type FeatureRequest = z.infer<typeof featureRequestSchema>;

export const bugReportSchema = z.object({
  id: z.string(),
  planning_item_id: z.string(),
  severity: z.enum(BUG_SEVERITIES).optional(),
  environment: z.string().nullable().optional(),
  detected_in_version: z.string().nullable().optional(),
  fixed_in_version: z.string().nullable().optional(),
  steps_to_reproduce: z.string().nullable().optional(),
});

export type BugReport = z.infer<typeof bugReportSchema>;

export const versionScopeItemSchema = z.object({
  id: z.string(),
  planning_item_id: z.string(),
  product_version_id: z.string(),
  added_at: z.string().optional(),
  removed_at: z.string().nullable().optional(),
});

export type VersionScopeItem = z.infer<typeof versionScopeItemSchema>;

export const triageDecisionSchema = z.object({
  id: z.string(),
  planning_item_id: z.string(),
  decision: z.string(),
  rationale: z.string().nullable().optional(),
  decided_by: z.string().nullable().optional(),
  decided_at: z.string().optional(),
});

export type TriageDecision = z.infer<typeof triageDecisionSchema>;

export const planningItemSchema = z.object({
  id: z.string(),
  title: z.string(),
  description: z.string().nullable().optional(),
  item_type: z.enum(PLANNING_ITEM_TYPES),
  status: z.enum(PLANNING_ITEM_STATUSES).default("new"),
  priority: z.enum(PLANNING_ITEM_PRIORITIES).default("medium"),
  product_version_id: z.string().nullable().optional(),
  project_id: z.string().nullable().optional(),
  // Relative path within the project's working directory where this item's
  // output should be written (e.g. "docs/api.md", "src/auth/").
  output_path: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  feature_request: featureRequestSchema.nullable().optional(),
  bug_report: bugReportSchema.nullable().optional(),
  version_scope_items: z.array(versionScopeItemSchema).optional().default([]),
  triage_decisions: z.array(triageDecisionSchema).optional().default([]),
});

export type PlanningItem = z.infer<typeof planningItemSchema>;

// Payload schema (what the create/edit form submits).
export const planningItemCreateSchema = z.object({
  title: z.string().min(1, "Title is required").max(200, "Title is too long"),
  description: z.string().max(4000, "Description is too long").optional().or(z.literal("")),
  item_type: z.enum(PLANNING_ITEM_TYPES).default("feature"),
  status: z.enum(PLANNING_ITEM_STATUSES).default("new"),
  priority: z.enum(PLANNING_ITEM_PRIORITIES).default("medium"),
  product_version_id: z.string().optional().or(z.literal("")),
  project_id: z.string().min(1, "Project is required"),
  // Relative output path within the project's working directory.
  output_path: z.string().max(1024).optional().or(z.literal("")),
  // Bug-specific (only meaningful when item_type === "bug" / "hotfix")
  severity: z.enum(BUG_SEVERITIES).optional().or(z.literal("")),
  environment: z.string().max(500).optional().or(z.literal("")),
  detected_in_version: z.string().max(100).optional().or(z.literal("")),
});

export type PlanningItemCreateInput = z.infer<typeof planningItemCreateSchema>;

export const planningItemUpdateSchema = planningItemCreateSchema.partial();
export type PlanningItemUpdateInput = z.infer<typeof planningItemUpdateSchema>;

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const planningItemKeys = {
  all: ["planning-items"] as const,
  detail: (id: string) => ["planning-items", id] as const,
};

const RESOURCE = "/api/v1/planning-items";

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function usePlanningItems(projectId?: string) {
  return useQuery({
    queryKey: projectId ? [...planningItemKeys.all, "project", projectId] : planningItemKeys.all,
    queryFn: () =>
      apiClient.get<PlanningItem[]>(projectId ? `${RESOURCE}?project_id=${projectId}` : RESOURCE),
  });
}

export function useDeletePlanningItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, cascadeTasks = false }: { id: string; cascadeTasks?: boolean }) =>
      apiClient.delete(`${RESOURCE}/${id}${cascadeTasks ? "?cascade_tasks=true" : ""}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: planningItemKeys.all });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export function usePlanningItem(id: string | undefined) {
  return useQuery({
    queryKey: planningItemKeys.detail(id ?? ""),
    queryFn: () => apiClient.get<PlanningItem>(`${RESOURCE}/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreatePlanningItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PlanningItemCreateInput) =>
      apiClient.post<PlanningItem>(RESOURCE, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: planningItemKeys.all });
    },
  });
}

export function useUpdatePlanningItem(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PlanningItemUpdateInput) =>
      apiClient.put<PlanningItem>(`${RESOURCE}/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: planningItemKeys.all });
      queryClient.invalidateQueries({ queryKey: planningItemKeys.detail(id) });
    },
  });
}
