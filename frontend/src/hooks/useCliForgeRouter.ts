import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export type CliForgeRouterTool = "claude" | "codex" | "antigravity";

export interface CliForgeRouterStatus {
  claude: boolean;
  codex: boolean;
  antigravity: boolean;
}

export interface ToggleCliForgeRouterPayload {
  tool: CliForgeRouterTool;
  enabled: boolean;
}

export interface ToggleCliForgeRouterResponse {
  tool: string;
  enabled: boolean;
  config_path: string;
  status: CliForgeRouterStatus;
}

const RESOURCE = "/api/v1/forgerouter";

export const cliForgeRouterKeys = {
  status: ["forgerouter-cli-status"] as const,
};

export function useCliForgeRouterStatus() {
  return useQuery({
    queryKey: cliForgeRouterKeys.status,
    queryFn: () => apiClient.get<CliForgeRouterStatus>(`${RESOURCE}/cli-status`),
    staleTime: 30_000,
  });
}

export function useToggleCliForgeRouter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ToggleCliForgeRouterPayload) =>
      apiClient.put<ToggleCliForgeRouterResponse>(`${RESOURCE}/cli-toggle`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(cliForgeRouterKeys.status, data.status);
      queryClient.invalidateQueries({ queryKey: cliForgeRouterKeys.status });
    },
  });
}
