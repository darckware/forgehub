import { useMemo, useState } from "react";
import {
  SCRIPT_RISK_NEEDS,
  riskCovers,
  useAuthorizedAgents,
  useRequestAgentTask,
  type AgentRequestResult,
  type AuthorizedAgent,
} from "@/hooks/useAgentMaintenance";
import { useDirectAgents, type DirectAgent } from "@/hooks/useDirectAccess";
import { useHostGroups, type HostGroup } from "@/hooks/useHostInventory";
import { useWorkItems, type WorkItem } from "@/hooks/useClientOps";
import { scriptFits, useHostScripts, useScriptCategories, type HostScript } from "@/hooks/useHostScripts";
import type { Server } from "@/hooks/useServers";

/** The backend's own reason when it gave one (string detail, or a coded
 * `{code, message}` such as MAINTENANCE_CLIENT_MISMATCH), else the raw error. */
function requestErrorText(error: Error): string {
  const detail = (error as { body?: { detail?: unknown } }).body?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string") return detail.message;
  return error.message;
}

export interface ChosenScript {
  script: HostScript;
  values: Record<string, string>;
}

/** Why an agent can't take this request; null = it can. */
export type CandidateBlock = "risk_too_low" | "scripts_need_delegation" | "not_covering";

/** An agent "Pedir ao agente" lists: what it may do on *these* machines. */
export interface AgentRequestCandidate {
  id: string;
  name: string;
  /** Lowest per-machine ceiling of its script delegations over every chosen
   * machine (backend machine_ceilings); null = scripts don't cover them all. */
  scriptsCeiling: string | null;
  /** A direct-access configuration in force covers every chosen machine. */
  commands: boolean;
  block: CandidateBlock | null;
}

/** The ceiling a set of script delegations gives on every machine, as the
 * backend computes it: per machine the highest covering delegation, then the
 * lowest across machines; null when one machine isn't covered. */
export function scriptsCeilingFor(entry: AuthorizedAgent, machines: Server[], groups: HostGroup[]): string | null {
  if (!machines.length) return null;
  const groupsOf = (id: string) => new Set(groups.filter((g) => g.server_ids.includes(id)).map((g) => g.id));
  let lowest: string | null = null;
  for (const m of machines) {
    const inGroups = groupsOf(m.id);
    const risks = entry.delegations
      .filter((d) => (d.servers ?? []).includes(m.id) || (d.host_groups ?? []).some((g) => inGroups.has(g)))
      .map((d) => d.max_risk ?? "low");
    if (!risks.length) return null;
    const best = risks.reduce((a, b) => (riskCovers(a, b) ? a : b));
    lowest = lowest === null || riskCovers(lowest, best) ? best : lowest;
  }
  return lowest;
}

/** A direct access covers every machine (backend direct_access_for): on the
 * list, a profile that reaches run_remote_command, in force, all machines or
 * each one in its snapshot. */
export function commandsCover(agent: DirectAgent | undefined, machines: Server[], now = Date.now()): boolean {
  const config = agent?.configuration;
  if (!agent?.allowed || agent.unsupported_reason || !config || !machines.length) return false;
  if (config.expires_at && new Date(config.expires_at).getTime() <= now) return false;
  return config.all_machines || machines.every((m) => config.machines.some((c) => c.id === m.id));
}

/** "Pedir ao agente" (2026-10-19; either permission since 2026-11-11, plan
 * REMOTE_ACCESS_SUPPORT_ADJUSTMENTS_PLAN Fase 2 item 2): free-text
 * instruction, optionally the library scripts the agent must use (with their
 * values), the client's ticket/demand, and one or more agents -- one Messages
 * task each. Same rule as the backend: with scripts chosen, only an agent whose
 * script delegation covers their risk on every machine; with none, a script
 * delegation (any risk) or a direct access covering every machine.
 * idle -> submitting -> done | error. */
