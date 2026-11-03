/**
 * Remote Access › Machines: servers and workstations in one table, sectioned
 * by how the VPS reaches each one (phase 3 of
 * docs/architecture/REMOTE_ACCESS_SERVERS_UNIFICATION_PLAN.md). Replaces
 * useWorkstationsViewModel (workstations only, bucketed by client) and the
 * state that lived loose in pages/servers/index.tsx.
 *
 * Sections come from `access_path` on /servers/readiness: Tailscale (direct
 * 100.x), one per subnet router ("via srv-sup"), no path, and unknown. Tailnet
 * devices with no inventory row are listed apart, each with "Register".
 *
 * Open to the "servers" module since phase 4 (the old Servers page redirects
 * here). /vpn/status is admin-only, so for anyone else it isn't fetched: the
 * sections still come from readiness, without router routes or unregistered
 * devices.
 */
import { useMemo, useState } from "react";
import {
  useDeleteServer,
  useServers,
  useToggleServerAccess,
  type HostKind,
  type Server,
} from "@/hooks/useServers";
import {
  countReadiness,
  useCreateHostGroup,
  useDeleteHostGroup,
  useHostGroups,
  useHostReadiness,
  useTailnetSync,
  type AccessPath,
  type HostGroup,
  type HostReadinessEntry,
  type HostStatus,
  type ReadinessCounts,
  type TailnetSyncResult,
} from "@/hooks/useHostInventory";
import { usePermission } from "@/hooks/usePermission";
import { useVpnAction, useVpnStatus, type VpnActionResult, type VpnNode } from "@/hooks/useVpn";
import { useAuthStore } from "@/store/authStore";

export type ReadinessFilter = "all" | "ready" | "attention" | "offline";
export type KindFilter = "all" | HostKind;
export type PathFilter = "all" | "tailscale" | "subnet" | "none" | "unregistered";
export type SectionKind = "tailscale" | "subnet" | "none" | "unknown";

export interface MachineRow {
  machine: Server;
  readiness: HostReadinessEntry | undefined;
  /** The linked tailnet device, when there is one. */
  node: VpnNode | undefined;
}

export interface MachineSection {
  key: string;
  kind: SectionKind;
  /** Subnet sections: the router and the routes it carries. */
  routerName: string | null;
  routes: string[];
  /** Subnet sections: the VPS sees the route but does not accept routes. */
  notAccepted: boolean;
  rows: MachineRow[];
  counts: ReadinessCounts;
}

export interface MachineFilters {
  query: string;
  kind: KindFilter;
  /** "all", "none" (no client) or a Darckware client id. */
  client: string;
  readiness: ReadinessFilter;
  path: PathFilter;
}

const ATTENTION: HostStatus[] = ["partial", "not_prepared"];
const SECTION_ORDER: Record<SectionKind, number> = { tailscale: 0, subnet: 1, none: 2, unknown: 3 };

function matchesReadiness(state: HostStatus | undefined, filter: ReadinessFilter): boolean {
  if (filter === "all") return true;
  if (filter === "attention") return state !== undefined && ATTENTION.includes(state);
  if (filter === "ready") return state === "complete";
  return state === filter;
}

function sectionKindOf(path: AccessPath | undefined): SectionKind {
  if (path === "tailscale") return "tailscale";
  if (path === "subnet" || path === "subnet_not_accepted") return "subnet";
  if (path === "none") return "none";
  return "unknown";
}

function matchesPath(kind: SectionKind, filter: PathFilter): boolean {
  if (filter === "all") return true;
  if (filter === "unregistered") return false;
  return kind === filter;
}

