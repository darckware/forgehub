import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface DevelopmentRequest {
  id: string; product_id: string; title: string; description: string;
  requested_by: string | null; priority: string; status: string; created_at: string;
}
export interface ConceptRevision {
  id: string; revision: number; problem_statement: string; vision: string | null;
  scope_summary: string | null; created_by: string | null; created_at: string;
}
export interface ConceptDetail {
  concept: { id: string; product_id: string; status: string; current_revision_id: string | null };
  current_revision: ConceptRevision | null; revisions: ConceptRevision[];
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

export function useDevelopmentRequests() {
  return useQuery({ queryKey: ["conception", "requests"], queryFn: () => apiClient.get<DevelopmentRequest[]>("/api/v1/conception/requests") });
}
export function useCreateIdea() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; problem_statement: string; vision?: string; scope_summary?: string; requested_by?: string }) =>
      apiClient.post("/api/v1/conception/ideas", payload),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["conception"] }); client.invalidateQueries({ queryKey: ["products"] }); },
  });
}
export function useConcept(productId?: string) {
  return useQuery({ queryKey: ["concept", productId], queryFn: () => apiClient.get<ConceptDetail>(`/api/v1/products/${productId}/concept`), enabled: Boolean(productId) });
}
export function useReviseConcept() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, productId: _productId, ...payload }: { conceptId: string; productId: string; problem_statement: string; vision?: string; scope_summary?: string; created_by?: string }) =>
      apiClient.post<ConceptDetail>(`/api/v1/product-concepts/${conceptId}/revisions`, payload),
    onSuccess: (data) => client.invalidateQueries({ queryKey: ["concept", data.concept.product_id] }),
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
export function useAuthorizeDeliveryPlanning() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ conceptId, ...payload }: { conceptId: string; version: string; project_name: string; project_description?: string; owner?: string }) =>
      apiClient.post<{ project_id: string; project_scope_id: string }>(`/api/v1/product-concepts/${conceptId}:authorize-delivery-planning`, payload),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["products"] }); client.invalidateQueries({ queryKey: ["projects"] }); },
  });
}
export function useBlueprint(productId?: string) {
  return useQuery({ queryKey: ["blueprint", productId], queryFn: () => apiClient.get<BlueprintDetail>(`/api/v1/products/${productId}/system-blueprint`), enabled: Boolean(productId) });
}
export function useBlueprintGraph(revisionId?: string | null) {
  return useQuery({ queryKey: ["blueprint-graph", revisionId], queryFn: () => apiClient.get<BlueprintGraph>(`/api/v1/blueprint-revisions/${revisionId}/graph`), enabled: Boolean(revisionId) });
}
export function useAddSystemElement() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ revisionId, ...payload }: { revisionId: string; stable_key: string; family: string; element_type: string; name: string; description?: string }) => apiClient.post(`/api/v1/blueprint-revisions/${revisionId}/elements`, payload),
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
