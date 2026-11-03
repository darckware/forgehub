import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ActivityAgent, AgentLiveSnapshot } from "@/hooks/useAgentActivity";
import { channelBadges, useAgentBoardViewModel } from "@/hooks/useAgentBoardViewModel";

const agent = (id: string, runtime_type: string, extra: Partial<ActivityAgent> = {}) =>
  ({ id, name: id, runtime_type, live: null, ...extra }) as unknown as ActivityAgent;

describe("useAgentBoardViewModel (A.1)", () => {
  it("keeps every agent the backend sends, external runtimes included", () => {
    const agents = [agent("a", "hermes"), agent("b", "codex"), agent("c", "claude"), agent("d", "agy")];
    const { result } = renderHook(() =>
      useAgentBoardViewModel({ agents, snapshot: null, isLoading: false, isError: false }),
    );
    expect(result.current.status).toBe("ready");
    expect(result.current.agents.map((item) => item.id)).toEqual(["a", "b", "c", "d"]);
  });

  it("takes live state from the stream frame", () => {
    const snapshot = {
      agents: [{ agent_id: "b", live: { state: "idle", source: "messages" }, spark: [], tokens_last_hour: 0, cost_today: 0 }],
    } as unknown as AgentLiveSnapshot;
    const { result } = renderHook(() =>
      useAgentBoardViewModel({ agents: [agent("a", "hermes"), agent("b", "codex")], snapshot, isLoading: false, isError: false }),
    );
    expect(result.current.agents.find((item) => item.id === "b")?.live?.state).toBe("idle");
    expect(result.current.agents.find((item) => item.id === "a")?.live).toBeNull();
  });

  it("reports loading, error and empty", () => {
    const render = (props: { isLoading: boolean; isError: boolean; agents?: ActivityAgent[] }) =>
      renderHook(() => useAgentBoardViewModel({ snapshot: null, agents: props.agents, ...props })).result.current.status;
    expect(render({ isLoading: true, isError: false })).toBe("loading");
    expect(render({ isLoading: false, isError: true })).toBe("error");
    expect(render({ isLoading: false, isError: false, agents: [] })).toBe("empty");
  });
});

describe("channelBadges", () => {
  it("hides channels the agent doesn't have and keeps unknown neutral", () => {
    expect(channelBadges({ telegram: "not_applicable", gateway: "not_applicable" })).toEqual([]);
    expect(channelBadges(null)).toEqual([]);
    expect(channelBadges({ telegram: "unknown", gateway: "down" })).toEqual([
      { key: "telegram", value: "unknown", tone: "unknown" },
      { key: "gateway", value: "down", tone: "warning" },
    ]);
    expect(channelBadges({ telegram: "ok", gateway: "ok" }).map((badge) => badge.tone)).toEqual(["ok", "ok"]);
  });
});
