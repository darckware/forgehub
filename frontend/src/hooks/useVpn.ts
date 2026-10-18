import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";

/**
 * Remote Access (formerly "VPN", 2026-10-15). The tailnet is read from the
 * VPS's own point of view: `server` is this node and `peers` every device it
 * can reach. Actions address "self" or a peer's stable Tailscale ID -- the
 * backend resolves the address from a fresh read, never from the client.
 */
export type VpnAction = "restart" | "test";
export type VpnNodeState = "online" | "offline" | "needs_login" | "unavailable";
export type VpnPathKind = "direct" | "derp" | "idle" | "unavailable";

export interface VpnPosture {
  accept_dns: boolean;
  accept_routes: boolean;
  advertise_exit_node: boolean;
  tailscale_ssh: boolean;
  exit_node: boolean;
  restricted: boolean;
}

export interface VpnNode {
  id: string;
  name: string | null;
  hostname: string | null;
  dns_name: string | null;
  os: string | null;
  tags: string[];
  tailscale_ipv4: string | null;
  /** Subnets this node routes that the VPS can see (approved + allowed by its ACL). */
  subnet_routes?: string[];
  state: VpnNodeState;
  online: boolean;
  active: boolean;
  last_seen: string | null;
  key_expiry: string | null;
  rx_bytes: number;
  tx_bytes: number;
  connection: { kind: VpnPathKind; relay: string | null } | null;
  daemon_state: string | null;
  posture: VpnPosture | null;
}

export interface VpnStatus {
  backend_state: string;
  server: VpnNode;
  peers: VpnNode[];
  checked_at: string;
  source_error: string | null;
  sources: Array<{
    name: "status" | "systemd" | "preferences";
    status: "fresh" | "unavailable";
    checked_at: string;
    error_code: string | null;
  }>;
}

export interface VpnOperation {
  id: string;
  actor_username: string | null;
  target: string;
  target_name: string | null;
  action: string;
  status: "running" | "succeeded" | "failed";
  result_code: string | null;
  summary: string | null;
  started_at: string;
  completed_at: string | null;
  created_at: string;
}

export interface VpnActionResult {
  success: boolean;
  code: string;
  summary: string;
  operation_id: string;
  target_name: string | null;
  latency_ms: number | null;
  path: "direct" | "derp" | null;
}

export const SELF_NODE = "self";

export const vpnKeys = {
  status: ["vpn", "status"] as const,
  operations: ["vpn", "operations"] as const,
};

export function vpnActionPath(node: string): string {
  return `/api/v1/vpn/nodes/${encodeURIComponent(node)}/actions`;
}

/** Tailscale tags are `tag:<name>`; the page groups and labels by `<name>`. */
export function tagLabel(tag: string): string {
  return tag.startsWith("tag:") ? tag.slice(4) : tag;
}

export function useVpnStatus() {
  return useQuery<VpnStatus>({
    queryKey: vpnKeys.status,
    queryFn: () => apiClient.get("/api/v1/vpn/status"),
    refetchInterval: () => (document.visibilityState === "visible" ? 15_000 : false),
    retry: false,
  });
}

export function useVpnOperations() {
  return useQuery<{ operations: VpnOperation[]; limit: number }>({
    queryKey: vpnKeys.operations,
    queryFn: () => apiClient.get("/api/v1/vpn/operations", { params: { limit: 25 } }),
    refetchInterval: () => (document.visibilityState === "visible" ? 25_000 : false),
    retry: false,
  });
}

export function useVpnAction() {
  const queryClient = useQueryClient();
  return useMutation<VpnActionResult, Error, { node: string; action: VpnAction }>({
    mutationFn: ({ node, action }) => apiClient.post(vpnActionPath(node), { action }),
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: vpnKeys.status }),
        queryClient.invalidateQueries({ queryKey: vpnKeys.operations }),
      ]);
    },
  });
}

/** Tailscale policy file as recorded on the Remote Access page (the admin
 * console stays where it is applied), analyzed for the server -> client tags
 * SSH rule maintenance depends on. */
export interface TailnetPolicyAnalysis {
  client_tags: string[];
  tags_with_ssh: string[];
  missing_ssh: string[];
  snippet: string | null;
  style: string;
  warnings: string[];
  server_tag: string;
}

export interface TailnetPolicyVersion {
  id: string;
  note: string | null;
  saved_by: string;
  created_at: string;
}

export interface TailnetPolicy extends TailnetPolicyVersion {
  content: string;
  analysis: TailnetPolicyAnalysis | null;
  parse_error: string | null;
}

export interface TailnetPolicyState {
  current: TailnetPolicy | null;
  versions: TailnetPolicyVersion[];
}

export function useTailnetPolicy(versionId: string | null) {
  return useQuery<TailnetPolicyState>({
    queryKey: ["vpn", "policy", versionId],
    queryFn: () => apiClient.get(`/api/v1/vpn/policy${versionId ? `?version_id=${versionId}` : ""}`),
  });
}

export function useSaveTailnetPolicy() {
  const qc = useQueryClient();
  return useMutation<TailnetPolicy, Error, { content: string; note: string | null }>({
    mutationFn: (data) => apiClient.post("/api/v1/vpn/policy", data),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["vpn", "policy"] }),
  });
}
