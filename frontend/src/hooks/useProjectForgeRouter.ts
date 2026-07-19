import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Per-project ForgeRouter integration hooks.
 *
 * ForgeRouter config is always written inside the project's
 * working_directory_path — never in global user directories.
 * See backend/app/api/routes/project.py and host-bridge/app.py.
 */

export const projectForgeRouterConfigSchema = z.object({
  project_id: z.string(),
  claude_api_key: z.string().nullable(),
  codex_api_key: z.string().nullable(),
  antigravity_api_key: z.string().nullable(),
  claude_enabled: z.boolean(),
  codex_enabled: z.boolean(),
  antigravity_enabled: z.boolean(),
  configured_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ProjectForgeRouterConfig = z.infer<typeof projectForgeRouterConfigSchema>;

export const forgeRouterGlobalAuditSchema = z.object({
  clean: z.boolean(),
  findings: z.array(z.record(z.string())),
});
export type ForgeRouterGlobalAudit = z.infer<typeof forgeRouterGlobalAuditSchema>;

export interface ProjectForgeRouterToggle {
  enabled: boolean;
  claude_api_key?: string;
  codex_api_key?: string;
  antigravity_api_key?: string;
  claude?: boolean;
  codex?: boolean;
  antigravity?: boolean;
}

const RESOURCE = "/api/v1/projects";

export const projectForgeRouterKeys = {
  config: (projectId: string) => ["project-forgerouter", projectId] as const,
  live: (projectId: string) => ["project-forgerouter-live", projectId] as const,
  audit: ["forgerouter-global-audit"] as const,
};

export function useProjectForgeRouterConfig(projectId: string) {
  return useQuery({
    queryKey: projectForgeRouterKeys.config(projectId),
    queryFn: () => apiClient.get<ProjectForgeRouterConfig>(`${RESOURCE}/${projectId}/forgerouter`),
    staleTime: 30_000,
  });
}

export function useToggleProjectForgeRouter(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ProjectForgeRouterToggle) =>
      apiClient.put<ProjectForgeRouterConfig>(`${RESOURCE}/${projectId}/forgerouter`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(projectForgeRouterKeys.config(projectId), data);
      queryClient.invalidateQueries({ queryKey: projectForgeRouterKeys.live(projectId) });
    },
  });
}

export function useForgeRouterGlobalAudit() {
  return useQuery({
    queryKey: projectForgeRouterKeys.audit,
    queryFn: () =>
      apiClient.get<ForgeRouterGlobalAudit>(`${RESOURCE}/forgerouter/audit`),
    staleTime: 60_000,
  });
}
