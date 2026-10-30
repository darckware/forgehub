import { useMemo } from "react";
import type {
  ActivityAgent,
  ActivityChannelHealth,
  AgentLiveSnapshot,
  AgentLiveSnapshotItem,
} from "@/hooks/useAgentActivity";

/**
 * The Agent Activity board (Plano Integrado A.1): every eligible agent of the registry.
 *
 * Who is on the board is decided by the backend (active registry entries; inactive and
 * retired agents are never sent), so this hook filters nothing by runtime: an external
 * executor (claude/codex/agy) with nothing running arrives as `idle` and stays on the
 * board -- before A.1 the page hid it until Messages ran it. Nothing here counts agents.
 *
 * It merges the slower read model (`GET /agent-activity`: identity, work, channel health)
 * with the newest stream/replay frame (live state), and turns each agent's channel health
 * into ready-to-render badges. A channel the agent doesn't have (`not_applicable`) yields
 * no badge, so a missing Telegram never reads as an agent being offline.
 */
export type AgentBoardStatus = "loading" | "error" | "empty" | "ready";

export type ChannelBadgeTone = "ok" | "warning" | "unknown";

export interface ChannelBadge {
  key: "telegram" | "gateway";
  value: string;
  tone: ChannelBadgeTone;
}

export interface AgentBoardViewModel {
  status: AgentBoardStatus;
  agents: ActivityAgent[];
  snapshotByAgent: Map<string, AgentLiveSnapshotItem>;
  channelBadgesByAgent: Map<string, ChannelBadge[]>;
}

const TONE: Record<string, ChannelBadgeTone> = {
  ok: "ok",
  unknown: "unknown",
  not_running: "warning",
  not_configured: "warning",
  down: "warning",
};

export function channelBadges(health: ActivityChannelHealth | null | undefined): ChannelBadge[] {
  if (!health) return [];
  const badges: ChannelBadge[] = [];
  for (const key of ["telegram", "gateway"] as const) {
    const value = health[key];
    if (value === "not_applicable") continue;
    badges.push({ key, value, tone: TONE[value] ?? "unknown" });
  }
  return badges;
}

export function useAgentBoardViewModel({
  agents,
  snapshot,
  isLoading,
  isError,
}: {
  agents: ActivityAgent[] | undefined;
  snapshot: AgentLiveSnapshot | null | undefined;
  isLoading: boolean;
  isError: boolean;
}): AgentBoardViewModel {
  const snapshotByAgent = useMemo(
    () => new Map<string, AgentLiveSnapshotItem>((snapshot?.agents ?? []).map((item) => [item.agent_id, item])),
    [snapshot],
  );
  // Live state from the newest frame wins over the read model's.
  const merged = useMemo<ActivityAgent[]>(
    () =>
      (agents ?? []).map((agent) =>
        snapshot ? { ...agent, live: snapshotByAgent.get(agent.id)?.live ?? null } : agent,
      ),
    [agents, snapshot, snapshotByAgent],
  );
  const channelBadgesByAgent = useMemo(
    () => new Map(merged.map((agent) => [agent.id, channelBadges(agent.channel_health)])),
    [merged],
  );
  const status: AgentBoardStatus = isLoading
    ? "loading"
    : isError
      ? "error"
      : merged.length === 0
        ? "empty"
        : "ready";
  return { status, agents: merged, snapshotByAgent, channelBadgesByAgent };
}
