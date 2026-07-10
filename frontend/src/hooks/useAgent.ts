import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/**
 * Agent domain (see docs/SPEC.md 4.6 Agent Domain / PRD.md 5.11-5.13):
 *   agents, sub_agents, skills, agent_skills, sub_agent_skills,
 *   agent_cost_rates, agent_capacities
 *
 * Agent is the primary entity -- an executor or coordinator agent. It owns
 * SubAgents (subordinate agents with scoped permissions/skills), Skills
 * (via the agent_skills association), cost rates, and capacities.
 *
 * Backend contract: every sub-resource is nested under /api/v1/agents/...
 * (never flat /api/v1/skills, /api/v1/sub-agents, etc. -- see
 * backend/app/api/routes/agent.py, prefix="/api/v1/agents").
 */

export const AGENT_TYPES = ["executor", "coordinator", "hybrid"] as const;
export type AgentType = (typeof AGENT_TYPES)[number];

export const AGENT_STATUSES = ["active", "inactive", "retired"] as const;
export type AgentStatus = (typeof AGENT_STATUSES)[number];

export const SKILL_RISK_LEVELS = ["low", "medium", "high", "critical"] as const;
export type SkillRiskLevel = (typeof SKILL_RISK_LEVELS)[number];

export const SKILL_ORIGINS = ["internal", "third_party", "foundation"] as const;
export type SkillOrigin = (typeof SKILL_ORIGINS)[number];

export const RUNTIME_TIERS = ["A", "B", "C"] as const;
export type RuntimeTier = (typeof RUNTIME_TIERS)[number];

// ---------------------------------------------------------------------------
// Schemas
// ---------------------------------------------------------------------------

export const skillAgentRefSchema = z.object({
  agent_id: z.string(),
  agent_name: z.string(),
});

export type SkillAgentRef = z.infer<typeof skillAgentRefSchema>;

export const skillSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  version: z.string(),
  origin: z.enum(SKILL_ORIGINS).default("internal"),
  risk_level: z.enum(SKILL_RISK_LEVELS).default("low"),
  permissions: z.string().default(""),
  is_approved: z.boolean().default(false),
  security_reviewed: z.boolean().default(false),
  // Agents holding this skill (agent_skills grants), embedded by the list
  // endpoint so the Skills page can filter by holder.
  agents: z.array(skillAgentRefSchema).default([]),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type Skill = z.infer<typeof skillSchema>;

export const agentSkillSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  skill_id: z.string(),
  inheritable: z.boolean().default(false),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type AgentSkill = z.infer<typeof agentSkillSchema>;

export const subAgentSkillSchema = z.object({
  id: z.string(),
  sub_agent_id: z.string(),
  skill_id: z.string(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type SubAgentSkill = z.infer<typeof subAgentSkillSchema>;

export const subAgentSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  status: z.enum(AGENT_STATUSES).default("active"),
  permission_scope: z.string().nullable().optional(),
  is_active: z.boolean().default(true),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
});

export type SubAgent = z.infer<typeof subAgentSchema>;

export const agentCostRateSchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  rate_unit: z.string(),
  rate_amount: z.number(),
  currency: z.string().default("USD"),
  is_active: z.boolean().default(true),
});

export type AgentCostRate = z.infer<typeof agentCostRateSchema>;

export const agentCapacitySchema = z.object({
  id: z.string(),
  agent_id: z.string(),
  max_concurrent_tasks: z.number(),
  max_daily_tasks: z.number().nullable().optional(),
  notes: z.string().nullable().optional(),
});

export type AgentCapacity = z.infer<typeof agentCapacitySchema>;

export const agentSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  agent_type: z.enum(AGENT_TYPES).default("executor"),
  status: z.enum(AGENT_STATUSES).default("active"),
  is_active: z.boolean().default(true),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  // Hermes Foundation metadata -- read-only, populated by the sync below.
  profile_slug: z.string().nullable().optional(),
  layer: z.string().nullable().optional(),
  runtime_tier: z.enum(RUNTIME_TIERS).nullable().optional(),
  telegram_required: z.boolean().default(false),
  has_profile: z.boolean().default(false),
  mission: z.string().nullable().optional(),
  source_path: z.string().nullable().optional(),
  sub_agents: z.array(subAgentSchema).optional().default([]),
  agent_skills: z.array(agentSkillSchema).optional().default([]),
  cost_rates: z.array(agentCostRateSchema).optional().default([]),
  capacities: z.array(agentCapacitySchema).optional().default([]),
});

