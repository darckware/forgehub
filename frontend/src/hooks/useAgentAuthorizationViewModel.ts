import { useEffect, useMemo, useRef, useState } from "react";
import { useAgents } from "@/hooks/useAgent";
import { REMOTE_ACCESS_ACTION, RISK_LEVELS, riskCovers, type RiskLevel } from "@/hooks/useAgentMaintenance";
import {
  useConfigureDirectAgent,
  useDirectAgents,
  useRemoveDirectAgent,
  type DirectAccess,
  type DirectAccessInput,
  type DirectAgentRemoved,
  type DirectDuration,
  type DirectPurpose,
} from "@/hooks/useDirectAccess";
import { refusalText, useDirectAgentsViewModel, type DirectAgentsViewModel } from "@/hooks/useDirectAgentsViewModel";
import {
  useAuthorityDelegations,
  useGrantAuthorityDelegation,
  useRevokeAuthorityDelegation,
  type AuthorityDelegation,
} from "@/hooks/useGovernance";
import { useMachineScope, type MachineScope } from "@/hooks/useMachineScope";
import { ApiError } from "@/lib/api";

/** Validity of a library-scripts permission, in days (0 = keep the current
 * expiry). Free commands use hours (DIRECT_DURATIONS): a script delegation is a
 * standing mandate bounded by risk, a direct access is a short working window. */
export const VALIDITY_DAYS = [1, 7, 30] as const;
/** The scripts delegation's reason when it has none of its own. */
export const DEFAULT_SCRIPTS_REASON = "Manutenção de máquinas pelo Acesso Remoto";
const OLD_ACCESS_MS = 7 * 86_400_000;

/** One active remote_access.execute delegation, as stored. */
export interface ScriptGrant {
  id: string;
  risk: string;
  machines: string[];
  groups: string[];
  expiresAt: string;
  /** Starts in the future (valid_from after now). */
  futureFrom: string | null;
  /** Limited to a product or project: it doesn't apply to plain maintenance. */
  projectScoped: boolean;
  delegation: AuthorityDelegation;
}

/** One agent with any machine permission, as the card's row shows it. */
export interface AgentAuthorizationRow {
  id: string;
  name: string;
  runtimeType: string | null;
  /** Library scripts: every active remote_access.execute delegation (also
   * future or project-scoped ones, shown as such); null = none. */
  scripts: {
    maxRisk: string;
    machines: string[];
    groups: string[];
    /** The earliest expiry: "Manter" never extends a delegation. */
    until: string;
    grants: ScriptGrant[];
    /** More than one delegation, or one that a single org-wide grant can't
     * represent (future start, project scope): replacing needs a confirmation. */
    irregular: boolean;
    reason: string;
  } | null;
  /** Free commands (direct access); null = not on the direct list. */
  commands: {
    config: DirectAccess | null;
    expired: boolean;
    /** Configured with no machine at all: grants nothing. */
    noScope: boolean;
    /** Configured more than 7 days ago and still in force. */
    old: boolean;
  } | null;
  /** Why the agent can't use each permission (backend codes); null = it can. */
  scriptsReason: string | null;
  commandsReason: string | null;
}

export type ScriptsChange = "none" | "grant" | "replace" | "revoke" | "finish_revoke";
export type CommandsChange = "none" | "save" | "remove";
export type PermissionOutcome =
  | { state: "saved" }
  | { state: "failed"; message: string }
  | { state: "cancelled" }
  /** The new delegation exists; revoking the previous one failed. */
  | { state: "pending_revoke"; message: string };
export interface SaveOutcomes {
  scripts?: PermissionOutcome;
  commands?: PermissionOutcome;
}

interface ScriptsBaseline {
  enabled: boolean;
  risk: RiskLevel;
  servers: string[];
  groups: string[];
  delegations: AuthorityDelegation[];
  /** Created by this panel but the old ones it replaces are still active. */
  pendingRevoke: AuthorityDelegation[];
  expiresAt: string | null;
  irregular: boolean;
  reason: string;
}
interface CommandsBaseline {
  enabled: boolean;
  listed: boolean;
  allMachines: boolean;
  servers: string[];
  hours: DirectDuration;
  elevation: boolean;
  purpose: DirectPurpose | "";
  reason: string;
}

