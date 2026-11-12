import { useEffect, useMemo, useState } from "react";
import { useServers } from "@/hooks/useServers";
import { useHostGroups, useHostReadiness, type HostReadinessEntry } from "@/hooks/useHostInventory";
import { useDirectAgents } from "@/hooks/useDirectAccess";
import { useGrantAuthorityDelegation, useRevokeAuthorityDelegation } from "@/hooks/useGovernance";
import { REMOTE_ACCESS_ACTION, useAuthorizedAgents, type AuthorizedAgent, type RiskLevel } from "@/hooks/useAgentMaintenance";
import type { Agent } from "@/hooks/useAgent";

export const VALIDITY_DAYS = [1, 7, 30] as const;

/** Why a machine row carries a note, from its readiness (backend
 * `classify_readiness`). Only "not_prepared" (no ForgeHub login yet -- also a
 * partial, RustDesk-only machine) and "disabled" (access off in ForgeHub) make
 * it unpickable. "offline" (switched off, tailnet offline) and "unknown"
 * (probe unread) stay pickable: the grant stores machine ids, and whether the
 * machine answers is decided when an agent runs something (409 then). */
export type GrantMachineHint = "offline" | "unknown" | "not_prepared" | "disabled";

function machineHint(entry: HostReadinessEntry | undefined, pending: boolean): GrantMachineHint | null {
  if (pending) return null;
  switch (entry?.readiness) {
    case "ready":
    case "busy":
      return null;
    case "offline":
    case "not_prepared":
    case "disabled":
      return entry.readiness;
    default:
      return "unknown";
  }
}

/** An agent the grant panel lists. `unsupportedReason` is the backend's code
 * (`direct_access_problem`, e.g. PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS) of why
 * it couldn't use a machine access; such an agent is shown but not pickable. */
export interface GrantAgentRow {
  agent: Agent;
  unsupportedReason: string | null;
  selectable: boolean;
}

/** A machine the grant panel lists, with its readiness. A machine that was
 * never prepared (or has access off) is not pickable ("preparar primeiro"). */
export interface GrantMachineRow {
  id: string;
  name: string;
  /** Address and client, for telling similar names apart. */
  detail: string | null;
  readiness: HostReadinessEntry | undefined;
  hint: GrantMachineHint | null;
  selectable: boolean;
}

/** Choices dropped because they stopped being pickable while the panel was open. */
export interface GrantPruned {
  agents: number;
  machines: number;
}

/** What the footer says will be granted, from the values that will be sent. */
export interface GrantSummary {
  agents: number;
  machines: number;
  groups: number;
  risk: RiskLevel;
  days: number;
}

/** "Agentes autorizados" (Remote Access › Machines): grant several agents at
 * once -- one governance delegation each, so each is revoked on its own --
 * and revoke after a confirmation. idle -> granting -> submitting.
 *
 * The grant panel (2026-11-11, plan REMOTE_ACCESS_SUPPORT_ADJUSTMENTS_PLAN
 * gap 6) only lets through what can actually be used: an agent whose runtime
 * or profile can't reach the maintenance tools, and a machine without
 * ForgeHub's login, are listed disabled with the reason. Either source still
 * loading (or unreadable) never blocks the grant: the rows stay enabled and
 * the panel says the check is pending -- the backend decides in the end. */
export interface AuthorizedAgentsViewModel {
  status: "loading" | "idle" | "granting" | "submitting" | "error";
  authorized: AuthorizedAgent[];
  /** Machines matching the search, in name order. */
  machines: GrantMachineRow[];
  /** Every machine, before the search. */
  machineCount: number;
  groups: {id: string; name: string}[];
  selectedMachines: Set<string>;
  selectedGroups: Set<string>;
  toggleMachine: (id: string) => void;
  toggleGroup: (id: string) => void;
  machineQuery: string;
  setMachineQuery: (value: string) => void;
  /** Every selectable visible machine is selected (and there is at least one). */
  allVisibleSelected: boolean;
  /** Selects every selectable visible machine, or clears them when all are. */
  toggleAllVisible: () => void;
  /** Readiness not read yet (or unreadable): machines aren't filtered by it. */
  readinessPending: boolean;
  /** Set when a refresh made a chosen agent/machine unpickable and it was unchecked. */
  pruned: GrantPruned | null;
  /** Agents that can still be granted (active, not yet authorized). */
  grantable: Agent[];
  agentRows: GrantAgentRow[];
  /** Eligibility not read yet (or unreadable): agents aren't filtered by it. */
  eligibilityPending: boolean;
  /** The grant dialog is open (stays open on error, closes on success). */
  grantOpen: boolean;
  openGrant: () => void;
  closeGrant: () => void;
  chosen: Set<string>;
  toggleAgent: (id: string) => void;
  risk: RiskLevel;
  setRisk: (value: RiskLevel) => void;
  days: number;
  setDays: (value: number) => void;
  summary: GrantSummary;
  canGrant: boolean;
  grant: () => Promise<void>;
  revoking: AuthorizedAgent | null;
  askRevoke: (entry: AuthorizedAgent) => void;
  cancelRevoke: () => void;
  confirmRevoke: () => Promise<void>;
  revokePending: boolean;
  error: string | null;
}

