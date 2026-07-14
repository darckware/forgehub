import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
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
  X,
} from "lucide-react";
import claudeIcon from "@lobehub/icons-static-png/dark/claude-color.png";
import codexIcon from "@lobehub/icons-static-png/dark/codex-color.png";
import antigravityIcon from "@lobehub/icons-static-png/dark/antigravity-color.png";
import opencodeIcon from "@lobehub/icons-static-png/light/opencode.png";
import hermesIcon from "@lobehub/icons-static-png/light/hermesagent.png";
import piIcon from "@/assets/icons/pi.svg";
import { Button } from "@/components/ui/button";
import { TerminalPane } from "@/components/TerminalPane";
import { WorkingDirPicker } from "@/components/WorkingDirPicker";
import { apiClient } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useServers, buildSshCommand } from "@/hooks/useServers";
import { useClickOutside } from "@/hooks/useClickOutside";
import { ChatPane, clearChatTabStaging } from "@/components/chat/ChatPane";
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

type Launcher = { label: string; command: string; icon?: string; iconBg?: string };

// "CLI" -- AI coding-assistant CLIs you'd run ad-hoc against this checkout.
const CLI_LAUNCHERS: Launcher[] = [
  { label: "Claude", command: "claude", icon: claudeIcon },
  { label: "Codex", command: "codex", icon: codexIcon },
  { label: "Antigravity", command: "agy", icon: antigravityIcon },
  // pi's mark is a plain white glyph (no built-in background), so it needs
  // a dark backing square to read against this button's light background --
  // unlike the others above, which are already self-contained color PNGs.
  { label: "PI", command: "pi", icon: piIcon, iconBg: "bg-black" },
  { label: "Opencode", command: "opencode", icon: opencodeIcon },
];

