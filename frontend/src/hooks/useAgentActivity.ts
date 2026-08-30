import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";
import { demandKeys } from "./useDemands";
import { notificationKeys } from "./useNotifications";

const uuidSchema = z.string().uuid();
// Pydantic's `datetime` contract permits both timezone-aware and naive ISO
// strings, so accept either serialization without changing the raw value.
const timestampSchema = z.string().datetime({ offset: true, local: true });

export const activityRecordLinkSchema = z.object({
  source_type: z.string(),
  source_id: uuidSchema,
  canonical_path: z.string(),
  label: z.string().nullable(),
});
export type ActivityRecordLink = z.infer<typeof activityRecordLinkSchema>;

export const activityCheckpointSchema = z.object({
  id: uuidSchema,
  execution_id: uuidSchema,
  occurred_at: timestampSchema,
  status: z.string(),
  resume_from_step_key: z.string().nullable(),
  summary: z.string().nullable(),
  evidence_summary: z.string().nullable(),
  verification_summary: z.string().nullable(),
  error_code: z.string().nullable(),
  blocker_code: z.string().nullable(),
  canonical_path: z.string(),
});
export type ActivityCheckpoint = z.infer<typeof activityCheckpointSchema>;

export const activityProfileSummarySchema = z.object({
  status: z.enum(["healthy", "warning", "error", "unavailable"]),
  checked_at: timestampSchema,
  runtime_native: z.boolean(),
  canonical_path: z.string(),
  profile_path: z.string().nullable(),
  last_heartbeat_at: timestampSchema.nullable(),
  issues: z.array(z.string()),
});
export type ActivityProfileSummary = z.infer<typeof activityProfileSummarySchema>;

export const activityCurrentWorkSchema = z.object({
  project_id: uuidSchema.nullable(),
  project_name: z.string().nullable(),
  project_path: z.string().nullable(),
  task_id: uuidSchema.nullable(),
  task_title: z.string().nullable(),
  task_path: z.string().nullable(),
  assignment_id: uuidSchema.nullable(),
  work_package_id: uuidSchema.nullable(),
  execution_id: uuidSchema.nullable(),
  execution_path: z.string().nullable(),
  action: z.string().nullable(),
  branch: z.string().nullable(),
  working_directory_path: z.string().nullable(),
  requested_by_agent_id: uuidSchema.nullable(),
  source_message_id: uuidSchema.nullable(),
  source_message_path: z.string().nullable(),
});
export type ActivityCurrentWork = z.infer<typeof activityCurrentWorkSchema>;

export const activityAgentSchema = z.object({
  id: uuidSchema,
  name: z.string(),
  profile_slug: z.string().nullable(),
  runtime_type: z.string(),
  availability: z.enum(["available", "busy", "degraded", "unavailable", "unknown"]),
  availability_reason: z.string().nullable(),
  last_heartbeat_at: timestampSchema.nullable(),
  canonical_path: z.string(),
  current_work: activityCurrentWorkSchema.nullable(),
  latest_checkpoint: activityCheckpointSchema.nullable(),
  profile_summary: activityProfileSummarySchema,
});
export type ActivityAgent = z.infer<typeof activityAgentSchema>;

export const activityMessageEdgeSchema = z.object({
  message_id: uuidSchema,
  from_agent_id: uuidSchema.nullable(),
  from_agent_name: z.string().nullable(),
  target_agent_id: uuidSchema.nullable(),
  target_agent_name: z.string().nullable(),
  reply_to_id: uuidSchema.nullable(),
  project_id: uuidSchema.nullable(),
  task_id: uuidSchema.nullable(),
  subject: z.string().nullable(),
  dispatch_status: z.string(),
  requires_response: z.boolean(),
  response_status: z.string().nullable(),
  waiting_for_response: z.boolean(),
  waiting_on_agent_id: uuidSchema.nullable(),
  sent_at: timestampSchema,
  updated_at: timestampSchema,
  responded_at: timestampSchema.nullable(),
  canonical_path: z.string(),
});
export type ActivityMessageEdge = z.infer<typeof activityMessageEdgeSchema>;

export const activityPriorAttemptSchema = z.object({
  id: uuidSchema,
  execution_id: uuidSchema,
  attempt_number: z.number().int().min(1),
  started_at: timestampSchema,
  completed_at: timestampSchema.nullable(),
  outcome: z.string(),
  error_code: z.string().nullable(),
  summary: z.string().nullable(),
  canonical_path: z.string(),
  related_records: z.array(activityRecordLinkSchema),
});
export type ActivityPriorAttempt = z.infer<typeof activityPriorAttemptSchema>;

