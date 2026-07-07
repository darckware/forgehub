import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Docs "área de criação" (backend/app/api/routes/docs.py): filesystem tree
 * over /root/docs — inline-editable markdown, uploads/downloads for
 * everything else. Planning cross-links (doc_links) arrive in phase 3.
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

const RESOURCE = "/api/v1/docs";

export const docsKeys = {
  tree: ["docs-tree"] as const,
  file: (path: string) => ["docs-file", path] as const,
};

export function useDocsTree() {
  return useQuery({
    queryKey: docsKeys.tree,
    queryFn: async () => z.array(docNodeSchema).parse(await apiClient.get<unknown>(`${RESOURCE}/tree`)),
  });
}

/** Only markdown/text files are readable inline (backend enforces it). */
export function useDocFile(path: string | null) {
  return useQuery({
    queryKey: docsKeys.file(path ?? ""),
    queryFn: async () =>
      docFileSchema.parse(await apiClient.get<unknown>(`${RESOURCE}/file`, { params: { path: path ?? "" } })),
    enabled: Boolean(path),
  });
}

function useInvalidateTree() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: docsKeys.tree });
}

export function useSaveDocFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      apiClient.put<DocFile>(`${RESOURCE}/file`, { path, content }),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: docsKeys.tree });
      queryClient.invalidateQueries({ queryKey: docsKeys.file(vars.path) });
    },
  });
}

export function useDeleteDocPath() {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: (path: string) => apiClient.delete<void>(`${RESOURCE}/file`, { params: { path } }),
    onSuccess: invalidate,
  });
}

export function useCreateDocFolder() {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: (path: string) => apiClient.post<DocNode>(`${RESOURCE}/folder`, { path }),
    onSuccess: invalidate,
  });
}

export function useRenameDocPath() {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: ({ path, newPath }: { path: string; newPath: string }) =>
      apiClient.post<DocNode>(`${RESOURCE}/rename`, { path, new_path: newPath }),
    onSuccess: invalidate,
  });
}

export function useUploadDocFile() {
  const invalidate = useInvalidateTree();
  return useMutation({
    mutationFn: ({ folder, file }: { folder: string; file: File }) => {
      const form = new FormData();
      form.append("folder", folder);
      form.append("file", file);
      return apiClient.postForm<DocNode>(`${RESOURCE}/upload`, form);
    },
    onSuccess: invalidate,
  });
}

export async function downloadDoc(path: string): Promise<void> {
  const { blob, filename } = await apiClient.downloadFile(
    `${RESOURCE}/download?path=${encodeURIComponent(path)}`
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || path.split("/").pop() || "download";
  a.click();
  URL.revokeObjectURL(url);
}
