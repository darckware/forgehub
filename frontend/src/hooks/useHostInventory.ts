import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { Server } from "@/hooks/useServers";

/** Remote Access phase 2 (docs/architecture/REMOTE_MAINTENANCE_PLAN.md):
 * machine groups, tailnet sync and readiness. Machines themselves are the
 * `servers` rows (useServers.ts) -- a workstation is a row with
 * kind="workstation". */

export interface HostGroup {
  id: string;
  name: string;
  darckware_client_id: string | null;
  darckware_client_name: string | null;
  description: string | null;
  server_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface HostGroupInput {
  name?: string;
  darckware_client_id?: string | null;
  darckware_client_name?: string | null;
  description?: string | null;
  server_ids?: string[];
}

export type HostReadiness =
  | "ready"
  | "busy"
  | "offline"
  | "not_prepared"
  | "disabled"
  | "unknown";

/** The color (backend `classify_status`): what can be done with the machine.
 * complete = every channel its kind needs (workstation: SSH + RustDesk; server:
 * SSH); partial = online with one missing; not_prepared = no channel yet. */
export type HostStatus = "complete" | "partial" | "not_prepared" | "offline" | "disabled" | "unknown";

/** How the VPS reaches the machine's registered address (backend
 * `classify_access_path`): a Tailscale IP, a subnet routed by another node, or
 * nothing it can see. "unknown" = tailnet unreadable, never shown as "none". */
export type AccessPath = "tailscale" | "subnet" | "subnet_not_accepted" | "none" | "unknown";

export interface HostReadinessEntry {
  server_id: string;
  readiness: HostReadiness;
  status?: HostStatus;
  rustdesk_id?: string | null;
  tailnet_online: boolean | null;
  ssh: string | null;
  detail: string | null;
  access_path?: AccessPath;
  access_via_node_id?: string | null;
  access_via_name?: string | null;
  tailscale_ipv4?: string | null;
}

export interface HostReadinessResult {
  entries: HostReadinessEntry[];
  checked_at: string;
  tailnet_available: boolean;
  ssh_checked_at: string | null;
}

export interface TailnetSyncEntry {
  node_id: string;
  name: string | null;
  tailscale_ipv4: string | null;
  os: string | null;
  online: boolean;
  tags: string[];
  /** "available" = in the tailnet, not in the inventory, not imported. Only
   * an explicit import (import_node_ids) turns it into a workstation. */
  outcome: "created" | "updated" | "linked" | "unchanged" | "available";
  server_id: string | null;
  suggested_client_tag: string | null;
}

export interface TailnetSyncResult {
  entries: TailnetSyncEntry[];
  missing_server_ids: string[];
}

const GROUPS_KEY = ["host-groups"] as const;
const READINESS_KEY = ["servers", "readiness"] as const;

export function useHostGroups() {
  return useQuery<HostGroup[]>({
    queryKey: GROUPS_KEY,
    queryFn: () => apiClient.get("/api/v1/host-groups"),
    staleTime: 30_000,
  });
}

function useInvalidateInventory() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: GROUPS_KEY });
    void qc.invalidateQueries({ queryKey: ["servers"] });
  };
}

export function useCreateHostGroup() {
  const invalidate = useInvalidateInventory();
  return useMutation<HostGroup, Error, HostGroupInput>({
    mutationFn: (data) => apiClient.post("/api/v1/host-groups", data),
    onSuccess: invalidate,
  });
}

export function useUpdateHostGroup() {
  const invalidate = useInvalidateInventory();
  return useMutation<HostGroup, Error, { id: string; data: HostGroupInput }>({
    mutationFn: ({ id, data }) => apiClient.put(`/api/v1/host-groups/${id}`, data),
    onSuccess: invalidate,
  });
}

