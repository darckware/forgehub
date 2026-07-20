import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";
import type { DocGraph } from "@/components/GraphView";

/** Browser + editor for the Obsidian vault (mounted read-write at /vault
 * in the backend container) -- see backend/app/api/routes/vault.py. */

export interface VaultNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: VaultNode[];
}

export const vaultNoteSchema = z.object({
  path: z.string(),
  content: z.string(),
});

export type VaultNote = z.infer<typeof vaultNoteSchema>;

const RESOURCE = "/api/v1/vault";

export const vaultKeys = {
  tree: ["vault-tree"] as const,
  note: (path: string) => ["vault-note", path] as const,
};

export function useVaultTree() {
  return useQuery({
    queryKey: vaultKeys.tree,
    queryFn: () => apiClient.get<VaultNode[]>(`${RESOURCE}/tree`),
  });
}

export function useVaultNote(path: string | undefined) {
  return useQuery({
    queryKey: vaultKeys.note(path ?? ""),
    queryFn: () => apiClient.get<VaultNote>(`${RESOURCE}/note`, { params: { path } }),
    enabled: Boolean(path),
  });
}

export function useVaultGraph() {
  return useQuery({
    queryKey: ["vault-graph"],
    queryFn: () => apiClient.get<DocGraph>(`${RESOURCE}/graph`),
  });
}

export function useUpdateVaultNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      apiClient.put<VaultNote>(`${RESOURCE}/note`, { content }, { params: { path } }),
    onSuccess: (note) => {
      queryClient.setQueryData(vaultKeys.note(note.path), note);
      // PUT also creates brand-new notes (see vault.py docstring), so the
      // tree may have gained a node -- cheap to refetch either way.
      queryClient.invalidateQueries({ queryKey: vaultKeys.tree });
    },
  });
}

export function useCreateVaultFolder() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => apiClient.post<VaultNode>(`${RESOURCE}/folder`, { path }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: vaultKeys.tree });
    },
  });
}

export function useDeleteVaultNote() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => apiClient.delete<void>(`${RESOURCE}/note`, { params: { path } }),
    onSuccess: (_data, path) => {
      queryClient.removeQueries({ queryKey: vaultKeys.note(path) });
      queryClient.invalidateQueries({ queryKey: vaultKeys.tree });
      queryClient.invalidateQueries({ queryKey: ["vault-graph"] });
    },
  });
}

/** Backs both the content panel's rename button and the tree's hover
 * rename/drag-and-drop-move icons. */
export function useRenameVaultPath() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, newPath }: { path: string; newPath: string }) =>
      apiClient.post<VaultNode>(`${RESOURCE}/rename`, { path, new_path: newPath }),
    onSuccess: (_data, { path }) => {
      queryClient.removeQueries({ queryKey: vaultKeys.note(path) });
      queryClient.invalidateQueries({ queryKey: vaultKeys.tree });
      queryClient.invalidateQueries({ queryKey: ["vault-graph"] });
    },
  });
}

export function useUploadVaultFile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ folder, file }: { folder: string; file: File }) => {
      const form = new FormData();
      form.append("folder", folder);
      form.append("file", file);
      return apiClient.postForm<VaultNode>(`${RESOURCE}/upload`, form);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: vaultKeys.tree });
      queryClient.invalidateQueries({ queryKey: ["vault-graph"] });
    },
  });
}

/** Deletes a note, a folder (recursively), or any other file -- unlike
 * useDeleteVaultNote, not restricted to markdown. Backs the tree's hover
 * delete icon. */
export function useDeleteVaultPath() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (path: string) => apiClient.delete<void>(`${RESOURCE}/path`, { params: { path } }),
    onSuccess: (_data, path) => {
      queryClient.removeQueries({ queryKey: vaultKeys.note(path) });
      queryClient.invalidateQueries({ queryKey: vaultKeys.tree });
      queryClient.invalidateQueries({ queryKey: ["vault-graph"] });
    },
  });
}

export async function downloadVaultFile(path: string): Promise<void> {
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
