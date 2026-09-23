import { describe, expect, it } from "vitest";
import { restoreWorkspaceState, WORKSPACE_STORAGE_KEYS } from "./workspaceState";

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
