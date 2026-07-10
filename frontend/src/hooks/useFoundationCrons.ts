import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Hermes `hermes cron` job registry (backend/app/api/routes/foundation.py
 * list_cron_jobs). Pure filesystem read of each profile's cron/jobs.json --
 * no DB table backs this, same as the rest of the Foundation router.
 */

export const cronJobSchema = z.object({
  profile: z.string(),
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  script: z.string().nullable(),
  schedule_display: z.string().nullable(),
  enabled: z.boolean(),
  state: z.string(),
  status: z.enum(["active", "paused", "disabled"]),
  // Whether the job is actually executing (status only mirrors the enabled
  // flag): overdue = its next_run_at is in the past, the scheduler is not
  // running it. See foundation.py's _job_health.
  health: z.enum(["ok", "error", "overdue", "never_ran", "off"]),
  next_run_at: z.string().nullable(),
  last_run_at: z.string().nullable(),
  last_status: z.string().nullable(),
  last_error: z.string().nullable(),
  // mtime of the script's execution log in crons/logs/ -- real run evidence.
  last_log_at: z.string().nullable(),
  deliver: z.string().nullable(),
});

export type CronJob = z.infer<typeof cronJobSchema>;

// A profile's cron/jobs.json that failed to parse. Its jobs are absent from
// `jobs` AND that profile's scheduler has stopped running them (the gateway
// refuses to tick on a corrupted store) -- must be shown, never swallowed.
export const cronStoreErrorSchema = z.object({
  profile: z.string(),
  store: z.string(),
  error: z.string(),
});

export type CronStoreError = z.infer<typeof cronStoreErrorSchema>;

const cronJobListSchema = z.object({
  jobs: z.array(cronJobSchema),
  store_errors: z.array(cronStoreErrorSchema).default([]),
});

export type CronJobList = z.infer<typeof cronJobListSchema>;

export const cronJobKeys = {
  list: ["foundation-crons"] as const,
};

export function useFoundationCrons() {
  return useQuery({
    queryKey: cronJobKeys.list,
    queryFn: async () => {
      const data = await apiClient.get<unknown>("/api/v1/foundation/crons");
      return cronJobListSchema.parse(data);
    },
  });
}

export function useDeleteCronJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiClient.delete(`/api/v1/foundation/crons/${jobId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cronJobKeys.list });
    },
  });
}

export interface CronJobUpdate {
  name?: string;
  description?: string;
  schedule_display?: string;
  deliver?: string;
  enabled?: boolean;
}

export function useUpdateCronJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ jobId, updates }: { jobId: string; updates: CronJobUpdate }) =>
      apiClient.put<unknown>(`/api/v1/foundation/crons/${jobId}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cronJobKeys.list });
    },
  });
}

/** Re-arm a job: clears its last error/status and recomputes the next run
 * from the schedule, without changing whether it is enabled. */
export function useResetCronJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiClient.post<unknown>(`/api/v1/foundation/crons/${jobId}/reset`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cronJobKeys.list });
    },
  });
}