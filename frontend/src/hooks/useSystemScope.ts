import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface DevelopmentRequest {
  id: string; product_id: string; title: string; description: string;
  requested_by: string | null; priority: string; status: string; created_at: string;
}
export type TechStackLayer = "frontend" | "backend" | "database" | "deploy_infra";
export interface TechStackDecision {
  layer: TechStackLayer; decision: string; rationale: string | null;
}
export interface ConceptRevision {
  id: string; revision: number; problem_statement: string; vision: string | null;
  scope_summary: string | null; created_by: string | null; created_at: string;
  project_description: string | null; working_directory_path: string | null;
  tech_stack_decisions: TechStackDecision[] | null;
}
export interface ConceptDetail {
  concept: { id: string; product_id: string; status: string; current_revision_id: string | null };
  current_revision: ConceptRevision | null; revisions: ConceptRevision[];
}
export interface IdeaCreatedResult {
  product_id: string;
  concept: { id: string; product_id: string; status: string; current_revision_id: string | null };
}
export interface BlueprintRevision {
  id: string; revision: number; status: string; concept_revision_id: string | null;
  product_version_id: string | null; content_hash: string | null;
}
export interface BlueprintDetail {
  blueprint: { id: string; product_id: string; name: string; current_revision_id: string | null };
  current_revision: BlueprintRevision | null; revisions: BlueprintRevision[];
}
export interface SystemElement {
  id: string; stable_key: string; family: string; element_type: string; name: string;
  description: string | null; criticality: string; parent_id: string | null;
}
export interface BlueprintGraph {
  revision: BlueprintRevision;
  elements: { element: SystemElement; revision: { id: string; spec_snapshot: Record<string, unknown> } }[];
  relations: { id: string; from_element_id: string; to_element_id: string; relation_type: string }[];
}
export interface ProjectScope {
  id: string; project_id: string; blueprint_base_revision_id: string;
  revision: number; status: string; created_by: string | null;
}
export interface ScopeItem {
  id: string; system_element_id: string; change_type: string; applicability: string;
  rationale: string | null; acceptance_criteria: { id: string; criterion: string }[];
}
export interface TechStackOption {
  id: string; layer: TechStackLayer; name: string; description: string | null;
  source: "org_standard" | "custom";
  /** Only meaningful for layer="frontend" -- a frontend scenario/toolchain,
   * not a separate layer. Null for every other layer and for an
   * unclassified frontend option. */
  platform: "web_app" | "landing_page" | "institutional_site" | "pwa" | "mobile" | null;
}
export const TECH_STACK_PLATFORMS = ["web_app", "landing_page", "institutional_site", "pwa", "mobile"] as const;
export type TechStackPlatform = (typeof TECH_STACK_PLATFORMS)[number];

export function useTechStackOptions(layer: TechStackLayer) {
  return useQuery({
    queryKey: ["tech-stack-options", layer],
    queryFn: () => apiClient.get<TechStackOption[]>(`/api/v1/tech-stack-options?layer=${layer}`),
  });
}
export function useCreateTechStackOption() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { layer: TechStackLayer; name: string; description?: string }) =>
      apiClient.post<TechStackOption>("/api/v1/tech-stack-options", payload),
    onSuccess: (data) => client.invalidateQueries({ queryKey: ["tech-stack-options", data.layer] }),
  });
}