export function useAuthorizedAgentsViewModel(): AuthorizedAgentsViewModel {
  const { authorized, agents, isLoading } = useAuthorizedAgents();
  const machines = useServers();
  const groups = useHostGroups();
  const [granting, setGranting] = useState(false);
  // Same query keys as the Direct access and Machines cards on this page, so
  // these share their cache; readiness is only polled here while the panel is open.
  const directAgents = useDirectAgents();
  const readiness = useHostReadiness(granting);
  const [selectedMachines, setSelectedMachines] = useState<Set<string>>(new Set());
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
  const [machineQuery, setMachineQuery] = useState("");
  const grantMutation = useGrantAuthorityDelegation();
  const revokeMutation = useRevokeAuthorityDelegation();
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [risk, setRisk] = useState<RiskLevel>("medium");
  const [days, setDays] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [revoking, setRevoking] = useState<AuthorizedAgent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pruned, setPruned] = useState<GrantPruned | null>(null);

  const authorizedIds = new Set(authorized.map((a) => a.agent.id));
  const grantable = agents.filter((a) => a.is_active && a.status === "active" && !authorizedIds.has(a.id))
    .sort((a, b) => a.name.localeCompare(b.name));

  const eligibilityPending = !Array.isArray(directAgents.data);
  const reasonByAgent = useMemo(
    () => new Map((Array.isArray(directAgents.data) ? directAgents.data : []).map((a) => [a.id, a.unsupported_reason])),
    [directAgents.data],
  );
  const agentRows: GrantAgentRow[] = grantable.map((agent) => {
    const unsupportedReason = eligibilityPending ? null : reasonByAgent.get(agent.id) ?? null;
    return { agent, unsupportedReason, selectable: unsupportedReason === null };
  });
  const selectableAgents = new Set(agentRows.filter((r) => r.selectable).map((r) => r.agent.id));

  const readinessEntries = readiness.data?.entries;
  const readinessPending = !Array.isArray(readinessEntries);
  const byServer = useMemo(
    () => new Map((Array.isArray(readinessEntries) ? readinessEntries : []).map((e) => [e.server_id, e])),
    [readinessEntries],
  );
  const allMachines: GrantMachineRow[] = useMemo(() => (machines.data ?? [])
    .map((m) => {
      const entry = byServer.get(m.id);
      const hint = machineHint(entry, readinessPending);
      return {
        id: m.id,
        name: m.name,
        detail: [m.ip_address, m.darckware_client_name].filter(Boolean).join(" · ") || null,
        readiness: entry,
        hint,
        selectable: hint !== "not_prepared" && hint !== "disabled",
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name)), [machines.data, byServer, readinessPending]);
  const needle = machineQuery.trim().toLowerCase();
  const visibleMachines = needle
    ? allMachines.filter((m) => `${m.name} ${m.detail ?? ""}`.toLowerCase().includes(needle))
    : allMachines;
  const visibleSelectable = visibleMachines.filter((m) => m.selectable);
  const allVisibleSelected = visibleSelectable.length > 0 && visibleSelectable.every((m) => selectedMachines.has(m.id));
  const selectableMachines = new Set(allMachines.filter((m) => m.selectable).map((m) => m.id));

  // A choice that stopped being pickable after it was made (eligibility and
  // readiness refresh every 30 s) is unchecked, and the panel says so -- never
  // left checked-but-disabled while silently missing from what is sent.
  const agentKey = [...selectableAgents].sort().join(",");
  const machineKey = [...selectableMachines].sort().join(",");
  useEffect(() => {
    if (!granting) return;
    const agentIds = new Set(agentKey ? agentKey.split(",") : []);
    const machineIds = new Set(machineKey ? machineKey.split(",") : []);
    const staleAgents = [...chosen].filter((id) => !agentIds.has(id));
    const staleMachines = [...selectedMachines].filter((id) => !machineIds.has(id));
    if (!staleAgents.length && !staleMachines.length) return;
    if (staleAgents.length) setChosen((cur) => new Set([...cur].filter((id) => agentIds.has(id))));
    if (staleMachines.length) setSelectedMachines((cur) => new Set([...cur].filter((id) => machineIds.has(id))));
    setPruned((cur) => ({
      agents: (cur?.agents ?? 0) + staleAgents.length,
      machines: (cur?.machines ?? 0) + staleMachines.length,
    }));
  }, [granting, agentKey, machineKey, chosen, selectedMachines]);

  // What will actually be sent (also the summary): the same filter, so a
  // render between a refresh and the pruning above can't send a stale id.
  const effectiveAgents = [...chosen].filter((id) => selectableAgents.has(id));
  const effectiveMachines = [...selectedMachines].filter((id) => selectableMachines.has(id));
  const effectiveGroups = [...selectedGroups].filter((id) => (groups.data ?? []).some((g) => g.id === id));
  const hasScope = effectiveMachines.length > 0 || effectiveGroups.length > 0;

  const toggleSet = (setter: typeof setSelectedMachines, id: string) => setter((cur) => {
    const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next;
  });

  const status = isLoading ? "loading" : submitting ? "submitting" : error ? "error" : granting ? "granting" : "idle";
  return {
    status,
    authorized,
    machines: visibleMachines,
    machineCount: allMachines.length,
    groups: groups.data ?? [],
    selectedMachines,
    selectedGroups,
    toggleMachine: (id) => { if (selectableMachines.has(id)) toggleSet(setSelectedMachines, id); },
    toggleGroup: (id) => toggleSet(setSelectedGroups, id),
    machineQuery,
    setMachineQuery,
    allVisibleSelected,
    toggleAllVisible: () => setSelectedMachines((cur) => {
      const next = new Set(cur);
      for (const m of visibleSelectable) {
        if (allVisibleSelected) next.delete(m.id); else next.add(m.id);
      }
      return next;
    }),
    readinessPending,
    pruned,
    grantable,
    agentRows,
    eligibilityPending,
    grantOpen: granting,
    openGrant: () => {
      setError(null); setPruned(null); setChosen(new Set()); setSelectedMachines(new Set()); setSelectedGroups(new Set());
      setMachineQuery(""); setDays(1); setGranting(true);
    },
    closeGrant: () => { if (!submitting) setGranting(false); },
    chosen,
    toggleAgent: (id) => { if (selectableAgents.has(id)) toggleSet(setChosen, id); },
    risk,
    setRisk,
    days,
    setDays,
    summary: { agents: effectiveAgents.length, machines: effectiveMachines.length, groups: effectiveGroups.length, risk, days },
    canGrant: effectiveAgents.length > 0 && hasScope && !submitting,
    grant: async () => {
      if (!effectiveAgents.length || !hasScope || submitting) return;
      setSubmitting(true);
      setError(null);
      const expires = new Date(Date.now() + days * 86_400_000).toISOString();
      try {
        for (const id of effectiveAgents) {
          await grantMutation.mutateAsync({
            grantee_agent_id: id, allowed_actions: [REMOTE_ACCESS_ACTION], scope_type: "organization",
            servers: effectiveMachines, host_groups: effectiveGroups, max_risk: risk, expires_at: expires, reason: "Manutenção de máquinas pelo Acesso Remoto",
          });
        }
        setGranting(false);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setSubmitting(false);
      }
    },
    revoking,
    askRevoke: (entry) => { setError(null); setRevoking(entry); },
    cancelRevoke: () => setRevoking(null),
    confirmRevoke: async () => {
      if (!revoking) return;
      try {
        for (const d of revoking.delegations) await revokeMutation.mutateAsync(d.id);
        setRevoking(null);
      } catch (e) {
        setError((e as Error).message);
      }
    },
    revokePending: revokeMutation.isPending,
    error,
  };
}
