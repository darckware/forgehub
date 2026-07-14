import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface ExecutionWave {
  id: string; project_id: string; baseline_id: string; pipeline_stage_id?: string | null;
  name: string; status: string; wip_limit: number; budget_limit?: number | null;
  preflight_snapshot?: { eligible: boolean; tasks: Array<{ task_id: string; eligible: boolean; reasons: string[] }> } | null;
  preflight_hash?: string | null; starts_at?: string | null; paused_at?: string | null;
}
export interface WorkPackage {
  id: string; task_id: string; assignment_id: string; runtime_profile_id: string;
  execution_wave_id: string; revision: number; status: string; validation_errors: string[];
  payload_hash: string; payload: Record<string, unknown>;
}

const invalidate = (qc: ReturnType<typeof useQueryClient>, projectId?: string, waveId?: string) => {
  if (projectId) qc.invalidateQueries({ queryKey: ["execution-waves", projectId] });
  if (waveId) qc.invalidateQueries({ queryKey: ["work-packages", waveId] });
  qc.invalidateQueries({ queryKey: ["tasks"] });
};

export function useExecutionWaves(projectId?: string) {
  return useQuery({ queryKey: ["execution-waves", projectId ?? ""], queryFn: () => apiClient.get<ExecutionWave[]>(`/api/v1/projects/${projectId}/execution-waves`), enabled: Boolean(projectId) });
}
export function useCreateExecutionWave(projectId: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (payload: Record<string, unknown>) => apiClient.post<ExecutionWave>(`/api/v1/projects/${projectId}/execution-waves`, payload), onSuccess: () => invalidate(qc, projectId) });
}
export function useWaveAction(projectId: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ waveId, action }: { waveId: string; action: "preflight" | "approve" | "activate" | "pause" | "resume" | "complete" }) => apiClient.post(`/api/v1/execution-waves/${waveId}:${action}`, {}), onSuccess: () => invalidate(qc, projectId) });
}
export function useWorkPackages(waveId?: string) {
  return useQuery({ queryKey: ["work-packages", waveId ?? ""], queryFn: () => apiClient.get<WorkPackage[]>(`/api/v1/execution-waves/${waveId}/work-packages`), enabled: Boolean(waveId) });
}
export function useBuildWorkPackage(projectId: string, waveId: string, taskId: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (payload: Record<string, unknown>) => apiClient.post<WorkPackage>(`/api/v1/execution-waves/${waveId}/tasks/${taskId}/work-packages`, payload), onSuccess: () => invalidate(qc, projectId, waveId) });
}
export function usePackageAction(projectId: string, waveId: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: ({ packageId, action }: { packageId: string; action: "issue" | "dispatch" }) => apiClient.post(`/api/v1/work-packages/${packageId}:${action}`, {}), onSuccess: () => invalidate(qc, projectId, waveId) });
}
export function useRefreshGovernedExecution(taskId: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (executionId: string) => apiClient.post(`/api/v1/executions/${executionId}:refresh-runtime`, {}), onSuccess: () => qc.invalidateQueries({ queryKey: ["task-executions", taskId] }) });
}