export interface AgentRequestViewModel {
  status: "idle" | "submitting" | "done" | "error";
  /** The machines the request goes to (the offered ones minus any unticked). */
  machines: Server[];
  /** Every machine the panel was opened with. */
  offeredMachines: Server[];
  isMachineChosen: (id: string) => boolean;
  /** Tick/untick an offered machine. Submitting needs at least one. */
  toggleMachine: (id: string) => void;
  candidates: AgentRequestCandidate[];
  chosenAgents: Set<string>;
  toggleAgent: (id: string) => void;
  instruction: string;
  setInstruction: (value: string) => void;
  /** Library scripts that fit every chosen machine, grouped by classification. */
  scriptGroups: { label: string; scripts: HostScript[] }[];
  scripts: ChosenScript[];
  addScript: (id: string) => void;
  removeScript: (id: string) => void;
  setScriptValue: (id: string, name: string, value: string) => void;
  clientItems: WorkItem[];
  itemKey: string;
  setItemKey: (value: string) => void;
  canSubmit: boolean;
  submit: () => void;
  result: AgentRequestResult[] | null;
  error: string | null;
}

export interface AgentRequestOptions {
  /** Opened from a client's ticket/demand (Clientes › Demandas, Fase 3):
   * that item is preselected, even when it isn't in the open-items list. */
  initialItem?: WorkItem | null;
  /** Start with no machine ticked (a client's whole fleet offered from its
   * ticket: the operator picks, at least one). Default: all offered ticked. */
  startUnticked?: boolean;
}

