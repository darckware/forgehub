import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Artifact domain (see docs/SPEC.md 4.7 Artifact Domain):
 *   artifacts, artifact_versions
 *
 * Primary entity: Artifact. An Artifact represents any formal deliverable
 * produced in the project -- PRD, SPEC, DATA SPEC, SECURITY SPEC, source
 * code, migration, test report, release notes, pull request, deployment
 * package, or approval record (PRD.md 5.7). Artifacts link to task
 * executions and pipeline stages, and a stage cannot complete while its
 * required artifacts are missing (SPEC.md 5.6 / 6.2). Each Artifact carries
 * a nested ordered list of ArtifactVersion records capturing every revision
 * of the deliverable over time.
 *
 * Backend contract: /api/v1/artifacts (list/create/get/update/delete).
 */

export const ARTIFACT_TYPES = [
  "prd",
  "spec",
  "data_spec",
  "business_rule_spec",
  "security_spec",
  "source_code",
  "migration",
  "test_report",
  "release_notes",
  "pull_request",
  "deployment_package",
  "approval_record",
  "screen",
  "component",
  "report",
  "database_schema",
  "table",
  "stored_procedure",
  "reference_doc",
  "context_brief",
  "other",
] as const;

export type ArtifactType = (typeof ARTIFACT_TYPES)[number];

export const ARTIFACT_STATUSES = [
  "draft",
  "in_review",
  "approved",
  "rejected",
  "superseded",
] as const;

export type ArtifactStatus = (typeof ARTIFACT_STATUSES)[number];

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

export const artifactVersionSchema = z.object({
  id: z.string(),
  artifact_id: z.string(),
  version: z.string(),
  content_url: z.string().nullable().optional(),
  checksum: z.string().nullable().optional(),
  notes: z.string().nullable().optional(),
  is_current: z.boolean().optional().default(false),
  created_at: z.string().optional(),
});

export type ArtifactVersion = z.infer<typeof artifactVersionSchema>;

export const artifactSchema = z.object({
  id: z.string(),
  name: z.string(),
  artifact_type: z.enum(ARTIFACT_TYPES).default("other"),
  status: z.enum(ARTIFACT_STATUSES).default("draft"),
  description: z.string().nullable().optional(),
  project_id: z.string().nullable().optional(),
  pipeline_stage_id: z.string().nullable().optional(),
  task_execution_id: z.string().nullable().optional(),
  is_locked: z.boolean().optional().default(false),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  versions: z.array(artifactVersionSchema).optional().default([]),
});

export type Artifact = z.infer<typeof artifactSchema>;

// Payload schemas (what the create/edit form submits).
export const artifactCreateSchema = z.object({
  name: z.string().min(1, "Name is required").max(200, "Name is too long"),
  artifact_type: z.enum(ARTIFACT_TYPES).default("other"),
  status: z.enum(ARTIFACT_STATUSES).default("draft"),
  description: z.string().max(2000, "Description is too long").optional().or(z.literal("")),
  project_id: z.string().optional().or(z.literal("")),
  pipeline_stage_id: z.string().optional().or(z.literal("")),
  task_execution_id: z.string().optional().or(z.literal("")),
  is_locked: z.boolean().optional().default(false),
});

export type ArtifactCreateInput = z.infer<typeof artifactCreateSchema>;

export const artifactUpdateSchema = artifactCreateSchema.partial();
export type ArtifactUpdateInput = z.infer<typeof artifactUpdateSchema>;

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const artifactKeys = {
  all: ["artifacts"] as const,
  detail: (id: string) => ["artifacts", id] as const,
};

const RESOURCE = "/api/v1/artifacts";

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useArtifacts() {
  return useQuery({
    queryKey: artifactKeys.all,
    queryFn: () => apiClient.get<Artifact[]>(RESOURCE),
  });
}

export function useArtifact(id: string | undefined) {
  return useQuery({
    queryKey: artifactKeys.detail(id ?? ""),
    queryFn: () => apiClient.get<Artifact>(`${RESOURCE}/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateArtifact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ArtifactCreateInput) => apiClient.post<Artifact>(RESOURCE, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all });
    },
  });
}

export function useUpdateArtifact(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ArtifactUpdateInput) =>
      apiClient.patch<Artifact>(`${RESOURCE}/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all });
      queryClient.invalidateQueries({ queryKey: artifactKeys.detail(id) });
    },
  });
}

export function useDeleteArtifact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: artifactKeys.all });
    },
  });
}