export function useDeleteHostGroup() {
  const invalidate = useInvalidateInventory();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/host-groups/${id}`),
    onSuccess: invalidate,
  });
}

export function useTailnetSync() {
  const invalidate = useInvalidateInventory();
  return useMutation<TailnetSyncResult, Error, string[] | void>({
    mutationFn: (importNodeIds) =>
      apiClient.post("/api/v1/servers/tailnet:sync", { import_node_ids: importNodeIds ?? [] }),
    onSuccess: invalidate,
  });
}

/** Polled every 30 s. The backend reads the tailnet on every call but keeps
 * the SSH probe for 5 minutes, so polling never turns into a login storm on
 * the stations. `refresh()` forces a new probe. */
export function useHostReadiness(enabled = true) {
  const qc = useQueryClient();
  const query = useQuery<HostReadinessResult>({
    queryKey: READINESS_KEY,
    queryFn: () => apiClient.get("/api/v1/servers/readiness"),
    refetchInterval: 30_000,
    enabled,
  });
  const forceProbe = useMutation<HostReadinessResult, Error, void>({
    mutationFn: () => apiClient.get("/api/v1/servers/readiness?refresh=true"),
    onSuccess: (data) => qc.setQueryData(READINESS_KEY, data),
  });
  return { ...query, forceProbe };
}

export interface ReadinessCounts {
  total: number;
  ready: number;
  offline: number;
  attention: number;
}

/** By color: "ready" = complete; "attention" = partial or not prepared (a
 * channel is missing). "unknown"/"disabled" count only toward the total. */
export function countReadiness(
  serverIds: string[],
  byId: Map<string, HostReadinessEntry>,
): ReadinessCounts {
  const counts: ReadinessCounts = { total: serverIds.length, ready: 0, offline: 0, attention: 0 };
  for (const id of serverIds) {
    const state = byId.get(id)?.status;
    if (state === "complete") counts.ready += 1;
    else if (state === "offline") counts.offline += 1;
    else if (state === "partial" || state === "not_prepared") counts.attention += 1;
  }
  return counts;
}

export interface ClientBucket {
  key: string;
  clientId: string | null;
  clientName: string | null;
  machines: Server[];
  groups: HostGroup[];
}

/** Workstations bucketed by client (no client last), each bucket with the
 * groups that belong to that client. Servers stay on the Servers page. */
export function bucketByClient(machines: Server[], groups: HostGroup[]): ClientBucket[] {
  const buckets = new Map<string, ClientBucket>();
  const keyOf = (clientId: string | null) => clientId ?? "none";
  const ensure = (clientId: string | null, clientName: string | null) => {
    const key = keyOf(clientId);
    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = { key, clientId, clientName, machines: [], groups: [] };
      buckets.set(key, bucket);
    }
    if (!bucket.clientName && clientName) bucket.clientName = clientName;
    return bucket;
  };
  for (const machine of machines) {
    if (machine.kind !== "workstation") continue;
    ensure(machine.darckware_client_id, machine.darckware_client_name).machines.push(machine);
  }
  for (const group of groups) {
    ensure(group.darckware_client_id, group.darckware_client_name).groups.push(group);
  }
  return [...buckets.values()].sort((a, b) => {
    if (a.clientId === null) return 1;
    if (b.clientId === null) return -1;
    return (a.clientName ?? "").localeCompare(b.clientName ?? "");
  });
}

export interface HostPreparation {
  server_id: string;
  os_family: string;
  language: "powershell" | "sh";
  /** mode "copy": the script to paste once through RustDesk. */
  script: string | null;
  public_key: string;
  key_created: boolean;
  key_path: string;
  login: string;
  /** mode "ssh": the execution running preparation -> key check -> lock admin. */
  execution_id: string | null;
}

export interface HostPreparationInput {
  serverId: string;
  mode: "copy" | "ssh";
  admin_user: string | null;
  admin_password: string | null;
  disable_admin: boolean;
}

/** Puts a station under the `darckware` login (password generated and kept in
 * ForgeVault). "ssh" logs in once as the client's administrator (password
 * never stored), checks the new login with the key, then -- only if that
 * worked -- disables the administrator. "copy" returns the script for RustDesk. */
export function usePrepareHost() {
  const qc = useQueryClient();
  return useMutation<HostPreparation, Error, HostPreparationInput>({
    mutationFn: ({ serverId, ...body }) => apiClient.post(`/api/v1/servers/${serverId}/preparation`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["servers"] });
      void qc.invalidateQueries({ queryKey: ["host-executions"] });
    },
  });
}

// --- Machine passwords and rotation ---------------------------------------

export interface LoginPassword {
  server_id: string;
  login: string;
  password: string;
}

/** Admin-only and audited on the backend: every reveal is recorded.
 * `kind`: the machine login's password, or RustDesk's (login = RustDesk ID). */
export function useRevealLoginPassword(kind: "login" | "rustdesk" = "login") {
  return useMutation<LoginPassword, Error, string>({
    mutationFn: (serverId) =>
      apiClient.get(`/api/v1/servers/${serverId}/${kind === "rustdesk" ? "rustdesk-password" : "login-password"}`),
  });
}

export type RotationKind = "login_password" | "ssh_key";

/** Rotation on demand: the darckware password (new version in ForgeVault,
 * applied, verified; previous restored on failure) or the SSH key (new one
 * installed and verified before the old one is removed). One execution. */
export function useRotateMachines() {
  const qc = useQueryClient();
  return useMutation<{ execution_id: string }, Error, { server_ids: string[]; kind: RotationKind }>({
    mutationFn: (body) => apiClient.post("/api/v1/servers/rotations", body),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["host-executions"] }),
  });
}
