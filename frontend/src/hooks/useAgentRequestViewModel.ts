import { useMemo, useState } from "react";
import {
  SCRIPT_RISK_NEEDS,
  riskCovers,
  useAuthorizedAgents,
  useRequestAgentTask,
  type AgentRequestResult,
  type AuthorizedAgent,
} from "@/hooks/useAgentMaintenance";
import { useWorkItems, type WorkItem } from "@/hooks/useClientOps";
import { scriptFits, useHostScripts, useScriptCategories, type HostScript } from "@/hooks/useHostScripts";
import type { Server } from "@/hooks/useServers";

export interface ChosenScript {
  script: HostScript;
  values: Record<string, string>;
}

/** "Pedir ao agente" (2026-10-19): free-text instruction, optionally the
 * library scripts the agent must use (with their values), the client's
 * ticket/demand, and one or more authorized agents -- one Messages task each.
 * idle -> submitting -> done | error. */
export interface AgentRequestViewModel {
  status: "idle" | "submitting" | "done" | "error";
  machines: Server[];
  authorized: AuthorizedAgent[];
  /** Agents whose delegation covers the chosen scripts' risk. */
  canPick: (entry: AuthorizedAgent) => boolean;
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

export function useAgentRequestViewModel(machines: Server[]): AgentRequestViewModel {
  const { authorized } = useAuthorizedAgents();
  const library = useHostScripts();
  const categories = useScriptCategories();
  const request = useRequestAgentTask();
  const [chosenAgents, setChosenAgents] = useState<Set<string>>(new Set());
  const [instruction, setInstruction] = useState("");
  const [scripts, setScripts] = useState<ChosenScript[]>([]);
  const [itemKey, setItemKey] = useState("");

  const clientIds = new Set(machines.map((m) => m.darckware_client_id ?? ""));
  const clientId = clientIds.size === 1 ? [...clientIds][0] : "";
  const workItems = useWorkItems({ client_account_id: clientId, stage: "open" }, Boolean(clientId));
  const clientItems = clientId ? workItems.data?.items ?? [] : [];

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
  const canPick = (entry: AuthorizedAgent) => riskCovers(entry.maxRisk, needed);
  const pickable = new Set(authorized.filter(canPick).map((a) => a.agent.id));
  const agentIds = [...chosenAgents].filter((id) => pickable.has(id));
  const missingRequired = scripts.some((c) => c.script.parameters.some(
    (p) => p.required && !p.vault_secret && !p.default && !p.secret && !(c.values[p.name] ?? "").trim()));
  const status = request.isPending ? "submitting" : request.isError ? "error" : request.data ? "done" : "idle";

  return {
    status,
    machines,
    authorized,
    canPick,
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
    error: request.error?.message ?? null,
  };
}
