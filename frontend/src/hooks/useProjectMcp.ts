import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Project-scoped MCP servers -- Claude Code's `.mcp.json` at the project's
 * working_directory_path, the code/dev-tool counterpart of per-agent MCP
 * (useAgent.ts's useAgentMcpServers/useUpsertAgentMcpServer). Only "claude"
 * is supported today -- see backend/app/db/models/project_mcp.py's module
 * docstring for why. Unlike per-agent MCP, ForgeHub does keep a DB row here
 * (desired state); `last_synced_at`/`last_sync_error` report the outcome of
 * the last attempt to make the real `.mcp.json` match it, and `/live` reads
 * the file directly, independent of the DB.
 */

export const PROJECT_MCP_RUNTIME_TYPES = ["claude"] as const;

export const projectMcpServerSchema = z.object({
  id: z.string(),
  project_id: z.string(),
  runtime_type: z.string(),
  name: z.string(),
  transport: z.string(),
  command: z.string().nullable().optional(),
  args: z.array(z.string()).default([]),
  env: z.record(z.string()).default({}),
  url: z.string().nullable().optional(),
  enabled: z.boolean().default(true),
  last_synced_at: z.string().nullable().optional(),
  last_sync_error: z.string().nullable().optional(),
});

export type ProjectMcpServer = z.infer<typeof projectMcpServerSchema>;

export const projectMcpServersLiveSchema = z.object({
  project_path: z.string(),
  config_path: z.string(),
  config_exists: z.boolean(),
  servers: z
    .array(
      z.object({
        name: z.string(),
        command: z.string().nullable().optional(),
        args: z.array(z.string()).default([]),
        env: z.record(z.string()).default({}),
        url: z.string().nullable().optional(),
      }),
    )
    .default([]),
});

export type ProjectMcpServersLive = z.infer<typeof projectMcpServersLiveSchema>;

export interface ProjectMcpServerInput {
  name: string;
  runtime_type?: string;
  command?: string | null;
  args?: string[];
  env?: Record<string, string>;
  url?: string | null;
}

const RESOURCE = "/api/v1/projects";

export const projectMcpKeys = {
  list: (projectId: string) => ["project-mcp-servers", projectId] as const,
  live: (projectId: string, runtimeType: string) =>
    ["project-mcp-servers-live", projectId, runtimeType] as const,
};

export function useProjectMcpServers(projectId: string | undefined) {
  return useQuery({
    queryKey: projectMcpKeys.list(projectId ?? ""),
    queryFn: () => apiClient.get<ProjectMcpServer[]>(`${RESOURCE}/${projectId}/mcp-servers`),
    enabled: Boolean(projectId),
  });
}

export function useProjectMcpServersLive(projectId: string | undefined, runtimeType = "claude") {
  return useQuery({
    queryKey: projectMcpKeys.live(projectId ?? "", runtimeType),
    queryFn: () =>
      apiClient.get<ProjectMcpServersLive>(`${RESOURCE}/${projectId}/mcp-servers/live`, {
        params: { runtime_type: runtimeType },
      }),
    enabled: Boolean(projectId),
  });
}

export function useUpsertProjectMcpServer(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, runtime_type = "claude", ...server }: ProjectMcpServerInput) =>
      apiClient.put<ProjectMcpServer>(`${RESOURCE}/${projectId}/mcp-servers/${name}`, {
        runtime_type,
        transport: server.url ? "http" : "stdio",
        command: server.command ?? null,
        args: server.args ?? [],
        env: server.env ?? {},
        url: server.url ?? null,
        enabled: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectMcpKeys.list(projectId) });
      queryClient.invalidateQueries({ queryKey: ["project-mcp-servers-live", projectId] });
    },
  });
}

export function useDeleteProjectMcpServer(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, runtimeType = "claude" }: { name: string; runtimeType?: string }) =>
      apiClient.delete<void>(`${RESOURCE}/${projectId}/mcp-servers/${name}`, {
        params: { runtime_type: runtimeType },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectMcpKeys.list(projectId) });
      queryClient.invalidateQueries({ queryKey: ["project-mcp-servers-live", projectId] });
    },
  });
}
