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

export type ExecTrigger = "manual" | "schedule" | "agent";

export interface HostExecutionSummary {
  id: string;
  parent_execution_id: string | null;
  trigger: ExecTrigger;
  agent_id: string | null;
  agent_name: string | null;
  schedule_id: string | null;
  script_id: string | null;
  script_name: string | null;
  script_version: number | null;
  retry_until: string | null;
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
  script_id?: string | null;
  parameter_values?: Record<string, string | null>;
  command?: string | null;
  shell?: ExecShell | null;
  server_ids: string[];
  group_ids: string[];
  timeout_seconds: number;
}

const KEY = ["host-executions"] as const;

function isLive(e: { verdict: ExecVerdict } | undefined) {
  return e?.verdict === "running";
}

export interface ExecutionLogFilters {
  agent_id?: string;
  requested_by?: string;
  trigger?: ExecTrigger;
  server_id?: string;
  script_id?: string;
}

/** Execution log. Filters by agent (decision 7: what each agent ran), person,
 * origin, machine or script. */
export function useHostExecutions(limit = 20, filters: ExecutionLogFilters = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  for (const [k, v] of Object.entries(filters)) if (v) params.set(k, v);
  return useQuery<HostExecutionSummary[]>({
    queryKey: [...KEY, "list", limit, filters],
    queryFn: () => apiClient.get(`/api/v1/host-executions?${params.toString()}`),
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
    {
      id: string;
      command?: string | null;
      shell?: ExecShell | null;
      script_id?: string | null;
      parameter_values?: Record<string, string | null>;
      timeout_seconds?: number;
    }
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

/** A failure ForgeHub knows how to explain, recognized in a machine's output. */
export interface KnownFailure {
  kind: "tailscale_not_unattended";
  /** The Windows account the local Tailscale is bound to, when the output names it. */
  owner: string | null;
}

/** Recognizes failures whose fix is outside the script, so the screen can say
 * what to do instead of only showing the raw PowerShell error.
 *
 * tailscale_not_unattended (2026-10-18, desk-semed-admin): a Tailscale set up
 * from the Windows app, logged in as a person, only answers that person's
 * session; `tailscale status` from any other account -- the `darckware` login
 * ForgeHub runs as -- gets "401 Unauthorized: Tailscale already in use by
 * <owner>". The darckware-remote installer checks Tailscale before touching
 * RustDesk, so "Install RustDesk" fails there until the owner turns on
 * "Run unattended". ForgeHub can't fix it from that account by design. */
export function detectKnownFailure(output: string | null): KnownFailure | null {
  if (!output) return null;
  const match = /Tailscale already in use by\s+(.+?),\s*pid/i.exec(output);
  if (match || /failed to connect to local tailscaled[\s\S]*401 Unauthorized/i.test(output)) {
    return { kind: "tailscale_not_unattended", owner: match?.[1]?.trim() ?? null };
  }
  return null;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}
