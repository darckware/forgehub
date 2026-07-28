import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * MCP catalog -- register a server once, assign it to agents/projects from
 * one place, instead of retyping the same command/args/env for each
 * agent's own `/mcp` entry by hand. See backend/app/api/routes/mcp_catalog.py.
 *
 * Does not replace useAgent.ts's per-agent MCP hooks or useProjectMcp.ts's
 * per-project ones -- those stay the direct editors; this is a layer on
 * top. `apply_to_all_agents` reaches every agent, including ones registered
 * after the flag was set (see the backend route's docstring) -- **writes to
 * every eligible agent's real config file for real**, not a preview.
 */

export const mcpCatalogServerSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  transport: z.string(),
  command: z.string().nullable().optional(),
  args: z.array(z.string()).default([]),
  env: z.record(z.string()).default({}),
  url: z.string().nullable().optional(),
  is_builtin: z.boolean().default(false),
  apply_to_all_agents: z.boolean().default(false),
});

export type McpCatalogServer = z.infer<typeof mcpCatalogServerSchema>;

export const mcpCatalogAssignmentSchema = z.object({
  id: z.string(),
  catalog_server_id: z.string(),
  target_type: z.enum(["agent", "project"]),
  target_id: z.string(),
  enabled: z.boolean(),
  last_synced_at: z.string().nullable().optional(),
  last_sync_error: z.string().nullable().optional(),
});

export type McpCatalogAssignment = z.infer<typeof mcpCatalogAssignmentSchema>;

export interface McpCatalogServerInput {
  name: string;
  description?: string | null;
  transport?: "stdio" | "http";
  command?: string | null;
  args?: string[];
  env?: Record<string, string>;
  url?: string | null;
  apply_to_all_agents?: boolean;
}

export interface McpCatalogAssignInput {
  targetType: "agent" | "project";
  targetId: string;
  /** Only meaningful for targetType "project" -- defaults to "claude"
   * server-side, the only project-scoped runtime supported today. */
  runtimeType?: string;
}

const RESOURCE = "/api/v1/mcp-catalog";

export const mcpCatalogKeys = {
  servers: ["mcp-catalog-servers"] as const,
  assignments: (serverId: string) => ["mcp-catalog-assignments", serverId] as const,
};

export function useMcpCatalogServers() {
  return useQuery({
    queryKey: mcpCatalogKeys.servers,
    queryFn: () => apiClient.get<McpCatalogServer[]>(`${RESOURCE}/servers`),
  });
}

export function useMcpCatalogAssignments(serverId: string | undefined) {
  return useQuery({
    queryKey: mcpCatalogKeys.assignments(serverId ?? ""),
    queryFn: () => apiClient.get<McpCatalogAssignment[]>(`${RESOURCE}/servers/${serverId}/assignments`),
    enabled: Boolean(serverId),
  });
}

export function useCreateMcpCatalogServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: McpCatalogServerInput) =>
      apiClient.post<McpCatalogServer>(`${RESOURCE}/servers`, {
        transport: payload.url ? "http" : "stdio",
        ...payload,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: mcpCatalogKeys.servers }),
  });
}

export function useUpdateMcpCatalogServer(serverId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: McpCatalogServerInput) =>
      apiClient.put<McpCatalogServer>(`${RESOURCE}/servers/${serverId}`, {
        transport: payload.url ? "http" : "stdio",
        ...payload,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: mcpCatalogKeys.servers }),
  });
}

export function useDeleteMcpCatalogServer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (serverId: string) => apiClient.delete<void>(`${RESOURCE}/servers/${serverId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: mcpCatalogKeys.servers }),
  });
}

export function useAssignMcpCatalogServer(serverId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ targetType, targetId, runtimeType = "claude" }: McpCatalogAssignInput) =>
      apiClient.post<McpCatalogAssignment>(`${RESOURCE}/servers/${serverId}/assign`, {
        target_type: targetType,
        target_id: targetId,
        runtime_type: runtimeType,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mcpCatalogKeys.assignments(serverId) });
      queryClient.invalidateQueries({ queryKey: mcpCatalogKeys.servers });
    },
  });
}

export function useUnassignMcpCatalogServer(serverId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assignmentId: string) =>
      apiClient.delete<void>(`${RESOURCE}/servers/${serverId}/assign/${assignmentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: mcpCatalogKeys.assignments(serverId) });
      queryClient.invalidateQueries({ queryKey: mcpCatalogKeys.servers });
    },
  });
}
