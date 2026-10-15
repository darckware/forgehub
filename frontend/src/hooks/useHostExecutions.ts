import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/** Remote Access phase 4: commands run on machines, one result per machine. */

export type ExecShell = "sh" | "powershell";
export type ExecResultStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type ExecVerdict = "running" | "succeeded" | "failed" | "nothing_ran";

export interface ExecCounts {
  total: number;
  pending: number;
  running: number;
  succeeded: number;
  failed: number;
  skipped: number;
}

export interface HostExecutionResult {
  id: string;
  server_id: string | null;
  server_name: string;
  status: ExecResultStatus;
  failure: "timeout" | "auth" | "connection" | "command" | "interrupted" | null;
  skip_reason: string | null;
  exit_code: number | null;
  stdout: string | null;
  stderr: string | null;
  truncated: boolean;
  duration_ms: number | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface HostExecutionSummary {
  id: string;
  parent_execution_id: string | null;
  shell: ExecShell;
  command: string;
  timeout_seconds: number;
  status: "running" | "completed" | "cancelled";
  requested_by: string;
  target_summary: string | null;
  started_at: string;
  finished_at: string | null;
  counts: ExecCounts;
  verdict: ExecVerdict;
}

export interface HostExecutionDetail extends HostExecutionSummary {
  results: HostExecutionResult[];
  follow_up_ids: string[];
}

export interface HostExecutionCreate {
  command: string;
  shell: ExecShell;
  server_ids: string[];
  group_ids: string[];
  timeout_seconds: number;
}

const KEY = ["host-executions"] as const;

function isLive(e: { verdict: ExecVerdict } | undefined) {
  return e?.verdict === "running";
}

export function useHostExecutions(limit = 20) {
  return useQuery<HostExecutionSummary[]>({
    queryKey: [...KEY, "list", limit],
    queryFn: () => apiClient.get(`/api/v1/host-executions?limit=${limit}`),
    refetchInterval: (query) => (query.state.data?.some(isLive) ? 3_000 : 30_000),
  });
}

/** Polls every 2 s while any machine is still pending/running. */
export function useHostExecution(id: string | undefined) {
  return useQuery<HostExecutionDetail>({
    queryKey: [...KEY, id],
    queryFn: () => apiClient.get(`/api/v1/host-executions/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => (isLive(query.state.data) ? 2_000 : false),
  });
}

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: KEY });
    void qc.invalidateQueries({ queryKey: ["servers", "readiness"] });
  };
}

export function useCreateHostExecution() {
  const invalidate = useInvalidate();
  return useMutation<HostExecutionDetail, Error, HostExecutionCreate>({
    mutationFn: (data) => apiClient.post("/api/v1/host-executions", data),
    onSuccess: invalidate,
  });
}

export function useFollowUpHostExecution() {
  const invalidate = useInvalidate();
  return useMutation<
    HostExecutionDetail,
    Error,
    { id: string; command: string; shell: ExecShell; timeout_seconds: number }
  >({
    mutationFn: ({ id, ...data }) => apiClient.post(`/api/v1/host-executions/${id}:follow-up`, data),
    onSuccess: invalidate,
  });
}

export function useCancelHostExecution() {
  const invalidate = useInvalidate();
  return useMutation<HostExecutionDetail, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/host-executions/${id}:cancel`, {}),
    onSuccess: invalidate,
  });
}

/** Shell that fits every machine picked, or null when they mix Windows with
 * Linux/macOS (the backend would skip the incompatible ones). */
export function shellForOs(osFamilies: (string | null)[]): ExecShell | null {
  if (osFamilies.length === 0) return null;
  const windows = osFamilies.filter((os) => os === "windows").length;
  if (windows === osFamilies.length) return "powershell";
  if (windows === 0) return "sh";
  return null;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}
