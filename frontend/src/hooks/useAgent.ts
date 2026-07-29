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

/**
 * Host-bridge /v1/agent-runs' runtime_type -- how an agent is actually
 * executed, and the axis the Agents page groups by: "hermes" is the eight
 * in-house Hermes profile agents, the other four are external CLI runtimes
 * with their own binary and their own config home (Porthos/claude,
 * Aramis/codex, Dartan/agy, Vector/openclaw). Null for agents registered by
 * hand that have no dispatchable runtime at all.
 */
export const AGENT_RUNTIME_TYPES = ["hermes", "claude", "codex", "agy", "openclaw"] as const;
export type AgentRuntimeType = (typeof AGENT_RUNTIME_TYPES)[number];

/** Hermes profile agents vs. external CLI runtimes -- the top-level split of
 *  the ecosystem view. */
export function isExternalRuntime(runtimeType: string | null | undefined): boolean {
  return Boolean(runtimeType) && runtimeType !== "hermes";
}

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
  department: z.string().nullable().optional(),
  sector: z.string().nullable().optional(),
  reports_to_profile_slug: z.string().nullable().optional(),
  forgerouter_api_key_configured: z.boolean().default(false),
  // Decrypted value -- only ever present on the single-agent GET
  // (AgentDetailOut), admin-only, absent everywhere else (list, other
  // domains' Agent references). See backend/app/db/models/agent.py's
  // forgerouter_api_key_encrypted docstring for why this reverses the
  // column's original write-only design (2026-07-29).
  forgerouter_api_key: z.string().nullable().optional(),
  // Host-bridge /v1/agent-runs' runtime_type -- only set for agents that
  // can be dispatched via the Inbox: Porthos/Aramis/Dartan (claude/codex/
  // agy, their own external CLIs), the classic Hermes-profile agents
  // (hermes), and Vector (openclaw). Null for everyone else.
  runtime_type: z.enum(AGENT_RUNTIME_TYPES).nullable().optional(),
  // Where this agent's profile files (SOUL.md, IDENTITY.md, ...) live on the
  // host. `home_path` is the registered override, `effective_home_path` is
  // what the backend actually reads -- the override when set, otherwise the
  // runtime convention (/root/.hermes/profiles/<slug>, /root/.claude, ...).
  home_path: z.string().nullable().optional(),
  effective_home_path: z.string().nullable().optional(),
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
  forgerouter_api_key: z.string().max(1000).optional(),
  clear_forgerouter_api_key: z.boolean().optional(),
  // Absolute host path; "" clears the override and restores the runtime default.
  home_path: z.string().max(1000).optional(),
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
      // The MCP screens are keyed by the same roster: a sync that adds or
      // retires an agent must not leave them showing the previous one.
      queryClient.invalidateQueries({ queryKey: agentMcpKeys.overview });
    },
  });
}

/** Bulk "import all" for the ForgeRouter API key -- pulls every active
 * agent's already-issued key straight from ForgeRouter's own registry
 * (ai_router.agents), for agents ForgeRouter already knows about, not just
 * the Hermes-profile ones the sync above already covers (2026-07-29). See
 * useImportAgentForgeRouterKey below for the per-agent counterpart. */
export interface ForgeRouterKeySyncAgent {
  agent_id: string;
  agent_name: string;
  matched: boolean;
  updated: boolean;
}

export interface ForgeRouterKeySyncResult {
  checked: number;
  matched: number;
  updated: number;
  agents: ForgeRouterKeySyncAgent[];
  unmatched_forgerouter_agents: string[];
}

export function useSyncForgeRouterKeys() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<ForgeRouterKeySyncResult>(`${RESOURCE}/sync/forgerouter-keys`),
    // agentKeys.all is ["agents"], a prefix of every agentKeys.detail(id) --
    // TanStack Query's default partial matching means this one invalidation
    // already covers the list and every open detail query too.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: agentKeys.all }),
  });
}

/** Per-agent "Import" button next to the ForgeRouter API key field on the
 * agent detail page -- same source/matching rule as the bulk sync above,
 * scoped to one agent. */
