import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";
import { agentLiveSnapshotSchema } from "./useAgentActivity";

const uuidSchema = z.string().uuid();
const timestampSchema = z.string().datetime({ offset: true, local: true });

export const timelineToolSchema = z.object({
  start: timestampSchema,
  end: timestampSchema.nullable(),
  tool_name: z.string().nullable(),
  status: z.string().nullable(),
  duration_ms: z.number().int().nullable(),
});
export type TimelineTool = z.infer<typeof timelineToolSchema>;

export const timelineBlockSchema = z.object({
  key: z.string(),
  kind: z.enum(["turn", "dispatch", "workspace"]),
  start: timestampSchema,
  end: timestampSchema.nullable(),
  platform: z.string().nullable(),
  counterpart_kind: z.enum(["owner", "human", "agent", "system"]).nullable(),
  counterpart_ref: z.string().nullable(),
  counterpart_agent_id: uuidSchema.nullable(),
  model: z.string().nullable(),
  status: z.string().nullable(),
  error_type: z.string().nullable(),
  session_id: z.string().nullable(),
  turn_id: z.string().nullable(),
  message_number: z.number().int().nullable(),
  tools: z.array(timelineToolSchema),
  canonical_path: z.string().nullable(),
});
export type TimelineBlock = z.infer<typeof timelineBlockSchema>;

export const timelineLaneSchema = z.object({
  agent_id: uuidSchema,
  blocks: z.array(timelineBlockSchema),
});
export type TimelineLane = z.infer<typeof timelineLaneSchema>;

export const timelineMessageSchema = z.object({
  id: uuidSchema,
  number: z.number().int().nullable(),
  at: timestampSchema,
  from_agent_id: uuidSchema,
  target_agent_id: uuidSchema,
  subject: z.string().nullable(),
  canonical_path: z.string(),
});
export type TimelineMessage = z.infer<typeof timelineMessageSchema>;

export const timelineEventSchema = z.object({
  key: z.string(),
  occurred_at: timestampSchema,
  agent_id: uuidSchema.nullable(),
  profile: z.string().nullable(),
  source: z.enum(["runtime", "messages", "workspace"]),
  kind: z.string(),
  platform: z.string().nullable(),
  counterpart_kind: z.string().nullable(),
  counterpart_ref: z.string().nullable(),
  model: z.string().nullable(),
  tool_name: z.string().nullable(),
  status: z.string().nullable(),
  error_type: z.string().nullable(),
  duration_ms: z.number().int().nullable(),
  session_id: z.string().nullable(),
  turn_id: z.string().nullable(),
  message_number: z.number().int().nullable(),
  canonical_path: z.string().nullable(),
});
export type TimelineEvent = z.infer<typeof timelineEventSchema>;

export const routineOutcomeSchema = z.enum(["scheduled", "pending", "running", "done", "failed", "missed", "skipped"]);
export type RoutineOutcome = z.infer<typeof routineOutcomeSchema>;

/**
 * One routine occurrence (A.2): one per (routine, instant). Past ones carry their outcome,
 * the next 24 h are `scheduled`; `missed` = its deadline passed without a run.
 */
export const timelineRoutineSchema = z.object({
  key: z.string(),
  routine_id: uuidSchema,
  agent_id: uuidSchema,
  title: z.string(),
  routine_kind: z.string(),
  timezone: z.string(),
  occurrence_at: timestampSchema,
  deadline_at: timestampSchema,
  outcome: routineOutcomeSchema,
  recorded: z.boolean(),
  run_id: uuidSchema.nullable(),
  detail: z.string().nullable(),
  finished_at: timestampSchema.nullable(),
  duration_ms: z.number().int().nullable(),
  message_number: z.number().int().nullable(),
  canonical_path: z.string().nullable(),
});
export type TimelineRoutine = z.infer<typeof timelineRoutineSchema>;

export const activityTimelineSchema = z.object({
  start: timestampSchema,
  end: timestampSchema,
  generated_at: timestampSchema,
  lanes: z.array(timelineLaneSchema),
  messages: z.array(timelineMessageSchema),
  events: z.array(timelineEventSchema),
  truncated: z.boolean(),
  // Optional: a backend from before A.2 doesn't send them.
  routines: z.array(timelineRoutineSchema).optional(),
  routines_until: timestampSchema.nullable().optional(),
});
export type ActivityTimeline = z.infer<typeof activityTimelineSchema>;

export interface TimelineWindow {
  start: string;
  end: string;
}

export const activityTimelineKeys = {
  all: ["agent-activity", "timeline"] as const,
  window: (window: TimelineWindow | null) => ["agent-activity", "timeline", window] as const,
  snapshotAt: (at: string | null) => ["agent-activity", "snapshot", at] as const,
};

/**
 * GET /api/v1/agent-activity/timeline -- lanes, messages between agents and the event
 * table for one window. `refetchInterval` is set only while the window ends "now".
 */
export function useActivityTimeline(window: TimelineWindow | null, options: { refetchInterval?: number | false } = {}) {
  return useQuery({
    queryKey: activityTimelineKeys.window(window),
    queryFn: () => apiClient.get<unknown>("/api/v1/agent-activity/timeline", { params: window ? { start: window.start, end: window.end } : {} }),
    select: (value) => activityTimelineSchema.parse(value),
    enabled: window !== null,
    placeholderData: keepPreviousData,
    refetchInterval: options.refetchInterval ?? false,
  });
}

/** GET /api/v1/agent-activity/snapshot?at= -- the live frame as it stood at a past instant. */
export function useActivitySnapshotAt(at: string | null) {
  return useQuery({
    queryKey: activityTimelineKeys.snapshotAt(at),
    queryFn: () => apiClient.get<unknown>("/api/v1/agent-activity/snapshot", { params: { at: at ?? undefined } }),
    select: (value) => agentLiveSnapshotSchema.parse(value),
    enabled: at !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity, // the past doesn't change
  });
}
