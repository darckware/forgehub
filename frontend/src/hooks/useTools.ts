import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Tool domain — registry of tools built by agents (see
 * backend/app/api/routes/tool.py, prefix="/api/v1/tools"). Each tool
 * records its file location, functional description, category and the
 * responsible agent (agent_id → agents; agent_name is resolved by the
 * backend for display).
 */

export const AGENT_TOOL_STATUSES = ["active", "deprecated", "archived"] as const;
export type AgentToolStatus = (typeof AGENT_TOOL_STATUSES)[number];

export const agentToolSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  agent_name: z.string().nullable(),
  name: z.string(),
  description: z.string(),
  file_path: z.string(),
  category: z.string(),
  status: z.enum(AGENT_TOOL_STATUSES),
  created_at: z.string(),
  updated_at: z.string(),
});

export type AgentTool = z.infer<typeof agentToolSchema>;

export interface ToolFilter {
  agentId?: string;
  category?: string;
  status?: AgentToolStatus;
  q?: string;
}

export interface ToolCreateInput {
  agent_id: string;
  name: string;
  description: string;
  file_path: string;
  category: string;
  status?: AgentToolStatus;
}

export type ToolUpdateInput = Partial<ToolCreateInput>;

export const toolKeys = {
  all: ["tools"] as const,
  list: (filter: ToolFilter = {}) => ["tools", "list", filter] as const,
  categories: ["tools", "categories"] as const,
};

const RESOURCE = "/api/v1/tools";

export function useTools(filter: ToolFilter = {}) {
  return useQuery({
    queryKey: toolKeys.list(filter),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filter.agentId) params.set("agent_id", filter.agentId);
      if (filter.category) params.set("category", filter.category);
      if (filter.status) params.set("status", filter.status);
      if (filter.q) params.set("q", filter.q);
      const qs = params.toString();
      const data = await apiClient.get<unknown>(qs ? `${RESOURCE}?${qs}` : RESOURCE);
      return z.array(agentToolSchema).parse(data);
    },
  });
}

export function useToolCategories() {
  return useQuery({
    queryKey: toolKeys.categories,
    queryFn: () => apiClient.get<string[]>(`${RESOURCE}/categories`),
  });
}

export interface ToolScanResult {
  scanned: number;
  created: number;
  skipped: number;
}

/** Populates the registry from the live filesystem (profile scripts +
 * central cron/scripts catalogs); files with no determinable responsible
 * agent are assigned to Athos. Idempotent — already-registered paths are
 * skipped. */
export function useScanTools() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<ToolScanResult>(`${RESOURCE}/scan`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: toolKeys.all }),
  });
}

export function useCreateTool() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ToolCreateInput) => apiClient.post<AgentTool>(RESOURCE, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: toolKeys.all }),
  });
}

export function useUpdateTool() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ToolUpdateInput }) =>
      apiClient.patch<AgentTool>(`${RESOURCE}/${id}`, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: toolKeys.all }),
  });
}

export function useDeleteTool() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, deleteFile = false }: { id: string; deleteFile?: boolean }) =>
      apiClient.delete(`${RESOURCE}/${id}${deleteFile ? "?delete_file=true" : ""}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: toolKeys.all }),
  });
}

export interface ToolContent {
  file_path: string;
  content: string | null;
  exists: boolean;
}

/** Reads the tool's file from disk (host path resolved via the backend
 * container's mounts; refuses paths outside the managed catalogs). */
export function useToolContent(id: string | null) {
  return useQuery({
    queryKey: ["tools", "content", id],
    queryFn: () => apiClient.get<ToolContent>(`${RESOURCE}/${id}/content`),
    enabled: !!id,
    staleTime: 0,
    retry: false,
  });
}

export function useSaveToolContent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      apiClient.put<ToolContent>(`${RESOURCE}/${id}/content`, { content }),
    onSuccess: (_, { id }) =>
      queryClient.invalidateQueries({ queryKey: ["tools", "content", id] }),
  });
}
