import { describe, expect, it } from "vitest";
import { explorerServerFor, restoreWorkspaceState, serverHome, WORKSPACE_STORAGE_KEYS } from "./workspaceState";

describe("workspace explorer tab persistence", () => {
  it("restores an explorer tab with its last path", () => {
    const tabs = [{ kind: "explorer", id: "e1", label: "Explorer", path: "/root/project" }];
    const store: Record<string, string> = {
      [WORKSPACE_STORAGE_KEYS.tabs]: JSON.stringify(tabs),
      [WORKSPACE_STORAGE_KEYS.activeTab]: "e1",
    };
    const restored = restoreWorkspaceState({ getItem: (k) => store[k] ?? null });
    expect(restored.tabs).toEqual(tabs);
    expect(restored.activeTabId).toBe("e1");
  });
});

describe("explorer per machine", () => {
  const srv = { id: "s1", name: "srv-app05", home: "/home/deploy" };
  const tabs = [
    { kind: "terminal" as const, id: "bash", label: "bash01" },
    { kind: "terminal" as const, id: "ssh", label: "srv-app05", command: "ssh deploy@10.0.0.5", server: srv },
    { kind: "explorer" as const, id: "e1", label: "Explorer", path: "/root" },
    { kind: "chat" as const, id: "c1", agentId: "a1" },
  ];

  it("an SSH tab points the Explorer at its server; anything else at the VPS", () => {
    expect(explorerServerFor(tabs, "ssh")).toEqual(srv);
    expect(explorerServerFor(tabs, "bash")).toBeUndefined();
    expect(explorerServerFor(tabs, "c1")).toBeUndefined();
    expect(explorerServerFor(tabs, "e1")).toBe("stay");
  });

  it("restores SSH and Explorer tabs with their server", () => {
    const stored = [tabs[1], { kind: "explorer", id: "e2", label: "Explorer", path: "/home/deploy", server: srv }];
    const store: Record<string, string> = { [WORKSPACE_STORAGE_KEYS.tabs]: JSON.stringify(stored) };
    expect(restoreWorkspaceState({ getItem: (k) => store[k] ?? null }).tabs).toEqual(stored);
  });

  it("an Explorer on a server starts in its user's home", () => {
    expect(serverHome("root")).toBe("/root");
    expect(serverHome("deploy")).toBe("/home/deploy");
  });
});
