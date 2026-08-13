import { useEffect, useMemo, useRef, useState } from "react";
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
  SquareTerminal,
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
import { useServers, buildSshCommand } from "@/hooks/useServers";
import { fetchOpenclawDashboardUrl } from "@/hooks/useTerminalBrowse";
import { useClickOutside } from "@/hooks/useClickOutside";
import { ChatPane, clearChatTabStaging } from "@/components/chat/ChatPane";
import { ChannelPane } from "@/components/channel/ChannelPane";
import { useAgents } from "@/hooks/useAgent";
import { WebAppPane } from "@/components/WebAppPane";
import { useAssistantContext } from "@/hooks/useAssistant";
import { useAssistantStore } from "@/store/assistantStore";
import { useProducts } from "@/hooks/useProduct";

// Tabs/active-tab are persisted (not just in-memory state) so that
// navigating to another page and back to Workspace recreates the same tabs
// with the same ids -- TerminalPane then reconnects using those ids as its
// tmux session name, re-attaching to the still-running session instead of
// losing it. See TerminalPane.tsx and host-bridge/app.py's terminal_ws.
const TABS_STORAGE_KEY = "forgehub-workspace-tabs";
const ACTIVE_TAB_STORAGE_KEY = "forgehub-workspace-active-tab";
const APP_URL_STORAGE_KEY = "forgehub-workspace-app-url";
const SELECTED_PRODUCT_STORAGE_KEY = "forgehub-workspace-selected-product";
const DEFAULT_APP_URL = "http://localhost:5174";
// Top-level Workspace mode: "conversas" is the existing tab system below,
// completely unchanged; "canais" renders the new multi-agent ChatChannel
// room instead. Deliberately NOT another WorkspaceTab kind -- ChatChannel
// has its own participants/sidebar model (N agents + the human, shared
// context), not a single agentId per tab, so folding it into the existing
// tab persistence/reorder machinery would force an awkward shape onto both.
const VIEW_MODE_STORAGE_KEY = "forgehub-workspace-view-mode";
type WorkspaceViewMode = "conversas" | "canais";

type WorkspaceTab =
  | {
      kind: "chat";
      id: string;
      agentId: string;
      historyCollapsed?: boolean;
      artifactsOpen?: boolean;
      composerText?: string;
    }
  | { kind: "terminal"; id: string; label: string; command?: string; cwd?: string }
  | { kind: "web"; id: string; label: string; url: string };

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
          {(servers ?? []).map((s) => (
            <button
              key={s.id}
              type="button"
              className="flex w-full flex-col items-start px-3 py-1.5 text-left hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                onLaunch(s.name, buildSshCommand(s));
                setOpen(false);
              }}
            >
              <span className="text-sm font-medium">{s.name}</span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {s.remote_user}@{s.ip_address}
              </span>
            </button>
          ))}
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

