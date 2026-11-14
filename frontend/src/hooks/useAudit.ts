import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Audit domain (backend/app/api/routes/audit.py): configurable ecosystem
 * checkpoints executed on the host via the chat bridge. Backs the Auditor
 * page — checklist CRUD, run-now (single/all) and run history.
 */

/** Auditor tiers (2026-11-13): each runs as one Operação 24x7 audit routine. */
export const AUDIT_FREQUENCIES = ["daily", "weekly", "monthly", "quarterly"] as const;
export const auditFrequencySchema = z.enum(AUDIT_FREQUENCIES);
export type AuditFrequency = z.infer<typeof auditFrequencySchema>;

export const auditRunSchema = z.object({
  id: z.string(),
  check_id: z.string(),
  batch_id: z.string().nullable().optional(),
  status: z.enum(["ok", "fail", "error", "timeout"]),
  exit_code: z.number().nullable(),
  output: z.string().nullable(),
  duration_ms: z.number().nullable(),
  requested_by: z.string(),
  created_at: z.string(),
});

export type AuditRun = z.infer<typeof auditRunSchema>;

const auditRemediationSchema = z.object({
  remediation_run: auditRunSchema,
  verification_run: auditRunSchema,
  escalated_to_inbox: z.boolean(),
  inbox_demand_id: z.string().nullable(),
});

export type AuditRemediation = z.infer<typeof auditRemediationSchema>;

export const auditCheckSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  category: z.string().nullable(),
  command: z.string(),
  remediation_description: z.string().nullable(),
  remediation_command: z.string().nullable(),
  workdir: z.string().nullable(),
  agent_profile: z.string(),
  enabled: z.boolean(),
  timeout_seconds: z.number(),
  frequency: auditFrequencySchema.default("weekly"),
  created_at: z.string(),
  updated_at: z.string(),
  last_run: auditRunSchema.nullable(),
  evidence_state: z.enum(["fresh", "stale", "never"]).optional(),
  expires_at: z.string().nullable().optional(),
});

export type AuditCheck = z.infer<typeof auditCheckSchema>;

export const athosAuditMonitorSchema = z.object({
  state: z.enum(["healthy", "degraded", "failed", "not_configured", "replaced"]),
  job_id: z.string().nullable(),
  job_name: z.string().nullable(),
  script: z.string().nullable(),
  schedule: z.string().nullable(),
  enabled: z.boolean().nullable(),
  health: z.string().nullable(),
  last_run_at: z.string().nullable(),
  last_status: z.string().nullable(),
  next_run_at: z.string().nullable(),
  last_cron_run_at: z.string().nullable(),
  issues: z.array(z.string()),
});

export const auditTierSchema = z.object({
  frequency: auditFrequencySchema,
  enabled_checks: z.number(),
  last_complete_run_at: z.string().nullable(),
  routine_id: z.string().nullable(),
  routine_title: z.string().nullable(),
  routine_enabled: z.boolean(),
  schedule: z.string().nullable(),
  timezone: z.string().nullable(),
  next_due_at: z.string().nullable(),
  overdue: z.boolean(),
});

export type AuditTier = z.infer<typeof auditTierSchema>;

const auditStatusSchema = z.object({
  total: z.number(),
  enabled: z.number(),
  ok: z.number(),
  fail: z.number(),
  never_ran: z.number(),
  stale: z.number().default(0),
  last_complete_cron_run_at: z.string().nullable().default(null),
  last_run_at: z.string().nullable(),
  athos_monitor: athosAuditMonitorSchema.nullish(),
  schedule_source: z.enum(["routines", "hermes_cron"]).default("hermes_cron"),
  tiers: z.array(auditTierSchema).default([]),
});

export type AuditStatus = z.infer<typeof auditStatusSchema>;

export interface AuditCheckInput {
  name: string;
  description?: string | null;
  category?: string | null;
  command: string;
  remediation_description?: string | null;
  remediation_command?: string | null;
  workdir?: string | null;
  agent_profile?: string;
  enabled?: boolean;
  timeout_seconds?: number;
  frequency?: AuditFrequency;
}

