import { useMemo, useState } from "react";

import {
  SELF_NODE,
  useVpnAction,
  useVpnOperations,
  useVpnStatus,
  type VpnActionResult,
  type VpnNode,
  type VpnOperation,
  type VpnStatus,
} from "@/hooks/useVpn";

/**
 * Remote Access › Tailscale network: diagnostics only since phase 4 of
 * docs/architecture/REMOTE_ACCESS_SERVERS_UNIFICATION_PLAN.md -- the VPS's own
 * node, the subnet routers the VPS sees, totals and the operation history.
 * The device list moved into Machines (useMachinesViewModel), where a
 * registered device and its inventory row are one line.
 */
export type RemoteAccessStatus = "loading" | "error" | "ready";

export interface RemoteAccessViewModel {
  status: RemoteAccessStatus;
  data: VpnStatus | undefined;
  refreshing: boolean;
  degraded: boolean;
  refresh: () => void;

  totals: { devices: number; online: number; offline: number };
  /** Peers announcing approved subnet routes, by name. */
  routers: VpnNode[];
  /** Whether the VPS accepts subnet routes; null when the posture is unknown. */
  acceptRoutes: boolean | null;

  operations: VpnOperation[];
  operationsLoading: boolean;

  confirmingRestart: boolean;
  askRestart: () => void;
  cancelRestart: () => void;
  confirmRestart: () => void;
  restarting: boolean;
  actionError: string | null;
  lastResult: VpnActionResult | null;
}

export function useRemoteAccessViewModel(): RemoteAccessViewModel {
  const statusQuery = useVpnStatus();
  const operationsQuery = useVpnOperations();
  const action = useVpnAction();
  const [confirmingRestart, setConfirmingRestart] = useState(false);
  const [lastResult, setLastResult] = useState<VpnActionResult | null>(null);

  const peers = useMemo(() => statusQuery.data?.peers ?? [], [statusQuery.data]);

  const routers = useMemo(
    () =>
      peers
        .filter((p) => (p.subnet_routes ?? []).length > 0)
        .sort((a, b) => (a.name ?? a.hostname ?? "").localeCompare(b.name ?? b.hostname ?? "")),
    [peers],
  );

  const totals = useMemo(() => {
    const online = peers.filter((device) => device.online).length;
    return { devices: peers.length, online, offline: peers.length - online };
  }, [peers]);

  const data = statusQuery.data;
  const status: RemoteAccessStatus = statusQuery.isLoading ? "loading" : statusQuery.isError || !data ? "error" : "ready";
  const pendingNode = action.isPending ? action.variables?.node ?? null : null;

  const run = (node: string, kind: "restart", onDone?: () => void) => {
    setLastResult(null);
    action.mutate(
      { node, action: kind },
      {
        onSuccess: (result) => {
          setLastResult(result);
          onDone?.();
        },
      },
    );
  };

  return {
    status,
    data,
    refreshing: statusQuery.isFetching,
    degraded: Boolean(data && (data.source_error || data.sources.some((source) => source.status === "unavailable"))),
    refresh: () => void statusQuery.refetch(),

    totals,
    routers,
    acceptRoutes: data?.server.posture?.accept_routes ?? null,

    operations: operationsQuery.data?.operations ?? [],
    operationsLoading: operationsQuery.isLoading,

    confirmingRestart,
    askRestart: () => {
      action.reset();
      setConfirmingRestart(true);
    },
    cancelRestart: () => setConfirmingRestart(false),
    confirmRestart: () => run(SELF_NODE, "restart", () => setConfirmingRestart(false)),
    restarting: pendingNode === SELF_NODE,
    actionError: action.error?.message ?? null,
    lastResult,
  };
}
