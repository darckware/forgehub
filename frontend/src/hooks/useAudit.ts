import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Audit domain (backend/app/api/routes/audit.py): configurable ecosystem
 * checkpoints executed on the host via the chat bridge. Backs the Auditor
 * page — checklist CRUD, run-now (single/all) and run history.
 */

export const auditRunSchema = z.object({
  id: z.string(),
  check_id: z.string(),
  status: z.enum(["ok", "fail", "error", "timeout"]),
  exit_code: z.number().nullable(),
  output: z.string().nullable(),
  duration_ms: z.number().nullable(),
  requested_by: z.string(),
  created_at: z.string(),
});

export type AuditRun = z.infer<typeof auditRunSchema>;

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
  created_at: z.string(),
  updated_at: z.string(),
  last_run: auditRunSchema.nullable(),
});

export type AuditCheck = z.infer<typeof auditCheckSchema>;

const auditStatusSchema = z.object({
  total: z.number(),
  enabled: z.number(),
  ok: z.number(),
  fail: z.number(),
  never_ran: z.number(),
  last_run_at: z.string().nullable(),
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
}

const RESOURCE = "/api/v1/audit";

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
    queryFn: async () => z.array(auditCheckSchema).parse(await apiClient.get<unknown>(`${RESOURCE}/checks`)),
  });
}

export function useAuditStatus() {
  return useQuery({
    queryKey: auditKeys.status,
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

/** "Solicitar checagem": dispatch every enabled check at once. */
export function useRunAllAuditChecks() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: () => apiClient.post<unknown>(`${RESOURCE}/run`),
    onSuccess: invalidate,
  });
}

/** Apply the check's administrator-approved repair and immediately recheck. */
export function useRemediateAuditCheck() {
  const invalidate = useInvalidateAudit();
  return useMutation({
    mutationFn: (checkId: string) => apiClient.post<unknown>(`${RESOURCE}/checks/${checkId}/remediate`),
    onSuccess: invalidate,
  });
}