export default function WorkspacePage() {
  const { t } = useTranslation("workspace");
  const { data: allAgents } = useAgents();
  const { data: products = [] } = useProducts();
  const chatableAgents = useMemo(
    () => (allAgents ?? []).filter((a) => Boolean(a.profile_slug)),
    [allAgents]
  );

  const [viewMode, setViewMode] = useState<WorkspaceViewMode>(
    () => (localStorage.getItem(VIEW_MODE_STORAGE_KEY) as WorkspaceViewMode | null) ?? "conversas"
  );
  useEffect(() => {
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, viewMode);
  }, [viewMode]);

  const [tabs, setTabs] = useState<WorkspaceTab[]>(() => {
    try {
      const raw = localStorage.getItem(TABS_STORAGE_KEY);
      return raw ? (JSON.parse(raw) as WorkspaceTab[]) : [];
    } catch {
      return [];
    }
  });
  const [activeTabId, setActiveTabId] = useState<string>(
    () => localStorage.getItem(ACTIVE_TAB_STORAGE_KEY) ?? ""
  );
  const [workingDir, setWorkingDir] = useState<string | undefined>(undefined);
  const appUrl = localStorage.getItem(APP_URL_STORAGE_KEY) ?? DEFAULT_APP_URL;
  const [selectedProductId, setSelectedProductId] = useState(
    () => localStorage.getItem(SELECTED_PRODUCT_STORAGE_KEY) ?? ""
  );
  const workspaceUploadInputRef = useRef<HTMLInputElement>(null);
  const [workspaceUploadStatus, setWorkspaceUploadStatus] = useState<"idle" | "uploading" | "success" | "error">(
    "idle"
  );

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
    localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(tabs));
  }, [tabs]);

  useEffect(() => {
    localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTabId);
  }, [activeTabId]);

  useEffect(() => {
    if (products.length === 0) return;
    if (products.some((product) => product.id === selectedProductId)) return;
    const fallback = products.find((product) => product.name.trim().toLowerCase() === "forgehub") ?? products[0];
    setSelectedProductId(fallback.id);
  }, [products, selectedProductId]);

  useEffect(() => {
    if (selectedProductId) localStorage.setItem(SELECTED_PRODUCT_STORAGE_KEY, selectedProductId);
  }, [selectedProductId]);


  function openChatTab(agentId: string) {
    const id = crypto.randomUUID();
    // Defaults to collapsed (2026-07-28, Marcelo) -- the conversation list
    // takes up room that most sessions don't need open; toggled back on
    // per-tab via the history button same as before.
    setTabs((t) => [...t, { kind: "chat", id, agentId, historyCollapsed: true }]);
    setActiveTabId(id);
  }

  function openTerminalTab(label: string, command?: string, cwdOverride?: string) {
    const id = crypto.randomUUID();
    setTabs((t) => [...t, { kind: "terminal", id, label, command, cwd: cwdOverride ?? workingDir }]);
    setActiveTabId(id);
  }

  function openWebTab(label = "Web App", url = products.find((product) => product.id === selectedProductId)?.application_url ?? appUrl) {
    const id = crypto.randomUUID();
    setTabs((current) => [...current, { kind: "web", id, label, url }]);
    setActiveTabId(id);
  }

  function toggleWebBrowser() {
    if (activeWebTab) {
      const fallback = [...tabs].reverse().find((tab) => tab.kind !== "web");
      setActiveTabId(fallback?.id ?? "");
      return;
    }
    const existing = tabs.find((tab): tab is WorkspaceTab & { kind: "web" } => tab.kind === "web");
    const targetUrl = existing?.url ?? appUrl;
    if (existing) setActiveTabId(existing.id);
    else openWebTab("Web App", targetUrl);
  }

  function updateWebTabUrl(tabId: string, url: string) {
    setTabs((current) =>
      current.map((tab) => (tab.id === tabId && tab.kind === "web" ? { ...tab, url } : tab))
    );
  }

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
    const tab = tabs.find((t) => t.id === id);
    const remaining = tabs.filter((t) => t.id !== id);
    setTabs(remaining);
    setActiveTabId((current) => (current === id ? remaining[remaining.length - 1]?.id ?? "" : current));
    clearChatTabStaging(id);
    if (tab?.kind === "terminal") {
      // Fire-and-forget: this is the one place a tab's session should
      // actually end, as opposed to every other disconnect (tab switch,
      // navigating away), which only detaches and leaves it running.
      apiClient.post(`/api/v1/terminal/sessions/${id}/kill`).catch(() => {});
    }
  }

  function handleAgentChangeForTab(tabId: string, agentId: string) {
    setTabs((t) => t.map((x) => (x.id === tabId && x.kind === "chat" ? { ...x, agentId } : x)));
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
    if (tabs.length === 0) openChatTab(chatableAgents[0].id);
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
        <div className="flex items-center gap-1 px-2 py-1.5">
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

        {/* Dedicated tab strip: sortable (drag-and-drop) + horizontal scroll. */}
        <div className="flex items-center gap-1 overflow-x-auto border-t border-border/60 px-2 py-1">
          {tabs.map((tab) =>
            tab.kind === "chat" ? (
              <div
                key={tab.id}
                draggable
                onDragStart={() => (dragTabIdRef.current = tab.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleTabDrop(tab.id)}
                onClick={() => setActiveTabId(tab.id)}
                className={cn(
                  "group flex shrink-0 cursor-grab items-center gap-1.5 rounded-md px-3 py-1 text-sm active:cursor-grabbing",
                  tab.id === activeTabId
                    ? "bg-accent text-accent-foreground"
                    : "cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <MessageSquare className="h-3.5 w-3.5" />
                {chatableAgents.find((a) => a.id === tab.agentId)?.name ?? t("tabs.defaultChatName")}
                <button
                  type="button"
                  aria-label={t("tabs.closeChatTab")}
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : tab.kind === "terminal" ? (
              <div
                key={tab.id}
                draggable
                onDragStart={() => (dragTabIdRef.current = tab.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleTabDrop(tab.id)}
                onClick={() => setActiveTabId(tab.id)}
                className={cn(
                  "group flex shrink-0 cursor-grab items-center gap-1.5 rounded-md px-3 py-1 text-sm active:cursor-grabbing",
                  tab.id === activeTabId
                    ? "bg-accent text-accent-foreground"
                    : "cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <SquareTerminal className="h-3.5 w-3.5" />
                {tab.label}
                <button
                  type="button"
                  aria-label={t("tabs.closeTab", { label: tab.label })}
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : (
              <div
                key={tab.id}
                draggable
                onDragStart={() => (dragTabIdRef.current = tab.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleTabDrop(tab.id)}
                onClick={() => setActiveTabId(tab.id)}
                className={cn(
                  "group flex shrink-0 cursor-grab items-center gap-1.5 rounded-md px-3 py-1 text-sm active:cursor-grabbing",
                  tab.id === activeTabId
                    ? "bg-accent text-accent-foreground"
                    : "cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Globe2 className="h-3.5 w-3.5" />
                {tab.label}
                <button
                  type="button"
                  aria-label={t("tabs.closeTab", { label: tab.label })}
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )
          )}
        </div>
      </div>

      <div className="relative flex-1">
        {tabs.map((tab) =>
          tab.kind === "chat" ? (
            <ChatPane
              key={tab.id}
              tabId={tab.id}
              active={tab.id === activeTabId}
              agentId={tab.agentId}
              chatableAgents={chatableAgents}
              onAgentChange={(agentId) => handleAgentChangeForTab(tab.id, agentId)}
              historyCollapsed={Boolean(tab.historyCollapsed)}
              artifactsOpen={Boolean(tab.artifactsOpen)}
              workingDir={workingDir}
            />
          ) : tab.kind === "terminal" ? (
            <div key={tab.id} className={cn("absolute inset-0 p-2", tab.id !== activeTabId && "hidden")}>
              <TerminalPane sessionId={tab.id} command={tab.command} cwd={tab.cwd} active={tab.id === activeTabId} />
            </div>
          ) : (
            <div key={tab.id} className={cn("absolute inset-0", tab.id !== activeTabId && "hidden")}>
              <WebAppPane
                url={tab.url}
                products={products}
                onUrlChange={(url) => updateWebTabUrl(tab.id, url)}
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