export function useAgentRequestViewModel(offered: Server[], options: AgentRequestOptions = {}): AgentRequestViewModel {
  const { initialItem, startUnticked = false } = options;
  const { authorized } = useAuthorizedAgents();
  const directAgents = useDirectAgents();
  const { data: hostGroups } = useHostGroups();
  const library = useHostScripts();
  const categories = useScriptCategories();
  const request = useRequestAgentTask();
  const [chosenAgents, setChosenAgents] = useState<Set<string>>(new Set());
  const [instruction, setInstruction] = useState("");
  const [scripts, setScripts] = useState<ChosenScript[]>([]);
  const [itemKey, setItemKey] = useState(initialItem ? `${initialItem.kind}:${initialItem.id}` : "");
  const [excluded, setExcluded] = useState<Set<string>>(() => new Set(startUnticked ? offered.map((m) => m.id) : []));
  const machines = useMemo(() => offered.filter((m) => !excluded.has(m.id)), [offered, excluded]);

  // The client comes from every offered machine, so unticking one never drops the item list.
  const clientIds = new Set(offered.map((m) => m.darckware_client_id ?? ""));
  const clientId = clientIds.size === 1 ? [...clientIds][0] : "";
  const workItems = useWorkItems({ client_account_id: clientId, stage: "open" }, Boolean(clientId));
  const openItems = clientId ? workItems.data?.items ?? [] : [];
  const clientItems = initialItem && !openItems.some((i) => i.kind === initialItem.kind && i.id === initialItem.id)
    ? [initialItem, ...openItems] : openItems;

  const scriptGroups = useMemo(() => {
    const labels = new Map((categories.data ?? []).map((c) => [c.id, c.label]));
    const groups = new Map<string, HostScript[]>();
    for (const s of library.data ?? []) {
      if (s.archived || !machines.every((m) => scriptFits(s.platform, m.os_family))) continue;
      const label = labels.get(s.category_id) ?? "—";
      groups.set(label, [...(groups.get(label) ?? []), s]);
    }
    return [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([label, list]) => ({ label, scripts: list }));
  }, [library.data, categories.data, machines]);

  const needed = scripts.reduce<string>((acc, c) => {
    const need = SCRIPT_RISK_NEEDS[c.script.risk] ?? "high";
    return riskCovers(acc, need) ? acc : need;
  }, "low");
  const candidates = useMemo<AgentRequestCandidate[]>(() => {
    const direct = Array.isArray(directAgents.data) ? directAgents.data : [];
    const byId = new Map<string, AgentRequestCandidate>();
    // A script delegation counts only when the agent's profile reaches
    // run_maintenance_script (backend agent_tool_problems), as for commands.
    const scriptsProblem = new Map(direct.map((a) => [a.id, a.scripts_unsupported_reason ?? null]));
    for (const entry of authorized) {
      const usable = !scriptsProblem.get(entry.agent.id);
      byId.set(entry.agent.id, {
        id: entry.agent.id, name: entry.agent.name,
        scriptsCeiling: usable ? scriptsCeilingFor(entry, machines, hostGroups ?? []) : null, commands: false, block: null,
      });
    }
    for (const agent of direct) {
      const cover = commandsCover(agent, machines);
      const row = byId.get(agent.id);
      if (row) row.commands = cover;
      else if (cover) byId.set(agent.id, { id: agent.id, name: agent.name, scriptsCeiling: null, commands: true, block: null });
    }
    for (const row of byId.values()) {
      if (scripts.length) {
        row.block = row.scriptsCeiling === null ? (row.commands ? "scripts_need_delegation" : "not_covering")
          : riskCovers(row.scriptsCeiling, needed) ? null : "risk_too_low";
      } else {
        row.block = row.scriptsCeiling !== null || row.commands ? null : "not_covering";
      }
    }
    return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [authorized, directAgents.data, hostGroups, machines, scripts.length, needed]);
  const pickable = new Set(candidates.filter((c) => c.block === null).map((c) => c.id));
  const agentIds = [...chosenAgents].filter((id) => pickable.has(id));
  const missingRequired = scripts.some((c) => c.script.parameters.some(
    (p) => p.required && !p.vault_secret && !p.default && !p.secret && !(c.values[p.name] ?? "").trim()));
  const status = request.isPending ? "submitting" : request.isError ? "error" : request.data ? "done" : "idle";

  return {
    status,
    machines,
    offeredMachines: offered,
    isMachineChosen: (id) => !excluded.has(id),
    toggleMachine: (id) => setExcluded((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    }),
    candidates,
    chosenAgents,
    toggleAgent: (id) => setChosenAgents((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    }),
    instruction,
    setInstruction,
    scriptGroups,
    scripts,
    addScript: (id) => {
      const script = (library.data ?? []).find((s) => s.id === id);
      if (script && !scripts.some((c) => c.script.id === id)) setScripts((cur) => [...cur, { script, values: {} }]);
    },
    removeScript: (id) => setScripts((cur) => cur.filter((c) => c.script.id !== id)),
    setScriptValue: (id, name, value) =>
      setScripts((cur) => cur.map((c) => (c.script.id === id ? { ...c, values: { ...c.values, [name]: value } } : c))),
    clientItems,
    itemKey: clientItems.some((i) => `${i.kind}:${i.id}` === itemKey) ? itemKey : "",
    setItemKey,
    canSubmit: agentIds.length > 0 && instruction.trim().length >= 5 && !missingRequired && machines.length > 0 && !request.isPending,
    submit: () => {
      const [kind, id] = itemKey.split(":");
      const item = id && clientItems.some((i) => `${i.kind}:${i.id}` === itemKey)
        ? { darckware_item_kind: kind as "ticket" | "demand", darckware_item_id: id } : {};
      request.mutate({
        agent_ids: agentIds,
        server_ids: machines.map((m) => m.id),
        instruction: instruction.trim(),
        scripts: scripts.map((c) => ({
          script_id: c.script.id,
          parameter_values: Object.fromEntries(Object.entries(c.values).filter(([, v]) => v.trim())),
        })),
        ...item,
      });
    },
    result: request.data ?? null,
    error: request.error ? requestErrorText(request.error) : null,
  };
}
