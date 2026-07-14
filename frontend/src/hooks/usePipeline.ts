import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Pipeline domain (see docs/SPEC.md 4.3 Pipeline Domain):
 *   pipeline_templates, pipeline_template_stages, pipeline_template_required_artifacts,
 *   project_pipelines, pipeline_stages, pipeline_stage_dependencies,
 *   pipeline_stage_required_artifacts, pipeline_stage_gates
 *
 * Primary entity: ProjectPipeline. Every project must have an active pipeline
 * (PRD.md 5.5 / SPEC.md 6.2). A ProjectPipeline carries a nested ordered list
 * of PipelineStage, each of which may declare required artifacts and gates
 * (human approval / independent verification) that block completion and
 * advancement of dependent stages until satisfied.
 *
 * Backend contract: /api/v1/pipelines (list/create/get/update/delete).
 */

export const PIPELINE_STATUSES = ["draft", "active", "paused", "completed", "archived"] as const;
export type PipelineStatus = (typeof PIPELINE_STATUSES)[number];

export const STAGE_STATUSES = [
  "pending",
  "in_progress",
  "blocked",
  "completed",
  "skipped",
] as const;
export type StageStatus = (typeof STAGE_STATUSES)[number];

export const STAGE_TYPES = [
  "discovery",
  "spec",
  "architecture_review",
  "implementation",
  "migration",
  "testing",
  "build",
  "release_notes",
  "deployment_package",
  "release_approval",
  "other",
] as const;
export type StageType = (typeof STAGE_TYPES)[number];

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

export const stageRequiredArtifactSchema = z.object({
  id: z.string(),
  stage_id: z.string(),
  artifact_type: z.string(),
  artifact_id: z.string().nullable().optional(),
  is_mandatory: z.boolean().default(true),
  is_fulfilled: z.boolean().default(false),
});

export type StageRequiredArtifact = z.infer<typeof stageRequiredArtifactSchema>;

export const stageGateSchema = z.object({
  id: z.string(),
  stage_id: z.string(),
  name: z.string(),
  gate_type: z.string(),
  is_mandatory: z.boolean().default(true),
  status: z.string(),
  approved_by: z.string().nullable().optional(),
});

export type StageGate = z.infer<typeof stageGateSchema>;

export const pipelineStageSchema = z.object({
  id: z.string(),
  pipeline_id: z.string(),
  name: z.string(),
  stage_type: z.enum(STAGE_TYPES).optional(),
  order_index: z.number().int(),
  status: z.enum(STAGE_STATUSES).default("pending"),
  revision: z.number().int().default(1),
  requires_approval: z.boolean().optional().default(false),
  requires_verification: z.boolean().optional().default(false),
  depends_on_stage_ids: z.array(z.string()).optional().default([]),
  required_artifacts: z.array(stageRequiredArtifactSchema).optional().default([]),
  gates: z.array(stageGateSchema).optional().default([]),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type PipelineStage = z.infer<typeof pipelineStageSchema>;

export const projectPipelineSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  name: z.string(),
  template_id: z.string().nullable().optional(),
  status: z.enum(PIPELINE_STATUSES).default("draft"),
  is_active: z.boolean().optional().default(true),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  stages: z.array(pipelineStageSchema).optional().default([]),
});

export type ProjectPipeline = z.infer<typeof projectPipelineSchema>;

// Payload schemas (what the create/edit form submits).
export const pipelineCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(200, "Name is too long"),
  project_id: z.string().min(1, "Project is required"),
  pipeline_template_id: z.string().optional().or(z.literal("")),
  status: z.enum(PIPELINE_STATUSES).default("draft"),
  is_active: z.boolean().optional().default(true),
});

export type PipelineCreateInput = z.infer<typeof pipelineCreateSchema>;

export const pipelineUpdateSchema = pipelineCreateSchema.partial();
export type PipelineUpdateInput = z.infer<typeof pipelineUpdateSchema>;