export interface AgentAuthorizationForm {
  scriptsEnabled: boolean;
  risk: RiskLevel;
  /** 0 = keep the current expiry (only offered when the agent already has one). */
  days: number;
  /** Required to replace an irregular set of script delegations by one. */
  consolidateConfirmed: boolean;
  commandsEnabled: boolean;
  commandsAllMachines: boolean;
  hours: DirectDuration;
  elevation: boolean;
  purpose: DirectPurpose | "";
  /** The free commands' reason (the direct configuration's own). */
  reason: string;
}

/** What each permission would be saved with. */
export interface PermissionScope {
  all: boolean;
  machines: string[];
  groups: string[];
}

/** "Agentes autorizados" (Remote Access › Agents, 2026-11-11, plan
 * REMOTE_ACCESS_SUPPORT_ADJUSTMENTS_PLAN Fase 2 items 1 and 6): one card, one
 * row per agent with any permission, one right-hand panel per agent with two
 * independent permissions:
 *  - library scripts: a remote_access.execute delegation (max risk, validity
 *    in days), created/revoked through /governed/authority-delegations -- an
 *    edit creates the new delegation first and only then revokes the old ones,
 *    so a failure never leaves the agent with less than before; a revoke that
 *    failed stays pending and "Salvar" retries just that;
 *  - free commands: the direct-access configuration (PUT/DELETE
 *    /remote-access/direct/agents/{id}, duration in hours), with the backend's
 *    sensitive-coverage confirmation (409 SENSITIVE_CONFIRMATION_REQUIRED).
 * The machine picker is shared, but each permission keeps its own scope: a
 * permission is saved with the picker's selection only when the user changed
 * the selection; otherwise it is re-sent with its own machines, so editing one
 * permission never moves the other's machines. Saving calls only what changed,
 * each permission on its own; failures are reported per permission and the
 * panel stays open with what still differs.
 * A Hermes agent with no permission yet starts on "Somente leitura"
 * (scripts, read risk only, no commands); turning commands on for it asks for
 * a confirmation: a free command can't be guaranteed read-only. */
export interface AgentAuthorizationViewModel {
  status: "loading" | "error" | "idle" | "editing" | "submitting" | "confirming";
  rows: AgentAuthorizationRow[];
  /** The permissions couldn't be read: nothing can be added or edited. */
  loadError: string | null;
  /** Active agents with no permission, for "Adicionar agente". */
  addable: { id: string; name: string }[];
  now: number;

  editing: { agentId: string | null; isNew: boolean } | null;
  openAdd: () => void;
  openEdit: (agentId: string) => void;
  close: () => void;
  chooseAgent: (agentId: string) => void;
  agent: { id: string; name: string; runtimeType: string | null } | null;
  isHermes: boolean;
  scriptsReason: string | null;
  commandsReason: string | null;
  eligibilityPending: boolean;
  current: AgentAuthorizationRow | null;

  scope: MachineScope;
  scriptsScope: PermissionScope;
  commandsScope: PermissionScope;
  form: AgentAuthorizationForm;
  setScriptsEnabled: (on: boolean) => void;
  setRisk: (risk: RiskLevel) => void;
  setDays: (days: number) => void;
  setConsolidateConfirmed: (on: boolean) => void;
  setCommandsEnabled: (on: boolean) => void;
  setCommandsAllMachines: (on: boolean) => void;
  setHours: (hours: DirectDuration) => void;
  setElevation: (on: boolean) => void;
  setPurpose: (purpose: DirectPurpose | "") => void;
  setReason: (reason: string) => void;
  applyReadOnly: () => void;
  isReadOnly: boolean;
  confirmingHermesCommands: boolean;
  confirmHermesCommands: () => void;
  cancelHermesCommands: () => void;
  /** Scripts and commands had different machines when the panel opened. */
  scopesDiffer: boolean;

