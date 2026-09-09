import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export type NexoOsKind = "linux" | "windows";
export type NexoInstallationStatus = "package_ready" | "downloaded" | "online" | "outdated" | "error";
export interface NexoBuild {
  id: string;
  git_sha: string;
  agent_version: string;
  os_kind: NexoOsKind;
  status: "queued" | "building" | "ready" | "failed";
  artifact_size: number | null;
  sha256: string | null;
  build_log_excerpt: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}
export interface NexoBuildCatalog {
  source: { git_sha: string; agent_version: string };
  builds: NexoBuild[];
}
export interface NexoInstallation {
  id: string;
  workstation_id: string;
  client_id: string;
  build_id: string;
  client_name: string;
  workstation_hostname: string | null;
  os_kind: NexoOsKind;
  status: NexoInstallationStatus;
  expected_version: string;
  detected_version: string | null;
  package_generated_at: string;
  downloaded_at: string | null;
  online_at: string | null;
  last_report_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}
export interface NexoInstallationEvent {
  id: string;
  event_type: "package_generated" | "downloaded" | "first_report" | "version_mismatch" | "error";
  from_status: NexoInstallationStatus | null;
  to_status: NexoInstallationStatus;
  detail: string | null;
  actor_user_id: string | null;
  created_at: string;
}
export interface NexoInstallationDetail extends NexoInstallation { events: NexoInstallationEvent[] }
export interface NexoInstallationFilters {
  client_id?: string;
  workstation_id?: string;
  os_kind?: NexoOsKind;
  status?: NexoInstallationStatus;
}

export function useNexoBuilds() {
  return useQuery<NexoBuildCatalog>({
    queryKey: ["nexo-builds"],
    queryFn: ({ signal }) => apiClient.get("/api/v1/nexo-agent-builds", { signal }),
    staleTime: 15_000,
    refetchInterval: (query) => query.state.data?.builds.some((build) => build.status === "queued" || build.status === "building") ? 3_000 : false,
  });
}
export function useRefreshNexoBuilds() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<NexoBuild[]>("/api/v1/nexo-agent-builds"),
    retry: false,
    // A platform can complete before another fails; always refresh persisted state.
    onSettled: () => qc.invalidateQueries({ queryKey: ["nexo-builds"] }),
  });
}
export function useNexoInstallations(filters: NexoInstallationFilters = {}) {
  return useQuery<NexoInstallation[]>({
    queryKey: ["nexo-installations", filters],
    queryFn: ({ signal }) => apiClient.get("/api/v1/nexo-installations", { params: { ...filters }, signal }),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}
export function useNexoInstallation(installationId?: string | null) {
  return useQuery<NexoInstallationDetail>({
    queryKey: ["nexo-installations", "detail", installationId],
    queryFn: ({ signal }) => apiClient.get(`/api/v1/nexo-installations/${encodeURIComponent(installationId!)}`, { signal }),
    enabled: Boolean(installationId),
    refetchInterval: 15_000,
  });
}
export function useGenerateNexoPackage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ workstationId, buildId }: { workstationId: string; buildId: string }) => {
      const { blob, filename } = await apiClient.postDownload(`/api/v1/workstations/${encodeURIComponent(workstationId)}/installation-package?build_id=${encodeURIComponent(buildId)}`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      try {
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
      } finally {
        anchor.remove();
        URL.revokeObjectURL(url);
      }
    },
    retry: false,
    // Delivery can fail after token rotation committed. Reconcile even on failure.
    onSettled: () => Promise.all(["nexo-builds", "nexo-installations", "workstations"].map((key) => qc.invalidateQueries({ queryKey: [key] }))),
  });
}