export interface ForgeRouterKeyImportResult {
  matched: boolean;
  updated: boolean;
  forgerouter_api_key_configured: boolean;
}

export function useImportAgentForgeRouterKey(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<ForgeRouterKeyImportResult>(`${RESOURCE}/${agentId}/forgerouter-key/import`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
      queryClient.invalidateQueries({ queryKey: agentKeys.detail(agentId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Profile Markdown files (SOUL.md, IDENTITY.md, TOOLS.md, ...)
//
// Per-agent, not per-Hermes-profile: these endpoints resolve the directory
// from the agent's own runtime, so the four external CLI runtimes
// (Porthos/claude, Aramis/codex, Dartan/agy, Vector/openclaw) show their
// files exactly like the eight Hermes profiles do. The older
// /api/v1/foundation/profiles/{slug}/files/... route only ever saw the
// latter — see useFoundation.ts.
// ---------------------------------------------------------------------------

/**
 * The canonical profile file set, in provisioning order. Mirrors
 * `CORE_PROFILE_FILES` in backend/app/core/agent_profile_files.py — kept
 * client-side so the org chart can render one chip per file without a
 * request per agent; content is only fetched when a chip is opened.
 */
export const CORE_PROFILE_FILES = [
  "SOUL.md",
  "IDENTITY.md",
  "USER.md",
  "TOOLS.md",
  "AGENTS.md",
  "FOUNDATION_LINK.md",
  "HEARTBEAT.md",
  "MEMORY.md",
  "CONTINUITY.md",
] as const;

/** Files that only exist for one runtime. Claude Code reads CLAUDE.md as its
 *  native always-loaded entrypoint — AGENTS.md's role on the other runtimes. */
const RUNTIME_EXTRA_FILES: Record<string, readonly string[]> = {
  claude: ["CLAUDE.md"],
};

/** `<PROFILE>_SUBAGENTS.md` — only for agents that orchestrate sub-agents. */
export function subAgentsFileName(profileSlug: string | null | undefined): string | null {
  if (!profileSlug) return null;
  return `${profileSlug.toUpperCase().replace(/-/g, "_")}_SUBAGENTS.md`;
}

/** Every profile file this agent may have. Same ordering and membership rule
 *  as the backend's `allowed_filenames` — the two must not drift. */
export function profileFileNamesFor(agent: {
  runtime_type?: string | null;
  profile_slug?: string | null;
}): string[] {
  const names: string[] = [...CORE_PROFILE_FILES];
  names.push(...(RUNTIME_EXTRA_FILES[agent.runtime_type ?? ""] ?? []));
  const subAgents = subAgentsFileName(agent.profile_slug);
  if (subAgents) names.push(subAgents);
  return names;
}

export const agentProfileFileInfoSchema = z.object({
  filename: z.string(),
  path: z.string(),
  exists: z.boolean(),
  size: z.number().nullable().optional(),
  modified_at: z.string().nullable().optional(),
});

export type AgentProfileFileInfo = z.infer<typeof agentProfileFileInfoSchema>;

export const agentProfileFilesSchema = z.object({
  agent_id: z.string(),
  home_path: z.string().nullable().optional(),
  /** False means the directory exists in the registry but is not reachable
   *  from the backend process (a missing bind mount under Docker) — the UI
   *  must show which path was tried instead of pretending the files are gone. */
  home_resolved: z.boolean().default(false),
  files: z.array(agentProfileFileInfoSchema).default([]),
});

export type AgentProfileFiles = z.infer<typeof agentProfileFilesSchema>;

export const agentProfileFileSchema = z.object({
  agent_id: z.string(),
  filename: z.string(),
  path: z.string(),
  /** null (not "") when the file does not exist yet. */
  content: z.string().nullable(),
});

export type AgentProfileFile = z.infer<typeof agentProfileFileSchema>;

export const agentProfileFileKeys = {
  list: (agentId: string) => ["agent-profile-files", agentId] as const,
  detail: (agentId: string, filename: string) =>
    ["agent-profile-files", agentId, filename] as const,
};

export function useAgentProfileFiles(agentId: string | undefined) {
  return useQuery({
    queryKey: agentProfileFileKeys.list(agentId ?? ""),
    queryFn: () => apiClient.get<AgentProfileFiles>(`${RESOURCE}/${agentId}/profile-files`),
    enabled: Boolean(agentId),
  });
}

export function useAgentProfileFile(agentId: string | undefined, filename: string | undefined) {
  return useQuery({
    queryKey: agentProfileFileKeys.detail(agentId ?? "", filename ?? ""),
    queryFn: () =>
      apiClient.get<AgentProfileFile>(`${RESOURCE}/${agentId}/profile-files/${filename}`),
    enabled: Boolean(agentId && filename),
  });
}

export function useUpdateAgentProfileFile(agentId: string, filename: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (content: string) =>
      apiClient.put<AgentProfileFile>(`${RESOURCE}/${agentId}/profile-files/${filename}`, {
        content,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(agentProfileFileKeys.detail(agentId, filename), data);
      // A first write creates the file, so the exists/size/mtime list is stale.
      queryClient.invalidateQueries({ queryKey: agentProfileFileKeys.list(agentId) });
    },
  });
}

// ---------------------------------------------------------------------------
// Telegram channel status
// ---------------------------------------------------------------------------

export const AGENT_TELEGRAM_STATUSES = [
  "ok",
  "not_running",
  "not_configured",
  "unknown",
  "not_applicable",
] as const;
export type AgentTelegramStatusValue = (typeof AGENT_TELEGRAM_STATUSES)[number];

export const agentTelegramStatusSchema = z.object({
  agent_id: z.string(),
  agent_name: z.string(),
  profile_slug: z.string().nullable().optional(),
  required: z.boolean().default(false),
  /** Bot token + home channel present in the agent's own profile .env. */
  installed: z.boolean().default(false),
  home_channel_name: z.string().nullable().optional(),
  service: z.string().nullable().optional(),
  /** null = the systemd check could not run, NOT "the gateway is down". */
  running: z.boolean().nullable().optional(),
  status: z.enum(AGENT_TELEGRAM_STATUSES).default("unknown"),
});

export type AgentTelegramStatus = z.infer<typeof agentTelegramStatusSchema>;

export const agentTelegramStatusListSchema = z.object({
  agents: z.array(agentTelegramStatusSchema).default([]),
  check_error: z.string().nullable().optional(),
});

export type AgentTelegramStatusList = z.infer<typeof agentTelegramStatusListSchema>;

export const agentTelegramKeys = {
  all: ["agent-telegram-status"] as const,
};

/** Whole-roster Telegram health in one request — the org chart and the list
 *  table both render a badge per agent, so a per-agent query would fan out
 *  into a dozen systemd checks. */
export function useAgentsTelegramStatus() {
  return useQuery({
    queryKey: agentTelegramKeys.all,
    queryFn: () => apiClient.get<AgentTelegramStatusList>(`${RESOURCE}/telegram-status`),
    // The gateway can go down between page loads; this is a liveness signal.
    refetchInterval: 60_000,
  });
}

// ---------------------------------------------------------------------------
// MCP servers
//
// Not stored by ForgeHub: these read and write each runtime's own config file
// (a Hermes profile's config.yaml, ~/.claude.json, ~/.codex/config.toml, ...),
// which is what the runtime actually loads. See backend core/agent_mcp.py.
// ---------------------------------------------------------------------------

export const agentMcpServerSchema = z.object({
  name: z.string(),
  /** null for an HTTP server, which carries `url` instead. */
  command: z.string().nullable().optional(),
  args: z.array(z.string()).default([]),
  env: z.record(z.string()).default({}),
  url: z.string().nullable().optional(),
  enabled: z.boolean().default(true),
});

export type AgentMcpServer = z.infer<typeof agentMcpServerSchema>;

export const agentMcpServersSchema = z.object({
  agent_id: z.string(),
  runtime_type: z.string().nullable().optional(),
  /** Host path of the runtime's own config file — always shown, so an
   *  operator can verify the result outside ForgeHub. */
  config_path: z.string().nullable().optional(),
  config_exists: z.boolean().default(false),
  /** Whether this runtime's format has an enable/disable flag at all.
   *  Claude Code and agy have none: there, off means removed. */
  supports_toggle: z.boolean().default(false),
  /** A config file that exists but does not parse — surfaced instead of
   *  failing the screen, since diagnosing that is why you opened it. */
  error: z.string().nullable().optional(),
  servers: z.array(agentMcpServerSchema).default([]),
});

export type AgentMcpServers = z.infer<typeof agentMcpServersSchema>;

export const agentMcpOverviewItemSchema = agentMcpServersSchema.extend({
  agent_name: z.string(),
  profile_slug: z.string().nullable().optional(),
  /** False = the agent has no runtime that could load an MCP server (an
   *  agent registered without runtime_type). Listed, never hidden. */
  supported: z.boolean().default(true),
});

export type AgentMcpOverviewItem = z.infer<typeof agentMcpOverviewItemSchema>;

export const agentRuntimeSyncSchema = z.object({
  checked: z.number().default(0),
  updated: z.number().default(0),
  agents: z
    .array(
      z.object({
        agent_id: z.string(),
        agent_name: z.string(),
        runtime_type: z.string().nullable().optional(),
        detected_runtime_type: z.string().nullable().optional(),
        evidence: z.string().nullable().optional(),
        home_path: z.string().nullable().optional(),
        home_resolved: z.boolean().default(false),
        mcp_config_exists: z.boolean().default(false),
        applied: z.boolean().default(false),
        issues: z.array(z.string()).default([]),
      }),
    )
    .default([]),
  unregistered_profiles: z.array(z.string()).default([]),
});

export type AgentRuntimeSync = z.infer<typeof agentRuntimeSyncSchema>;

/** The *real* sync: reconciles each agent's runtime against what is installed
 *  on the host, unlike useSyncHermesAgents which reads the Foundation docs.
 *  Only fills a missing runtime_type; conflicts are reported, not applied. */
export function useSyncAgentRuntimes() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<AgentRuntimeSync>(`${RESOURCE}/sync/runtimes`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.all });
      queryClient.invalidateQueries({ queryKey: agentMcpKeys.overview });
    },
  });
}

