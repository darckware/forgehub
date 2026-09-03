import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";


export type VpnNodeRole = "local" | "remote";
export type VpnAction = "connect" | "disconnect" | "restart" | "test";
export type VpnNodeState = "online" | "offline" | "needs_login" | "unavailable";
export type VpnPathKind = "direct" | "derp" | "idle" | "unavailable";

export interface VpnNode {
  role: VpnNodeRole;
  hostname: string | null;
  tailscale_ipv4: string | null;
  state: VpnNodeState;
  online: boolean;
  active: boolean;
  last_seen: string | null;
  rx_bytes: number;
  tx_bytes: number;
  daemon_state: string;
  posture: {
    accept_dns: boolean;
    accept_routes: boolean;
    advertise_exit_node: boolean;
    tailscale_ssh: boolean;
    exit_node: boolean;
    restricted: boolean;
  } | null;
}

export interface VpnStatus {
  independent_from_cloudflare: true;
  backend_state: string;
  nodes: VpnNode[];
  connection: {
    kind: VpnPathKind;
    relay: string | null;
    latency_ms: number | null;
  };
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
  target: VpnNodeRole;
  action: VpnAction;
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
}

export const vpnKeys = {
  status: ["vpn", "status"] as const,
  operations: ["vpn", "operations"] as const,
};

export function vpnActionPath(node: VpnNodeRole): string {
  return `/api/v1/vpn/nodes/${node}/actions`;
}

export function useVpnStatus() {
  return useQuery<VpnStatus>({
    queryKey: vpnKeys.status,
    queryFn: () => apiClient.get("/api/v1/vpn/status"),
    refetchInterval: () => (document.visibilityState === "visible" ? 10_000 : false),
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
  return useMutation<VpnActionResult, Error, { node: VpnNodeRole; action: VpnAction }>({
    mutationFn: ({ node, action }) => apiClient.post(vpnActionPath(node), { action }),
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: vpnKeys.status }),
        queryClient.invalidateQueries({ queryKey: vpnKeys.operations }),
      ]);
    },
  });
}