export function useDevelopmentRequests() {
  return useQuery({ queryKey: ["conception", "requests"], queryFn: () => apiClient.get<DevelopmentRequest[]>("/api/v1/conception/requests") });
}
export function useCreateIdea() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      name: string; problem_statement: string; vision?: string; scope_summary?: string; requested_by?: string;
      project_description?: string; working_directory_path?: string; tech_stack_decisions?: TechStackDecision[];
    }) => apiClient.post<IdeaCreatedResult>("/api/v1/conception/ideas", payload),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["conception"] }); client.invalidateQueries({ queryKey: ["products"] }); },
  });
}
export function useUpdateDevelopmentRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, ...payload }: { requestId: string; title: string; description: string; requested_by?: string }) =>
      apiClient.patch<DevelopmentRequest>(`/api/v1/conception/requests/${requestId}`, payload),
    onSuccess: () => client.invalidateQueries({ queryKey: ["conception"] }),
  });
}
export function useConcept(productId?: string) {
  return useQuery({ queryKey: ["concept", productId], queryFn: () => apiClient.get<ConceptDetail>(`/api/v1/products/${productId}/concept`), enabled: Boolean(productId) });
}
export function useReviseConcept() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, productId: _productId, ...payload }: {
      conceptId: string; productId: string; problem_statement: string; vision?: string; scope_summary?: string; created_by?: string;
      project_description?: string; working_directory_path?: string; tech_stack_decisions?: TechStackDecision[];
    }) => apiClient.post<ConceptDetail>(`/api/v1/product-concepts/${conceptId}/revisions`, payload),
    onSuccess: (data) => client.invalidateQueries({ queryKey: ["concept", data.concept.product_id] }),
  });
}
export function useUpdateConceptDeliveryMetadata() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, ...payload }: {
      conceptId: string; project_description?: string; working_directory_path?: string; tech_stack_decisions?: TechStackDecision[];
    }) => apiClient.patch<ConceptDetail>(`/api/v1/product-concepts/${conceptId}/delivery-metadata`, payload),
    onSuccess: (data) => client.invalidateQueries({ queryKey: ["concept", data.concept.product_id] }),
  });
}
export interface ConceptDocumentSummary { filename: string; size: number; updated_at: string; }
export interface ConceptDocument { filename: string; content: string; updated_at: string; }
export function useConceptDocuments(conceptId?: string) {
  return useQuery({
    queryKey: ["concept-documents", conceptId],
    queryFn: () => apiClient.get<ConceptDocumentSummary[]>(`/api/v1/product-concepts/${conceptId}/documents`),
    enabled: Boolean(conceptId),
  });
}
export function useConceptDocument(conceptId?: string, filename?: string) {
  return useQuery({
    queryKey: ["concept-document", conceptId, filename],
    queryFn: () => apiClient.get<ConceptDocument>(`/api/v1/product-concepts/${conceptId}/documents/${encodeURIComponent(filename!)}`),
    enabled: Boolean(conceptId && filename),
  });
}
export function useSaveConceptDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, filename, content }: { conceptId: string; filename: string; content: string }) =>
      apiClient.put<ConceptDocument>(`/api/v1/product-concepts/${conceptId}/documents/${encodeURIComponent(filename)}`, { content }),
    onSuccess: (_, variables) => {
      client.invalidateQueries({ queryKey: ["concept-documents", variables.conceptId] });
      client.invalidateQueries({ queryKey: ["concept-document", variables.conceptId, variables.filename] });
    },
  });
}
export function useUploadConceptDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, file }: { conceptId: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return apiClient.postForm<ConceptDocument>(`/api/v1/product-concepts/${conceptId}/documents:upload`, form);
    },
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["concept-documents", variables.conceptId] }),
  });
}
export function useDeleteConceptDocument() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, filename }: { conceptId: string; filename: string }) =>
      apiClient.delete(`/api/v1/product-concepts/${conceptId}/documents/${encodeURIComponent(filename)}`),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["concept-documents", variables.conceptId] }),
  });
}
export function useSubmitConcept() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (conceptId: string) => apiClient.post<ConceptDetail>(`/api/v1/product-concepts/${conceptId}:submit`), onSuccess: (data) => { client.invalidateQueries({ queryKey: ["concept", data.concept.product_id] }); client.invalidateQueries({ queryKey: ["governed-approval-requests"] }); } });
}
export function useDecideConcept() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, decision, decidedBy }: { conceptId: string; decision: "approved" | "rework"; decidedBy: string }) =>
      apiClient.post<ConceptDetail>(`/api/v1/product-concepts/${conceptId}:decide`, { decision, decided_by: decidedBy }),
    onSuccess: (data) => { client.invalidateQueries({ queryKey: ["concept", data.concept.product_id] }); client.invalidateQueries({ queryKey: ["blueprint", data.concept.product_id] }); },
  });
}
export interface DeliveryPlanningProjectSpec {
  solution_type: "web_app" | "mobile_app" | "api_service" | "database" | "deploy";
  project_name: string;
  project_description?: string;
  owner?: string;
  working_directory_path?: string;
  // When set: auto-creates a ProjectAgentMembership for this agent on the
  // new Project and assigns it to every task the authorization creates
  // there (Pacote 3, 2026-08-01).
  responsible_agent_id?: string;
  // creation | maintenance -- per-project, not shared across the
  // submission, since one idea can produce a new app alongside a
  // maintenance change to an existing one (2026-08-15).
  project_type?: "creation" | "maintenance";
}
export interface DeliveryPlanningProjectResult {
  project_id: string; project_scope_id: string; solution_type: string;
  scope_items_created: number; tasks_created: number;
}
export interface DeliveryPlanningAuthorizationOut {
  product_id: string; product_version_id: string; blueprint_revision_id: string;
  projects: DeliveryPlanningProjectResult[];
}
export function useAuthorizeDeliveryPlanning() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, ...payload }: {
      conceptId: string; version: string; projects: DeliveryPlanningProjectSpec[];
      // Chosen once for the whole submission (Conception's Pipeline/Template
      // section), applied to every Project this call creates.
      pipeline_template_id?: string;
    }) =>
      apiClient.post<DeliveryPlanningAuthorizationOut>(`/api/v1/product-concepts/${conceptId}:authorize-delivery-planning`, payload),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["products"] }); client.invalidateQueries({ queryKey: ["projects"] }); },
  });
}
export function useSyncArtifactsToProject() {
  return useMutation({
    mutationFn: ({ conceptId, projectId }: { conceptId: string; projectId: string }) =>
      apiClient.post<{ project_id: string; files_written: string[] }>(
        `/api/v1/product-concepts/${conceptId}/sync-artifacts-to-project/${projectId}`
      ),
  });
}
export function usePreviewConceptSummary() {
  return useMutation({
    mutationFn: (productId: string) => apiClient.get<{ summary: string }>(`/api/v1/products/${productId}/system-blueprint/summary`),
  });
}
export function useBlueprint(productId?: string) {
  return useQuery({ queryKey: ["blueprint", productId], queryFn: () => apiClient.get<BlueprintDetail>(`/api/v1/products/${productId}/system-blueprint`), enabled: Boolean(productId) });
}
export function useBlueprintGraph(revisionId?: string | null) {
  return useQuery({ queryKey: ["blueprint-graph", revisionId], queryFn: () => apiClient.get<BlueprintGraph>(`/api/v1/blueprint-revisions/${revisionId}/graph`), enabled: Boolean(revisionId) });
}
export function useCreateBlueprintRevision() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, cloneFromRevisionId }: { productId: string; cloneFromRevisionId?: string }) =>
      apiClient.post<BlueprintRevision>(`/api/v1/products/${productId}/system-blueprint/revisions`, { clone_from_revision_id: cloneFromRevisionId }),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["blueprint", variables.productId] }),
  });
}
export function useAddSystemElement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, ...payload }: { revisionId: string; stable_key: string; family: string; element_type: string; name: string; description?: string; spec_snapshot?: Record<string, unknown> }) => apiClient.post(`/api/v1/blueprint-revisions/${revisionId}/elements`, payload),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["blueprint-graph", variables.revisionId] }),
  });
}
export function useMoveSystemElement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, elementId, spec_snapshot }: { revisionId: string; elementId: string; spec_snapshot: Record<string, unknown> }) =>
      apiClient.patch(`/api/v1/blueprint-revisions/${revisionId}/elements/${elementId}`, { spec_snapshot }),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["blueprint-graph", variables.revisionId] }),
  });
}
export function useUpdateSystemElement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, elementId, ...payload }: { revisionId: string; elementId: string; name?: string; description?: string; family?: string; element_type?: string; stable_key?: string; spec_snapshot?: Record<string, unknown> }) =>
      apiClient.patch(`/api/v1/blueprint-revisions/${revisionId}/elements/${elementId}`, payload),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["blueprint-graph", variables.revisionId] }),
  });
}
export function useRemoveSystemElement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, elementId }: { revisionId: string; elementId: string }) =>
      apiClient.delete(`/api/v1/blueprint-revisions/${revisionId}/elements/${elementId}`),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["blueprint-graph", variables.revisionId] }),
  });
}
export function useAddSystemRelation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, ...payload }: { revisionId: string; from_element_id: string; to_element_id: string; relation_type: string }) => apiClient.post(`/api/v1/blueprint-revisions/${revisionId}/relations`, payload),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["blueprint-graph", variables.revisionId] }),
  });
}
export function useDeleteSystemRelation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, relationId }: { revisionId: string; relationId: string }) =>
      apiClient.delete(`/api/v1/blueprint-revisions/${revisionId}/relations/${relationId}`),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["blueprint-graph", variables.revisionId] }),
  });
}
export function useValidateBlueprint() {
  return useMutation({ mutationFn: (revisionId: string) => apiClient.post<{ valid: boolean; issues: { severity: string; message: string }[] }>(`/api/v1/blueprint-revisions/${revisionId}:validate`) });
}
export function useProjectScopes(projectId?: string) {
  return useQuery({ queryKey: ["project-scopes", projectId], queryFn: () => apiClient.get<ProjectScope[]>(`/api/v1/projects/${projectId}/scopes`), enabled: Boolean(projectId) });
}
export function useScopeItems(scopeId?: string) {
  return useQuery({ queryKey: ["scope-items", scopeId], queryFn: () => apiClient.get<ScopeItem[]>(`/api/v1/project-scopes/${scopeId}/items`), enabled: Boolean(scopeId) });
}
export function useAddScopeItem() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scopeId, ...payload }: { scopeId: string; system_element_id: string; change_type: string; applicability: string; rationale?: string; acceptance_criteria: { criterion: string }[] }) => apiClient.post(`/api/v1/project-scopes/${scopeId}/items`, payload),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["scope-items", variables.scopeId] }),
  });
}
export function useScopeExecutionStatus(scopeId?: string) {
  return useQuery({
    queryKey: ["scope-execution-status", scopeId],
    queryFn: () => apiClient.get<Record<string, string>>(`/api/v1/project-scopes/${scopeId}/execution-status`),
    enabled: Boolean(scopeId),
  });
}
