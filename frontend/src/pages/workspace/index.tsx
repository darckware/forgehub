import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Bot,
  Check,
  ChevronDown,
  Feather,
  Globe2,
  Loader2,
  MessageSquare,
  History,
  KeyRound,
  Package,
  Power,
  PowerOff,
  Send,
  SquareTerminal,
  Trash2,
  Unplug,
  Upload,
  Users,
  X,
} from "lucide-react";
import claudeIcon from "@lobehub/icons-static-png/dark/claude-color.png";
import codexIcon from "@lobehub/icons-static-png/dark/codex-color.png";
import antigravityIcon from "@lobehub/icons-static-png/dark/antigravity-color.png";
import opencodeIcon from "@lobehub/icons-static-png/light/opencode.png";
import hermesIcon from "@lobehub/icons-static-png/light/hermesagent.png";
import openclawIcon from "@lobehub/icons-static-png/dark/openclaw-color.png";
import piIcon from "@/assets/icons/pi.svg";
import { Button } from "@/components/ui/button";
import { TerminalPane } from "@/components/TerminalPane";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { apiClient } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  useServers,
  useServerStatusProbe,
  buildSshCommand,
  type Server,
  type ServerCheckStatus,
} from "@/hooks/useServers";
import { fetchOpenclawDashboardUrl } from "@/hooks/useTerminalBrowse";
import { useClickOutside } from "@/hooks/useClickOutside";
import { ChatPane, clearChatTabStaging } from "@/components/chat/ChatPane";
import { ChannelPane } from "@/components/channel/ChannelPane";
import { TelegramPane } from "@/components/TelegramPane";
import { useAgents } from "@/hooks/useAgent";
import { WebAppPane } from "@/components/WebAppPane";
import { useAssistantContext } from "@/hooks/useAssistant";
import { useAssistantStore } from "@/store/assistantStore";
import { useProducts } from "@/hooks/useProduct";
import {
  WORKSPACE_STORAGE_KEYS,
  WORKSPACE_STORAGE_VERSION,
  repairActiveTabId,
  restoreWorkspaceState,
  type WebAppTarget,
  type WorkspaceTab,
  type WorkspaceViewMode,
} from "./workspaceState";

// Tabs/active-tab are persisted (not just in-memory state) so that
// navigating to another page and back to Workspace recreates the same tabs
// with the same ids -- TerminalPane then reconnects using those ids as its
// tmux session name, re-attaching to the still-running session instead of
// losing it. See TerminalPane.tsx and host-bridge/app.py's terminal_ws.
const DEFAULT_APP_URL = "http://localhost:5174";
// Top-level Workspace mode: "conversas" is the existing tab system below,
// completely unchanged; "canais" renders the new multi-agent ChatChannel
// room instead. Deliberately NOT another WorkspaceTab kind -- ChatChannel
// has its own participants/sidebar model (N agents + the human, shared
// context), not a single agentId per tab, so folding it into the existing
// tab persistence/reorder machinery would force an awkward shape onto both.
type Launcher = { label: string; command: string; icon?: string; iconBg?: string; hasWebPanel?: boolean };

// Used only if fetchOpenclawDashboardUrl fails (bridge unreachable) -- same
// URL host-bridge itself falls back to when it can't read the gateway
// token, just without the auth fragment (the dashboard then prompts for it).
const OPENCLAW_DASHBOARD_FALLBACK_URL = "http://127.0.0.1:28340/";

// "CLI" -- AI coding-assistant CLIs you'd run ad-hoc against this checkout.
const CLI_LAUNCHERS: Launcher[] = [
  { label: "Claude", command: "claude", icon: claudeIcon },
  { label: "Codex", command: "codex", icon: codexIcon },
  { label: "Antigravity", command: "agy", icon: antigravityIcon },
  // pi's mark is a plain white glyph and opencode's is a plain black glyph
  // (neither has a built-in background) -- unlike the color logos above,
  // which read fine on both a light and a dark page theme on their own,
  // these need a fixed backing chip so they don't wash out into whichever
  // theme is active (a black glyph on the dark-mode toolbar is otherwise
  // invisible, same reasoning as hermes below).
  { label: "PI", command: "pi", icon: piIcon, iconBg: "bg-black" },
  { label: "Opencode", command: "opencode", icon: opencodeIcon, iconBg: "bg-white" },
];

// "Runtimes" -- agent orchestration platforms (as opposed to one-shot
// coding CLIs above).
const RUNTIME_LAUNCHERS: Launcher[] = [
  // openclaw-color is a full-color mark (like the CLI logos above), so it
  // needs no backing chip; hermes' mark is a plain black glyph, same
  // dark-mode-invisibility issue as opencode's above.
  //
  // OpenClaw also runs its own web Control UI (`openclaw dashboard`, same
  // gateway port as the TUI's websocket) -- `hasWebPanel` below opens it in
  // a new external browser tab (Marcelo, 2026-07-29: operator's browser
  // runs on the same host as OpenClaw, so `127.0.0.1` resolves fine there;
  // no longer routed through the internal Workspace Browser). Never
  // embedded as an iframe either -- it sends `X-Frame-Options: DENY`.
  // A second entry point alongside the TUI terminal tab every other
  // launcher opens. See LauncherMenu.
  { label: "OpenClaw", command: "openclaw", icon: openclawIcon, hasWebPanel: true },
  { label: "Hermes", command: "hermes", icon: hermesIcon, iconBg: "bg-white" },
];