  scriptsChange: ScriptsChange;
  commandsChange: CommandsChange;
  scriptsNeedScope: boolean;
  /** A replace of irregular delegations waits for `consolidateConfirmed`. */
  scriptsNeedConsolidation: boolean;
  canSave: boolean;
  save: () => Promise<void>;
  outcomes: SaveOutcomes | null;
  sensitive: { all: boolean; machines: string[] } | null;
  confirmSensitive: () => Promise<void>;
  cancelSensitive: () => void;
  /** The last authorization saved in full; `direct` = commands were removed. */
  saved: { name: string; direct: DirectAgentRemoved | null } | null;

  removing: AgentAuthorizationRow | null;
  askRemove: (row: AgentAuthorizationRow) => void;
  cancelRemove: () => void;
  confirmRemove: () => Promise<void>;
  removePending: boolean;
  removeError: string | null;
  removed: { name: string; direct: DirectAgentRemoved | null } | null;

  pause: DirectAgentsViewModel;
}

const sameSet = (a: Iterable<string>, b: Iterable<string>) => {
  const x = new Set(a); const y = new Set(b);
  return x.size === y.size && [...x].every((v) => y.has(v));
};
const asRisk = (value: string): RiskLevel => (RISK_LEVELS as readonly string[]).includes(value) ? value as RiskLevel : "high";

/** Every delegation removal and display counts: active, for this action, not
 * expired -- whatever its start or product/project limit. */
export function isActiveScriptsDelegation(d: AuthorityDelegation, now = Date.now()): boolean {
  return d.status === "active" && d.allowed_actions.includes(REMOTE_ACCESS_ACTION) && new Date(d.expires_at).getTime() > now;
}

const EMPTY_FORM: AgentAuthorizationForm = {
  scriptsEnabled: false, risk: "medium", days: 1, consolidateConfirmed: false, commandsEnabled: false,
  commandsAllMachines: false, hours: 0, elevation: false, purpose: "", reason: "",
};

const isNotListed = (e: unknown) => e instanceof ApiError && e.status === 404;

