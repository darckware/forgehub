import { z } from "zod";

export const WORKSPACE_STORAGE_VERSION = 1;
export const WORKSPACE_STORAGE_KEYS = {
  version: "forgehub-workspace-state-version",
  tabs: "forgehub-workspace-tabs",
  activeTab: "forgehub-workspace-active-tab",
  viewMode: "forgehub-workspace-view-mode",
  workingDir: "forgehub-workspace-working-dir",
} as const;

export type WorkspaceViewMode = "conversas" | "canais";

export type WebAppTarget =
  | { mode: "product"; id: string }
  | { mode: "app"; id: string }
  | { mode: "url" };

export type WorkspaceTab =
  | {
      kind: "chat";
      id: string;
      agentId: string;
      historyCollapsed?: boolean;
      artifactsOpen?: boolean;
      composerText?: string;
      sessionId?: string;
    }
  | { kind: "terminal"; id: string; label: string; command?: string; cwd?: string }
  | { kind: "telegram"; id: string; agentId: string }
  | { kind: "web"; id: string; label: string; url: string; target?: WebAppTarget }
  | { kind: "explorer"; id: string; label: string; path: string };

const nonEmptyString = z.string().trim().min(1);
const webTargetSchema = z.discriminatedUnion("mode", [
  z.object({ mode: z.literal("product"), id: nonEmptyString }),
  z.object({ mode: z.literal("app"), id: nonEmptyString }),
  z.object({ mode: z.literal("url") }),
]);
const workspaceTabSchema = z.discriminatedUnion("kind", [
  z.object({
    kind: z.literal("chat"),
    id: nonEmptyString,
    agentId: nonEmptyString,
    historyCollapsed: z.boolean().optional(),
    artifactsOpen: z.boolean().optional(),
    composerText: z.string().optional(),
    sessionId: nonEmptyString.optional(),
  }),
  z.object({
    kind: z.literal("terminal"),
    id: nonEmptyString,
    label: nonEmptyString,
    command: z.string().optional(),
    cwd: nonEmptyString.optional(),
  }),
  z.object({
    kind: z.literal("telegram"),
    id: nonEmptyString,
    agentId: nonEmptyString,
  }),
  z.object({
    kind: z.literal("web"),
    id: nonEmptyString,
    label: nonEmptyString,
    url: nonEmptyString,
    target: webTargetSchema.optional(),
  }),
  z.object({
    kind: z.literal("explorer"),
    id: nonEmptyString,
    label: nonEmptyString,
    path: nonEmptyString,
  }),
]);
const workspaceTabsSchema = z.array(workspaceTabSchema);

interface StorageReader {
  getItem(key: string): string | null;
}

export interface RestoredWorkspaceState {
  tabs: WorkspaceTab[];
  activeTabId: string;
  viewMode: WorkspaceViewMode;
  workingDir?: string;
}

export function repairActiveTabId(tabs: WorkspaceTab[], requestedId: string): string {
  return tabs.some((tab) => tab.id === requestedId) ? requestedId : tabs[0]?.id ?? "";
}

export function restoreWorkspaceState(storage: StorageReader): RestoredWorkspaceState {
  const storedMode = storage.getItem(WORKSPACE_STORAGE_KEYS.viewMode);
  const viewMode: WorkspaceViewMode = storedMode === "canais" || storedMode === "conversas" ? storedMode : "conversas";

  let tabs: WorkspaceTab[] = [];
  const rawTabs = storage.getItem(WORKSPACE_STORAGE_KEYS.tabs);
  if (rawTabs) {
    try {
      const parsed = workspaceTabsSchema.safeParse(JSON.parse(rawTabs));
      if (parsed.success) tabs = parsed.data;
    } catch {
      // A corrupt local cache must never prevent the Workspace from loading.
    }
  }

  const requestedActiveTab = storage.getItem(WORKSPACE_STORAGE_KEYS.activeTab) ?? "";
  const storedWorkingDir = storage.getItem(WORKSPACE_STORAGE_KEYS.workingDir)?.trim();
  return {
    tabs,
    activeTabId: repairActiveTabId(tabs, requestedActiveTab),
    viewMode,
    workingDir: storedWorkingDir || undefined,
  };
}