export const pipelineTemplateSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type PipelineTemplate = z.infer<typeof pipelineTemplateSchema>;

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const pipelineKeys = {
  all: ["pipelines"] as const,
  detail: (id: string) => ["pipelines", id] as const,
  templates: ["pipeline-templates"] as const,
  progress: (projectId: string) => ["project-progress", projectId] as const,
  timeline: (projectId: string) => ["project-progress", projectId, "timeline"] as const,
};

const RESOURCE = "/api/v1/pipelines";

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function usePipelines() {
  return useQuery({
    queryKey: pipelineKeys.all,
    queryFn: () => apiClient.get<ProjectPipeline[]>(RESOURCE),
  });
}

export function usePipeline(id: string | undefined) {
  return useQuery({
    queryKey: pipelineKeys.detail(id ?? ""),
    queryFn: () => apiClient.get<ProjectPipeline>(`${RESOURCE}/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreatePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PipelineCreateInput) => apiClient.post<ProjectPipeline>(RESOURCE, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.all });
    },
  });
}

export function useUpdatePipeline(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PipelineUpdateInput) =>
      apiClient.patch<ProjectPipeline>(`${RESOURCE}/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.all });
      queryClient.invalidateQueries({ queryKey: pipelineKeys.detail(id) });
    },
  });
}

export function useDeletePipeline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.all });
    },
  });
}

export function usePipelineTemplates() {
  return useQuery({
    queryKey: pipelineKeys.templates,
    queryFn: () => apiClient.get<PipelineTemplate[]>(`${RESOURCE}/templates`),
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; description?: string; is_active?: boolean }) =>
      apiClient.post<PipelineTemplate>(`${RESOURCE}/templates`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: pipelineKeys.templates }),
  });
}

export function useUpdateTemplate(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name?: string; description?: string; is_active?: boolean }) =>
      apiClient.patch<PipelineTemplate>(`${RESOURCE}/templates/${id}`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: pipelineKeys.templates }),
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/templates/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: pipelineKeys.templates }),
  });
}

export interface TemplateStage {
  id: string;
  template_id: string;
  name: string;
  stage_type: string;
  order_index: number;
  requires_approval: boolean;
  requires_verification: boolean;
}

export function useTemplateStages(templateId: string) {
  return useQuery({
    queryKey: ["template-stages", templateId],
    queryFn: () => apiClient.get<TemplateStage[]>(`${RESOURCE}/template-stages`, { params: { template_id: templateId } }),
    enabled: Boolean(templateId),
  });
}

export function useCreateTemplateStage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { template_id: string; name: string; stage_type: string; order_index: number; requires_approval?: boolean; requires_verification?: boolean }) =>
      apiClient.post<TemplateStage>(`${RESOURCE}/template-stages`, payload),
    onSuccess: (_data, vars) => qc.invalidateQueries({ queryKey: ["template-stages", vars.template_id] }),
  });
}

export function useUpdateTemplateStage(templateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; name?: string; stage_type?: string; order_index?: number; requires_approval?: boolean; requires_verification?: boolean }) =>
      apiClient.patch<TemplateStage>(`${RESOURCE}/template-stages/${id}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["template-stages", templateId] }),
  });
}

export function useDeleteTemplateStage(templateId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/template-stages/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["template-stages", templateId] }),
  });
}

export function useImportPipelineAsTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: { pipeline_id: string; name: string; description?: string }) =>
      apiClient.post<PipelineTemplate>(`${RESOURCE}/import-as-template`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: pipelineKeys.templates }),
  });
}

// ---------------------------------------------------------------------------
// Stage CRUD
// ---------------------------------------------------------------------------

export const stageCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  stage_type: z.enum(STAGE_TYPES),
  order_index: z.coerce.number().int().min(0),
  status: z.enum(STAGE_STATUSES).default("pending"),
  requires_approval: z.boolean().default(false),
  requires_verification: z.boolean().default(false),
});

export type StageCreateInput = z.infer<typeof stageCreateSchema>;

export function useCreateStage(pipelineId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: StageCreateInput) =>
      apiClient.post<PipelineStage>(`${RESOURCE}/${pipelineId}/stages`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.detail(pipelineId) });
    },
  });
}

export function useUpdateStage(pipelineId: string, stageId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<StageCreateInput>) =>
      apiClient.patch<PipelineStage>(`${RESOURCE}/stages/${stageId}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.detail(pipelineId) });
    },
  });
}

