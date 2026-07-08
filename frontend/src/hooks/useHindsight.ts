import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface HindsightProfile {
  profile: string;
  uses_hindsight: boolean;
  memory_enabled: boolean | null;
  user_profile_enabled: boolean | null;
  write_approval: boolean | null;
  memory_char_limit: number | null;
  user_char_limit: number | null;
  config_path: string;
  hindsight_config_path: string | null;
  hindsight_configured: boolean;
}

export interface HindsightStatus {
  summary: {
    configured: boolean;
    daemon_active: boolean;
    recording_configured: boolean;
    recording_effective: boolean;
    active_profile_count: number;
    profile_config_count: number;
    primary_profile: string | null;
  };
  connection: {
    mode: string;
    api_url: string | null;
    timeout: number | null;
    idle_timeout: number | string | null;
    config_path: string | null;
    env_path: string | null;
  };
  probe: {
    ok: boolean;
    status_code: number | null;
    error: string | null;
    version: unknown;
    health: unknown;
  };
  llm: {
    provider: string | null;
    model: string | null;
    base_url: string | null;
    api_key_present: boolean;
  };
  memory: {
    bank_id: string;
    bank_enabled: boolean | null;
    recall_budget: string | null;
    auto_recall: boolean;
    auto_retain: boolean;
    retain_async: boolean;
    retain_every_n_turns: number;
    memory_mode: string;
    retain_tags: string | null;
    retain_source: string | null;
  };
  profiles: HindsightProfile[];
  processes: { pid: string; uptime_seconds: number; command: string }[];
  logs: {
    runtime: { path?: string; exists: boolean; updated_at?: number | null; lines: string[] };
    default: { path?: string; exists: boolean; updated_at?: number | null; lines: string[] };
    startup: { path?: string; exists: boolean; updated_at?: number | null; lines: string[] };
    latest_errors: { source: string; line: string }[];
  };
  analysis: {
    storage_source: string;
    database_control_recommendation: string;
    current_risk: string;
  };
}

export function useHindsightStatus() {
  return useQuery<HindsightStatus>({
    queryKey: ["hindsight", "status"],
    queryFn: () => apiClient.get("/api/v1/hindsight/status"),
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useHindsightRestart() {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean; stdout: string; stderr: string }, Error>({
    mutationFn: () => apiClient.post("/api/v1/hindsight/restart"),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["hindsight", "status"] });
    },
  });
}

export type HindsightLogTarget = "runtime" | "default" | "startup";

export function useClearHindsightLog() {
  const queryClient = useQueryClient();
  return useMutation<{ success: boolean; path: string; cleared: boolean }, Error, HindsightLogTarget>({
    mutationFn: (target) => apiClient.post("/api/v1/hindsight/clear-log", { target }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["hindsight", "status"] });
    },
  });
}