export const agentMcpKeys = {
  overview: ["agent-mcp-servers"] as const,
  detail: (agentId: string) => ["agent-mcp-servers", agentId] as const,
};

export function useAgentMcpServers(agentId: string | undefined) {
  return useQuery({
    queryKey: agentMcpKeys.detail(agentId ?? ""),
    queryFn: () => apiClient.get<AgentMcpServers>(`${RESOURCE}/${agentId}/mcp-servers`),
    enabled: Boolean(agentId),
    retry: false, // a runtime that cannot load MCP servers 400s; retrying won't change that
  });
}

/** Whole-roster view for the MCP page — one request instead of a query per
 *  agent, same reason as the Telegram roster above. */
export function useAgentsMcpOverview() {
  return useQuery({
    queryKey: agentMcpKeys.overview,
    queryFn: () => apiClient.get<{ agents: AgentMcpOverviewItem[] }>(`${RESOURCE}/mcp-servers`),
  });
}

export interface AgentMcpServerInput {
  name: string;
  command?: string | null;
  args?: string[];
  env?: Record<string, string>;
  url?: string | null;
  enabled?: boolean;
}

export function useUpsertAgentMcpServer(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, ...server }: AgentMcpServerInput) =>
      apiClient.put<AgentMcpServers>(`${RESOURCE}/${agentId}/mcp-servers/${name}`, {
        command: server.command ?? null,
        args: server.args ?? [],
        env: server.env ?? {},
        url: server.url ?? null,
        enabled: server.enabled ?? true,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(agentMcpKeys.detail(agentId), data);
      queryClient.invalidateQueries({ queryKey: agentMcpKeys.overview });
    },
  });
}

export function useDeleteAgentMcpServer(agentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiClient.delete<AgentMcpServers>(`${RESOURCE}/${agentId}/mcp-servers/${name}`),
    onSuccess: (data) => {
      queryClient.setQueryData(agentMcpKeys.detail(agentId), data);
      queryClient.invalidateQueries({ queryKey: agentMcpKeys.overview });
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
  is_approved?: boolean;
  security_reviewed?: boolean;
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
