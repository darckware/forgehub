import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Docs "áreas de criação" (backend/app/api/routes/docs.py): a user-
 * configurable list of filesystem roots (any absolute host path, the whole
 * host filesystem is mounted at /host-root) -- inline-editable markdown,
 * uploads/downloads for everything else, per area. Planning cross-links
 * (doc_links) and /convert stay scoped to the original /root/docs area only
 * (see docs.py's module docstring).
 */

const docNodeSchema: z.ZodType<DocNode> = z.lazy(() =>
  z.object({
    name: z.string(),
    path: z.string(),
    type: z.enum(["file", "dir"]),
    children: z.array(docNodeSchema).nullable().optional(),
  })
);

export interface DocNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: DocNode[] | null;
}

const docFileSchema = z.object({ path: z.string(), content: z.string() });

export type DocFile = z.infer<typeof docFileSchema>;

const docAreaSchema = z.object({
  id: z.string(),
  name: z.string(),
  host_path: z.string(),
});

export type DocArea = z.infer<typeof docAreaSchema>;

const RESOURCE = "/api/v1/docs";

export const docsKeys = {
  areas: ["docs-areas"] as const,
  tree: (areaId: string) => ["docs-tree", areaId] as const,
  file: (areaId: string, path: string) => ["docs-file", areaId, path] as const,
};

export function useDocAreas() {
  return useQuery({
    queryKey: docsKeys.areas,
    queryFn: async () => z.array(docAreaSchema).parse(await apiClient.get<unknown>(`${RESOURCE}/areas`)),
  });
}

export function useCreateDocArea() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; host_path: string }) =>
      apiClient.post<DocArea>(`${RESOURCE}/areas`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: docsKeys.areas }),
  });
}

export function useDeleteDocArea() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (areaId: string) => apiClient.delete<void>(`${RESOURCE}/areas/${areaId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: docsKeys.areas }),
  });
}

export function useDocsTree(areaId: string | null) {
  return useQuery({
    queryKey: docsKeys.tree(areaId ?? ""),
    queryFn: async () =>
      z
        .array(docNodeSchema)
        .parse(await apiClient.get<unknown>(`${RESOURCE}/tree`, { params: { area_id: areaId ?? "" } })),
    enabled: Boolean(areaId),
  });
}

/** Only markdown/text files are readable inline (backend enforces it). */
export function useDocFile(areaId: string | null, path: string | null) {
  return useQuery({
    queryKey: docsKeys.file(areaId ?? "", path ?? ""),
    queryFn: async () =>
      docFileSchema.parse(
        await apiClient.get<unknown>(`${RESOURCE}/file`, { params: { area_id: areaId ?? "", path: path ?? "" } })
      ),
    enabled: Boolean(areaId && path),
  });
}

function useInvalidateTree(areaId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: docsKeys.tree(areaId) });
}

export function useSaveDocFile(areaId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      apiClient.put<DocFile>(`${RESOURCE}/file`, { area_id: areaId, path, content }),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: docsKeys.tree(areaId) });
      queryClient.invalidateQueries({ queryKey: docsKeys.file(areaId, vars.path) });
    },
  });
}

export function useDeleteDocPath(areaId: string) {
  const invalidate = useInvalidateTree(areaId);
  return useMutation({
    mutationFn: (path: string) =>
      apiClient.delete<void>(`${RESOURCE}/file`, { params: { area_id: areaId, path } }),
    onSuccess: invalidate,
  });
}

export function useCreateDocFolder(areaId: string) {
  const invalidate = useInvalidateTree(areaId);
  return useMutation({
    mutationFn: (path: string) => apiClient.post<DocNode>(`${RESOURCE}/folder`, { area_id: areaId, path }),
    onSuccess: invalidate,
  });
}

/** Backs both the rename prompt and drag-and-drop moves in the tree (a
 * move is just a rename to the same basename under a different folder). */
export function useRenameDocPath(areaId: string) {
  const invalidate = useInvalidateTree(areaId);
  return useMutation({
    mutationFn: ({ path, newPath }: { path: string; newPath: string }) =>
      apiClient.post<DocNode>(`${RESOURCE}/rename`, { area_id: areaId, path, new_path: newPath }),
    onSuccess: invalidate,
  });
}

export function useUploadDocFile(areaId: string) {
  const invalidate = useInvalidateTree(areaId);
  return useMutation({
    mutationFn: ({ folder, file }: { folder: string; file: File }) => {
      const form = new FormData();
      form.append("area_id", areaId);
      form.append("folder", folder);
      form.append("file", file);
      return apiClient.postForm<DocNode>(`${RESOURCE}/upload`, form);
    },
    onSuccess: invalidate,
  });
}

export async function downloadDoc(areaId: string, path: string): Promise<void> {
  const { blob, filename } = await apiClient.downloadFile(
    `${RESOURCE}/download?area_id=${encodeURIComponent(areaId)}&path=${encodeURIComponent(path)}`
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || path.split("/").pop() || "download";
  a.click();
  URL.revokeObjectURL(url);
}
