import { useMemo, useState } from "react";

import {
  SELF_NODE,
  tagLabel,
  useVpnAction,
  useVpnOperations,
  useVpnStatus,
  type VpnActionResult,
  type VpnNode,
  type VpnOperation,
  type VpnStatus,
} from "@/hooks/useVpn";

export type RemoteAccessStatus = "loading" | "error" | "ready";
export type DeviceStateFilter = "all" | "online" | "offline";

/** "" is the bucket for untagged devices. */
export interface DeviceGroup {
  tag: string;
  label: string;
  devices: VpnNode[];
  online: number;
}

export interface RemoteAccessViewModel {
  status: RemoteAccessStatus;
  data: VpnStatus | undefined;
  refreshing: boolean;
  degraded: boolean;
  refresh: () => void;

  totals: { devices: number; online: number; offline: number };
  groups: DeviceGroup[];
  groupOptions: Array<{ tag: string; label: string }>;
  query: string;
  setQuery: (value: string) => void;
  groupFilter: string;
  setGroupFilter: (value: string) => void;
  stateFilter: DeviceStateFilter;
  setStateFilter: (value: DeviceStateFilter) => void;

  operations: VpnOperation[];
  operationsLoading: boolean;

  /** Peer id currently being tested, if any. */
  testingId: string | null;
  testDevice: (device: VpnNode) => void;
  confirmingRestart: boolean;
  askRestart: () => void;
  cancelRestart: () => void;
  confirmRestart: () => void;
  restarting: boolean;
  actionError: string | null;
  lastResult: VpnActionResult | null;
}

/** A device is grouped under its first tag -- in this tailnet the tag names
 * the client and role (`gatling-users`, `semed-srv`), so listing it once
 * avoids the same machine showing up in two places. */
function groupKey(device: VpnNode): string {
  return device.tags[0] ?? "";
}

function matches(device: VpnNode, query: string): boolean {
  if (!query) return true;
  const haystack = [device.name, device.hostname, device.tailscale_ipv4, device.os, ...device.tags.map(tagLabel)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

export function useRemoteAccessViewModel(): RemoteAccessViewModel {
  const statusQuery = useVpnStatus();
  const operationsQuery = useVpnOperations();
  const action = useVpnAction();
  const [query, setQuery] = useState("");
  const [groupFilter, setGroupFilter] = useState("all");
  const [stateFilter, setStateFilter] = useState<DeviceStateFilter>("all");
  const [confirmingRestart, setConfirmingRestart] = useState(false);
  const [lastResult, setLastResult] = useState<VpnActionResult | null>(null);

  const peers = useMemo(() => statusQuery.data?.peers ?? [], [statusQuery.data]);

  const groupOptions = useMemo(() => {
    const tags = new Set(peers.map(groupKey));
    return [...tags]
      .sort((a, b) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)))
      .map((tag) => ({ tag, label: tag ? tagLabel(tag) : "" }));
  }, [peers]);

  const groups = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const byTag = new Map<string, VpnNode[]>();
    for (const device of peers) {
      const tag = groupKey(device);
      if (groupFilter !== "all" && tag !== groupFilter) continue;
      if (stateFilter === "online" && !device.online) continue;
      if (stateFilter === "offline" && device.online) continue;
      if (!matches(device, needle)) continue;
      byTag.set(tag, [...(byTag.get(tag) ?? []), device]);
    }
    return groupOptions
      .filter((option) => byTag.has(option.tag))
      .map((option) => {
        const devices = byTag.get(option.tag) ?? [];
        return { tag: option.tag, label: option.label, devices, online: devices.filter((d) => d.online).length };
      });
  }, [peers, groupOptions, query, groupFilter, stateFilter]);

  const totals = useMemo(() => {
    const online = peers.filter((device) => device.online).length;
    return { devices: peers.length, online, offline: peers.length - online };
  }, [peers]);

  const data = statusQuery.data;
  const status: RemoteAccessStatus = statusQuery.isLoading ? "loading" : statusQuery.isError || !data ? "error" : "ready";
  const pendingNode = action.isPending ? action.variables?.node ?? null : null;

  const run = (node: string, kind: "restart" | "test", onDone?: () => void) => {
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
    groups,
    groupOptions,
    query,
    setQuery,
    groupFilter,
    setGroupFilter,
    stateFilter,
    setStateFilter,

    operations: operationsQuery.data?.operations ?? [],
    operationsLoading: operationsQuery.isLoading,

    testingId: pendingNode && pendingNode !== SELF_NODE ? pendingNode : null,
    testDevice: (device) => run(device.id, "test"),
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
