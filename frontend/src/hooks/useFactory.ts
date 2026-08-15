import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Software Factory cockpit
 *
 * Read-only aggregation over the product/system_scope/backlog/task domains.
 * Backend contract: GET /api/v1/factory/cockpit (app/api/routes/factory.py).
 * The Factory domain owns no table.
 *
 * The shape is a Product -> Project tree: a product is durable and every
 * evolution of it becomes a project that walks the five phases. Product is
 * the root (not a flat project list) because this screen replaced the
 * Products and Projects pages in the sidebar -- a product with no project
 * yet still has to be reachable here.
 */

export const PHASE_KEYS = ["conception", "designer", "procedures", "execution", "quality"] as const;
export type PhaseKey = (typeof PHASE_KEYS)[number];

/** Route each phase opens when clicked, so the cockpit is a way into the
 * bottleneck and not just a read-out. */
export const PHASE_ROUTES: Record<PhaseKey, string> = {
  conception: "/conception",
  designer: "/system-map",
  procedures: "/backlog",
  execution: "/tasks",
  quality: "/governance",
};

export const phaseStatusSchema = z.object({
  key: z.enum(PHASE_KEYS),
  state: z.enum(["approved", "in_progress", "pending", "blocked"]),
  detail: z.string().nullable().optional(),
  total: z.number().nullable().optional(),
  done: z.number().nullable().optional(),
});

export type PhaseStatus = z.infer<typeof phaseStatusSchema>;

export const projectCockpitRowSchema = z.object({
  project_id: z.string(),
  project_name: z.string(),
  project_status: z.string(),
  project_description: z.string().nullable().optional(),
  version_id: z.string(),
  version_number: z.string(),
  version_status: z.string(),
  phases: z.array(phaseStatusSchema),
  planning_count: z.number().default(0),
  task_count: z.number().default(0),
  total_cost: z.number().default(0),
  // Team/room visibility (2026-08-05, Software Factory fix): active
  // ProjectAgentMembership count and this project's (oldest) ChatChannel,
  // if any -- see backend factory.py's team_size_by_project/channel_by_project.
  team_size: z.number().default(0),
  channel_id: z.string().nullable().optional(),
  // creation | maintenance + the project's active pipeline, if any
  // (2026-08-15) -- which development path this project is actually on.
  project_type: z.enum(["creation", "maintenance"]).default("creation"),
  pipeline_name: z.string().nullable().optional(),
  pipeline_template_name: z.string().nullable().optional(),
});

export type ProjectCockpitRow = z.infer<typeof projectCockpitRowSchema>;

export const productVersionRowSchema = z.object({
  version_id: z.string(),
  version_number: z.string(),
  version_status: z.string(),
});

export const productCockpitRowSchema = z.object({
  product_id: z.string(),
  product_name: z.string(),
  product_status: z.string(),
  product_description: z.string().nullable().optional(),
  application_url: z.string().nullable().optional(),
  application_url_dev: z.string().nullable().optional(),
  concept_status: z.string().nullable().optional(),
  versions: z.array(productVersionRowSchema),
  projects: z.array(projectCockpitRowSchema),
});

export type ProductCockpitRow = z.infer<typeof productCockpitRowSchema>;

export const cockpitSchema = z.object({
  products: z.array(productCockpitRowSchema),
});

export type Cockpit = z.infer<typeof cockpitSchema>;

export const cockpitKeys = {
  all: ["factory", "cockpit"] as const,
};

export function useCockpit() {
  return useQuery({
    queryKey: cockpitKeys.all,
    queryFn: async () => cockpitSchema.parse(await apiClient.get("/api/v1/factory/cockpit")),
  });
}

/**
 * Agent execution + dispatch telemetry (Pacote 5).
 *
 * Backend contract: GET /api/v1/factory/agent-telemetry (app/api/routes/factory.py).
 * Already aggregated server-side (per-agent counts/rates/avg duration/cost/
 * 14-day history) -- the frontend never recomputes this from raw executions.
 */
export const agentTelemetryHistoryPointSchema = z.object({
  date: z.string(),
  count: z.number(),
});

export const agentTelemetryRowSchema = z.object({
  agent_id: z.string(),
  agent_name: z.string(),
  executions_total: z.number(),
  executions_successful: z.number(),
  executions_failed: z.number(),
  executions_other: z.number(),
  success_rate: z.number().nullable().optional(),
  avg_duration_seconds: z.number().nullable().optional(),
  total_cost: z.number().default(0),
  dispatch_total: z.number(),
  dispatch_completed: z.number(),
  dispatch_failed: z.number(),
  dispatch_success_rate: z.number().nullable().optional(),
  history: z.array(agentTelemetryHistoryPointSchema).default([]),
});

export type AgentTelemetryRow = z.infer<typeof agentTelemetryRowSchema>;

export const agentTelemetrySchema = z.object({
  agents: z.array(agentTelemetryRowSchema),
});

export type AgentTelemetry = z.infer<typeof agentTelemetrySchema>;

export const agentTelemetryKeys = {
  all: ["factory", "agent-telemetry"] as const,
};

export function useAgentTelemetry() {
  return useQuery({
    queryKey: agentTelemetryKeys.all,
    queryFn: async () =>
      agentTelemetrySchema.parse(await apiClient.get("/api/v1/factory/agent-telemetry")),
  });
}
