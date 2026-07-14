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
  /** Where "Run Cleanup" moves eligible files and "Empty trash" (a
   * separate action) permanently deletes -- see System Control's Cleanup
   * card. Independent of the external Hermes "foundation-clear" cron,
   * which always empties its own hardcoded /root/trash regardless of
   * this setting. */
  trash_root: string;
  cleanup_scan_root: string;
  cleanup_prune_paths: string[];
  cleanup_prune_names: string[];
  timezone: string;
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
    },
  });
}