// "Runtimes" -- agent orchestration platforms (as opposed to one-shot
// coding CLIs above). Add OpenClaw or similar here once it has a launch
// command.
const RUNTIME_LAUNCHERS: Launcher[] = [
  { label: "Hermes", command: "hermes", icon: hermesIcon },
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
        title="Connect via SSH"
        aria-label="SSH"
        onClick={() => setOpen((v) => !v)}
      >
        <KeyRound className="h-3.5 w-3.5" />
        SSH
        <ChevronDown className="h-3 w-3 opacity-60" />
      </Button>
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md">
          {(servers ?? []).length === 0 && (
            <p className="px-3 py-3 text-xs italic text-muted-foreground">
              No servers registered. See "Servers" in the sidebar menu.
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

export default function WorkspacePage() {
  const { data: allAgents } = useAgents();
  const { data: products = [] } = useProducts();
  const chatableAgents = useMemo(
    () => (allAgents ?? []).filter((a) => Boolean(a.profile_slug)),
    [allAgents]
  );

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
    setTabs((t) => [...t, { kind: "chat", id, agentId }]);
    setActiveTabId(id);
  }

  function openTerminalTab(label: string, command?: string) {
    const id = crypto.randomUUID();
    setTabs((t) => [...t, { kind: "terminal", id, label, command, cwd: workingDir }]);
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
  const setPendingSeed = useAssistantStore((state) => state.setPendingSeed);

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

  function openAssistantForWebEnvironment() {
    if (!webAssistantContext) return;
    setPendingSeed(webAssistantContext.build());
    setAssistantOpen(true);
  }

  function defaultAgentIdForNewTab(): string {
    return activeChatTab?.agentId ?? chatableAgents[0]?.id ?? "";
  }

  if (chatableAgents.length === 0) {
    return (
      <div className="flex h-[60vh] items-center justify-center text-center text-muted-foreground">
        <div>
          <Bot className="mx-auto mb-3 h-10 w-10" />
          <p>No agent with a Hermes profile available to chat with yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col pl-4">
      <div className="flex flex-col border-b border-border">
        {/* Toolbar: static actions on the left, working-dir/launchers on the right. */}
        <div className="flex items-center gap-1 px-2 py-1.5">
          <Button
            variant={activeChatTab && !activeChatTab.historyCollapsed ? "secondary" : "outline"}
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={!activeChatTab}
            aria-label={activeChatTab?.historyCollapsed ? "Show conversation history" : "Hide conversation history"}
            title="Conversation history"
            onClick={() => activeChatTab && toggleHistoryCollapsed(activeChatTab.id)}
          >
            <History className="h-4 w-4" />
          </Button>
          <Button
            variant={activeChatTab?.artifactsOpen ? "secondary" : "outline"}
            size="icon"
            className="h-8 w-8 shrink-0"
            disabled={!activeChatTab}
            aria-label={activeChatTab?.artifactsOpen ? "Hide artifacts panel" : "Show artifacts panel"}
            title="Conversation artifacts"
            onClick={() => activeChatTab && toggleArtifactsPanel(activeChatTab.id)}
          >
            <Package className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="New chat"
            aria-label="New chat"
            onClick={() => openChatTab(defaultAgentIdForNewTab())}
          >
            <MessageSquare className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8 shrink-0"
            title="New terminal"
            aria-label="New terminal"
            onClick={() => openTerminalTab("bash")}
          >
            <SquareTerminal className="h-4 w-4" />
          </Button>
          <Button
            variant={activeWebTab ? "secondary" : "outline"}
            size="icon"
            className="h-8 w-8 shrink-0"
            title={activeWebTab ? "Hide internal browser" : "Open internal browser"}
            aria-label={activeWebTab ? "Hide internal browser" : "Open internal browser"}
            onClick={toggleWebBrowser}
          >
            <Globe2 className="h-4 w-4" />
          </Button>
          <Button
            variant={activeWebTab ? "outline" : "ghost"}
            size="sm"
            className="h-8 gap-1.5"
            disabled={!activeWebTab}
            title={activeWebTab ? "Open the selected assistant with the current web environment" : "Open a web tab first"}
            onClick={openAssistantForWebEnvironment}
          >
            <Bot className="h-4 w-4" /> Assistant
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
            title={workingDir ? "Upload files to the working folder" : "Select a working folder first"}
            aria-label="Upload files to the working folder"
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
          <span className="text-[10px] font-medium uppercase text-muted-foreground" title="Coding-assistant CLIs">
            CLI
          </span>
          {CLI_LAUNCHERS.map((l) => (
            <Button
              key={l.command}
              variant="outline"
              size="icon"
              className="h-7 w-7"
              title={l.label}
              aria-label={`Open ${l.label}`}
              onClick={() => openTerminalTab(l.label, l.command)}
            >
              <LauncherIcon icon={l.icon} iconBg={l.iconBg} />
            </Button>
          ))}
          <div className="mx-1 h-5 w-px bg-border" />
          <span className="text-[10px] font-medium uppercase text-muted-foreground" title="Agent runtimes/orchestrators">
            Runtimes
          </span>
          {RUNTIME_LAUNCHERS.map((l) => (
            <Button
              key={l.command}
              variant="outline"
              size="icon"
              className="h-7 w-7"
              title={l.label}
              aria-label={`Open ${l.label}`}
              onClick={() => openTerminalTab(l.label, l.command)}
            >
              <LauncherIcon icon={l.icon} iconBg={l.iconBg} />
            </Button>
          ))}
        </div>

        {/* Dedicated tab strip: sortable (drag-and-drop) + horizontal scroll. */}
        <div className="flex items-center gap-1 overflow-x-auto border-t border-border/60 px-2 py-1">
          {tabs.map((t) =>
            t.kind === "chat" ? (
              <div
                key={t.id}
                draggable
                onDragStart={() => (dragTabIdRef.current = t.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleTabDrop(t.id)}
                onClick={() => setActiveTabId(t.id)}
                className={cn(
                  "group flex shrink-0 cursor-grab items-center gap-1.5 rounded-md px-3 py-1 text-sm active:cursor-grabbing",
                  t.id === activeTabId
                    ? "bg-accent text-accent-foreground"
                    : "cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <MessageSquare className="h-3.5 w-3.5" />
                {chatableAgents.find((a) => a.id === t.agentId)?.name ?? "Chat"}
                <button
                  type="button"
                  aria-label="Close chat tab"
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(t.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : t.kind === "terminal" ? (
              <div
                key={t.id}
                draggable
                onDragStart={() => (dragTabIdRef.current = t.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleTabDrop(t.id)}
                onClick={() => setActiveTabId(t.id)}
                className={cn(
                  "group flex shrink-0 cursor-grab items-center gap-1.5 rounded-md px-3 py-1 text-sm active:cursor-grabbing",
                  t.id === activeTabId
                    ? "bg-accent text-accent-foreground"
                    : "cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <SquareTerminal className="h-3.5 w-3.5" />
                {t.label}
                <button
                  type="button"
                  aria-label={`Close ${t.label}`}
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(t.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ) : (
              <div
                key={t.id}
                draggable
                onDragStart={() => (dragTabIdRef.current = t.id)}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => handleTabDrop(t.id)}
                onClick={() => setActiveTabId(t.id)}
                className={cn(
                  "group flex shrink-0 cursor-grab items-center gap-1.5 rounded-md px-3 py-1 text-sm active:cursor-grabbing",
                  t.id === activeTabId
                    ? "bg-accent text-accent-foreground"
                    : "cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )}
              >
                <Globe2 className="h-3.5 w-3.5" />
                {t.label}
                <button
                  type="button"
                  aria-label={`Close ${t.label}`}
                  className="opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(t.id);
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
        {tabs.map((t) =>
          t.kind === "chat" ? (
            <ChatPane
              key={t.id}
              tabId={t.id}
              active={t.id === activeTabId}
              agentId={t.agentId}
              chatableAgents={chatableAgents}
              onAgentChange={(agentId) => handleAgentChangeForTab(t.id, agentId)}
              historyCollapsed={Boolean(t.historyCollapsed)}
              artifactsOpen={Boolean(t.artifactsOpen)}
              workingDir={workingDir}
            />
          ) : t.kind === "terminal" ? (
            <div key={t.id} className={cn("absolute inset-0 p-2", t.id !== activeTabId && "hidden")}>
              <TerminalPane sessionId={t.id} command={t.command} cwd={t.cwd} active={t.id === activeTabId} />
            </div>
          ) : (
            <div key={t.id} className={cn("absolute inset-0", t.id !== activeTabId && "hidden")}>
              <WebAppPane
                url={t.url}
                products={products}
                onUrlChange={(url) => updateWebTabUrl(t.id, url)}
              />
            </div>
          )
        )}

        {tabs.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-center text-muted-foreground">
            <div>
              <MessageSquare className="mx-auto mb-3 h-10 w-10" />
              <p className="font-medium">No tabs open</p>
              <p className="text-sm">Start a conversation or open a terminal using the buttons above.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