export type Agent = z.infer<typeof agentSchema>;

/** Base payload shape -- server assigns id and timestamps. */
export const agentInputSchema = z.object({
  name: z.string().min(1, "Name is required").max(150, "Name is too long"),
  description: z.string().max(2000, "Description is too long").optional().or(z.literal("")),
  agent_type: z.enum(AGENT_TYPES).default("executor"),
  status: z.enum(AGENT_STATUSES).default("active"),
  is_active: z.boolean().default(true),
});

export const agentUpdateSchema = agentInputSchema.partial();
export type AgentUpdateInput = z.infer<typeof agentUpdateSchema>;

export const hermesSyncResultSchema = z.object({
  agents: z.object({ created: z.number(), updated: z.number() }),
  sub_agents: z.object({ created: z.number(), updated: z.number() }),
  skills: z.object({ created: z.number(), updated: z.number() }),
  agent_skills: z.object({ created: z.number() }),
  warnings: z.array(z.string()).default([]),
});

export type HermesSyncResult = z.infer<typeof hermesSyncResultSchema>;

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const agentKeys = {
  all: ["agents"] as const,
  detail: (id: string) => ["agents", id] as const,
};

const RESOURCE = "/api/v1/agents";

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useAgents() {
  return useQuery({
    queryKey: agentKeys.all,
    queryFn: () => apiClient.get<Agent[]>(RESOURCE),
  });
}

export function useAgent(id: string | undefined) {
  return useQuery({
    queryKey: agentKeys.detail(id ?? ""),
    queryFn: () => apiClient.get<Agent>(`${RESOURCE}/${id}`),
    enabled: Boolean(id),
  });
}

export function useUpdateAgent(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AgentUpdateInput) =>
      apiClient.patch<Agent>(`${RESOURCE}/${id}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
      queryClient.invalidateQueries({ queryKey: agentKeys.detail(id) });
    },
  });
}

export function useDeleteAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${RESOURCE}/${id}`),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
      queryClient.invalidateQueries({ queryKey: agentKeys.detail(id) });
    },
  });
}

export function useDeleteSubAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, subAgentId }: { agentId: string; subAgentId: string }) =>
      apiClient.delete<void>(`${RESOURCE}/${agentId}/sub-agents/${subAgentId}`),
    onSuccess: (_data, { agentId }) => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
      queryClient.invalidateQueries({ queryKey: agentKeys.detail(agentId) });
    },
  });
}

export function useSyncHermesAgents() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<HermesSyncResult>(`${RESOURCE}/sync/hermes-foundation`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Skills catalog (for associating skills with an agent)
// ---------------------------------------------------------------------------

export const skillKeys = {
  all: ["agent-skills-catalog"] as const,
};

export function useSkills() {
  return useQuery({
    queryKey: skillKeys.all,
    queryFn: () => apiClient.get<Skill[]>(`${RESOURCE}/skills`),
  });
}

export interface SkillUpdateInput {
  name?: string;
  version?: string;
  description?: string | null;
  origin?: SkillOrigin;
  risk_level?: SkillRiskLevel;
  permissions?: string;
}

/** Partial update of a skill's registry metadata. The backend rejects
 * edits (other than approval flags) on already-approved skills — approved
 * skills must not change without a new version (SPEC 6.5 rule 8). */
export function useUpdateSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ skillId, updates }: { skillId: string; updates: SkillUpdateInput }) =>
      apiClient.patch<Skill>(`${RESOURCE}/skills/${skillId}`, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

/** Delete the skill's registry row (grants cascade). The SKILL.md file in
 * the profile is untouched, so a Hermes Foundation sync re-imports it. */
export function useDeleteSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) => apiClient.delete<void>(`${RESOURCE}/skills/${skillId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

/** @param agentSkillId the agent_skills association row id (NOT the skill id). */
export function useRemoveSkillFromAgent(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentSkillId: string) =>
      apiClient.delete<void>(`${RESOURCE}/${agentId}/skills/${agentSkillId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.detail(agentId) });
    },
  });
}