const RESOURCE = "/api/v1/audit";
// Evidence can expire without any mutation; keep mounted status and rows current.
const EVIDENCE_REFRESH_MS = 60_000;

export const auditKeys = {
  checks: ["audit-checks"] as const,
  status: ["audit-status"] as const,
  runs: (checkId: string | null) => ["audit-runs", checkId] as const,
};

function useInvalidateAudit() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: auditKeys.checks });
    queryClient.invalidateQueries({ queryKey: auditKeys.status });
    queryClient.invalidateQueries({ queryKey: ["audit-runs"] });
  };
}

export function useAuditChecks() {
  return useQuery({
    queryKey: auditKeys.checks,
    refetchInterval: EVIDENCE_REFRESH_MS,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
    queryFn: async () => z.array(auditCheckSchema).parse(await apiClient.get<unknown>(`${RESOURCE}/checks`)),
  });
}

export function useAuditStatus() {
  return useQuery({
    queryKey: auditKeys.status,
    refetchInterval: EVIDENCE_REFRESH_MS,
    refetchIntervalInBackground: true,
    refetchOnWindowFocus: true,
    queryFn: async () => auditStatusSchema.parse(await apiClient.get<unknown>(`${RESOURCE}/status`)),
  });
}

export function useAuditRuns(checkId: string | null) {
  return useQuery({
    queryKey: auditKeys.runs(checkId),
    queryFn: async () =>
      z
        .array(auditRunSchema)
        .parse(await apiClient.get<unknown>(`${RESOURCE}/runs?limit=10${checkId ? `&check_id=${checkId}` : ""}`)),
    enabled: Boolean(checkId),
  });
}

export function useCreateAuditCheck() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: (payload: AuditCheckInput) => apiClient.post<unknown>(`${RESOURCE}/checks`, payload),
    onSuccess: invalidate,
  });
}

export function useUpdateAuditCheck() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: ({ checkId, updates }: { checkId: string; updates: Partial<AuditCheckInput> }) =>
      apiClient.patch<unknown>(`${RESOURCE}/checks/${checkId}`, updates),
    onSuccess: invalidate,
  });
}

export function useDeleteAuditCheck() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: (checkId: string) => apiClient.delete<void>(`${RESOURCE}/checks/${checkId}`),
    onSuccess: invalidate,
  });
}

/** Run a single check now. */
export function useRunAuditCheck() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: (checkId: string) => apiClient.post<unknown>(`${RESOURCE}/checks/${checkId}/run`),
    onSuccess: invalidate,
  });
}

/** "Solicitar checagem": dispatch every enabled check at once, or one tier's. */
export function useRunAllAuditChecks() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: (frequency?: AuditFrequency) =>
      apiClient.post<unknown>(`${RESOURCE}/run${frequency ? `?frequency=${frequency}` : ""}`),
    onSuccess: invalidate,
  });
}

/** Admin: run a tier now through its audit routine ("Executar agora"). The
 * batch runs in the background, so this returns at once instead of holding
 * an HTTP request for the whole batch; the tier's status refreshes after. */
export function useRunAuditRoutineNow() {
  const invalidate = useInvalidateAudit();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (routineId: string) => apiClient.post<unknown>(`/api/v1/operations/routines/${routineId}:run-now`),
    onSuccess: () => {
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["operations"] });
    },
  });
}

/** Admin: move a check to another frequency tier. */
export function useSetAuditCheckFrequency() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: ({ checkId, frequency }: { checkId: string; frequency: AuditFrequency }) =>
      apiClient.put<unknown>(`${RESOURCE}/checks/${checkId}/frequency`, { frequency }),
    onSuccess: invalidate,
  });
}

/** Delegate the approved correction to Athos, recheck, and escalate if needed. */
export function useRemediateAuditCheck() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: async (checkId: string) =>
      auditRemediationSchema.parse(
        await apiClient.post<unknown>(`${RESOURCE}/checks/${checkId}/remediate`),
      ),
    onSuccess: invalidate,
  });
}
