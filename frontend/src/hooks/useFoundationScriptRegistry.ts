import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/** Foundation page's "Scripts" card -- a curated list of scripts that
 * implement something documented under /root/.hermes/foundation, distinct
 * from the full per-profile Crons/Scripts catalog (useFoundationScripts.ts,
 * despite the similar name, is that other one). See
 * backend/app/api/routes/foundation_script.py. */

export const foundationScriptSchema = z.object({
  id: z.string(),
  name: z.string(),
  path: z.string().nullable(),
  description: z.string().nullable(),
  doc_path: z.string().nullable(),
  source: z.enum(["manual", "sync"]),
  created_at: z.string(),
  updated_at: z.string(),
});

export type FoundationScript = z.infer<typeof foundationScriptSchema>;

const syncResultSchema = z.object({
  added: z.number(),
  already_registered: z.number(),
  scanned_docs: z.number(),
  discovered: z.array(z.string()),
});

export type FoundationScriptSyncResult = z.infer<typeof syncResultSchema>;

const RESOURCE = "/api/v1/foundation-scripts";

export const foundationScriptKeys = {
  list: ["foundation-scripts"] as const,
};

export function useFoundationScriptRegistry() {
  return useQuery({
    queryKey: foundationScriptKeys.list,
    queryFn: async () => {
      const data = await apiClient.get<unknown>(RESOURCE);
      return z.array(foundationScriptSchema).parse(data);
    },
  });
}

export function useCreateFoundationScript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; path?: string | null; description?: string | null }) =>
      apiClient.post<unknown>(RESOURCE, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: foundationScriptKeys.list }),
  });
}

export function useUpdateFoundationScript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: { path?: string | null; description?: string | null; doc_path?: string | null };
    }) => apiClient.patch<unknown>(`${RESOURCE}/${id}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: foundationScriptKeys.list }),
  });
}

export function useDeleteFoundationScript() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: foundationScriptKeys.list }),
  });
}

const contentSchema = z.object({ content: z.string() });

export function useFoundationScriptContent(id: string | undefined) {
  return useQuery({
    queryKey: ["foundation-scripts", id, "content"],
    queryFn: async () => {
      const data = await apiClient.get<unknown>(`${RESOURCE}/${id}/content`);
      return contentSchema.parse(data);
    },
    enabled: Boolean(id),
    retry: false,
  });
}

export function useSyncFoundationScripts() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const data = await apiClient.post<unknown>(`${RESOURCE}/sync`, {});
      return syncResultSchema.parse(data);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: foundationScriptKeys.list }),
  });
}
