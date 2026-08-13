import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/** Mirrors backend/app/api/routes/system_control.py's AppConfigUpdate --
 * every field here is backed by a settings.<NAME> default sourced from
 * repo-root forgehub.config (not secrets -- those stay in .env). Saving
 * rewrites that file AND updates the running backend's in-memory settings
 * immediately, no restart required. */
export interface AppConfig {
  hermes_source_path: string;
  git_control_default_repo: string;
  backup_root: string;
  /** Trash path passed to the same Athos cleanup policy used by the weekly
   * foundation-clear cron. */
  trash_root: string;
  cleanup_scan_root: string;
  cleanup_prune_paths: string[];
  cleanup_prune_names: string[];
  timezone: string;
  /** Language the in-app AI chat (Workspace tabs + Assistant drawer)
   * answers in -- "pt-BR" or "en". The backend appends the matching hidden
   * instruction to each outgoing agent call; nothing visible changes in
   * the transcript. */
  chat_response_language: string;
  /** App shell language ("en" or "pt-BR") new users get on creation --
   * independent of chat_response_language above. Existing users' own
   * ui_language is untouched by changing this. */
  default_ui_language: string;
  /** Root config/state directory per agent runtime (e.g. "claude" ->
   * "/root/.claude"), keyed by runtime name -- not by individual agent,
   * since every Hermes-profile agent shares hermes_source_path's tree.
   * Reference/visibility only, not consumed by Git Control/Backup. */
  agent_runtime_paths: Record<string, string>;
  /** Name of a service-kind row in ForgeRouter's own registry
   * (ai_router.agents, kind='service' -- e.g. "Hindsight") whose key
   * pre-fills the Dashboard's ProjectsForgeRouterCard "Enter the
   * ForgeRouter API key..." prompt. Empty string = no default set. */
  default_forgerouter_service_name: string;
}

export function useAppConfig() {
  return useQuery<AppConfig>({
    queryKey: ["system-control", "config"],
    queryFn: () => apiClient.get("/api/v1/system-control/config"),
    retry: false,
  });
}

export function useUpdateAppConfig() {
  const queryClient = useQueryClient();
  return useMutation<AppConfig, Error, AppConfig>({
    mutationFn: (payload) => apiClient.put("/api/v1/system-control/config", payload),
    onSuccess: async (data) => {
      queryClient.setQueryData(["system-control", "config"], data);
      // Every downstream default (Git Control's repo picker, Backups'
      // BACKUP_ROOT-derived locations, Cleanup) depends on these values --
      // refetch instead of leaving stale caches around after a save.
      await queryClient.invalidateQueries({ queryKey: ["system-control"] });
      // Chat surfaces localize their chrome from the configured response
      // language (useChatLanguage) -- apply a change without a reload.
      await queryClient.invalidateQueries({ queryKey: ["chat", "language"] });
    },
  });
}
