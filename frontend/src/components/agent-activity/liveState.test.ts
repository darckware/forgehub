import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import type { ActivityLiveState } from "@/hooks/useAgentActivity";
import { describeLiveState, formatElapsed } from "./liveState";

// Echoes the key plus interpolation values so assertions don't depend on a locale.
const t = ((key: string, opts?: Record<string, unknown>) => {
  const vars = opts ? Object.entries(opts).filter(([k]) => k !== "defaultValue") : [];
  return vars.length ? `${key}(${vars.map(([k, v]) => `${k}=${v}`).join(",")})` : key;
}) as unknown as TFunction;

const NOW = Date.parse("2026-09-28T12:00:00Z");

function live(overrides: Partial<ActivityLiveState>): ActivityLiveState {
  return {
    state: "idle", since: null, source: "runtime", platform: null, counterpart_kind: null,
    counterpart_ref: null, model: null, tool_name: null, session_id: null, turn_id: null,
    last_event_at: null, reason: null, turns_last_hour: 0, tools_last_hour: 0,
    failures_last_hour: 0, pending_count: 0, ...overrides,
  };
}

describe("describeLiveState", () => {
  it("names the tool, elapsed time, counterpart and channel while executing", () => {
    const text = describeLiveState(
      live({ state: "executing", tool_name: "terminal", since: "2026-09-28T11:59:18Z",
             counterpart_kind: "owner", platform: "telegram" }),
      t, NOW,
    );
    expect(text.headline).toBe("live.state.executing(tool=terminal) · 42 s");
    expect(text.context).toBe("live.counterpart.owner · live.platform.telegram");
  });

  it("masks outside contacts and drops context once idle", () => {
    expect(
      describeLiveState(live({ state: "thinking", counterpart_kind: "human", counterpart_ref: "···1234" }), t, NOW).context,
    ).toBe("live.counterpart.human(ref=···1234)");
    const idle = describeLiveState(live({ since: "2026-09-28T10:00:00Z", platform: "telegram" }), t, NOW);
    expect(idle.headline).toBe("live.state.idleSince(time=2 h)");
    expect(idle.context).toBeNull();
  });
});

describe("formatElapsed", () => {
  it("uses compact units", () => {
    expect(formatElapsed("2026-09-28T11:55:00Z", NOW)).toBe("5 min");
    expect(formatElapsed("2026-09-25T12:00:00Z", NOW)).toBe("3 d");
    expect(formatElapsed(null, NOW)).toBeNull();
  });
});