/** Pure: filter the inventory and split it into access-path sections. */
export function buildMachineSections(
  machines: Server[],
  readinessById: Map<string, HostReadinessEntry>,
  nodesById: Map<string, VpnNode>,
  filters: MachineFilters,
): MachineSection[] {
  const q = filters.query.trim().toLowerCase();
  const sections = new Map<string, MachineSection>();
  for (const machine of machines) {
    const readiness = readinessById.get(machine.id);
    const kind = sectionKindOf(readiness?.access_path);
    if (filters.kind !== "all" && machine.kind !== filters.kind) continue;
    if (filters.client === "none" && machine.darckware_client_id) continue;
    if (filters.client !== "all" && filters.client !== "none" && machine.darckware_client_id !== filters.client) continue;
    if (!matchesReadiness(readiness?.status, filters.readiness)) continue;
    if (!matchesPath(kind, filters.path)) continue;
    if (
      q &&
      ![machine.name, machine.ip_address, machine.location, machine.tailnet_name, machine.darckware_client_name, readiness?.tailscale_ipv4]
        .some((v) => v?.toLowerCase().includes(q))
    ) continue;

    const routerId = kind === "subnet" ? readiness?.access_via_node_id ?? "" : "";
    const key = kind === "subnet" ? `subnet:${routerId}` : kind;
    let section = sections.get(key);
    if (!section) {
      section = {
        key,
        kind,
        routerName: kind === "subnet" ? readiness?.access_via_name ?? null : null,
        routes: kind === "subnet" ? nodesById.get(routerId)?.subnet_routes ?? [] : [],
        notAccepted: false,
        rows: [],
        counts: { total: 0, ready: 0, offline: 0, attention: 0 },
      };
      sections.set(key, section);
    }
    if (readiness?.access_path === "subnet_not_accepted") section.notAccepted = true;
    section.rows.push({
      machine,
      readiness,
      node: machine.tailnet_node_id ? nodesById.get(machine.tailnet_node_id) : undefined,
    });
  }
  return [...sections.values()]
    .map((section) => ({
      ...section,
      rows: section.rows.sort((a, b) => a.machine.name.localeCompare(b.machine.name)),
      counts: countReadiness(section.rows.map((r) => r.machine.id), readinessById),
    }))
    .sort((a, b) => SECTION_ORDER[a.kind] - SECTION_ORDER[b.kind] || (a.routerName ?? "").localeCompare(b.routerName ?? ""));
}

/** Pure: tailnet devices with no inventory row (phones, laptops, a machine not imported yet). */
export function unregisteredDevices(machines: Server[], peers: VpnNode[], query: string): VpnNode[] {
  const linked = new Set(machines.map((m) => m.tailnet_node_id).filter(Boolean));
  const q = query.trim().toLowerCase();
  return peers
    .filter((p) => !linked.has(p.id))
    .filter((p) => !q || [p.name, p.hostname, p.tailscale_ipv4].some((v) => v?.toLowerCase().includes(q)))
    .sort((a, b) => (a.name ?? "").localeCompare(b.name ?? ""));
}

