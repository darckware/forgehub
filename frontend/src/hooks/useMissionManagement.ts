import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/lib/api";
import i18n from "@/i18n";
export interface MissionRecord {
  project_id: string; name: string; description: string | null; working_directory_path: string | null;
  product_version_id: string; orchestrator_agent_id: string; priority: number; deadline_at: string | null;
  budget_limit: string | number | null; state: string; planning_stage: string | null; current_baseline_id: string | null; row_version: number;
}
export function useMissionRecord(id: string | undefined) {
  return useQuery({ queryKey: ["mission-record", id], queryFn: () => apiClient.get<MissionRecord>(`/api/v1/missions/${id}`), enabled: Boolean(id) });
}
export function useSaveMission(id?: string) {
  const cache = useQueryClient();
  return useMutation({ mutationFn: (body: Record<string, unknown>) => id
    ? apiClient.patch<{ project_id: string }>(`/api/v1/missions/${id}`, body)
    : apiClient.post<{ project_id: string }>("/api/v1/missions", body),
    onSuccess: async () => { await cache.invalidateQueries({ queryKey: ["missions"] }); await cache.invalidateQueries({ queryKey: ["mission-record"] }); await cache.invalidateQueries({ queryKey: ["mission-board"] }); },
  });
}
export function useCancelMission(id?: string) {
  const cache = useQueryClient();
  return useMutation({ mutationFn: (body: { expected_row_version: number; reason: string }) => apiClient.post<MissionRecord>(`/api/v1/missions/${id}:transition`, { ...body, to: "cancelled" }),
    onSuccess: async () => { await cache.invalidateQueries({ queryKey: ["missions"] }); await cache.invalidateQueries({ queryKey: ["mission-record"] }); await cache.invalidateQueries({ queryKey: ["mission-board"] }); },
  });
}
export function useApplyMissionMember(projectId: string) {
  const cache = useQueryClient();
  return useMutation({
    mutationFn: (body: { idempotency_key: string; operations: Array<{ op: "add" | "update" | "release"; agent_id: string; role?: string; responsibilities?: string; can_review?: boolean }> }) =>
      apiClient.post(`/api/v1/missions/${projectId}/members:apply`, body),
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({ queryKey: ["project-memberships", projectId] }),
        cache.invalidateQueries({ queryKey: ["mission-board", projectId] }),
      ]);
    },
  });
}
export function missionError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.status === 409) return i18n.t("missions:form.conflict");
    const body = error.body as { detail?: { message?: string; violations?: Array<{ message?: string }> } | string };
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail && !Array.isArray(body.detail) && body.detail.message) return [body.detail.message, ...(body.detail.violations ?? []).map((v) => v.message)].filter(Boolean).join(" ");
  }
  return fallback;
}
