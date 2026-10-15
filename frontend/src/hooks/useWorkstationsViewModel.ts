import { useMemo, useState } from "react";
import { useServers, type Server } from "@/hooks/useServers";
import {
  bucketByClient,
  countReadiness,
  useCreateHostGroup,
  useDeleteHostGroup,
  useHostGroups,
  useHostReadiness,
  useTailnetSync,
  type ClientBucket,
  type HostGroup,
  type HostReadiness,
  type HostReadinessEntry,
  type ReadinessCounts,
  type TailnetSyncEntry,
  type TailnetSyncResult,
} from "@/hooks/useHostInventory";

export type ReadinessFilter = "all" | "ready" | "attention" | "offline";

export interface WorkstationBucketView extends ClientBucket {
  counts: ReadinessCounts;
  groupCounts: Map<string, ReadinessCounts>;
}

export interface WorkstationsViewModel {
  status: "loading" | "error" | "ready";
  buckets: WorkstationBucketView[];
  totals: ReadinessCounts;
  readinessOf: (serverId: string) => HostReadinessEntry | undefined;
  groupsById: Map<string, HostGroup>;
  query: string;
  setQuery: (value: string) => void;
  filter: ReadinessFilter;
  setFilter: (value: ReadinessFilter) => void;
  tailnetAvailable: boolean;
  sshCheckedAt: string | null;
  probing: boolean;
  probeNow: () => void;
  syncing: boolean;
  sync: () => void;
  syncResult: TailnetSyncResult | null;
  syncError: string | null;
  /** Tailnet devices not in the inventory, from the last sync. */
  available: TailnetSyncEntry[];
  importSelection: Set<string>;
  toggleImport: (nodeId: string) => void;
  importSelected: () => void;
  importing: boolean;
  editing: Server | null;
  edit: (server: Server) => void;
  closeEdit: () => void;
  groupDraft: { name: string; clientId: string } | null;
  startGroup: (clientId?: string | null) => void;
  setGroupDraft: (draft: { name: string; clientId: string }) => void;
  cancelGroup: () => void;
  saveGroup: (clientName: string | null) => void;
  savingGroup: boolean;
  groupError: string | null;
  deletingGroup: HostGroup | null;
  askDeleteGroup: (group: HostGroup) => void;
  cancelDeleteGroup: () => void;
  confirmDeleteGroup: () => void;
  removingGroup: boolean;
}

const ATTENTION: HostReadiness[] = ["online_no_access", "not_prepared"];

function matchesFilter(state: HostReadiness | undefined, filter: ReadinessFilter): boolean {
  if (filter === "all") return true;
  if (filter === "attention") return state !== undefined && ATTENTION.includes(state);
  return state === filter;
}

export function useWorkstationsViewModel(): WorkstationsViewModel {
  const servers = useServers();
  const groups = useHostGroups();
  const readiness = useHostReadiness();
  const tailnetSync = useTailnetSync();
  const createGroup = useCreateHostGroup();
  const deleteGroup = useDeleteHostGroup();

  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ReadinessFilter>("all");
  const [editing, setEditing] = useState<Server | null>(null);
  const [groupDraft, setGroupDraft] = useState<{ name: string; clientId: string } | null>(null);
  const [deletingGroup, setDeletingGroup] = useState<HostGroup | null>(null);
  const [importSelection, setImportSelection] = useState<Set<string>>(new Set());
  // The last sync's report. Kept here, not read from the mutation, so that an
  // import (same mutation) replaces it with the post-import picture.
  const [syncResult, setSyncResult] = useState<TailnetSyncResult | null>(null);
  const runSync = (importNodeIds: string[] = []) =>
    tailnetSync.mutate(importNodeIds, {
      onSuccess: (result) => {
        setSyncResult(result);
        setImportSelection(new Set());
      },
    });

  const readinessById = useMemo(
    () => new Map((readiness.data?.entries ?? []).map((e) => [e.server_id, e])),
    [readiness.data],
  );
  const groupsById = useMemo(() => new Map((groups.data ?? []).map((g) => [g.id, g])), [groups.data]);

  const buckets = useMemo<WorkstationBucketView[]>(() => {
    const q = query.trim().toLowerCase();
    const visible = (servers.data ?? []).filter((s) => {
      if (!matchesFilter(readinessById.get(s.id)?.readiness, filter)) return false;
      if (!q) return true;
      return [s.name, s.ip_address, s.location, s.tailnet_name, s.darckware_client_name]
        .some((v) => v?.toLowerCase().includes(q));
    });
    return bucketByClient(visible, groups.data ?? [])
      .filter((b) => b.machines.length > 0 || (!q && filter === "all"))
      .map((b) => ({
        ...b,
        counts: countReadiness(b.machines.map((m) => m.id), readinessById),
        groupCounts: new Map(b.groups.map((g) => [g.id, countReadiness(g.server_ids, readinessById)])),
      }));
  }, [servers.data, groups.data, readinessById, query, filter]);

  const totals = useMemo(
    () => countReadiness(
      (servers.data ?? []).filter((s) => s.kind === "workstation").map((s) => s.id),
      readinessById,
    ),
    [servers.data, readinessById],
  );

  const status = servers.isLoading || groups.isLoading
    ? "loading"
    : servers.isError || groups.isError
      ? "error"
      : "ready";

  return {
    status,
    buckets,
    totals,
    readinessOf: (id) => readinessById.get(id),
    groupsById,
    query,
    setQuery,
    filter,
    setFilter,
    tailnetAvailable: readiness.data?.tailnet_available ?? true,
    sshCheckedAt: readiness.data?.ssh_checked_at ?? null,
    probing: readiness.forceProbe.isPending,
    probeNow: () => readiness.forceProbe.mutate(),
    syncing: tailnetSync.isPending && tailnetSync.variables?.length === 0,
    sync: () => runSync(),
    syncResult,
    syncError: tailnetSync.error?.message ?? null,
    available: syncResult?.entries.filter((e) => e.outcome === "available") ?? [],
    importSelection,
    toggleImport: (nodeId) =>
      setImportSelection((cur) => {
        const next = new Set(cur);
        if (next.has(nodeId)) next.delete(nodeId);
        else next.add(nodeId);
        return next;
      }),
    importSelected: () => {
      if (importSelection.size > 0) runSync([...importSelection]);
    },
    importing: tailnetSync.isPending && (tailnetSync.variables?.length ?? 0) > 0,
    editing,
    edit: setEditing,
    closeEdit: () => setEditing(null),
    groupDraft,
    startGroup: (clientId) => {
      createGroup.reset();
      setGroupDraft({ name: "", clientId: clientId ?? "" });
    },
    setGroupDraft,
    cancelGroup: () => setGroupDraft(null),
    saveGroup: (clientName) => {
      if (!groupDraft || !groupDraft.name.trim()) return;
      createGroup.mutate(
        {
          name: groupDraft.name.trim(),
          darckware_client_id: groupDraft.clientId || null,
          darckware_client_name: groupDraft.clientId ? clientName : null,
        },
        { onSuccess: () => setGroupDraft(null) },
      );
    },
    savingGroup: createGroup.isPending,
    groupError: createGroup.error?.message ?? null,
    deletingGroup,
    askDeleteGroup: (group) => {
      deleteGroup.reset();
      setDeletingGroup(group);
    },
    cancelDeleteGroup: () => setDeletingGroup(null),
    confirmDeleteGroup: () => {
      if (!deletingGroup) return;
      deleteGroup.mutate(deletingGroup.id, { onSuccess: () => setDeletingGroup(null) });
    },
    removingGroup: deleteGroup.isPending,
  };
}