export const activityIncidentSchema = z.object({
  key: z.string(),
  kind: z.enum([
    "execution_failed",
    "heartbeat_lost",
    "runtime_limit",
    "blocked",
    "approval_pending",
    "source_unavailable",
  ]),
  severity: z.enum(["info", "warning", "error", "critical"]),
  title: z.string(),
  occurred_at: timestampSchema,
  source_type: z.string(),
  source_id: uuidSchema,
  affected_agent_id: uuidSchema.nullable(),
  project_id: uuidSchema.nullable(),
  task_id: uuidSchema.nullable(),
  execution_id: uuidSchema.nullable(),
  checkpoint_id: uuidSchema.nullable(),
  resume_from_step_key: z.string().nullable(),
  error_code: z.string().nullable(),
  blocker_code: z.string().nullable(),
  summary: z.string().nullable(),
  recommended_action: z.enum([
    "request_athos_monitoring",
    "open_approval",
    "open_message",
    "inspect_execution",
  ]),
  prior_attempts: z.array(activityPriorAttemptSchema),
  last_observed_at: timestampSchema.nullable(),
  impact: z.string().nullable(),
  runtime_type: z.string().nullable(),
  provider: z.string().nullable(),
  current_owner_agent_id: uuidSchema.nullable(),
  canonical_path: z.string().nullable(),
  related_records: z.array(activityRecordLinkSchema),
});
export type ActivityIncident = z.infer<typeof activityIncidentSchema>;

export const activityTimelineEventSchema = z.object({
  key: z.string(),
  kind: z.string(),
  occurred_at: timestampSchema,
  source_type: z.string(),
  source_id: uuidSchema,
  title: z.string(),
  canonical_path: z.string(),
  summary: z.string().nullable(),
  agent_id: uuidSchema.nullable(),
  project_id: uuidSchema.nullable(),
  task_id: uuidSchema.nullable(),
  execution_id: uuidSchema.nullable(),
  checkpoint_id: uuidSchema.nullable(),
  approval_id: uuidSchema.nullable(),
  notification_id: uuidSchema.nullable(),
  related_records: z.array(activityRecordLinkSchema),
});
export type ActivityTimelineEvent = z.infer<typeof activityTimelineEventSchema>;

export const activitySourceFreshnessSchema = z.object({
  name: z.string(),
  status: z.enum(["fresh", "stale", "unavailable"]),
  checked_at: timestampSchema,
  observed_at: timestampSchema.nullable(),
  age_seconds: z.number().int().min(0).nullable(),
  detail: z.string().nullable(),
  error_code: z.string().nullable(),
});
export type ActivitySourceFreshness = z.infer<typeof activitySourceFreshnessSchema>;

export const agentActivitySchema = z.object({
  contract_version: z.literal("forge-agent-activity/v1"),
  generated_at: timestampSchema,
  project_id: uuidSchema.nullable(),
  agents: z.array(activityAgentSchema),
  message_edges: z.array(activityMessageEdgeSchema),
  incidents: z.array(activityIncidentSchema),
  timeline: z.array(activityTimelineEventSchema),
  source_freshness: z.array(activitySourceFreshnessSchema),
});
export type AgentActivity = z.infer<typeof agentActivitySchema>;

export const activityFiltersSchema = z.object({
  project_id: uuidSchema.optional(),
  window_minutes: z.number().int().min(1).max(24 * 60).optional(),
});
export type ActivityFilters = z.infer<typeof activityFiltersSchema>;

export const requestAthosMonitoringResultSchema = z.object({
  message_id: uuidSchema,
  message_number: z.number().int(),
  notification_id: uuidSchema,
  created: z.boolean(),
});
export type RequestAthosMonitoringResult = z.infer<typeof requestAthosMonitoringResultSchema>;

export interface RequestAthosMonitoringVariables {
  incidentKey: string;
  executionId: string;
  /** Omit only when the browser can safely create an idempotency key. */
  idempotencyKey?: string;
}

export const agentActivityKeys = {
  all: ["agent-activity"] as const,
  detail: (filters: ActivityFilters = {}) => ["agent-activity", filters] as const,
};

export function useAgentActivity(filters: ActivityFilters = {}) {
  return useQuery({
    queryKey: agentActivityKeys.detail(filters),
    queryFn: () => apiClient.get<unknown>("/api/v1/agent-activity", { params: filters }),
    select: (value) => agentActivitySchema.parse(value),
    refetchInterval: 5_000,
    refetchIntervalInBackground: true,
  });
}

export function useRequestAthosMonitoring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ incidentKey, executionId, idempotencyKey }: RequestAthosMonitoringVariables) => {
      const value = await apiClient.post<unknown>(
        `/api/v1/agent-activity/incidents/${encodeURIComponent(incidentKey)}:request-athos-monitoring`,
        {
          execution_id: executionId,
          idempotency_key: idempotencyKey ?? crypto.randomUUID(),
        }
      );
      return requestAthosMonitoringResultSchema.parse(value);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: agentActivityKeys.all }),
        queryClient.invalidateQueries({ queryKey: demandKeys.all }),
        queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
      ]);
    },
  });
}