export interface MachinesViewModel {
  status: "loading" | "error" | "ready";
  /** Admin-only parts (tailnet sync/register/test, install key, passwords):
   * their backend routes require an admin. */
  isAdmin: boolean;
  /** The "servers" module's flags: create/edit/import/toggle and delete. */
  canWrite: boolean;
  canDelete: boolean;
  sections: MachineSection[];
  unregistered: VpnNode[];
  totals: ReadinessCounts;
  clients: { id: string; name: string }[];
  groups: HostGroup[];
  groupsById: Map<string, HostGroup>;
  groupCounts: Map<string, ReadinessCounts>;
  filters: MachineFilters;
  setFilter: <K extends keyof MachineFilters>(key: K, value: MachineFilters[K]) => void;
  tailnetAvailable: boolean;
  acceptRoutes: boolean | null;
  sshCheckedAt: string | null;
  probing: boolean;
  probeNow: () => void;
  syncing: boolean;
  sync: () => void;
  syncResult: TailnetSyncResult | null;
  syncError: string | null;
  registering: string | null;
  register: (nodeId: string) => void;
  testing: string | null;
  testNode: (nodeId: string) => void;
  testResult: VpnActionResult | null;
  togglingAccess: boolean;
  toggleAccess: (machine: Server) => void;
  expandedId: string | null;
  toggleExpanded: (id: string) => void;
  /** null = closed, "new" = creating, a Server = editing. */
  form: Server | "new" | null;
  openForm: (target: Server | "new") => void;
  closeForm: () => void;
  installing: Server | null;
  closeInstall: () => void;
  /** Station opened in "Prepare station" from its row. */
  preparing: Server | null;
  closePrepare: () => void;
  /** One "Configure access" per machine (phase 5): a server gets the key
   * installed with an admin account, a station gets prepared. */
  configure: (machine: Server) => void;
  importingCsv: boolean;
  setImportingCsv: (open: boolean) => void;
  deleting: Server | null;
  askDelete: (machine: Server) => void;
  cancelDelete: () => void;
  confirmDelete: () => void;
  removing: boolean;
  groupDraft: { name: string; clientId: string } | null;
  startGroup: () => void;
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

const EMPTY_FILTERS: MachineFilters = { query: "", kind: "all", client: "all", readiness: "all", path: "all" };

export function useMachinesViewModel(): MachinesViewModel {
  const isAdmin = useAuthStore((state) => state.user?.is_admin ?? false);
  const perm = usePermission("servers");
  const servers = useServers();
  const groups = useHostGroups();
  const readiness = useHostReadiness();
  const vpn = useVpnStatus({ enabled: isAdmin });
  const tailnetSync = useTailnetSync();
  const vpnAction = useVpnAction();
  const toggle = useToggleServerAccess();
  const deleteServer = useDeleteServer();
  const createGroup = useCreateHostGroup();
  const deleteGroup = useDeleteHostGroup();

  const [filters, setFilters] = useState<MachineFilters>(EMPTY_FILTERS);
  const [syncResult, setSyncResult] = useState<TailnetSyncResult | null>(null);
  const [testResult, setTestResult] = useState<VpnActionResult | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [form, setForm] = useState<Server | "new" | null>(null);
  const [installing, setInstalling] = useState<Server | null>(null);
  const [preparing, setPreparing] = useState<Server | null>(null);
  const [importingCsv, setImportingCsv] = useState(false);
  const [deleting, setDeleting] = useState<Server | null>(null);
  const [groupDraft, setGroupDraft] = useState<{ name: string; clientId: string } | null>(null);
  const [deletingGroup, setDeletingGroup] = useState<HostGroup | null>(null);

  const machines = useMemo(() => servers.data ?? [], [servers.data]);
  const readinessById = useMemo(
    () => new Map((readiness.data?.entries ?? []).map((e) => [e.server_id, e])),
    [readiness.data],
  );
  const peers = useMemo(() => vpn.data?.peers ?? [], [vpn.data]);
  const nodesById = useMemo(() => new Map(peers.map((p) => [p.id, p])), [peers]);
  const groupsById = useMemo(() => new Map((groups.data ?? []).map((g) => [g.id, g])), [groups.data]);

  const sections = useMemo(
    () => buildMachineSections(machines, readinessById, nodesById, filters),
    [machines, readinessById, nodesById, filters],
  );
  const unregistered = useMemo(
    () =>
      filters.path === "all" || filters.path === "unregistered"
        ? unregisteredDevices(machines, peers, filters.query)
        : [],
    [machines, peers, filters.path, filters.query],
  );
  const clients = useMemo(() => {
    const byId = new Map<string, string>();
    for (const m of machines) {
      if (m.darckware_client_id) byId.set(m.darckware_client_id, m.darckware_client_name ?? m.darckware_client_id);
    }
    return [...byId].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name));
  }, [machines]);

  const runSync = (importNodeIds: string[] = []) =>
    tailnetSync.mutate(importNodeIds, { onSuccess: (result) => setSyncResult(result) });

  const status = servers.isLoading || groups.isLoading ? "loading" : servers.isError || groups.isError ? "error" : "ready";

  return {
    status,
    isAdmin,
    canWrite: perm.can_write,
    canDelete: perm.can_delete,
    sections,
    unregistered,
    totals: countReadiness(machines.map((m) => m.id), readinessById),
    clients,
    groups: groups.data ?? [],
    groupsById,
    groupCounts: new Map((groups.data ?? []).map((g) => [g.id, countReadiness(g.server_ids, readinessById)])),
    filters,
    setFilter: (key, value) => setFilters((cur) => ({ ...cur, [key]: value })),
    tailnetAvailable: readiness.data?.tailnet_available ?? true,
    acceptRoutes: vpn.data?.server.posture?.accept_routes ?? null,
    sshCheckedAt: readiness.data?.ssh_checked_at ?? null,
    probing: readiness.forceProbe.isPending,
    probeNow: () => readiness.forceProbe.mutate(),
    syncing: tailnetSync.isPending && tailnetSync.variables?.length === 0,
    sync: () => runSync(),
    syncResult,
    syncError: tailnetSync.error?.message ?? null,
    registering: tailnetSync.isPending && tailnetSync.variables?.length === 1 ? tailnetSync.variables[0] : null,
    register: (nodeId) => runSync([nodeId]),
    testing: vpnAction.isPending ? vpnAction.variables?.node ?? null : null,
    testNode: (nodeId) => {
      setTestResult(null);
      vpnAction.mutate({ node: nodeId, action: "test" }, { onSuccess: setTestResult });
    },
    testResult,
    togglingAccess: toggle.isPending,
    toggleAccess: (machine) => toggle.mutate(machine.id, { onSuccess: () => readiness.forceProbe.mutate() }),
    expandedId,
    toggleExpanded: (id) => setExpandedId((cur) => (cur === id ? null : id)),
    form,
    openForm: setForm,
    closeForm: () => setForm(null),
    installing,
    closeInstall: () => setInstalling(null),
    preparing,
    closePrepare: () => setPreparing(null),
    configure: (machine) => (machine.kind === "workstation" ? setPreparing(machine) : setInstalling(machine)),
    importingCsv,
    setImportingCsv,
    deleting,
    askDelete: (machine) => {
      deleteServer.reset();
      setDeleting(machine);
    },
    cancelDelete: () => setDeleting(null),
    confirmDelete: () => {
      if (!deleting) return;
      deleteServer.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
    },
    removing: deleteServer.isPending,
    groupDraft,
    startGroup: () => {
      createGroup.reset();
      setGroupDraft({ name: "", clientId: "" });
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
