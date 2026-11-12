import { useEffect, useMemo, useState } from "react";
import { useServers } from "@/hooks/useServers";
import { useHostGroups, useHostReadiness, type HostGroup, type HostReadinessEntry } from "@/hooks/useHostInventory";

/** Why a machine row carries a note, from its readiness (backend
 * `classify_readiness`). Only "not_prepared" (no ForgeHub login yet -- also a
 * partial, RustDesk-only machine) and "disabled" (access off in ForgeHub) make
 * it unpickable. "offline" (switched off, tailnet offline) and "unknown"
 * (probe unread) stay pickable: a permission stores machine ids, and whether
 * the machine answers is decided when an agent runs something (409 then). */
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

/** A machine the scope picker lists, with its readiness. A machine that was
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

/** Machines/groups chosen for a permission: search, readiness notes, "select
 * every visible", and the pruning of a choice that stopped being pickable
 * while the panel was open (readiness refreshes every 30 s) -- never left
 * checked-but-disabled while silently missing from what is sent. Extracted
 * from the Phase 1 grant panel (2026-11-11) for the single agent panel.
 * Readiness still loading (or unreadable) never blocks: rows stay enabled and
 * `readinessPending` says the check is pending -- the backend decides. */
export interface MachineScope {
  /** Machines matching the search, in name order. */
  machines: GrantMachineRow[];
  /** Every machine, before the search. */
  machineCount: number;
  groups: HostGroup[];
  selectedMachines: Set<string>;
  selectedGroups: Set<string>;
  toggleMachine: (id: string) => void;
  toggleGroup: (id: string) => void;
  /** Replaces the selection (opening the panel); doesn't count as an edit. */
  reset: (machines: Iterable<string>, groups: Iterable<string>) => void;
  machineQuery: string;
  setMachineQuery: (value: string) => void;
  allVisibleSelected: boolean;
  toggleAllVisible: () => void;
  readinessPending: boolean;
  /** Machines unchecked because they stopped being pickable; null when none. */
  pruned: number | null;
  /** What will be sent: selectable machines, existing groups. */
  effectiveMachines: string[];
  effectiveGroups: string[];
  /** The machine ids the selection covers (machines plus groups' members). */
  coveredMachineIds: Set<string>;
  /** The user changed the selection since the last reset. */
  touched: boolean;
  inventoryLoading: boolean;
  inventoryError: boolean;
  retryInventory: () => void;
}

export function useMachineScope(active: boolean): MachineScope {
  const servers = useServers();
  const groups = useHostGroups();
  // Same query key as the Machines card, so the cache is shared; polled only while open.
  const readiness = useHostReadiness(active);
  const [selectedMachines, setSelectedMachines] = useState<Set<string>>(new Set());
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
  const [machineQuery, setMachineQuery] = useState("");
  const [pruned, setPruned] = useState<number | null>(null);
  const [touched, setTouched] = useState(false);

  const readinessEntries = readiness.data?.entries;
  const readinessPending = !Array.isArray(readinessEntries);
  const byServer = useMemo(
    () => new Map((Array.isArray(readinessEntries) ? readinessEntries : []).map((e) => [e.server_id, e])),
    [readinessEntries],
  );
  const allMachines: GrantMachineRow[] = useMemo(() => (servers.data ?? [])
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
    .sort((a, b) => a.name.localeCompare(b.name)), [servers.data, byServer, readinessPending]);
  const needle = machineQuery.trim().toLowerCase();
  const visibleMachines = needle
    ? allMachines.filter((m) => `${m.name} ${m.detail ?? ""}`.toLowerCase().includes(needle))
    : allMachines;
  const visibleSelectable = visibleMachines.filter((m) => m.selectable);
  const allVisibleSelected = visibleSelectable.length > 0 && visibleSelectable.every((m) => selectedMachines.has(m.id));
  const selectableMachines = useMemo(() => new Set(allMachines.filter((m) => m.selectable).map((m) => m.id)), [allMachines]);
  const knownMachines = useMemo(() => new Set(allMachines.map((m) => m.id)), [allMachines]);

  // Prune only what is known and unpickable: an id the inventory doesn't list
  // (yet) isn't dropped while the list is still loading.
  const machineKey = [...selectableMachines].sort().join(",");
  useEffect(() => {
    if (!active || servers.isLoading) return;
    const stale = [...selectedMachines].filter((id) => knownMachines.has(id) && !selectableMachines.has(id));
    if (!stale.length) return;
    setSelectedMachines((cur) => new Set([...cur].filter((id) => !stale.includes(id))));
    setPruned((cur) => (cur ?? 0) + stale.length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, machineKey, selectedMachines, servers.isLoading]);

  const groupList = groups.data ?? [];
  const effectiveMachines = [...selectedMachines].filter((id) => selectableMachines.has(id));
  const effectiveGroups = [...selectedGroups].filter((id) => groupList.some((g) => g.id === id));
  const coveredMachineIds = new Set(effectiveMachines);
  for (const g of groupList) if (selectedGroups.has(g.id)) for (const id of g.server_ids) coveredMachineIds.add(id);

  const toggleSet = (setter: typeof setSelectedMachines, id: string) => {
    setTouched(true);
    setter((cur) => {
      const next = new Set(cur); if (next.has(id)) next.delete(id); else next.add(id); return next;
    });
  };

  return {
    machines: visibleMachines,
    machineCount: allMachines.length,
    groups: groupList,
    selectedMachines,
    selectedGroups,
    toggleMachine: (id) => { if (selectableMachines.has(id)) toggleSet(setSelectedMachines, id); },
    toggleGroup: (id) => toggleSet(setSelectedGroups, id),
    reset: (machines, nextGroups) => {
      setSelectedMachines(new Set(machines));
      setSelectedGroups(new Set(nextGroups));
      setMachineQuery("");
      setPruned(null);
      setTouched(false);
    },
    machineQuery,
    setMachineQuery,
    allVisibleSelected,
    toggleAllVisible: () => {
      setTouched(true);
      setSelectedMachines((cur) => {
        const next = new Set(cur);
        for (const m of visibleSelectable) {
          if (allVisibleSelected) next.delete(m.id); else next.add(m.id);
        }
        return next;
      });
    },
    readinessPending,
    pruned,
    effectiveMachines,
    effectiveGroups,
    coveredMachineIds,
    touched,
    inventoryLoading: servers.isLoading || groups.isLoading,
    inventoryError: Boolean(servers.error || groups.error),
    retryInventory: () => { void servers.refetch(); void groups.refetch(); },
  };
}
