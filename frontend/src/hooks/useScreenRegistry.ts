import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { SystemElement } from "./useSystemScope";

export type ScreenAttributeType = "string" | "number" | "boolean" | "date" | "relation";

export interface ScreenAttribute {
  name: string;
  type: ScreenAttributeType;
  required: boolean;
  description?: string | null;
  relation_target_screen_id?: string | null;
}

/** Stored verbatim as the screen element's spec_snapshot. Two independent,
 * optional prototype modes -- both conceptual, never the final
 * implementation (see backend/app/api/schemas/system_scope.py's ScreenSpec
 * docstring): free-form HTML for app-style screens, or a template + images
 * for site-style screens. */
export interface ScreenSpec {
  attributes: ScreenAttribute[];
  prototype_html?: string | null;
  css_framework?: string | null;
  template_ref?: string | null;
  image_refs?: string[];
}

export interface ScreenElementRevision {
  id: string;
  system_element_id: string;
  blueprint_revision_id: string;
  spec_snapshot: ScreenSpec;
  content_hash: string;
  status: string;
}

export interface Screen {
  scope_item_id: string;
  element: SystemElement;
  revision: ScreenElementRevision;
}

export interface BusinessRule {
  content: string;
  updated_at: string | null;
}

export interface DeriveDatabaseResult {
  revision_id: string;
  tables_created: number;
  tables_updated: number;
  fields_written: number;
}

export function useScreens(scopeId?: string) {
  return useQuery({
    queryKey: ["screens", scopeId],
    queryFn: () => apiClient.get<Screen[]>(`/api/v1/project-scopes/${scopeId}/screens`),
    enabled: Boolean(scopeId),
  });
}

export function useCreateScreen() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scopeId, ...payload }: {
      scopeId: string; name: string; description?: string; stable_key?: string; spec?: Partial<ScreenSpec>;
    }) => apiClient.post<Screen>(`/api/v1/project-scopes/${scopeId}/screens`, payload),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["screens", variables.scopeId] }),
  });
}

export function useUpdateScreen() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scopeId, elementId, ...payload }: {
      scopeId: string; elementId: string; name?: string; description?: string; spec?: Partial<ScreenSpec>;
    }) => apiClient.patch<Screen>(`/api/v1/project-scopes/${scopeId}/screens/${elementId}`, payload),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["screens", variables.scopeId] }),
  });
}

export function useRemoveScreen() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scopeId, elementId }: { scopeId: string; elementId: string }) =>
      apiClient.delete(`/api/v1/project-scopes/${scopeId}/screens/${elementId}`),
    onSuccess: (_, variables) => client.invalidateQueries({ queryKey: ["screens", variables.scopeId] }),
  });
}

export function useScreenBusinessRule(scopeId?: string, elementId?: string) {
  return useQuery({
    queryKey: ["screen-business-rule", scopeId, elementId],
    queryFn: () => apiClient.get<BusinessRule>(`/api/v1/project-scopes/${scopeId}/screens/${elementId}/business-rule`),
    enabled: Boolean(scopeId && elementId),
  });
}

export function useSaveScreenBusinessRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ scopeId, elementId, content }: { scopeId: string; elementId: string; content: string }) =>
      apiClient.put<BusinessRule>(`/api/v1/project-scopes/${scopeId}/screens/${elementId}/business-rule`, { content }),
    onSuccess: (_, variables) =>
      client.invalidateQueries({ queryKey: ["screen-business-rule", variables.scopeId, variables.elementId] }),
  });
}

export function useDeriveDatabase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (scopeId: string) => apiClient.post<DeriveDatabaseResult>(`/api/v1/project-scopes/${scopeId}/derive-database`),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["blueprint-graph", data.revision_id] });
    },
  });
}