export function useAgentAuthorizationViewModel(): AgentAuthorizationViewModel {
  const agentsQuery = useAgents();
  const delegationsQuery = useAuthorityDelegations();
  const directAgents = useDirectAgents();
  const pause = useDirectAgentsViewModel();
  const grantMutation = useGrantAuthorityDelegation();
  const revokeMutation = useRevokeAuthorityDelegation();
  const configureMutation = useConfigureDirectAgent();
  const removeMutation = useRemoveDirectAgent();

  const [editing, setEditing] = useState<{ agentId: string | null; isNew: boolean } | null>(null);
  const scope = useMachineScope(editing !== null);
  const [form, setForm] = useState<AgentAuthorizationForm>(EMPTY_FORM);
  const [baseScripts, setBaseScripts] = useState<ScriptsBaseline | null>(null);
  const [baseCommands, setBaseCommands] = useState<CommandsBaseline | null>(null);
  const [scopesDiffer, setScopesDiffer] = useState(false);
  const [confirmingHermesCommands, setConfirmingHermesCommands] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [outcomes, setOutcomes] = useState<SaveOutcomes | null>(null);
  const [sensitive, setSensitive] = useState<{ all: boolean; machines: string[] } | null>(null);
  const [saved, setSaved] = useState<{ name: string; direct: DirectAgentRemoved | null } | null>(null);
  const commandsRemoved = useRef<DirectAgentRemoved | null>(null);
  const [removing, setRemoving] = useState<AgentAuthorizationRow | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removed, setRemoved] = useState<{ name: string; direct: DirectAgentRemoved | null } | null>(null);
  // Steps of a row removal already done, so a retry skips them.
  const removal = useRef<{ id: string; revoked: Set<string>; directDone: boolean; direct: DirectAgentRemoved | null } | null>(null);
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(timer); }, []);

  const agents = useMemo(() => agentsQuery.data ?? [], [agentsQuery.data]);
  const direct = useMemo(() => (Array.isArray(directAgents.data) ? directAgents.data : []), [directAgents.data]);
  const eligibilityPending = !Array.isArray(directAgents.data);
  const directById = useMemo(() => new Map(direct.map((a) => [a.id, a])), [direct]);
  const loadError = delegationsQuery.isError
    ? refusalText(delegationsQuery.error)
    : directAgents.isError ? refusalText(directAgents.error) : null;

  const rows: AgentAuthorizationRow[] = useMemo(() => {
    const byId = new Map<string, AgentAuthorizationRow>();
    const agentById = new Map(agents.map((a) => [a.id, a]));
    const base = (id: string, name: string, runtimeType: string | null): AgentAuthorizationRow => {
      const info = directById.get(id);
      return {
        id, name: info?.name ?? name, runtimeType: info?.runtime_type ?? runtimeType,
        scripts: null, commands: null,
        scriptsReason: info?.scripts_unsupported_reason ?? null, commandsReason: info?.unsupported_reason ?? null,
      };
    };
    const grantsByAgent = new Map<string, ScriptGrant[]>();
    for (const d of delegationsQuery.data ?? []) {
      if (!isActiveScriptsDelegation(d, now)) continue;
      const startsAt = d.valid_from ? new Date(d.valid_from).getTime() : 0;
      grantsByAgent.set(d.grantee_id, [...(grantsByAgent.get(d.grantee_id) ?? []), {
        id: d.id, risk: d.max_risk ?? "low", machines: d.servers ?? [], groups: d.host_groups ?? [], expiresAt: d.expires_at,
        futureFrom: startsAt > now ? d.valid_from! : null, projectScoped: Boolean(d.product_id || d.project_id), delegation: d,
      }]);
    }
    for (const [agentId, grants] of grantsByAgent) {
      const agent = agentById.get(agentId);
      const info = directById.get(agentId);
      if (!agent && !info) continue;
      const row = base(agentId, agent?.name ?? info!.name, agent?.runtime_type ?? null);
      grants.sort((a, b) => a.expiresAt.localeCompare(b.expiresAt));
      row.scripts = {
        maxRisk: grants.reduce((best, g) => (riskCovers(g.risk, best) ? g.risk : best), "low"),
        machines: [...new Set(grants.flatMap((g) => g.machines))],
        groups: [...new Set(grants.flatMap((g) => g.groups))],
        until: grants[0].expiresAt,
        grants,
        irregular: grants.length > 1 || grants.some((g) => g.futureFrom || g.projectScoped),
        reason: grants.length === 1 ? grants[0].delegation.reason ?? "" : "",
      };
      byId.set(row.id, row);
    }
    for (const info of direct) {
      if (!info.allowed) continue;
      const row = byId.get(info.id) ?? base(info.id, info.name, info.runtime_type);
      const config = info.configuration;
      const expired = config?.expires_at ? new Date(config.expires_at).getTime() <= now : false;
      row.commands = {
        config,
        expired,
        noScope: !config || (!config.all_machines && config.machines.length === 0),
        old: Boolean(config) && !expired && now - new Date(config!.opened_at).getTime() > OLD_ACCESS_MS,
      };
      byId.set(row.id, row);
    }
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [agents, delegationsQuery.data, direct, directById, now]);

  const rowIds = new Set(rows.map((r) => r.id));
  const activeAgents = direct.length
    ? direct.map((a) => ({ id: a.id, name: a.name, runtimeType: a.runtime_type }))
    : agents.filter((a) => a.is_active && a.status === "active")
      .map((a) => ({ id: a.id, name: a.name, runtimeType: a.runtime_type ?? null }));
  const addable = activeAgents.filter((a) => !rowIds.has(a.id)).sort((a, b) => a.name.localeCompare(b.name))
    .map(({ id, name }) => ({ id, name }));

  const agentId = editing?.agentId ?? null;
  const current = agentId ? rows.find((r) => r.id === agentId) ?? null : null;
  const agentInfo = agentId ? activeAgents.find((a) => a.id === agentId) ?? (current ? { id: current.id, name: current.name, runtimeType: current.runtimeType } : null) : null;
  const isHermes = agentInfo?.runtimeType === "hermes";
  const scriptsReason = agentId ? directById.get(agentId)?.scripts_unsupported_reason ?? null : null;
  const commandsReason = agentId ? directById.get(agentId)?.unsupported_reason ?? null : null;

  /** Fills the form and the baselines from what the agent has now. */
  const loadAgent = (id: string) => {
    const row = rows.find((r) => r.id === id) ?? null;
    const info = directById.get(id);
    const runtime = info?.runtime_type ?? activeAgents.find((a) => a.id === id)?.runtimeType ?? row?.runtimeType ?? null;
    const scripts: ScriptsBaseline = row?.scripts
      ? { enabled: true, risk: asRisk(row.scripts.maxRisk), servers: row.scripts.machines, groups: row.scripts.groups,
          delegations: row.scripts.grants.map((g) => g.delegation), pendingRevoke: [], expiresAt: row.scripts.until,
          irregular: row.scripts.irregular, reason: row.scripts.reason }
      : { enabled: false, risk: "medium", servers: [], groups: [], delegations: [], pendingRevoke: [], expiresAt: null, irregular: false, reason: "" };
    const config = row?.commands?.config ?? null;
    const commandsActive = Boolean(config) && !row?.commands?.expired;
    const commands: CommandsBaseline = {
      enabled: commandsActive,
      listed: Boolean(row?.commands),
      allMachines: config?.all_machines ?? false,
      servers: config && !config.all_machines ? config.machines.map((m) => m.id) : [],
      hours: config?.duration_hours ?? 0,
      elevation: config?.allow_elevation ?? false,
      purpose: config?.purpose ?? "",
      reason: config?.reason ?? "",
    };
    setBaseScripts(scripts);
    setBaseCommands(commands);
    if (scripts.enabled) scope.reset(scripts.servers, scripts.groups);
    else scope.reset(commands.servers, []);
    setScopesDiffer(scripts.enabled && commandsActive && !commands.allMachines
      && (scripts.groups.length > 0 || !sameSet(scripts.servers, commands.servers)));
    const scriptsOk = !info?.scripts_unsupported_reason;
    const nothingYet = !scripts.enabled && !commands.enabled;
    setForm({
      scriptsEnabled: nothingYet ? scriptsOk : scripts.enabled,
      // A Hermes agent starts on "Somente leitura".
      risk: nothingYet ? (runtime === "hermes" ? "low" : "medium") : scripts.risk,
      days: scripts.enabled ? 0 : 1,
      consolidateConfirmed: false,
      commandsEnabled: commands.enabled,
      commandsAllMachines: commands.allMachines,
      hours: commands.hours,
      elevation: commands.elevation,
      purpose: commands.purpose,
      reason: commands.reason,
    });
    setOutcomes(null);
    setSensitive(null);
    commandsRemoved.current = null;
  };

  // Each permission's scope: the picker's selection when the user changed it
  // (or the permission is new), otherwise its own stored scope.
  const pickerScope: PermissionScope = { all: false, machines: scope.effectiveMachines, groups: scope.effectiveGroups };
  const scriptsScope: PermissionScope = baseScripts?.enabled && !scope.touched
    ? { all: false, machines: baseScripts.servers, groups: baseScripts.groups }
    : pickerScope;
  const commandsFromPicker = !baseCommands?.enabled || scope.touched || (baseCommands.allMachines && !form.commandsAllMachines);
  const commandsScope: PermissionScope = form.commandsAllMachines
    ? { all: true, machines: [], groups: [] }
    : commandsFromPicker ? pickerScope : { all: false, machines: baseCommands!.servers, groups: [] };
  const commandsCovered = commandsScope.all ? null
    : commandsFromPicker ? scope.coveredMachineIds : new Set(commandsScope.machines);

  const scriptsChange: ScriptsChange = (() => {
    if (!agentId || !baseScripts) return "none";
    if (!form.scriptsEnabled) return baseScripts.enabled || baseScripts.pendingRevoke.length ? "revoke" : "none";
    if (!baseScripts.enabled) return "grant";
    const scopeDiff = scope.touched
      && (!sameSet(scriptsScope.machines, baseScripts.servers) || !sameSet(scriptsScope.groups, baseScripts.groups));
    if (form.risk !== baseScripts.risk || scopeDiff || form.days !== 0) return "replace";
    return baseScripts.pendingRevoke.length ? "finish_revoke" : "none";
  })();

  const commandsChange: CommandsChange = (() => {
    if (!agentId || !baseCommands) return "none";
    if (!form.commandsEnabled) return baseCommands.enabled ? "remove" : "none";
    if (!baseCommands.enabled) return "save";
    const scopeDiff = !form.commandsAllMachines && commandsCovered !== null && !sameSet(commandsCovered, baseCommands.servers);
    return form.commandsAllMachines !== baseCommands.allMachines || scopeDiff || form.hours !== baseCommands.hours
      || form.elevation !== baseCommands.elevation || form.purpose !== baseCommands.purpose
      || form.reason.trim() !== baseCommands.reason ? "save" : "none";
  })();

  const writesScripts = scriptsChange === "grant" || scriptsChange === "replace";
  const scriptsNeedScope = writesScripts && scriptsScope.machines.length + scriptsScope.groups.length === 0;
  const scriptsNeedConsolidation = scriptsChange === "replace" && Boolean(baseScripts?.irregular) && !form.consolidateConfirmed;
  const scriptsBlocked = writesScripts && Boolean(scriptsReason);
  const commandsBlocked = commandsChange === "save" && Boolean(commandsReason);
  // Only a write that reads the picker needs the inventory; revoking or removing doesn't.
  const needsInventory = (writesScripts && scope.touched) || (writesScripts && !baseScripts?.enabled)
    || (commandsChange === "save" && !form.commandsAllMachines && commandsFromPicker);
  const canSave = Boolean(agentId) && !submitting && (scriptsChange !== "none" || commandsChange !== "none")
    && !scriptsNeedScope && !scriptsNeedConsolidation && !scriptsBlocked && !commandsBlocked
    && !(needsInventory && (scope.inventoryLoading || scope.inventoryError));

  const runScripts = async (): Promise<PermissionOutcome | undefined> => {
    if (!agentId || !baseScripts || scriptsChange === "none") return undefined;
    if (scriptsChange === "revoke") {
      const all = [...baseScripts.delegations, ...baseScripts.pendingRevoke];
      const done = new Set<string>();
      try {
        for (const d of all) { await revokeMutation.mutateAsync(d.id); done.add(d.id); }
        setBaseScripts({ ...baseScripts, enabled: false, delegations: [], pendingRevoke: [] });
        return { state: "saved" };
      } catch (e) {
        setBaseScripts({ ...baseScripts, delegations: baseScripts.delegations.filter((d) => !done.has(d.id)),
          pendingRevoke: baseScripts.pendingRevoke.filter((d) => !done.has(d.id)) });
        return { state: "failed", message: refusalText(e) };
      }
    }
    if (scriptsChange === "finish_revoke") {
      const done = new Set<string>();
      try {
        for (const d of baseScripts.pendingRevoke) { await revokeMutation.mutateAsync(d.id); done.add(d.id); }
        setBaseScripts({ ...baseScripts, pendingRevoke: [] });
        return { state: "saved" };
      } catch (e) {
        setBaseScripts({ ...baseScripts, pendingRevoke: baseScripts.pendingRevoke.filter((d) => !done.has(d.id)) });
        return { state: "pending_revoke", message: refusalText(e) };
      }
    }
    const expires = form.days === 0 && baseScripts.expiresAt
      ? baseScripts.expiresAt
      : new Date(Date.now() + (form.days || 1) * 86_400_000).toISOString();
    let created: AuthorityDelegation;
    try {
      created = await grantMutation.mutateAsync({
        grantee_agent_id: agentId, allowed_actions: [REMOTE_ACCESS_ACTION], scope_type: "organization",
        servers: scriptsScope.machines, host_groups: scriptsScope.groups, max_risk: form.risk,
        expires_at: expires, reason: baseScripts.reason || DEFAULT_SCRIPTS_REASON,
      });
    } catch (e) {
      return { state: "failed", message: refusalText(e) };
    }
    // Only after the new one exists: never less than before on a failure.
    const toRevoke = [...baseScripts.delegations, ...baseScripts.pendingRevoke];
    const next: ScriptsBaseline = {
      enabled: true, risk: form.risk, servers: scriptsScope.machines, groups: scriptsScope.groups,
      delegations: created?.id ? [created] : [], pendingRevoke: toRevoke,
      expiresAt: created?.expires_at ?? expires, irregular: false, reason: baseScripts.reason,
    };
    setForm((f) => ({ ...f, days: 0, consolidateConfirmed: false }));
    const done = new Set<string>();
    try {
      for (const d of toRevoke) { await revokeMutation.mutateAsync(d.id); done.add(d.id); }
      setBaseScripts({ ...next, pendingRevoke: [] });
      return { state: "saved" };
    } catch (e) {
      setBaseScripts({ ...next, pendingRevoke: toRevoke.filter((d) => !done.has(d.id)) });
      return { state: "pending_revoke", message: refusalText(e) };
    }
  };

  const runCommands = async (confirmed: boolean): Promise<PermissionOutcome | "confirm" | undefined> => {
    if (!agentId || !baseCommands || commandsChange === "none") return undefined;
    try {
      if (commandsChange === "remove") {
        try {
          commandsRemoved.current = await removeMutation.mutateAsync(agentId);
        } catch (e) {
          if (!isNotListed(e)) throw e;
        }
        setBaseCommands({ ...baseCommands, enabled: false, listed: false });
        return { state: "saved" };
      }
      const input: DirectAccessInput = {
        all_machines: commandsScope.all,
        server_ids: commandsScope.machines,
        group_ids: commandsScope.groups,
        reason: form.reason.trim() || null,
        purpose: form.purpose || null,
        duration_hours: form.hours,
        allow_elevation: form.elevation,
        confirm_sensitive: confirmed,
      };
      await configureMutation.mutateAsync({ agentId, input });
      setBaseCommands({
        enabled: true, listed: true, allMachines: commandsScope.all, servers: commandsCovered ? [...commandsCovered] : [],
        hours: form.hours, elevation: form.elevation, purpose: form.purpose, reason: form.reason.trim(),
      });
      return { state: "saved" };
    } catch (e) {
      const detail = e instanceof ApiError && e.status === 409
        ? (e.body as { detail?: { code?: string; all_machines?: boolean; machines?: string[] } })?.detail : null;
      if (!confirmed && detail?.code === "SENSITIVE_CONFIRMATION_REQUIRED") {
        setSensitive({ all: Boolean(detail.all_machines), machines: detail.machines ?? [] });
        return "confirm";
      }
      return { state: "failed", message: refusalText(e) };
    }
  };

  const finish = (result: SaveOutcomes) => {
    setOutcomes(result);
    const all = [result.scripts, result.commands].filter(Boolean) as PermissionOutcome[];
    if (all.length > 0 && all.every((o) => o.state === "saved")) {
      setSaved(agentInfo ? { name: agentInfo.name, direct: commandsRemoved.current } : null);
      setEditing(null);
    }
  };

  const save = async () => {
    if (!canSave) return;
    setSubmitting(true);
    setSaved(null);
    setOutcomes(null);
    commandsRemoved.current = null;
    try {
      const result: SaveOutcomes = {};
      const s = await runScripts();
      if (s) result.scripts = s;
      const c = await runCommands(false);
      if (c === "confirm") { setOutcomes(result); return; }
      if (c) result.commands = c;
      finish(result);
    } finally {
      setSubmitting(false);
    }
  };

  const edit = <K extends keyof AgentAuthorizationForm>(key: K) => (value: AgentAuthorizationForm[K]) => {
    setOutcomes(null);
    setForm((f) => ({ ...f, [key]: value }));
  };

  const status = delegationsQuery.isLoading || agentsQuery.isLoading || (eligibilityPending && directAgents.isLoading) ? "loading"
    : loadError ? "error"
    : submitting ? "submitting"
    : sensitive || confirmingHermesCommands || removing || pause.confirmingPause ? "confirming"
    : editing ? "editing" : "idle";

  return {
    status,
    rows,
    loadError,
    addable,
    now,
    editing,
    openAdd: () => {
      if (loadError) return;
      setSaved(null); setRemoved(null);
      setEditing({ agentId: null, isNew: true });
      setBaseScripts(null); setBaseCommands(null); setForm(EMPTY_FORM); setOutcomes(null);
      scope.reset([], []);
    },
    openEdit: (id) => {
      if (loadError) return;
      setSaved(null); setRemoved(null);
      setEditing({ agentId: id, isNew: false });
      loadAgent(id);
    },
    close: () => { if (!submitting) { setEditing(null); setSensitive(null); setConfirmingHermesCommands(false); } },
    chooseAgent: (id) => {
      if (!editing) return;
      if (!id) { setEditing({ ...editing, agentId: null }); setBaseScripts(null); setBaseCommands(null); return; }
      setEditing({ ...editing, agentId: id });
      loadAgent(id);
    },
    agent: agentInfo,
    isHermes,
    scriptsReason,
    commandsReason,
    eligibilityPending,
    current,
    scope,
    scriptsScope,
    commandsScope,
    form,
    setScriptsEnabled: (on) => { if (!on || !scriptsReason || form.scriptsEnabled) edit("scriptsEnabled")(on); },
    setRisk: edit("risk"),
    setDays: edit("days"),
    setConsolidateConfirmed: edit("consolidateConfirmed"),
    setCommandsEnabled: (on) => {
      if (on && commandsReason && !form.commandsEnabled) return;
      if (on && isHermes) { setConfirmingHermesCommands(true); return; }
      edit("commandsEnabled")(on);
    },
    setCommandsAllMachines: edit("commandsAllMachines"),
    setHours: edit("hours"),
    setElevation: edit("elevation"),
    setPurpose: edit("purpose"),
    setReason: edit("reason"),
    applyReadOnly: () => {
      setOutcomes(null);
      setForm((f) => ({ ...f, scriptsEnabled: scriptsReason ? f.scriptsEnabled : true, risk: "low", commandsEnabled: false, elevation: false }));
    },
    isReadOnly: form.scriptsEnabled && form.risk === "low" && !form.commandsEnabled && !form.elevation,
    confirmingHermesCommands,
    confirmHermesCommands: () => { setConfirmingHermesCommands(false); edit("commandsEnabled")(true); },
    cancelHermesCommands: () => setConfirmingHermesCommands(false),
    scopesDiffer,
    scriptsChange,
    commandsChange,
    scriptsNeedScope,
    scriptsNeedConsolidation,
    canSave,
    save,
    outcomes,
    sensitive,
    confirmSensitive: async () => {
      setSubmitting(true);
      try {
        const c = await runCommands(true);
        setSensitive(null);
        finish({ ...(outcomes ?? {}), ...(c && c !== "confirm" ? { commands: c } : {}) });
      } finally {
        setSubmitting(false);
      }
    },
    cancelSensitive: () => {
      setSensitive(null);
      setOutcomes((o) => ({ ...(o ?? {}), commands: { state: "cancelled" } }));
    },
    saved,
    removing,
    askRemove: (row) => {
      setRemoveError(null); setRemoved(null); setSaved(null); setRemoving(row);
      if (removal.current?.id !== row.id) removal.current = { id: row.id, revoked: new Set(), directDone: false, direct: null };
    },
    cancelRemove: () => { if (!removeBusy) setRemoving(null); },
    confirmRemove: async () => {
      if (!removing || removeBusy) return;
      const progress = removal.current?.id === removing.id
        ? removal.current
        : (removal.current = { id: removing.id, revoked: new Set(), directDone: false, direct: null });
      setRemoveError(null);
      setRemoveBusy(true);
      const errors: string[] = [];
      for (const g of removing.scripts?.grants ?? []) {
        if (progress.revoked.has(g.id)) continue;
        try { await revokeMutation.mutateAsync(g.id); progress.revoked.add(g.id); } catch (e) { errors.push(refusalText(e)); }
      }
      if (removing.commands && !progress.directDone) {
        try {
          progress.direct = await removeMutation.mutateAsync(removing.id);
          progress.directDone = true;
        } catch (e) {
          // Already off the list (another tab, a retry): that's the goal.
          if (isNotListed(e)) progress.directDone = true;
          else errors.push(refusalText(e));
        }
      }
      setRemoveBusy(false);
      if (errors.length) { setRemoveError(errors.join(" · ")); return; }
      setRemoved({ name: removing.name, direct: progress.direct });
      removal.current = null;
      setRemoving(null);
    },
    removePending: removeBusy,
    removeError,
    removed,
    pause,
  };
}
