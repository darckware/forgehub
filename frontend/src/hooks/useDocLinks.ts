import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Doc links (backend/app/api/routes/docs.py): cross-reference between a
 * /root/docs document and a Planning entity (product, product_version,
 * project, pipeline, planning_item, task, artifact). Polymorphic, same
 * pattern as governance's Approval/AuditEvent -- see db/models/doc_link.py.
 */

export const DOC_LINK_ENTITY_TYPES = [
  "product",
  "product_version",
  "project",
  "pipeline",
  "planning_item",
  "task",
  "artifact",
] as const;

export type DocLinkEntityType = (typeof DOC_LINK_ENTITY_TYPES)[number];

export const DOC_LINK_ENTITY_LABELS: Record<DocLinkEntityType, string> = {
  product: "Product",
  product_version: "Version",
  project: "Project",
  pipeline: "Pipeline",
  planning_item: "Planning",
  task: "Task",
  artifact: "Artifact",
};

export const docLinkSchema = z.object({
  id: z.string(),
  doc_path: z.string(),
  entity_type: z.enum(DOC_LINK_ENTITY_TYPES),
  entity_id: z.string(),
  entity_label: z.string().nullable(),
});

export type DocLink = z.infer<typeof docLinkSchema>;

const RESOURCE = "/api/v1/docs";

export const docLinkKeys = {
  forDoc: (path: string) => ["doc-links", "doc", path] as const,
  forEntity: (type: string, id: string) => ["doc-links", "entity", type, id] as const,
};

/** Every Planning entity linked to one doc -- backs the Docs page's link panel. */
export function useDocLinks(path: string | null) {
  return useQuery({
    queryKey: docLinkKeys.forDoc(path ?? ""),
    queryFn: async () =>
      z
        .array(docLinkSchema)
        .parse(await apiClient.get<unknown>(`${RESOURCE}/links`, { params: { path: path ?? "" } })),
    enabled: Boolean(path),
  });
}

/** Every doc linked to one Planning entity -- backs the "Docs" section on
 * detail screens (product/project/planning/task). */
export function useEntityDocLinks(entityType: DocLinkEntityType, entityId: string | undefined) {
  return useQuery({
    queryKey: docLinkKeys.forEntity(entityType, entityId ?? ""),
    queryFn: async () =>
      z.array(docLinkSchema).parse(
        await apiClient.get<unknown>(`${RESOURCE}/links/by-entity`, {
          params: { entity_type: entityType, entity_id: entityId ?? "" },
        })
      ),
    enabled: Boolean(entityId),
  });
}

export function useCreateDocLink(invalidateEntity?: { type: DocLinkEntityType; id: string }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { doc_path: string; entity_type: DocLinkEntityType; entity_id: string }) =>
      apiClient.post<DocLink>(`${RESOURCE}/links`, payload),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: docLinkKeys.forDoc(vars.doc_path) });
      queryClient.invalidateQueries({
        queryKey: docLinkKeys.forEntity(vars.entity_type, vars.entity_id),
      });
      if (invalidateEntity) {
        queryClient.invalidateQueries({
          queryKey: docLinkKeys.forEntity(invalidateEntity.type, invalidateEntity.id),
        });
      }
    },
  });
}

export function useDeleteDocLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => apiClient.delete<void>(`${RESOURCE}/links/${linkId}`),
    onSuccess: () => {
      // Broad invalidation: we don't know the (doc_path, entity) pair from
      // just the link id without an extra round trip.
      queryClient.invalidateQueries({ queryKey: ["doc-links"] });
    },
  });
}