function LauncherIcon({ icon, iconBg }: { icon?: string; iconBg?: string }) {
  if (!icon) return <Feather className="h-4 w-4" />;
  if (!iconBg) return <img src={icon} alt="" className="h-4 w-4" />;
  return (
    <span className={cn("flex h-4 w-4 items-center justify-center rounded-sm", iconBg)}>
      <img src={icon} alt="" className="h-3 w-3" />
    </span>
  );
}

function WorkspaceTabItem({
  tab,
  label,
  icon,
  active,
  onSelect,
  onClose,
  onTerminate,
  onKeyDown,
  onDragStart,
  onDrop,
  closeLabel,
  terminateLabel,
}: {
  tab: WorkspaceTab;
  label: string;
  icon: ReactNode;
  active: boolean;
  onSelect: () => void;
  onClose: () => void;
  onTerminate?: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  onDragStart: () => void;
  onDrop: () => void;
  closeLabel: string;
  terminateLabel?: string;
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
      className={cn(
        "group flex shrink-0 items-center rounded-md text-sm",
        active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
      )}
    >
      <button
        type="button"
        role="tab"
        id={`workspace-tab-${tab.id}`}
        aria-controls={`workspace-panel-${tab.id}`}
        aria-selected={active}
        tabIndex={active ? 0 : -1}
        className="flex cursor-grab items-center gap-1.5 py-1 pl-3 active:cursor-grabbing"
        onClick={onSelect}
        onKeyDown={onKeyDown}
      >
        {icon}
        <span>{label}</span>
      </button>
      {onTerminate && (
        <button
          type="button"
          aria-label={terminateLabel}
          title={terminateLabel}
          className="ml-1 opacity-60 hover:text-destructive sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
          onClick={onTerminate}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
      <button
        type="button"
        aria-label={closeLabel}
        title={closeLabel}
        className="ml-1 py-1 pr-2 opacity-60 hover:text-foreground sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100"
        onClick={onClose}
      >
        {tab.kind === "terminal" ? <Unplug className="h-3 w-3" /> : <X className="h-3 w-3" />}
      </button>
    </div>
  );
}

/** The three answers the SSH menu has to keep apart, each with its own icon
 * (2026-08-14, Marcelo: "no dropdown eu preciso saber o status da chave, foi
 * instalado sim ou não... desligado... e online"):
 *
 *   key    -- is there a working key? green when the probe authenticated with
 *             one, or (before any probe) when the row has an identity on file;
 *             red when the probe reached the host and key auth failed.
 *   power  -- is ForgeHub allowed to use this server at all? Green/red, the
 *             access switch, independent of whether the machine is up.
 *   dot    -- does it answer right now? Green online, red offline.
 *
 * They stay separate because they fail separately: a parked server may be
 * perfectly healthy, and an online one may have no key. Anything not yet
 * probed renders hollow rather than in a colour claiming a state nobody
 * checked.
 */
function SshRowSignals({
  server,
  checking,
  status,
}: {
  server: Server;
  checking: boolean;
  status?: ServerCheckStatus;
}) {
  // The probe is the authority when it has spoken; before that, a configured
  // identity file (or a recorded public key) is the best available answer.
  const keyRejected = status === "no_key" || status === "auth_failed" || status === "key_missing";
  const keyOk = status === "online" ? true : keyRejected ? false : Boolean(server.ssh_key_path || server.public_key);
  const keyKnown = status === "online" || keyRejected || (!status && Boolean(server.ssh_key_path || server.public_key));
  const reachable = status === "online" || status === "auth_failed" || status === "no_key";
  const unreachable = status === "offline" || status === "unreachable";

  return (
    <span className="flex shrink-0 items-center gap-1">
      <KeyRound
        className={cn(
          "h-3 w-3",
          !keyKnown ? "text-muted-foreground/40" : keyOk ? "text-emerald-500" : "text-red-500",
        )}
      />
      {server.access_enabled ? (
        <Power className="h-3 w-3 text-emerald-500" />
      ) : (
        <PowerOff className="h-3 w-3 text-red-500" />
      )}
      {checking ? (
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
      ) : !status || status === "disabled" || status === "probe_error" || status === "key_missing" ? (
        <span className="h-2 w-2 rounded-full border border-muted-foreground/50" />
      ) : (
        <span
          className={cn("h-2 w-2 rounded-full", reachable ? "bg-emerald-500" : unreachable ? "bg-red-500" : "border border-muted-foreground/50")}
        />
      )}
    </span>
  );
}

/** "SSH" launcher: icon+label button that drops down the registered server
 * inventory (name + IP, from the Servers page/domain) -- picking one opens
 * a new terminal tab pre-filled with `ssh [-i key] [-p port] user@ip`
 * (see useServers' buildSshCommand), reusing the same openTerminalTab flow
 * as the CLI/Runtime launchers above. */
function SshLauncherMenu({ onLaunch }: { onLaunch: (label: string, command: string) => void }) {
  const { t } = useTranslation("workspace");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);
  const { data: servers } = useServers();
  const probe = useServerStatusProbe();
  const lastProbeRef = useRef<{ at: number; signature: string } | null>(null);

  // Probe on first open, not on mount: this menu sits in the toolbar of every
  // Workspace visit, and each probe is a real SSH round trip on the host --
  // paying for twelve of them before anyone asks to connect would be rude to
  // both the browser and the servers. Parked rows are skipped by checkAll.
  useEffect(() => {
    if (!open || !servers || servers.length === 0) return;
    const signature = servers.map((server) => `${server.id}:${server.access_enabled}`).join("|");
    const last = lastProbeRef.current;
    if (last && last.signature === signature && Date.now() - last.at < 30_000) return;
    lastProbeRef.current = { at: Date.now(), signature };
    probe.checkAll(servers);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, servers]);

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="outline"
        size="sm"
        className="h-8 shrink-0 gap-1.5 px-2"
        title={t("toolbar.connectSsh")}
        aria-label={t("toolbar.ssh")}
        onClick={() => setOpen((v) => !v)}
      >
        <KeyRound className="h-3.5 w-3.5" />
        {t("toolbar.ssh")}
        <ChevronDown className="h-3 w-3 opacity-60" />
      </Button>
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md">
          {(servers ?? []).length === 0 && (
            <p className="px-3 py-3 text-xs italic text-muted-foreground">
              {t("toolbar.noServersRegistered")}
            </p>
          )}
          {(servers ?? []).map((s) => {
            const result = probe.statuses[s.id];
            const checking = probe.checkingIds.has(s.id);
            // A parked server is not offered at all: the row is still listed,
            // so it is clear the server exists and is simply switched off,
            // rather than silently missing from the menu.
            const parked = !s.access_enabled;
            return (
              <button
                key={s.id}
                type="button"
                disabled={parked}
                className="flex w-full flex-col items-start px-3 py-1.5 text-left hover:bg-accent hover:text-accent-foreground disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
                title={parked ? t("toolbar.sshAccessOff") : result?.detail}
                onClick={() => {
                  onLaunch(s.name, buildSshCommand(s));
                  setOpen(false);
                }}
              >
                <span className="flex w-full items-center gap-1.5">
                  <SshRowSignals server={s} checking={checking} status={result?.status} />
                  <span className="text-sm font-medium">{s.name}</span>
                  <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground">
                    {parked
                      ? t("toolbar.sshOff")
                      : checking
                        ? "…"
                        : result?.status === "online"
                          ? t("toolbar.sshOnline")
                          : result?.status === "auth_failed" || result?.status === "no_key" || result?.status === "key_missing"
                            ? t("toolbar.sshKeyProblem")
                            : result?.status === "probe_error"
                              ? t("toolbar.sshCheckFailed")
                          : result
                            ? t("toolbar.sshOffline")
                            : ""}
                  </span>
                </span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {s.remote_user}@{s.ip_address}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Launcher with two entry points (currently just OpenClaw, via its
 * `hasWebPanel`): a dropdown offering "Terminal" (same openTerminalTab flow
 * as every other launcher button) and "Web" (opens the tool's own web UI in
 * a new external browser tab, fetching a fresh, pre-authed URL from the
 * backend on each click -- see fetchOpenclawDashboardUrl and
 * RUNTIME_LAUNCHERS). Menu anchors to the button's *right* edge (`right-0`,
 * not `left-0`): this launcher sits at the far right of the toolbar, so a
 * left-anchored menu overflowed past the viewport edge and got clipped. */
function LauncherMenu({
  launcher,
  onOpenTerminal,
}: {
  launcher: Launcher;
  onOpenTerminal: (label: string, command: string) => void;
}) {
  const { t } = useTranslation("workspace");
  const [open, setOpen] = useState(false);
  const [loadingWeb, setLoadingWeb] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);

  async function openWeb() {
    setOpen(false);
    setLoadingWeb(true);
    try {
      const { url } = await fetchOpenclawDashboardUrl();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      window.open(OPENCLAW_DASHBOARD_FALLBACK_URL, "_blank", "noopener,noreferrer");
    } finally {
      setLoadingWeb(false);
    }
  }

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="outline"
        size="icon"
        className="h-7 w-7"
        title={launcher.label}
        aria-label={t("toolbar.openLauncher", { label: launcher.label })}
        onClick={() => setOpen((v) => !v)}
        disabled={loadingWeb}
      >
        {loadingWeb ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LauncherIcon icon={launcher.icon} iconBg={launcher.iconBg} />}
      </Button>
      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 mr-1 w-44 overflow-hidden rounded-md border border-border bg-card py-1 shadow-md">
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={() => {
              onOpenTerminal(launcher.label, launcher.command);
              setOpen(false);
            }}
          >
            <SquareTerminal className="h-3.5 w-3.5" />
            {t("toolbar.terminal")}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={openWeb}
          >
            <Globe2 className="h-3.5 w-3.5" />
            {t("toolbar.web")}
          </button>
        </div>
      )}
    </div>
  );
}

function LaunchersMenu({ onLaunch }: { onLaunch: (label: string, command: string) => void }) {
  const { t } = useTranslation("workspace");
  const [open, setOpen] = useState(false);
  const [loadingWeb, setLoadingWeb] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);

  async function openOpenClawWeb() {
    setOpen(false);
    setLoadingWeb(true);
    try {
      const { url } = await fetchOpenclawDashboardUrl();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      window.open(OPENCLAW_DASHBOARD_FALLBACK_URL, "_blank", "noopener,noreferrer");
    } finally {
      setLoadingWeb(false);
    }
  }

  return (
    <div className="relative 2xl:hidden" ref={containerRef}>
      <Button variant="outline" size="sm" className="h-8 gap-1.5 px-2" onClick={() => setOpen((value) => !value)} disabled={loadingWeb}>
        {loadingWeb ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Feather className="h-3.5 w-3.5" />}
        <span className="hidden lg:inline">{t("toolbar.launchers")}</span>
        <ChevronDown className="h-3 w-3 opacity-60" />
      </Button>
      {open && (
        <div className="absolute right-0 top-full z-30 mt-1 max-h-80 w-60 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md">
          <p className="px-3 py-1 text-[10px] font-medium uppercase text-muted-foreground">{t("toolbar.cli")}</p>
          {CLI_LAUNCHERS.map((launcher) => (
            <button key={launcher.command} type="button" className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent" onClick={() => { onLaunch(launcher.label, launcher.command); setOpen(false); }}>
              <LauncherIcon icon={launcher.icon} iconBg={launcher.iconBg} /> {launcher.label}
            </button>
          ))}
          <p className="mt-1 border-t border-border px-3 py-1 pt-2 text-[10px] font-medium uppercase text-muted-foreground">{t("toolbar.runtimes")}</p>
          {RUNTIME_LAUNCHERS.map((launcher) => (
            <div key={launcher.command} className="flex items-center hover:bg-accent">
              <button type="button" className="flex min-w-0 flex-1 items-center gap-2 px-3 py-1.5 text-left text-sm" onClick={() => { onLaunch(launcher.label, launcher.command); setOpen(false); }}>
                <LauncherIcon icon={launcher.icon} iconBg={launcher.iconBg} /> {launcher.label}
              </button>
              {launcher.hasWebPanel && (
                <button type="button" className="px-3 py-1.5" aria-label={t("toolbar.openLauncherWeb", { label: launcher.label })} onClick={() => void openOpenClawWeb()}><Globe2 className="h-3.5 w-3.5" /></button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function WorkspacePage() {
  const { t } = useTranslation("workspace");
  const { data: allAgents } = useAgents();
  const { data: products = [] } = useProducts();
  const chatableAgents = useMemo(
    () => (allAgents ?? []).filter((a) => Boolean(a.profile_slug)),
    [allAgents]
  );

  const restoredStateRef = useRef<ReturnType<typeof restoreWorkspaceState> | null>(null);
  if (!restoredStateRef.current) restoredStateRef.current = restoreWorkspaceState(localStorage);
  const restoredState = restoredStateRef.current;

  const [viewMode, setViewMode] = useState<WorkspaceViewMode>(restoredState.viewMode);
  useEffect(() => {
    localStorage.setItem(WORKSPACE_STORAGE_KEYS.viewMode, viewMode);
  }, [viewMode]);

  const [tabs, setTabs] = useState<WorkspaceTab[]>(restoredState.tabs);
  const [activeTabId, setActiveTabId] = useState<string>(restoredState.activeTabId);
  const [workingDir, setWorkingDir] = useState<string | undefined>(restoredState.workingDir);
  const workspaceUploadInputRef = useRef<HTMLInputElement>(null);
  const [workspaceUploadStatus, setWorkspaceUploadStatus] = useState<"idle" | "uploading" | "success" | "error">(
    "idle"
  );
  const [workspaceActionError, setWorkspaceActionError] = useState<string | null>(null);

  async function handleWorkspaceFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // allow picking the same file(s) again to re-trigger onChange
    if (files.length === 0 || !workingDir) return;
    setWorkspaceUploadStatus("uploading");
    const formData = new FormData();
    formData.append("dir", workingDir);
    files.forEach((f) => formData.append("files", f));
    try {
      await apiClient.postForm("/api/v1/terminal/upload-to-dir", formData);
      setWorkspaceUploadStatus("success");
    } catch {
      setWorkspaceUploadStatus("error");
    } finally {
      setTimeout(() => setWorkspaceUploadStatus("idle"), 1500);
    }
  }

  // Native HTML5 drag-and-drop for tab reordering -- a ref (not state) so
  // dragging doesn't trigger re-renders; only the drop commits a change.
  const dragTabIdRef = useRef<string | null>(null);

  // Drops the dragged tab immediately after the drop target, regardless of
  // whether the drag moved forward or backward in the list -- computing
  // the insertion index from the *post-removal* array (rather than the
  // original) avoids an off-by-one that otherwise cancels out
  // forward-adjacent drags.
  function handleTabDrop(targetId: string) {
    const draggedId = dragTabIdRef.current;
    dragTabIdRef.current = null;
    if (!draggedId || draggedId === targetId) return;
    setTabs((prev) => {
      const draggedIndex = prev.findIndex((t) => t.id === draggedId);
      if (draggedIndex === -1) return prev;
      const next = [...prev];
      const [dragged] = next.splice(draggedIndex, 1);
      const targetIndex = next.findIndex((t) => t.id === targetId);
      if (targetIndex === -1) return prev;
      next.splice(targetIndex + 1, 0, dragged);
      return next;
    });
  }

  useEffect(() => {
    localStorage.setItem(WORKSPACE_STORAGE_KEYS.version, String(WORKSPACE_STORAGE_VERSION));
    localStorage.setItem(WORKSPACE_STORAGE_KEYS.tabs, JSON.stringify(tabs));
  }, [tabs]);

  useEffect(() => {
    localStorage.setItem(WORKSPACE_STORAGE_KEYS.activeTab, activeTabId);
  }, [activeTabId]);

  useEffect(() => {
    if (workingDir) localStorage.setItem(WORKSPACE_STORAGE_KEYS.workingDir, workingDir);
    else localStorage.removeItem(WORKSPACE_STORAGE_KEYS.workingDir);
  }, [workingDir]);


  function openChatTab(agentId: string) {
    const id = crypto.randomUUID();
    // Defaults to collapsed (2026-07-28, Marcelo) -- the conversation list
    // takes up room that most sessions don't need open; toggled back on
    // per-tab via the history button same as before.
    setTabs((t) => [...t, { kind: "chat", id, agentId, historyCollapsed: true }]);
    setActiveTabId(id);
  }

  function openTelegramTab(agentId: string) {
    const existing = tabs.find((tab) => tab.kind === "telegram" && tab.agentId === agentId);
    if (existing) {
      setActiveTabId(existing.id);
      return;
    }
    const id = crypto.randomUUID();
    setTabs((current) => [...current, { kind: "telegram", id, agentId }]);
    setActiveTabId(id);
  }

  function openTerminalTab(label: string, command?: string, cwdOverride?: string) {
    const id = crypto.randomUUID();
    setTabs((t) => [...t, { kind: "terminal", id, label, command, cwd: cwdOverride ?? workingDir }]);
    setActiveTabId(id);
  }

  function defaultWebTarget(): { url: string; target: WebAppTarget } {
    const product = products.find((item) => item.name.trim().toLowerCase() === "forgehub") ?? products[0];
    const url = product?.application_url || product?.application_url_dev;
    return product && url ? { url, target: { mode: "product", id: product.id } } : { url: DEFAULT_APP_URL, target: { mode: "url" } };
  }

  function openWebTab(label = "Web App", initial?: { url: string; target: WebAppTarget }) {
    const web = initial ?? defaultWebTarget();
    const id = crypto.randomUUID();
    setTabs((current) => [...current, { kind: "web", id, label, ...web }]);
    setActiveTabId(id);
  }

  function toggleWebBrowser() {
    if (activeWebTab) {
      const fallback = [...tabs].reverse().find((tab) => tab.kind !== "web");
      setActiveTabId(fallback?.id ?? "");
      return;
    }
    const existing = tabs.find((tab): tab is WorkspaceTab & { kind: "web" } => tab.kind === "web");
    if (existing) setActiveTabId(existing.id);
    else openWebTab();
  }

  const updateWebTabUrl = useCallback((tabId: string, url: string) => {
    setTabs((current) =>
      current.map((tab) => (tab.id === tabId && tab.kind === "web" ? { ...tab, url } : tab))
    );
  }, []);

  const updateWebTabTarget = useCallback((tabId: string, target: WebAppTarget) => {
    setTabs((current) =>
      current.map((tab) => (tab.id === tabId && tab.kind === "web" ? { ...tab, target } : tab))
    );
  }, []);

  // Handoff from the Servers page's "open SSH" action: arrive with an
  // openSsh router state → open a terminal tab running the ssh command,
  // then clear the state so a refresh/back-forward doesn't re-open it.
  // The ref guards StrictMode's double effect run in dev.
  const location = useLocation();
  const navigate = useNavigate();
  const openSshHandledRef = useRef(false);
  useEffect(() => {
    const openSsh = (location.state as { openSsh?: { label: string; command: string } } | null)?.openSsh;
    if (!openSsh || openSshHandledRef.current) return;
    openSshHandledRef.current = true;
    openTerminalTab(openSsh.label, openSsh.command);
    navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  // Same handoff pattern as openSsh above -- "open terminal in this
  // project" (Fase 6.5) from a Project's detail page or the Systems Hub's
  // "Project MCP servers" tab, pre-seeded with that project's
  // working_directory_path instead of making the operator navigate
  // WorkingDirPicker's folder tree by hand every time.
  const openTerminalHandledRef = useRef(false);
  useEffect(() => {
    const openTerminal = (location.state as { openTerminal?: { label: string; cwd: string } } | null)
      ?.openTerminal;
    if (!openTerminal || openTerminalHandledRef.current) return;
    openTerminalHandledRef.current = true;
    openTerminalTab(openTerminal.label, undefined, openTerminal.cwd);
    navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  // Same handoff pattern as openSsh/openTerminal above -- "open this
  // project's channel" from the Project detail page's "Equipe & Canal"
  // section (ProjectAutomationCard). Switches to Canais mode and hands
  // ChannelPane the project so it can preselect (or offer to create) that
  // project's channel instead of landing on an unrelated one.
  const openChannelHandledRef = useRef(false);
  const [channelDefaultProjectId, setChannelDefaultProjectId] = useState<string | undefined>(undefined);
  useEffect(() => {
    const openChannel = (location.state as { openChannel?: { projectId: string } } | null)?.openChannel;
    if (!openChannel || openChannelHandledRef.current) return;
    openChannelHandledRef.current = true;
    setViewMode("canais");
    setChannelDefaultProjectId(openChannel.projectId);
    navigate(location.pathname, { replace: true, state: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  // Same handoff idea as openChannel above, but via a bookmarkable query
  // param instead of router state -- backs the sidebar's "Grupo de
  // Trabalho" entry (navSections.ts, Software Factory section, 2026-08-05)
  // so a plain link can jump straight to Canais instead of only landing on
  // whichever mode localStorage last remembered.
  const viewModeQueryHandledRef = useRef(false);
  useEffect(() => {
    if (viewModeQueryHandledRef.current) return;
    const requestedView = new URLSearchParams(location.search).get("view");
    if (requestedView !== "channels") return;
    viewModeQueryHandledRef.current = true;
    setViewMode("canais");
    navigate(location.pathname, { replace: true, state: location.state });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  function closeTab(id: string) {
    const remaining = tabs.filter((t) => t.id !== id);
    setTabs(remaining);
    setActiveTabId((current) => (current === id ? remaining[remaining.length - 1]?.id ?? "" : current));
    clearChatTabStaging(id);
  }

  async function terminateTerminalTab(id: string, label: string) {
    if (!window.confirm(t("tabs.confirmTerminateTerminal", { label }))) return;
    setWorkspaceActionError(null);
    try {
      await apiClient.post(`/api/v1/terminal/sessions/${id}/kill`);
      closeTab(id);
    } catch (error) {
      setWorkspaceActionError(error instanceof Error ? error.message : t("tabs.terminateTerminalFailed"));
    }
  }

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | undefined;
    if (event.key === "ArrowLeft") nextIndex = index === 0 ? tabs.length - 1 : index - 1;
    if (event.key === "ArrowRight") nextIndex = index === tabs.length - 1 ? 0 : index + 1;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;
    if (nextIndex === undefined) return;
    event.preventDefault();
    const nextTab = tabs[nextIndex];
    if (!nextTab) return;
    setActiveTabId(nextTab.id);
    requestAnimationFrame(() => document.getElementById(`workspace-tab-${nextTab.id}`)?.focus());
  }

  function handleAgentChangeForTab(tabId: string, agentId: string) {
    setTabs((t) => t.map((x) => (x.id === tabId && x.kind === "chat" ? { ...x, agentId, sessionId: undefined } : x)));
  }

  function handleTelegramAgentChange(tabId: string, agentId: string) {
    setTabs((current) => current.map((tab) =>
      tab.id === tabId && tab.kind === "telegram" ? { ...tab, agentId } : tab
    ));
  }

  function handleSessionChangeForTab(tabId: string, sessionId: string) {
    setTabs((current) =>
      current.map((tab) => tab.id === tabId && tab.kind === "chat" ? { ...tab, sessionId: sessionId || undefined } : tab)
    );
  }

  function toggleHistoryCollapsed(tabId: string) {
    setTabs((t) =>
      t.map((x) => (x.id === tabId && x.kind === "chat" ? { ...x, historyCollapsed: !x.historyCollapsed } : x))
    );
  }

  function toggleArtifactsPanel(tabId: string) {
    setTabs((t) =>
      t.map((x) => (x.id === tabId && x.kind === "chat" ? { ...x, artifactsOpen: !x.artifactsOpen } : x))
    );
  }

  // Runs once chatableAgents is available: if no tabs were restored from
  // storage, open one default chat tab so the page isn't empty on first
  // visit.
  const initRef = useRef(false);
  useEffect(() => {
    if (initRef.current || chatableAgents.length === 0) return;
    initRef.current = true;
    const validAgentIds = new Set(chatableAgents.map((agent) => agent.id));
    const repairedTabs = tabs.map((tab) =>
      (tab.kind === "chat" || tab.kind === "telegram") && !validAgentIds.has(tab.agentId)
        ? { ...tab, agentId: chatableAgents[0].id }
        : tab
    );
    if (repairedTabs.length === 0) {
      openChatTab(chatableAgents[0].id);
      return;
    }
    if (repairedTabs.some((tab, index) => tab !== tabs[index])) setTabs(repairedTabs);
    setActiveTabId((current) => repairActiveTabId(repairedTabs, current));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatableAgents]);

  const activeChatTab = tabs.find(
    (t): t is WorkspaceTab & { kind: "chat" } => t.id === activeTabId && t.kind === "chat"
  );
  const activeWebTab = tabs.find(
    (tab): tab is WorkspaceTab & { kind: "web" } => tab.id === activeTabId && tab.kind === "web"
  );
  const setAssistantOpen = useAssistantStore((state) => state.setOpen);
  const setPendingHiddenContext = useAssistantStore((state) => state.setPendingHiddenContext);

  const webAssistantContext = useMemo(() => {
    if (!activeWebTab) return null;
    return {
      label: "Use web environment",
      workingDir,
      build: () =>
        [
          "Estou usando o ambiente web do Workspace no ForgeHub.",
          `URL visível no navegador incorporado: ${activeWebTab.url}`,
          `Diretório de trabalho selecionado: ${workingDir ?? "não selecionado"}`,
          "Analise a aplicação pelos arquivos, logs, endpoints e comandos disponíveis.",
          "Esta é a sessão Chromium compartilhada por CDP. Use browser_snapshot antes de interagir e confirme o resultado com novo snapshot ou screenshot.",
          "Quando o usuário enviar uma instrução explícita no composer do Assistente, você está autorizado a controlar integralmente esta sessão para cumpri-la: navegar, clicar, rolar, focar, digitar, selecionar opções e enviar formulários.",
          "Não inicie interações por conta própria; o controle começa somente após a instrução explícita do usuário e deve ficar limitado ao pedido.",
          "Para o login de desenvolvimento do ForgeHub, use usuário admin e senha admin.",
        ].join("\n"),
    };
  }, [activeWebTab, workingDir]);
  useAssistantContext(webAssistantContext);

  // The environment instruction is internal grounding, not user prose --
  // it rides out invisibly with the user's first message (see
  // assistantStore's pendingHiddenContext) instead of filling the composer.
  function openAssistantForWebEnvironment() {
    if (!webAssistantContext) return;
    setPendingHiddenContext(webAssistantContext.build());
    setAssistantOpen(true);
  }

  function defaultAgentIdForNewTab(): string {
    return activeChatTab?.agentId ?? chatableAgents[0]?.id ?? "";
  }

  const modeToggle = (
    <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
      <Button
        variant={viewMode === "conversas" ? "secondary" : "ghost"}
        size="sm"
        className="h-7 gap-1.5"
        onClick={() => setViewMode("conversas")}
      >
        <MessageSquare className="h-3.5 w-3.5" />
        {t("viewMode.conversas")}
      </Button>
      <Button
        variant={viewMode === "canais" ? "secondary" : "ghost"}
        size="sm"
        className="h-7 gap-1.5"
        onClick={() => setViewMode("canais")}
      >
        <Users className="h-3.5 w-3.5" />
        {t("viewMode.canais")}
      </Button>
    </div>
  );

  // Channels and Conversations both stay mounted, toggled via CSS
  // `hidden` instead of a conditional-render/early-return swap -- an
  // agent turn in flight (a channel dispatch, or a chat stream) used to
  // die with zero trace the instant you switched away from its tab, since
  // switching used to unmount the whole pane (2026-08-07, Marcelo: "ao
  // sair da tela perdi o processamento da conversão com o agente. precisa
  // se manter igual ao chat da conversation" -- "algumas telas não podem
  // ser apagadas... precisam ter sessões e continuarem com o serviço").
  // Mirrors the pattern ChatPane's own tabs already use below (`!active &&
  // "hidden"`) rather than inventing a new one. This alone doesn't make a
  // backend turn survive a dropped connection (see channel.py's
  // _wake_agent_turn_streaming for that fix) -- it only stops the
  // *frontend* from throwing away an otherwise-healthy in-flight request
  // by destroying the component watching it.
  return (
    <div className="flex min-h-0 flex-1 flex-col pl-4">
      {modeToggle}
      <div className={cn("flex min-h-0 flex-1 flex-col", viewMode !== "canais" && "hidden")}>
        <ChannelPane agents={allAgents ?? []} defaultProjectId={channelDefaultProjectId} />
      </div>
      <div className={cn("flex min-h-0 flex-1 flex-col", viewMode !== "conversas" && "hidden")}>
      {chatableAgents.length === 0 ? (
        <div className="flex h-[60vh] items-center justify-center text-center text-muted-foreground">
          <div>
            <Bot className="mx-auto mb-3 h-10 w-10" />
            <p>{t("tabs.noAgentAvailable")}</p>
          </div>
        </div>
      ) : (
      <>
      <div className="flex flex-col border-b border-border">
        {/* Toolbar: static actions on the left, working-dir/launchers on the right. */}
        <div className="flex min-w-0 items-center gap-1 px-2 py-1.5">
          <Button
            variant={activeChatTab && !activeChatTab.historyCollapsed ? "secondary" : "outline"}
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={!activeChatTab}
            aria-label={activeChatTab?.historyCollapsed ? t("toolbar.showHistory") : t("toolbar.hideHistory")}
            title={t("toolbar.conversationHistory")}
            onClick={() => activeChatTab && toggleHistoryCollapsed(activeChatTab.id)}
          >
            <History className="h-4 w-4" />
          </Button>
          <Button
            variant={activeChatTab?.artifactsOpen ? "secondary" : "outline"}
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={!activeChatTab}
            aria-label={activeChatTab?.artifactsOpen ? t("toolbar.hideArtifacts") : t("toolbar.showArtifacts")}
            title={t("toolbar.conversationArtifacts")}
            onClick={() => activeChatTab && toggleArtifactsPanel(activeChatTab.id)}
          >
            <Package className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title={t("toolbar.newChat")}
            aria-label={t("toolbar.newChat")}
            onClick={() => openChatTab(defaultAgentIdForNewTab())}
          >
            <MessageSquare className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="Abrir Telegram do agente"
            aria-label="Abrir Telegram do agente"
            disabled={!activeChatTab}
            onClick={() => activeChatTab && openTelegramTab(activeChatTab.agentId)}
          >
            <Send className="h-4 w-4 text-sky-500" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title={t("toolbar.newTerminal")}
            aria-label={t("toolbar.newTerminal")}
            onClick={() => openTerminalTab("bash")}
          >
            <SquareTerminal className="h-4 w-4" />
          </Button>
          <Button
            variant={activeWebTab ? "secondary" : "outline"}
            size="icon"
            className="h-8 w-8 shrink-0"
            title={activeWebTab ? t("toolbar.hideInternalBrowser") : t("toolbar.openInternalBrowser")}
            aria-label={activeWebTab ? t("toolbar.hideInternalBrowser") : t("toolbar.openInternalBrowser")}
            onClick={toggleWebBrowser}
          >
            <Globe2 className="h-4 w-4" />
          </Button>
          <Button
            variant={activeWebTab ? "outline" : "ghost"}
            size="sm"
            className="h-8 w-8 p-0"
            disabled={!activeWebTab}
            title={activeWebTab ? t("toolbar.openAssistantWithWeb") : t("toolbar.openWebTabFirst")}
            aria-label={activeWebTab ? t("toolbar.openAssistantWithWeb") : t("toolbar.openWebTabFirst")}
            onClick={openAssistantForWebEnvironment}
          >
            <Bot className="h-4 w-4" />
          </Button>
          <SshLauncherMenu onLaunch={openTerminalTab} />
          <LaunchersMenu onLaunch={openTerminalTab} />
          <div className="flex-1" />
          <WorkingDirPicker workingDir={workingDir} onSelect={setWorkingDir} />
          <input
            ref={workspaceUploadInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={handleWorkspaceFileUpload}
          />
          <Button
            variant="outline"
            size="icon"
            className="h-7 w-7 shrink-0"
            disabled={!workingDir || workspaceUploadStatus === "uploading"}
            title={workingDir ? t("toolbar.uploadFiles") : t("toolbar.selectWorkingFolderFirst")}
            aria-label={t("toolbar.uploadFiles")}
            onClick={() => workspaceUploadInputRef.current?.click()}
          >
            {workspaceUploadStatus === "uploading" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : workspaceUploadStatus === "success" ? (
              <Check className="h-3.5 w-3.5 text-green-500" />
            ) : workspaceUploadStatus === "error" ? (
              <X className="h-3.5 w-3.5 text-destructive" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
          </Button>
          <div className="hidden items-center gap-1 2xl:flex">
          <div className="mx-1 h-5 w-px bg-border" />
          <span className="text-[10px] font-medium uppercase text-muted-foreground" title={t("toolbar.cliLaunchers")}>
            {t("toolbar.cli")}
          </span>
          {CLI_LAUNCHERS.map((l) => (
            <Button
              key={l.command}
              variant="outline"
              size="icon"
              className="h-7 w-7"
              title={l.label}
              aria-label={t("toolbar.openLauncher", { label: l.label })}
              onClick={() => openTerminalTab(l.label, l.command)}
            >
              <LauncherIcon icon={l.icon} iconBg={l.iconBg} />
            </Button>
          ))}
          <div className="mx-1 h-5 w-px bg-border" />
          <span className="text-[10px] font-medium uppercase text-muted-foreground" title={t("toolbar.runtimeLaunchers")}>
            {t("toolbar.runtimes")}
          </span>
          {RUNTIME_LAUNCHERS.map((l) =>
            l.hasWebPanel ? (
              <LauncherMenu key={l.command} launcher={l} onOpenTerminal={openTerminalTab} />
            ) : (
              <Button
                key={l.command}
                variant="outline"
                size="icon"
                className="h-7 w-7"
                title={l.label}
                aria-label={t("toolbar.openLauncher", { label: l.label })}
                onClick={() => openTerminalTab(l.label, l.command)}
              >
                <LauncherIcon icon={l.icon} iconBg={l.iconBg} />
              </Button>
            )
          )}
          </div>
        </div>

        {/* Dedicated tab strip: sortable (drag-and-drop) + horizontal scroll. */}
        <div role="tablist" aria-label={t("tabs.workspaceTabs")} className="flex items-center gap-1 overflow-x-auto border-t border-border/60 px-2 py-1">
          {tabs.map((tab, index) => {
            const label = tab.kind === "chat" || tab.kind === "telegram"
              ? chatableAgents.find((agent) => agent.id === tab.agentId)?.name ?? t("tabs.defaultChatName")
              : tab.label;
            return (
              <WorkspaceTabItem
                key={tab.id}
                tab={tab}
                label={label}
                icon={tab.kind === "chat" ? <MessageSquare className="h-3.5 w-3.5" /> : tab.kind === "terminal" ? <SquareTerminal className="h-3.5 w-3.5" /> : tab.kind === "telegram" ? <Send className="h-3.5 w-3.5 text-sky-500" /> : <Globe2 className="h-3.5 w-3.5" />}
                active={tab.id === activeTabId}
                onSelect={() => setActiveTabId(tab.id)}
                onClose={() => closeTab(tab.id)}
                onTerminate={tab.kind === "terminal" ? () => void terminateTerminalTab(tab.id, tab.label) : undefined}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
                onDragStart={() => (dragTabIdRef.current = tab.id)}
                onDrop={() => handleTabDrop(tab.id)}
                closeLabel={tab.kind === "terminal" ? t("tabs.detachTerminal", { label }) : t("tabs.closeTab", { label })}
                terminateLabel={tab.kind === "terminal" ? t("tabs.terminateTerminal", { label }) : undefined}
              />
            );
          })}
        </div>
        {workspaceActionError && (
          <div className="flex items-center justify-between gap-2 border-t border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs text-destructive">
            <span>{workspaceActionError}</span>
            <button type="button" aria-label={t("common:close")} onClick={() => setWorkspaceActionError(null)}><X className="h-3.5 w-3.5" /></button>
          </div>
        )}
      </div>

      <div className="relative flex-1">
        {tabs.map((tab) =>
          tab.kind === "chat" ? (
            <div key={tab.id} id={`workspace-panel-${tab.id}`} role="tabpanel" className={cn("absolute inset-0", tab.id !== activeTabId && "hidden")}>
              <ChatPane
                tabId={tab.id}
                active={tab.id === activeTabId}
                agentId={tab.agentId}
                initialSessionId={tab.sessionId}
                chatableAgents={chatableAgents}
                onAgentChange={(agentId) => handleAgentChangeForTab(tab.id, agentId)}
                onSessionChange={(sessionId) => handleSessionChangeForTab(tab.id, sessionId)}
                historyCollapsed={Boolean(tab.historyCollapsed)}
                artifactsOpen={Boolean(tab.artifactsOpen)}
                workingDir={workingDir}
              />
            </div>
          ) : tab.kind === "terminal" ? (
            <div key={tab.id} id={`workspace-panel-${tab.id}`} role="tabpanel" className={cn("absolute inset-0 p-2", tab.id !== activeTabId && "hidden")}>
              <TerminalPane sessionId={tab.id} command={tab.command} cwd={tab.cwd} active={tab.id === activeTabId} />
            </div>
          ) : tab.kind === "telegram" ? (
            <div key={tab.id} id={`workspace-panel-${tab.id}`} role="tabpanel" className={cn("absolute inset-0", tab.id !== activeTabId && "hidden")}>
              <TelegramPane
                agentId={tab.agentId}
                agents={chatableAgents}
                active={tab.id === activeTabId}
                onAgentChange={(agentId) => handleTelegramAgentChange(tab.id, agentId)}
              />
            </div>
          ) : (
            <div key={tab.id} id={`workspace-panel-${tab.id}`} role="tabpanel" className={cn("absolute inset-0", tab.id !== activeTabId && "hidden")}>
              <WebAppPane
                url={tab.url}
                target={tab.target}
                products={products}
                onUrlChange={(url) => updateWebTabUrl(tab.id, url)}
                onTargetChange={(target) => updateWebTabTarget(tab.id, target)}
              />
            </div>
          )
        )}

        {tabs.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-center text-muted-foreground">
            <div>
              <MessageSquare className="mx-auto mb-3 h-10 w-10" />
              <p className="font-medium">{t("tabs.noTabsOpen")}</p>
              <p className="text-sm">{t("tabs.noTabsOpenHelp")}</p>
            </div>
          </div>
        )}
      </div>
      </>
      )}
      </div>
    </div>
  );
}
