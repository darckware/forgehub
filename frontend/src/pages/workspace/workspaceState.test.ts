import { describe, expect, it } from "vitest";
import { restoreWorkspaceState } from "./workspaceState";

function storage(values: Record<string, string>) {
  return { getItem: (key: string) => values[key] ?? null };
}

describe("restoreWorkspaceState", () => {
  it("falls back safely when persisted JSON has the wrong shape", () => {
    const restored = restoreWorkspaceState(storage({
      "forgehub-workspace-tabs": "null",
      "forgehub-workspace-view-mode": "obsolete-mode",
      "forgehub-workspace-active-tab": "missing",
    }));

    expect(restored).toEqual({ tabs: [], activeTabId: "", viewMode: "conversas", workingDir: undefined });
  });

  it("repairs a stale active tab and restores a valid working directory", () => {
    const restored = restoreWorkspaceState(storage({
      "forgehub-workspace-tabs": JSON.stringify([
        { kind: "terminal", id: "terminal-1", label: "bash", cwd: "/work/project" },
      ]),
      "forgehub-workspace-active-tab": "removed-tab",
      "forgehub-workspace-view-mode": "canais",
      "forgehub-workspace-working-dir": "/work/project",
    }));

    expect(restored.activeTabId).toBe("terminal-1");
    expect(restored.workingDir).toBe("/work/project");
    expect(restored.viewMode).toBe("canais");
  });

  it("rejects an invalid member without discarding valid JSON silently", () => {
    const restored = restoreWorkspaceState(storage({
      "forgehub-workspace-tabs": JSON.stringify([{ kind: "terminal", id: "", label: "bash" }]),
    }));

    expect(restored.tabs).toEqual([]);
  });

  it("restores the per-agent Telegram channel tab", () => {
    const restored = restoreWorkspaceState(storage({
      "forgehub-workspace-tabs": JSON.stringify([
        { kind: "telegram", id: "telegram-athos", agentId: "athos-id" },
      ]),
      "forgehub-workspace-active-tab": "telegram-athos",
    }));

    expect(restored.tabs[0]).toEqual({ kind: "telegram", id: "telegram-athos", agentId: "athos-id" });
    expect(restored.activeTabId).toBe("telegram-athos");
  });
});