export function useDeleteStage(pipelineId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (stageId: string) =>
      apiClient.delete<void>(`${RESOURCE}/stages/${stageId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: pipelineKeys.detail(pipelineId) });
    },
  });
}

export function usePipelineGate(gateId: string | undefined) {
  return useQuery({
    queryKey: ["pipeline-gate", gateId],
    queryFn: () => apiClient.get<StageGate>(`/api/v1/pipelines/gates/${gateId}`),
    enabled: Boolean(gateId),
    staleTime: 300_000,
  });
}

export function useAllGates() {
  return useQuery({
    queryKey: ["pipeline-gates", "all"],
    queryFn: () => apiClient.get<StageGate[]>("/api/v1/pipelines/gates"),
    staleTime: 60_000,
  });
}

export interface ProgressCheckpoint {
  id: string;
  project_id: string;
  pipeline_stage_id: string | null;
  task_id: string | null;
  task_execution_id: string | null;
  sequence: number;
  checkpoint_type: string;
  step_key: string;
  step_label: string;
  evidence_refs: string[];
  last_confirmed_at: string;
  resume_from_step_key: string | null;
  blocker_code: string | null;
  error_code: string | null;
  message: string | null;
  actor_name: string;
}

export interface StageCompletionAssessment {
  id: string;
  pipeline_stage_id: string;
  stage_revision: number;
  input_hash: string;
  result: "ready" | "not_ready" | "stale";
  requirement_results: Array<{ key: string; kind: string; label: string; passed: boolean; value?: unknown }>;
  missing_requirements: Array<{ key: string; kind: string; label: string; passed: boolean; value?: unknown }>;
  blocking_reasons: Array<{ code: string; message?: string; resume_from?: string }>;
  evidence_refs: string[];
  evaluated_at: string;
}

export interface StageProgress {
  stage_id: string;
  pipeline_id: string;
  stage_name: string;
  order_index: number;
  effective_status: string;
  requirement_total: number;
  requirement_completed: number;
  missing_requirements: StageCompletionAssessment["missing_requirements"];
  last_checkpoint: ProgressCheckpoint | null;
  stopped_reason: string | null;
  resume_from: string | null;
  completion_assessment: StageCompletionAssessment | null;
}

export interface ProjectProgress {
  project_id: string;
  macroflow: "conception" | "delivery" | "operations";
  pipeline_id: string | null;
  current_stage_id: string | null;
  stages: StageProgress[];
  last_confirmed_at: string | null;
  stopped_at: { checkpoint_id: string; type: string; step_key: string; step_label: string; reason: string | null; task_execution_id: string | null } | null;
  first_safe_action: string | null;
}

export function useProjectProgress(projectId: string | undefined) {
  return useQuery({
    queryKey: pipelineKeys.progress(projectId ?? ""),
    queryFn: () => apiClient.get<ProjectProgress>(`/api/v1/projects/${projectId}/progress`),
    enabled: Boolean(projectId),
    refetchInterval: 30_000,
  });
}

export function useProgressTimeline(projectId: string | undefined) {
  return useQuery({
    queryKey: pipelineKeys.timeline(projectId ?? ""),
    queryFn: () => apiClient.get<ProgressCheckpoint[]>(`/api/v1/projects/${projectId}/progress-timeline`),
    enabled: Boolean(projectId),
  });
}

export function useEvaluateStageCompletion(projectId: string, stageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<StageCompletionAssessment>(`/api/v1/pipeline-stages/${stageId}:evaluate-completion`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: pipelineKeys.progress(projectId) }),
  });
}

export function useCompleteStage(projectId: string, pipelineId: string, stageId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assessmentId: string) => apiClient.post(`/api/v1/pipeline-stages/${stageId}:complete`, {
      assessment_id: assessmentId,
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: pipelineKeys.progress(projectId) });
      qc.invalidateQueries({ queryKey: pipelineKeys.detail(pipelineId) });
      qc.invalidateQueries({ queryKey: pipelineKeys.timeline(projectId) });
    },
  });
}
