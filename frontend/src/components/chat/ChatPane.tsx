/** ChatPane -- the single chat component (extracted verbatim from
 * pages/workspace/index.tsx on 2026-07-07). The Workspace consumes it for
 * its chat tabs; other pages (Docs, ...) open it inside a side drawer to
 * assist creation/filling, always with the same behavior: queue, SSE
 * streaming, elevation approvals, Telegram-style processing feed, voice.
 * One component, no forks -- fix bugs here, every surface gets them. */
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowUp,
  AudioLines,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  Eraser,
  Folder,
  FolderKanban,
  Loader2,
  Mic,
  MoreVertical,
  Paperclip,
  Pencil,
  Pin,
  PinOff,
  Plug,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ComposerShell } from "@/components/chat/ComposerShell";
import { ImprovePromptDialog } from "@/components/chat/ImprovePromptDialog";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Markdown } from "@/components/Markdown";
import { TestApplicationDialog } from "@/components/chat/TestApplicationDialog";
import { useFsList, type FsEntry } from "@/hooks/useTerminalBrowse";
import { getToken } from "@/lib/api";
import {
  getAssistantFileDragData,
  loadAssistantDraggedFile,
} from "@/lib/assistantFileDrag";
import { cn } from "@/lib/utils";
import { type Agent, useAgents, useAgentMcpServers } from "@/hooks/useAgent";
import { useActiveTurn } from "@/hooks/useActiveTurn";
import { useChatLanguage } from "@/hooks/useChatLanguage";
import { useClickOutside } from "@/hooks/useClickOutside";
import { usePromptCommands, type PromptCommand } from "@/hooks/usePromptCommands";
import { useDemands } from "@/hooks/useDemands";
import { useProjects } from "@/hooks/useProject";
import { useQueryClient } from "@tanstack/react-query";
import {
  chatKeys,
  useChatArtifacts,
  useChatMessages,
  useDeleteChatArtifact,
  useExecChatCommand,
  useSearchChatArtifacts,
  useDeleteChatMessage,
  useApproveChat,
  useSendChatMessage,
  useStreamChatMessage,
  useStreamImprovePrompt,
  useTranscribeAudio,
  downloadChatArtifact,
  type ChatMessage,
  type ChatSession,
  type ChatGroup,
  type ChatStreamEvent,
} from "@/hooks/useChat";
import { useChatSessionViewModel } from "@/hooks/useChatSessionViewModel";

// Tabs/active-tab are persisted (not just in-memory state) so that
// navigating to another page and back to Workspace recreates the same tabs
// with the same ids -- TerminalPane then reconnects using those ids as its
// tmux session name, re-attaching to the still-running session instead of
// losing it. See TerminalPane.tsx and host-bridge/app.py's terminal_ws.


// Attached-file and draft-text staging per chat tab, kept outside React
// state. Navigating to another page and back to Workspace remounts
// ChatTabPanel from scratch (unlike switching tabs within Workspace, which
// just CSS-hides it), so plain useState loses the pending image/draft; a
// File can't round-trip through the tabs' localStorage persistence either,
// and composer text isn't wired into it. These module-level maps survive
// that remount for the lifetime of the SPA session.
const attachmentByTabId = new Map<string, File[]>();
const composerTextByTabId = new Map<string, string>();

// Streams abertos por esta aba. É o único estado em voo que pertence mesmo
// ao cliente -- a conexão. O que a execução já produziu (passos, texto,
// aprovação pendente) pertence ao servidor desde 2026-08-13 e é lido de lá
// via useActiveTurn, para sobreviver a um F5, a um travamento da aba e a
// abrir a mesma conversa em outra máquina.
const abortByTabId = new Map<string, AbortController[]>();

/** Solta o stream que esta aba mantinha aberto. Fechar a aba é o único
 * momento em que abandonar a execução é a intenção -- e ainda assim isto
 * encerra só a conexão deste cliente: o turno vive no servidor. */
export function clearChatTabQueue(tabId: string): void {
  abortByTabId.get(tabId)?.forEach((controller) => controller.abort());
  abortByTabId.delete(tabId);
}

/** Drop a closed tab's staged draft/attachments (the Workspace calls this
 * when the user closes a chat tab -- the maps are module-private here). */
export function clearChatTabStaging(tabId: string): void {
  attachmentByTabId.delete(tabId);
  composerTextByTabId.delete(tabId);
  clearChatTabQueue(tabId);
}

// Composer auto-grow ceiling -- past this it scrolls internally instead
// of taking over the message area.
const COMPOSER_MAX_HEIGHT_PX = 240;

// A primingMessage turn is persisted by the backend with BOTH sides (the
// context sent and the agent's ack) wrapped in these markers (chat.py's
// _wrap_hidden, mirrored here) -- visibleMessages drops any message that is
// nothing but such a block, and strips a leading block off messages that
// carry user text after it (the older piggyback format), so internal
// instructions never render in the transcript.
const HIDDEN_CONTEXT_RE = /^\[\[forgehub:contexto-interno\]\]\n[\s\S]*?\n\[\[\/forgehub:contexto-interno\]\]\s*/;
/** Exported for ChannelPane.tsx's own live tool-step trail (2026-08-06,
 * Marcelo: "traz o passo a passo de ferramentas em tempo real também") --
 * same shape QueueStepsList/FinishedStepsTrail below already render. */
export type ChatQueueStep = {
  id: string;
  name: string;
  label: string;
  detail?: string;
  done: boolean;
  /** Set for mcp__forgehub_messages__send_agent_message -- renders a live
   * SubagentStatusCard instead of a plain checkmark line (2026-07-28). */
  demandNumber?: number;
};

/** Heuristic warning only (Fase 5 item 5, 2026-07-28) -- a session bound
 * to ForgeHub's own checkout, sending a command that looks like it
 * restarts the very backend/frontend serving this page, risks dropping
 * this turn's own connection mid-flight (see useChat.ts's connect-retry
 * comment for why a retry can't always save it). Advisory only, never
 * blocks sending -- false positives/negatives are both fine here. */
const SELF_RESTART_COMMAND_RE =
  /\b(docker\s+compose\s+(up|restart|down)|systemctl\s+restart|\.?\/?dev\.sh\s+restart|pm2\s+restart|supervisorctl\s+restart|kill(all)?\s+.*(uvicorn|vite|node))\b/i;

function isForgeHubRepoPath(path: string | null | undefined): boolean {
  return Boolean(path && /forgehub/i.test(path));
}

function toolEmoji(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("search")) return "🔍";
  if (n.includes("read")) return "📖";
  if (n.includes("write") || n.includes("edit")) return "📝";
  if (n.includes("term") || n.includes("shell") || n.includes("bash") || n.includes("exec")) return "💻";
  if (n.includes("code") || n.includes("python")) return "🐍";
  if (n.includes("web") || n.includes("http") || n.includes("fetch") || n.includes("browser")) return "🌐";
  if (n.includes("memory") || n.includes("recall") || n.includes("think")) return "🧠";
  if (n.includes("image") || n.includes("vision")) return "🖼️";
  if (n.includes("file")) return "📂";
  return "🔧";
}

function isTerminalTool(name: string): boolean {
  const n = name.toLowerCase();
  return n.includes("term") || n.includes("shell") || n.includes("bash") || n.includes("exec");
}

/** Telegram-style "digitando" ellipsis. */
function TypingDots() {
  return (
    <span className="inline-flex gap-0.5" aria-hidden>
      <span className="animate-bounce">·</span>
      <span className="animate-bounce [animation-delay:150ms]">·</span>
      <span className="animate-bounce [animation-delay:300ms]">·</span>
    </span>
  );
}

/** Live status for a message just created via
 * mcp__forgehub_messages__send_agent_message mid-conversation (see
 * FORGEHUB_MESSAGE.md's "Delegating to another agent mid-conversation").
 * Reuses useDemands() -- already shared/cached via react-query and already
 * polls faster (3s) while anything is in flight -- rather than a bespoke
 * fetch-by-number call, so this card updates on the same cadence as the
 * Messages page itself. */
function SubagentStatusCard({ number }: { number: number }) {
  const { t } = useTranslation(["chat", "demands"]);
  const { data: demands } = useDemands();
  const { data: agents } = useAgents();
  const demand = useMemo(() => demands?.find((d) => d.number === number), [demands, number]);
  const targetAgent = useMemo(
    () => agents?.find((a) => a.id === demand?.target_agent_id),
    [agents, demand?.target_agent_id]
  );

  if (!demand) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-2.5 py-1.5 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
        {t("queue.subagentLoading")}
      </div>
    );
  }

  const status = demand.dispatch_status;
  return (
    <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/20 px-2.5 py-1.5 text-xs">
      {status === "completed" ? (
        <CheckCircle2 className="h-3 w-3 shrink-0 text-emerald-600" />
      ) : status === "failed" ? (
        <AlertCircle className="h-3 w-3 shrink-0 text-destructive" />
      ) : (
        <Loader2 className="h-3 w-3 shrink-0 animate-spin text-muted-foreground" />
      )}
      <span className="truncate">
        {t("queue.subagentDelegatedTo", { number: demand.number, agent: targetAgent?.name ?? "?" })}
        {" — "}
        {status ? t(`dispatch.status.${status}`, { ns: "demands" }) : t("dispatch.status.pending", { ns: "demands" })}
      </span>
    </div>
  );
}

/** The tool-call trail for one turn (search/read/write/shell/... steps) --
 * shared by the live "processing" queue item and, once that turn finishes,
 * by FinishedStepsTrail below. Extracted so the trail is rendered
 * identically in both places rather than duplicated (2026-07-29: the
 * detail must survive past completion instead of being thrown away with
 * the queue item, see finishedStepsByMessageId). */
export function QueueStepsList({ steps }: { steps: ChatQueueStep[] }) {
  return (
    <>
      {steps.map((step) => {
        // Telegram-gateway style: terminal/code steps show the tool line
        // plus the EXACT command in a `shell` block (`detail` is verbatim
        // from tool_args; the label is an 80-char elision kept only as
        // fallback). Every other tool is a one-liner with its emoji.
        const isBlockTool = isTerminalTool(step.name) || step.name.toLowerCase().includes("code");
        const blockText = isBlockTool
          ? step.detail ?? (step.label !== step.name ? step.label.replace(/^Running\s+/i, "") : null)
          : null;
        return (
          <div key={step.id} className="space-y-1">
            <p className="flex items-center gap-2 text-xs text-muted-foreground" title={step.detail ?? step.label}>
              {step.done ? (
                <Check className="h-3 w-3 shrink-0 text-emerald-500" />
              ) : (
                <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
              )}
              <span aria-hidden>{toolEmoji(step.name)}</span>
              {blockText ? step.name : step.label}
            </p>
            {blockText && (
              <div className="ml-5 max-w-lg overflow-hidden rounded-md border border-border/60 bg-muted/50">
                <p className="border-b border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground">shell</p>
                <code className="block max-h-32 overflow-auto whitespace-pre-wrap break-all px-2 py-1 font-mono text-xs">
                  {blockText}
                </code>
              </div>
            )}
            {step.demandNumber != null && (
              <div className="ml-5 max-w-sm">
                <SubagentStatusCard number={step.demandNumber} />
              </div>
            )}
          </div>
        );
      })}
    </>
  );
}

/** The steps trail kept around after its turn finished -- rendered right
 * above the persisted assistant reply it belongs to, collapsible so a long
 * trail doesn't push the actual answer off screen, but never gone: this is
 * the "process detail and response are separate, don't erase the process
 * detail" behavior (2026-07-29, Marcelo). */
export function FinishedStepsTrail({ steps }: { steps: ChatQueueStep[] }) {
  const { t } = useTranslation(["chat"]);
  const [open, setOpen] = useState(true);
  if (steps.length === 0) return null;
  return (
    <div className="mb-1 max-w-[85%] space-y-1 rounded-lg border border-border/60 bg-muted/20 p-2">
      <button
        type="button"
        className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        {t("queue.processDetails")}
      </button>
      {open && <QueueStepsList steps={steps} />}
    </div>
  );
}

type ChatQueueApproval = { streamId: string; command?: string; description?: string; patternKeys?: string[] };

type ChatQueueItem = {
  id: string;
  content: string;
  attachmentName: string | null;
  files: File[];
  liveText: string;
  steps: ChatQueueStep[];
  status: "queued" | "processing" | "error";
  error?: string;
  approval: ChatQueueApproval | null;
  abortController: AbortController | null;
  /** True for a "Regenerate" request: reuses the last user message's text
   * without persisting a duplicate user turn, and its synthetic user
   * bubble is suppressed in the queue render (the real one is already in
   * `messages`). */
  isRegenerate?: boolean;
  /** Set when this turn was routed to a "#Agente"-mentioned agent other
   * than the tab's own -- shown in the processing card instead of the
   * generic "Pensando..." label, and passed as target_agent_id. */
  targetAgentId?: string;
  targetAgentName?: string;
  /** True for the 2nd+ mentioned-agent item from the same user input --
   * the first one already persisted the shared user message. */
  skipUserMessage?: boolean;
  /** True for an internal priming turn (see the primingMessage prop):
   * rendered as nothing at all while it runs (unless it errors), sent with
   * hidden=true so the backend persists both sides wrapped in the
   * HIDDEN_CONTEXT markers and the transcript drops them. */
  hidden?: boolean;
  /** True for a "!command" raw bash execution -- no agent/LLM call, see
   * exec_chat_command. content keeps the "!" prefix. */
  isExec?: boolean;
  /** Date.now() when this item entered "processing" -- powers the live
   * "Pensando há mm:ss" ticker (see ThinkingLabel). */
  startedAt?: number;
};

/** Exported for ChannelPane.tsx's own per-agent "working" ticker (2026-08-06,
 * Marcelo: "precisa ver a quantidade de processos em paralelo... com o
 * detalhamento de cada agente ao clicar as execuções em paralelo. O que
 * ficou determinado no chat da conversation") -- same mm:ss formatting,
 * reused rather than re-derived; the ticker component itself isn't reused
 * as-is since the channel's chip markup needs a different wrapper element. */
export function formatThinkingDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Ticks every second while processing -- shown above the steps/Parar
 * button, same spot the frozen "Pensou por mm:ss" occupies once the
 * reply is persisted (see MessageBubble). */
function LiveThinkingLabel({ startedAt }: { startedAt: number }) {
  const { t } = useTranslation("chat");
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const elapsed = Math.max(0, Math.round((now - startedAt) / 1000));
  return (
    <p className="text-xs text-muted-foreground">
      {t("thinking.working", { duration: formatThinkingDuration(elapsed) })}
    </p>
  );
}

/** Finds every "#Agente" mention in text, matching the longest agent name
 * available (so multi-word names like "Hermes UX" aren't cut short at the
 * first space), case-insensitive, deduped by agent id. */
function extractMentionedAgents(text: string, agents: Agent[]): Agent[] {
  const sortedByLongestName = [...agents].sort((a, b) => b.name.length - a.name.length);
  const found: Agent[] = [];
  for (const match of text.matchAll(/#/g)) {
    const rest = text.slice((match.index ?? 0) + 1);
    const restLower = rest.toLowerCase();
    for (const agent of sortedByLongestName) {
      const nameLower = agent.name.toLowerCase();
      if (!restLower.startsWith(nameLower)) continue;
      const nextChar = rest[agent.name.length];
      if (nextChar === undefined || /[\s.,!?;:]/.test(nextChar)) {
        found.push(agent);
        break;
      }
    }
  }
  return [...new Map(found.map((a) => [a.id, a])).values()];
}

function AgentPickerButton({
  agents,
  selectedAgentId,
  onSelect,
}: {
  agents: Agent[];
  selectedAgentId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation("chat");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const selected = agents.find((a) => a.id === selectedAgentId);

  useClickOutside(containerRef, () => setOpen(false), open);

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="ghost"
        size="icon"
        aria-label={selected ? t("agentPicker.agentLabel", { name: selected.name }) : t("agentPicker.selectAgent")}
        title={selected?.name ?? t("agentPicker.selectAgent")}
        onClick={() => setOpen((v) => !v)}
      >
        <Bot className="h-4 w-4" />
      </Button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 max-h-72 w-56 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md">
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => {
                onSelect(a.id);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground",
                a.id === selectedAgentId && "bg-accent text-accent-foreground"
              )}
            >
              <Bot className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{a.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Assigns/clears the CURRENT session's Project (Fase 5) -- lives inside
 * the chat history panel itself (see its render site: the Chats sidebar
 * header), deliberately separate from the generic filesystem
 * WorkingDirPicker used by the Workspace toolbar/"!command" (that one is
 * untouched -- this is project *management*, not folder browsing).
 * Backed by ChatSession.working_directory_path under the hood (a plain
 * path, not a FK -- see the model's docstring), but the picker itself
 * only ever offers registered Projects, never an arbitrary path. Disabled
 * with no active session -- there is nothing to PATCH yet (a brand new
 * tab creates its session lazily on first send). */
function SessionProjectPicker({
  currentPath,
  disabled,
  onSelect,
}: {
  currentPath: string | null | undefined;
  disabled: boolean;
  onSelect: (path: string | null) => void;
}) {
  const { t } = useTranslation("chat");
  const { data: projects } = useProjects();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);

  const projectsWithPath = (projects ?? []).filter(
    (p): p is typeof p & { working_directory_path: string } => Boolean(p.working_directory_path)
  );
  const current = projectsWithPath.find((p) => p.working_directory_path === currentPath);

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="ghost"
        size="sm"
        disabled={disabled}
        title={current ? current.working_directory_path : t("sessionFolder.pickProject")}
        onClick={() => setOpen((v) => !v)}
        className="h-6 max-w-full gap-1 px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
      >
        <FolderKanban className="h-3 w-3 shrink-0" />
        <span className="max-w-[8rem] truncate">{current ? current.name : t("sessionFolder.noProject")}</span>
      </Button>
      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 max-h-72 w-64 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md">
          <button
            type="button"
            onClick={() => {
              onSelect(null);
              setOpen(false);
            }}
            className="flex w-full items-center px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {t("sessionFolder.noProject")}
          </button>
          {projectsWithPath.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                onSelect(p.working_directory_path);
                setOpen(false);
              }}
              className="flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left hover:bg-accent hover:text-accent-foreground"
            >
              <span className="truncate text-sm">{p.name}</span>
              <span className="truncate text-[10px] text-muted-foreground">{p.working_directory_path}</span>
            </button>
          ))}
          {projectsWithPath.length === 0 && (
            <p className="px-3 py-2 text-xs italic text-muted-foreground">{t("sessionFolder.noProjectsRegistered")}</p>
          )}
        </div>
      )}
    </div>
  );
}

/** Per-chat-item "..." menu: rename / pin / delete. Replaces the lone
 * hover-only trash icon so the row doesn't get cluttered with separate
 * icons per action. */
type ProjectWithPath = { id: string; name: string; working_directory_path: string };

function ChatItemMenu({
  session,
  projects,
  groups,
  onRename,
  onTogglePin,
  onDelete,
  onMoveToProject,
  onMoveToGroup,
  onCreateGroupAndMove,
}: {
  session: ChatSession;
  projects: ProjectWithPath[];
  groups: ChatGroup[];
  onRename: () => void;
  onTogglePin: () => void;
  onDelete: () => void;
  onMoveToProject: (path: string | null) => void;
  onMoveToGroup: (groupId: string | null) => void;
  onCreateGroupAndMove: (name: string) => void;
}) {
  const { t } = useTranslation("chat");
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"main" | "project" | "group">("main");
  const [newGroupName, setNewGroupName] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  useClickOutside(
    containerRef,
    () => {
      setOpen(false);
      setView("main");
    },
    open
  );

  function close() {
    setOpen(false);
    setView("main");
    setNewGroupName("");
  }

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <button
        type="button"
        aria-label={t("itemMenu.chatOptions")}
        title={t("itemMenu.chatOptions")}
        className="rounded-md p-1 opacity-0 hover:bg-accent group-hover:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <MoreVertical className="h-3.5 w-3.5" />
      </button>
      {open && view === "main" && (
        <div
          className="absolute right-0 top-full z-10 mt-1 w-44 overflow-hidden rounded-md border border-border bg-card py-1 shadow-md"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={() => {
              close();
              onRename();
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
            {t("itemMenu.rename")}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={() => {
              close();
              onTogglePin();
            }}
          >
            {session.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
            {session.pinned ? t("itemMenu.unpin") : t("itemMenu.pin")}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={() => setView("project")}
          >
            <FolderKanban className="h-3.5 w-3.5" />
            {t("itemMenu.moveToProject")}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={() => setView("group")}
          >
            <Folder className="h-3.5 w-3.5" />
            {t("itemMenu.moveToGroup")}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-destructive hover:bg-accent"
            onClick={() => {
              close();
              onDelete();
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t("itemMenu.delete")}
          </button>
        </div>
      )}
      {open && view === "project" && (
        <div
          className="absolute right-0 top-full z-10 mt-1 max-h-72 w-56 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            onClick={() => setView("main")}
          >
            {t("itemMenu.back")}
          </button>
          <button
            type="button"
            className="flex w-full items-center px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            onClick={() => {
              close();
              onMoveToProject(null);
            }}
          >
            {t("sessionFolder.noProject")}
          </button>
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              className="flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                close();
                onMoveToProject(p.working_directory_path);
              }}
            >
              <span className="truncate text-sm">{p.name}</span>
            </button>
          ))}
          {projects.length === 0 && (
            <p className="px-3 py-2 text-xs italic text-muted-foreground">{t("sessionFolder.noProjectsRegistered")}</p>
          )}
        </div>
      )}
      {open && view === "group" && (
        <div
          className="absolute right-0 top-full z-10 mt-1 max-h-80 w-56 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            onClick={() => setView("main")}
          >
            {t("itemMenu.back")}
          </button>
          <button
            type="button"
            className="flex w-full items-center px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            onClick={() => {
              close();
              onMoveToGroup(null);
            }}
          >
            {t("groups.noGroup")}
          </button>
          {groups.map((g) => (
            <button
              key={g.id}
              type="button"
              className="flex w-full items-center px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                close();
                onMoveToGroup(g.id);
              }}
            >
              <span className="truncate">{g.name}</span>
            </button>
          ))}
          <div className="flex items-center gap-1 border-t border-border px-2 py-1.5">
            <input
              value={newGroupName}
              onChange={(e) => setNewGroupName(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              onKeyDown={(e) => {
                if (e.key === "Enter" && newGroupName.trim()) {
                  onCreateGroupAndMove(newGroupName.trim());
                  close();
                }
              }}
              placeholder={t("groups.newGroupPlaceholder")}
              className="h-7 min-w-0 flex-1 rounded-md border border-border bg-transparent px-2 text-xs outline-none focus:border-primary"
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0"
              disabled={!newGroupName.trim()}
              onClick={() => {
                if (!newGroupName.trim()) return;
                onCreateGroupAndMove(newGroupName.trim());
                close();
              }}
            >
              <Plus className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Gemini-style "model picker" pill, repurposed to pick the agent -- sits
 * inside the composer bar, right before the mic button. */
function AgentSelectorPill({
  agents,
  selectedAgentId,
  onSelect,
}: {
  agents: Agent[];
  selectedAgentId: string;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation("chat");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const selected = agents.find((a) => a.id === selectedAgentId);

  useClickOutside(containerRef, () => setOpen(false), open);

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded-full bg-background px-3 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground"
      >
        <span className="max-w-[8rem] truncate">{selected?.name ?? t("agentPicker.agentFallback")}</span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute bottom-full right-0 z-10 mb-2 max-h-72 w-60 overflow-y-auto rounded-md border border-border bg-card py-1 shadow-md">
          {agents.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => {
                onSelect(a.id);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            >
              <Check className={cn("h-3.5 w-3.5 shrink-0", a.id !== selectedAgentId && "opacity-0")} />
              <span className="truncate">{a.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Shows the MCP servers configured for the tab's currently selected agent
 * -- lets the user check what tools the agent has available without
 * leaving the chat to open the Agent or MCP Servers page. Read-only here;
 * editing stays on those pages. */
function AgentMcpInfoButton({ agentId }: { agentId: string }) {
  const { t } = useTranslation("chat");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const { data, isLoading, isError } = useAgentMcpServers(open ? agentId : undefined);

  useClickOutside(containerRef, () => setOpen(false), open);

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-full"
        aria-label={t("mcpInfo.viewMcps")}
        title={t("mcpInfo.viewMcps")}
        onClick={() => setOpen((v) => !v)}
      >
        <Plug className="h-4 w-4" />
      </Button>
      {open && (
        <div className="absolute bottom-full right-0 z-10 mb-2 max-h-72 w-64 overflow-y-auto rounded-md border border-border bg-card p-2 shadow-md">
          <p className="px-1 pb-1 text-xs font-medium text-muted-foreground">{t("mcpInfo.title")}</p>
          {isLoading && <p className="px-1 py-2 text-sm text-muted-foreground">{t("mcpInfo.loading")}</p>}
          {isError && <p className="px-1 py-2 text-sm text-destructive">{t("mcpInfo.error")}</p>}
          {!isLoading && !isError && data?.error && (
            <p className="px-1 py-2 text-sm text-destructive">{data.error}</p>
          )}
          {!isLoading && !isError && !data?.error && data && data.servers.length === 0 && (
            <p className="px-1 py-2 text-sm text-muted-foreground">{t("mcpInfo.empty")}</p>
          )}
          {!isLoading &&
            !isError &&
            data?.servers.map((server) => (
              <div key={server.name} className="flex items-center justify-between gap-2 rounded-md px-1 py-1.5 text-sm">
                <span className="truncate">{server.name}</span>
                {data.supports_toggle && (
                  <span
                    className={cn(
                      "shrink-0 rounded-full px-2 py-0.5 text-[11px]",
                      server.enabled
                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                        : "bg-muted text-muted-foreground",
                    )}
                  >
                    {server.enabled ? t("mcpInfo.enabled") : t("mcpInfo.disabled")}
                  </span>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

/** Gemini-style "+" attachment menu -- only one action applies in our
 * scope (no Drive/image/video generation), but kept as a menu since
 * that's the requested look. */
/** Discoverability legend for the composer's trigger characters -- lets a
 * user who doesn't know "@"/"/"/"#"/"$" exist find them from the "+" menu
 * instead of stumbling onto them by typing. Each entry inserts its trigger
 * char and opens the same picker typing it would. */
export function AttachMenuButton({
  onPickFile,
  onInsertTrigger,
  enabledTriggers,
}: {
  onPickFile: () => void;
  onInsertTrigger: (char: "/" | "@" | "#" | "$" | "!") => void;
  /** Restricts which trigger rows render -- defaults to all five
   * (ChatPane's existing behavior, unchanged). ChannelPane passes a
   * shorter list: "!" (direct bash) has no single owning agent/session in
   * a multi-agent room, so it's left out rather than shown and silently
   * doing nothing special (2026-08-06, see ChannelPane.tsx's own usage). */
  enabledTriggers?: ("/" | "@" | "#" | "$" | "!")[];
}) {
  const { t } = useTranslation("chat");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useClickOutside(containerRef, () => setOpen(false), open);

  const allTriggers: { char: "/" | "@" | "#" | "$" | "!"; labelKey: string }[] = [
    { char: "/", labelKey: "attachMenu.hermesCommand" },
    { char: "@", labelKey: "attachMenu.directoryFiles" },
    { char: "#", labelKey: "attachMenu.agents" },
    { char: "$", labelKey: "attachMenu.artifacts" },
    { char: "!", labelKey: "attachMenu.directBashCommand" },
  ];
  const triggers = enabledTriggers
    ? allTriggers.filter((trigger) => enabledTriggers.includes(trigger.char))
    : allTriggers;

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-full"
        aria-label={t("attachMenu.addAttachment")}
        onClick={() => setOpen((v) => !v)}
      >
        <Plus className="h-4 w-4" />
      </Button>
      {open && (
        <div className="absolute bottom-full left-0 z-10 mb-2 w-52 rounded-md border border-border bg-card py-1 shadow-md">
          <button
            type="button"
            onClick={() => {
              onPickFile();
              setOpen(false);
            }}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
          >
            <Paperclip className="h-4 w-4" />
            {t("attachMenu.sendFile")}
          </button>
          <div className="my-1 border-t border-border" />
          {triggers.map((trigger) => (
            <button
              key={trigger.char}
              type="button"
              onClick={() => {
                onInsertTrigger(trigger.char);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            >
              <span className="flex h-4 w-4 items-center justify-center font-mono text-xs text-muted-foreground">
                {trigger.char}
              </span>
              {t(trigger.labelKey)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export interface MentionFilePickerHandle {
  moveActive: (delta: number) => void;
  confirmActive: () => void;
}

/** "@" mention popover -- browse host files/dirs (via the same bridge used by
 * the terminal working-dir picker) and insert a path reference into the
 * composer, instead of inlining file content client-side (the agent already
 * has filesystem tools to read whatever path it's given).
 *
 * Keyboard nav (Arrow Up/Down + Enter) is driven from the composer textarea
 * via this imperative handle -- the textarea keeps focus while "@" is open
 * (so the user can keep typing the rest of the message), so the picker can't
 * own its own onKeyDown. */
export const MentionFilePicker = forwardRef<
  MentionFilePickerHandle,
  { rootPath?: string; onSelectPath: (path: string) => void; onClose: () => void }
>(function MentionFilePicker({ rootPath, onSelectPath, onClose }, ref) {
  const { t } = useTranslation("chat");
  const [path, setPath] = useState<string | undefined>(rootPath);
  const [activeIndex, setActiveIndex] = useState(0);
  const { data, isLoading } = useFsList(path, true);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, onClose);

  const entries = useMemo(() => data?.entries ?? [], [data?.entries]);

  useEffect(() => {
    setActiveIndex(0);
  }, [data?.path]);

  function selectEntry(entry: FsEntry) {
    if (entry.type === "dir") {
      setPath(entry.path);
    } else {
      onSelectPath(entry.path);
    }
  }

  useImperativeHandle(ref, () => ({
    moveActive(delta: number) {
      setActiveIndex((i) => {
        if (entries.length === 0) return i;
        return Math.max(0, Math.min(entries.length - 1, i + delta));
      });
    },
    confirmActive() {
      const entry = entries[activeIndex];
      if (entry) selectEntry(entry);
    },
  }));

  return (
    <div
      ref={containerRef}
      className="absolute bottom-full left-0 z-20 mb-2 max-h-72 w-80 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
    >
      <div className="sticky top-0 flex items-center justify-between gap-2 border-b border-border bg-card px-2 py-1.5">
        <p className="truncate text-xs text-muted-foreground" title={data?.path}>
          {data?.path ?? "..."}
        </p>
        <div className="flex items-center gap-1 shrink-0">
          {data?.path && (
            <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => onSelectPath(data.path)}>
              {t("mentionFilePicker.useFolder")}
            </Button>
          )}
          {data?.parent && (
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              aria-label={t("mentionFilePicker.parentFolder")}
              onClick={() => setPath(data.parent!)}
            >
              <ArrowUp className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
      {isLoading && <p className="px-3 py-3 text-xs text-muted-foreground">{t("mentionFilePicker.loading")}</p>}
      {entries.map((entry, index) => (
        <button
          key={entry.path}
          type="button"
          className={cn(
            "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-accent hover:text-accent-foreground",
            index === activeIndex && "bg-accent text-accent-foreground"
          )}
          onClick={() => selectEntry(entry)}
          onMouseEnter={() => setActiveIndex(index)}
        >
          {entry.type === "dir" ? (
            <Folder className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <Paperclip className="h-3.5 w-3.5 shrink-0" />
          )}
          <span className="truncate">{entry.name}</span>
        </button>
      ))}
      {data && data.entries.length === 0 && !isLoading && (
        <p className="px-3 py-3 text-xs italic text-muted-foreground">{t("mentionFilePicker.emptyFolder")}</p>
      )}
    </div>
  );
});

/** Slash commands ForgeHub actually executes via Hermes's own process_command()
 * dispatcher (see host-bridge/hermes_stream.py SAFE_SLASH_COMMANDS) instead of
 * forwarding the text to the LLM -- keep this list in sync with that one.
 * `description` holds an i18next key (chat.slashCommands.*), not literal
 * text -- SlashCommandPicker translates it at render time. */
const SAFE_SLASH_COMMANDS: { command: string; description: string }[] = [
  { command: "/model", description: "slashCommands.model" },
  { command: "/status", description: "slashCommands.status" },
  { command: "/help", description: "slashCommands.help" },
  { command: "/version", description: "slashCommands.version" },
  { command: "/title", description: "slashCommands.title" },
  { command: "/profile", description: "slashCommands.profile" },
  { command: "/config", description: "slashCommands.config" },
  { command: "/toolsets", description: "slashCommands.toolsets" },
  { command: "/platforms", description: "slashCommands.platforms" },
  { command: "/plugins", description: "slashCommands.plugins" },
];

/** Handled entirely client-side (never sent as a message) -- unlike
 * SAFE_SLASH_COMMANDS, which forward to Hermes's process_command(). Same
 * i18next-key convention as SAFE_SLASH_COMMANDS above. */
const LOCAL_SLASH_COMMANDS: { command: string; description: string }[] = [
  { command: "/new", description: "slashCommands.new" },
  { command: "/testar", description: "slashCommands.testar" },
];

export type SlashCommandItem =
  | { kind: "local"; command: string; description: string }
  | { kind: "hermes"; command: string; description: string }
  | { kind: "prompt"; command: string; description: string; prompt: string };

export interface SlashCommandPickerHandle {
  moveActive: (delta: number) => void;
  confirmActive: () => void;
}

/** Keyboard nav (Arrow Up/Down + Enter) is driven from the composer textarea
 * via this imperative handle, same pattern as MentionFilePickerHandle -- the
 * textarea keeps focus while "/" is open. */
export const SlashCommandPicker = forwardRef<
  SlashCommandPickerHandle,
  {
    promptCommands: PromptCommand[];
    onSelect: (item: SlashCommandItem) => void;
    onClose: () => void;
    /** ChannelPane opts out of both -- /model, /new etc. forward to (or
     * act on) a single agent's own Hermes CLI session, which has no
     * well-defined meaning addressed to a whole multi-agent channel.
     * Default true/true preserves ChatPane's existing behavior exactly
     * (2026-08-06, see ChannelPane.tsx's own SlashCommandPicker usage). */
    includeLocal?: boolean;
    includeHermes?: boolean;
    /** "up" (default) opens above the field, anchored to its bottom edge --
     * right for a composer pinned to the bottom of the screen. "down" opens
     * below instead, for a field near the top of its container where
     * "up" would render off-screen/behind other UI (2026-08-07, Marcelo:
     * "não dá para ver. Precisa colocar o menu para baixo" -- the Prompt
     * field in ImprovePromptDialog, which sits right under the modal's
     * title). */
    placement?: "up" | "down";
  }
>(function SlashCommandPicker(
  { promptCommands, onSelect, onClose, includeLocal = true, includeHermes = true, placement = "up" },
  ref
) {
  const { t } = useTranslation("chat");
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, onClose);
  const items = useMemo<SlashCommandItem[]>(
    () => [
      ...(includeLocal ? LOCAL_SLASH_COMMANDS.map((cmd) => ({ kind: "local" as const, ...cmd })) : []),
      ...(includeHermes ? SAFE_SLASH_COMMANDS.map((cmd) => ({ kind: "hermes" as const, ...cmd })) : []),
      ...promptCommands.map((cmd) => ({
        kind: "prompt" as const,
        command: `/${cmd.name}`,
        description: cmd.description,
        prompt: cmd.prompt,
      })),
    ],
    [promptCommands, includeLocal, includeHermes]
  );

  useImperativeHandle(ref, () => ({
    moveActive(delta: number) {
      setActiveIndex((i) => Math.max(0, Math.min(items.length - 1, i + delta)));
    },
    confirmActive() {
      const cmd = items[activeIndex];
      if (cmd) onSelect(cmd);
    },
  }), [activeIndex, items, onSelect]);

  return (
    <div
      ref={containerRef}
      className={cn(
        "absolute left-0 z-20 max-h-80 w-80 overflow-y-auto rounded-lg border border-border bg-card shadow-lg",
        placement === "down" ? "top-full mt-2" : "bottom-full mb-2"
      )}
    >
      {items.map((cmd, index) => (
        <button
          key={cmd.command}
          type="button"
          className={cn(
            "flex w-full flex-col items-start gap-0.5 px-3 py-1.5 text-left hover:bg-accent hover:text-accent-foreground",
            index === activeIndex && "bg-accent text-accent-foreground"
          )}
          onClick={() => onSelect(cmd)}
          onMouseEnter={() => setActiveIndex(index)}
        >
          <span className="flex w-full items-center justify-between gap-2">
            <span className="text-xs font-medium">{cmd.command}</span>
            <span className="rounded border border-border px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
              {cmd.kind === "local" ? t("slashCommands.kindLocal") : cmd.kind === "hermes" ? t("slashCommands.kindHermes") : t("slashCommands.kindPrompt")}
            </span>
          </span>
          <span className="text-[11px] text-muted-foreground">{cmd.kind === "prompt" ? cmd.description : t(cmd.description)}</span>
        </button>
      ))}
    </div>
  );
});

export interface AgentMentionPickerHandle {
  moveActive: (delta: number) => void;
  confirmActive: () => void;
}

/** "#Agente" picker -- routes a message directly to a different agent than
 * the tab's own (see stream_chat_message's target_agent_id), bypassing
 * Athos-style orchestration entirely. Filters live as you type after "#",
 * same keyboard-nav pattern as the other two pickers. */
export const AgentMentionPicker = forwardRef<
  AgentMentionPickerHandle,
  {
    agents: Agent[];
    query: string;
    onSelect: (agent: Agent) => void;
    onClose: () => void;
    /** See SlashCommandPicker's own `placement` docstring -- same "up"
     * (default, composer pinned to the bottom) vs "down" (field near the
     * top of its container, e.g. ImprovePromptDialog's Prompt field)
     * choice. */
    placement?: "up" | "down";
  }
>(function AgentMentionPicker({ agents, query, onSelect, onClose, placement = "up" }, ref) {
  const { t } = useTranslation("chat");
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, onClose);

  const filtered = useMemo(
    () => agents.filter((a) => a.name.toLowerCase().includes(query.toLowerCase())),
    [agents, query]
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useImperativeHandle(ref, () => ({
    moveActive(delta: number) {
      setActiveIndex((i) => (filtered.length === 0 ? 0 : Math.max(0, Math.min(filtered.length - 1, i + delta))));
    },
    confirmActive() {
      const agent = filtered[activeIndex];
      if (agent) onSelect(agent);
    },
  }));

  return (
    <div
      ref={containerRef}
      className={cn(
        "absolute left-0 z-20 max-h-72 w-64 overflow-y-auto rounded-lg border border-border bg-card shadow-lg",
        placement === "down" ? "top-full mt-2" : "bottom-full mb-2"
      )}
    >
      {filtered.map((agent, index) => (
        <button
          key={agent.id}
          type="button"
          className={cn(
            "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-accent hover:text-accent-foreground",
            index === activeIndex && "bg-accent text-accent-foreground"
          )}
          onClick={() => onSelect(agent)}
          onMouseEnter={() => setActiveIndex(index)}
        >
          <Bot className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{agent.name}</span>
        </button>
      ))}
      {filtered.length === 0 && (
        <p className="px-3 py-3 text-xs italic text-muted-foreground">{t("agentMentionPicker.noAgentsFound")}</p>
      )}
    </div>
  );
});

export interface ArtifactMentionPickerHandle {
  moveActive: (delta: number) => void;
  confirmActive: () => void;
}

/** "$Artefato" picker -- global (cross-session, cross-agent) search over
 * files created by any agent's write_file/patch tool calls (see
 * db/models/chat.py's ChatArtifact). Selecting one inserts the real
 * absolute path directly, same mechanic as the "@" file mention -- no
 * "$Name" token/resolution step. */
export const ArtifactMentionPicker = forwardRef<
  ArtifactMentionPickerHandle,
  { query: string; onSelectPath: (path: string) => void; onClose: () => void }
>(function ArtifactMentionPicker({ query, onSelectPath, onClose }, ref) {
  const { t } = useTranslation("chat");
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, onClose);
  const { data, isLoading } = useSearchChatArtifacts(query);
  const artifacts = data ?? [];

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  useImperativeHandle(ref, () => ({
    moveActive(delta: number) {
      setActiveIndex((i) => (artifacts.length === 0 ? 0 : Math.max(0, Math.min(artifacts.length - 1, i + delta))));
    },
    confirmActive() {
      const artifact = artifacts[activeIndex];
      if (artifact) onSelectPath(artifact.path);
    },
  }));

  return (
    <div
      ref={containerRef}
      className="absolute bottom-full left-0 z-20 mb-2 max-h-72 w-80 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
    >
      {isLoading && <p className="px-3 py-3 text-xs text-muted-foreground">{t("artifactMentionPicker.loading")}</p>}
      {artifacts.map((artifact, index) => (
        <button
          key={artifact.id}
          type="button"
          className={cn(
            "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-accent hover:text-accent-foreground",
            index === activeIndex && "bg-accent text-accent-foreground"
          )}
          onClick={() => onSelectPath(artifact.path)}
          onMouseEnter={() => setActiveIndex(index)}
        >
          <Paperclip className="h-3.5 w-3.5 shrink-0" />
          <div className="min-w-0">
            <p className="truncate">{artifact.name}</p>
            <p className="truncate text-[10px] opacity-70">{artifact.agent_name}</p>
          </div>
        </button>
      ))}
      {!isLoading && artifacts.length === 0 && (
        <p className="px-3 py-3 text-xs italic text-muted-foreground">{t("artifactMentionPicker.noArtifactsFound")}</p>
      )}
    </div>
  );
});

function VoiceOrb({ status, compact = false }: { status: "listening" | "processing" | "speaking"; compact?: boolean }) {
  const speaking = status === "speaking";
  const processing = status === "processing";

  // Outer glow ring — pulses fast + wide when speaking
  const outerScale = speaking
    ? [1, 1.45, 1.1, 1.55, 1, 1.35, 1]
    : processing
    ? [1, 1.12, 1]
    : [1, 1.06, 1];
  const outerDuration = speaking ? 1.0 : processing ? 2 : 3.5;

  // Main body rotation speed
  const bodyRotateDuration = speaking ? 1.8 : processing ? 3.5 : 7;

  // Inner core drifts around when speaking (speech rhythm x/y wobble)
  const coreX = speaking ? [0, 10, -6, 12, -9, 7, 0] : [0, 2, -2, 0];
  const coreY = speaking ? [0, -7, 9, -4, 7, -10, 0] : [0, -2, 2, 0];
  const coreScale = speaking
    ? [1, 1.25, 0.85, 1.35, 0.9, 1.2, 1]
    : processing
    ? [1, 1.08, 1]
    : [1, 1.04, 1];
  const coreDuration = speaking ? 1.3 : 3;

  // White flash center
  const flashScale = speaking
    ? [0.7, 1.6, 0.5, 1.8, 0.6, 1.4, 0.7]
    : [0.8, 1.1, 0.8];
  const flashDuration = speaking ? 0.55 : 2.2;

  const outerGrad = speaking
    ? "radial-gradient(circle, #06b6d4 0%, #6366f1 55%, transparent 75%)"
    : processing
    ? "radial-gradient(circle, #a855f7 0%, #7c3aed 55%, transparent 75%)"
    : "radial-gradient(circle, #8b5cf6 0%, #6366f1 55%, transparent 75%)";

  const bodyGrad = speaking
    ? "conic-gradient(from 0deg, #06b6d4, #6366f1, #a855f7, #0ea5e9, #06b6d4)"
    : processing
    ? "conic-gradient(from 0deg, #7c3aed, #a855f7, #ec4899, #8b5cf6, #7c3aed)"
    : "conic-gradient(from 0deg, #6366f1, #06b6d4, #8b5cf6, #0ea5e9, #6366f1)";

  const coreGrad = speaking
    ? "radial-gradient(circle, #ffffff 0%, #06b6d4 45%, #8b5cf6 85%)"
    : "radial-gradient(circle, #ffffff 0%, #a5b4fc 55%, #8b5cf6 100%)";

  const outer = compact ? "h-32 w-32" : "h-48 w-48";
  const body  = compact ? "h-24 w-24" : "h-36 w-36";
  const core  = compact ? "h-16 w-16" : "h-24 w-24";
  const flash = compact ? "h-7 w-7"   : "h-10 w-10";

  return (
    <div className={cn("relative flex items-center justify-center", outer)}>
      {/* Outer glow — expands dramatically when speaking */}
      <motion.div
        className="absolute inset-0 rounded-full"
        animate={{ scale: outerScale }}
        transition={{ duration: outerDuration, ease: "easeInOut", repeat: Infinity }}
        style={{ background: outerGrad, filter: "blur(20px)", opacity: 0.55 }}
      />

      {/* Body — rotates, speeds up when speaking */}
      <motion.div
        className={cn("absolute rounded-full", body)}
        animate={{ rotate: 360 }}
        transition={{ duration: bodyRotateDuration, ease: "linear", repeat: Infinity }}
        style={{ background: bodyGrad, filter: "blur(6px)" }}
      />

      {/* Inner core — drifts around when speaking */}
      <motion.div
        className={cn("absolute rounded-full", core)}
        animate={{ x: coreX, y: coreY, scale: coreScale }}
        transition={{ duration: coreDuration, ease: "easeInOut", repeat: Infinity }}
        style={{ background: coreGrad, filter: "blur(4px)" }}
      />

      {/* White flash — rapid fire when speaking */}
      <motion.div
        className={cn("absolute rounded-full bg-white", flash)}
        animate={{ scale: flashScale, opacity: speaking ? [0.5, 1, 0.3, 1, 0.4, 0.9, 0.5] : [0.4, 0.75, 0.4] }}
        transition={{ duration: flashDuration, ease: "easeInOut", repeat: Infinity }}
        style={{ filter: "blur(7px)" }}
      />
    </div>
  );
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const SLASH_COMMAND_NAMES = SAFE_SLASH_COMMANDS.map((cmd) => cmd.command.slice(1));

/** Slash command replies (host-bridge/hermes_stream.py's _run_slash_command)
 * are plain CLI text -- including box-drawing ASCII tables (/help) -- not
 * markdown. Rendering them through the Markdown component collapses single
 * newlines and mangles ASCII alignment, so detect them (by checking whether
 * the prior user turn was one of the whitelisted commands) and render as a
 * preformatted monospace block instead. */
function isSlashCommandMessage(text: string): boolean {
  const match = /^\/(\w+)/.exec(text.trim());
  return !!match && SLASH_COMMAND_NAMES.includes(match[1].toLowerCase());
}

/** "!command" raw bash output (see exec_chat_command) is also plain CLI
 * text, not markdown -- same rendering treatment as a slash command reply. */
function isBangCommandMessage(text: string): boolean {
  return text.trim().startsWith("!");
}

function isPlainTextReply(text: string): boolean {
  return isSlashCommandMessage(text) || isBangCommandMessage(text);
}

function MessageBubble({
  message,
  isCommandReply,
  onRegenerate,
  regenerateDisabled,
  respondingAgentName,
  onEdit,
  editDisabled,
}: {
  message: ChatMessage;
  isCommandReply?: boolean;
  onRegenerate?: () => void;
  regenerateDisabled?: boolean;
  /** Name badge shown above a reply that came from a "#Agente"-mentioned
   * agent other than the tab's own (message.responding_agent_id set). */
  respondingAgentName?: string;
  /** Only passed for the last user message in the thread -- edits it and
   * resends (see handleEditMessage: deletes this message + its reply,
   * then queues the new text as a fresh turn). */
  onEdit?: (newContent: string) => void;
  editDisabled?: boolean;
}) {
  const { t } = useTranslation("chat");
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(message.content);

  async function handleCopyMessage() {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  // ChatGPT-style: only the user's own turn gets a colored bubble. The
  // agent's reply is plain text flowing in the page, no card/background.
  if (!isUser) {
    return (
      <div className="group/msg max-w-[85%] text-sm text-foreground">
        {message.thinking_seconds != null && !isCommandReply && (
          <p className="mb-1 text-xs text-muted-foreground">
            {t("messageBubble.thoughtFor", { duration: formatThinkingDuration(message.thinking_seconds) })}
          </p>
        )}
        {respondingAgentName && (
          <span className="mb-1 flex w-fit items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">
            <Bot className="h-2.5 w-2.5" />
            {respondingAgentName}
          </span>
        )}
        {message.attachment_names && (
          <p className="mb-1 text-xs text-muted-foreground">📎 {message.attachment_names}</p>
        )}
        {isCommandReply ? (
          <pre className="whitespace-pre-wrap break-words rounded-lg bg-muted/50 px-3 py-2 font-mono text-xs">
            {message.content}
          </pre>
        ) : (
          <Markdown content={message.content} />
        )}
        <div className="mt-1 flex items-center gap-2 opacity-0 transition-opacity group-hover/msg:opacity-100">
          <button
            type="button"
            aria-label={t("messageBubble.copyMessage")}
            title={t("messageBubble.copyMessage")}
            onClick={handleCopyMessage}
            className="flex items-center gap-1 rounded-full px-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          </button>
          {onRegenerate && (
            <button
              type="button"
              aria-label={t("messageBubble.regenerateReply")}
              title={t("messageBubble.regenerateReply")}
              disabled={regenerateDisabled}
              onClick={onRegenerate}
              className="flex items-center gap-1 rounded-full px-1 text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              <RotateCcw className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
    );
  }

  if (isEditing) {
    return (
      <div className="flex justify-end">
        <div className="w-full max-w-[75%] space-y-2 rounded-2xl border border-indigo-500 bg-indigo-500/10 px-4 py-2">
          <Textarea
            autoFocus
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onEdit?.(editText);
                setIsEditing(false);
              }
              if (e.key === "Escape") {
                setEditText(message.content);
                setIsEditing(false);
              }
            }}
            rows={2}
            className="min-h-0 resize-none border-0 bg-transparent p-0 text-sm shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
          />
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setEditText(message.content);
                setIsEditing(false);
              }}
            >
              {t("messageBubble.cancel")}
            </Button>
            <Button
              size="sm"
              onClick={() => {
                onEdit?.(editText);
                setIsEditing(false);
              }}
            >
              {t("messageBubble.saveAndResend")}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="group/msg flex justify-end">
      <div className="flex max-w-[75%] flex-col items-end">
        <div className="rounded-2xl bg-indigo-600 px-4 py-2 text-sm text-white shadow-sm">
          {message.attachment_names && (
            <p className="mb-1 text-xs text-white/70">📎 {message.attachment_names}</p>
          )}
          <Markdown content={message.content} />
          {/* Fixed indigo-600 bubble in both themes -- the timestamp must
              be a fixed light tint too. text-primary-foreground flips to
              near-black in dark mode (it's meant to pair with the *theme's*
              bg-primary, not this hardcoded bubble color), which read as
              unreadably dark-on-dark against this background. */}
          <p className="mt-1 text-[10px] text-indigo-100/80">{formatTime(message.created_at)}</p>
        </div>
        {onEdit && (
          <button
            type="button"
            aria-label={t("messageBubble.editMessage")}
            title={t("messageBubble.editMessage")}
            disabled={editDisabled}
            onClick={() => {
              setEditText(message.content);
              setIsEditing(true);
            }}
            className="mt-1 flex items-center gap-1 rounded-full px-1 text-[11px] text-muted-foreground opacity-0 transition-opacity group-hover/msg:opacity-100 hover:text-foreground disabled:opacity-50"
          >
            <Pencil className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}

/** One open chat tab's full UI + state (history sidebar, messages,
 * composer). Always mounted while its tab exists -- only CSS-hidden when
 * inactive -- so switching tabs preserves the draft, attachment, and
 * scroll position, same as how terminal tabs keep their tmux session
 * alive in the background. */
export function ChatPane({
  tabId,
  active,
  agentId,
  chatableAgents,
  onAgentChange,
  initialComposerText,
  historyCollapsed,
  artifactsOpen,
  workingDir,
  startNewSession,
  emptyStateText,
  primingMessage,
  onAssistantMessage,
  lockAgent,
}: {
  tabId: string;
  active: boolean;
  agentId: string;
  chatableAgents: Agent[];
  onAgentChange: (agentId: string) => void;
  initialComposerText?: string;
  historyCollapsed: boolean;
  artifactsOpen: boolean;
  /** Hides the composer's agent-selector pill -- the agent is fixed by the
   * embedding context (e.g. a channel member's own individual session,
   * opened by clicking their name) rather than user-switchable
   * (2026-08-06, Marcelo: "quero introduzir o mesmo chat do agente no
   * canal... [o seletor] será realizado com o agente selecionado", i.e.
   * no picker needed -- one chat component, reused, not a second one). */
  lockAgent?: boolean;
  /** Same cwd used by "New Terminal" tabs -- backs the composer's
   * "!command" prefix so it runs in the same project context. */
  workingDir?: string;
  /** Skips auto-resuming the agent's most recent session on mount --
   * AssistantDrawer wants a blank chat every time it opens (see its
   * docstring), unlike Workspace's persistent tabs, which should pick up
   * where the user left off. */
  startNewSession?: boolean;
  /** Overrides the default "Send a message to start the conversation..."
   * placeholder shown while the session has no messages yet -- purely
   * client-side, no agent turn spent on it. */
  emptyStateText?: string;
  /** Internal grounding sent ONCE, by itself, as the opening turn of a
   * fresh session as soon as the pane mounts (requires startNewSession) --
   * e.g. AssistantDrawer's "read docs/MANUAL.md" note plus the current
   * screen's hidden context (see assistantStore's pendingHiddenContext).
   * Deliberately a separate agent turn instead of a prefix glued onto the
   * user's first message: the user's own text stays clean, and the agent
   * has the context before the user even starts typing. The whole exchange
   * (this message and the agent's ack) is persisted wrapped in
   * HIDDEN_CONTEXT markers (hidden=true on the stream call) and dropped
   * from the transcript. */
  primingMessage?: string;
  /** Fires once per completed assistant turn, with that message's full
   * text -- AssistantDrawer uses this to notice a ```forgehub-fill fenced
   * block and apply it to the page's form. Generic on purpose (just a
   * content string, no ForgeHub-specific parsing here): Workspace doesn't
   * pass it and isn't affected. */
  onAssistantMessage?: (content: string) => void;
}) {
  const { t } = useTranslation("chat");
  const {
    sessionId,
    setSessionId,
    ensureSession,
    editingSessionId,
    setEditingSessionId,
    editingTitle,
    setEditingTitle,
    sessions,
    chatSearchInput,
    setChatSearchInput,
    chatSearchTerm,
    isSearchingChats,
    displayedSessions,
    chatGroups,
    createChatGroup,
    updateChatGroup,
    deleteChatGroup,
    projectsWithPath,
    sessionsByProjectPath,
    sessionsByGroupId,
    looseSessions,
    projectFoldersWithSessions,
    projectsRootOpen,
    setProjectsRootOpen,
    groupsRootOpen,
    setGroupsRootOpen,
    openProjectPaths,
    setOpenProjectPaths,
    openGroupIds,
    setOpenGroupIds,
    toggleOpenPath,
    newGroupNameRoot,
    setNewGroupNameRoot,
    creatingGroup,
    setCreatingGroup,
    createSession,
    deleteSession,
    handleStartRename,
    handleCommitRename,
    handleTogglePin,
    activeSession,
    handleSetSessionWorkingDirectory,
    handleMoveSessionToProject,
    handleMoveSessionToGroup,
    handleCreateGroupAndMoveSession,
    pendingClearSessions,
    setPendingClearSessions,
    handleClearSessions,
    confirmClearSessions,
    handleNewChat,
  } = useChatSessionViewModel(agentId, startNewSession);
  // Chat chrome (composer placeholder, default empty state) follows the
  // configured response language, same one the agent is instructed to
  // answer in (Settings -> AI chat).
  const { texts: languageTexts } = useChatLanguage();
  const [composerText, setComposerText] = useState(
    () => composerTextByTabId.get(tabId) ?? initialComposerText ?? ""
  );
  useEffect(() => {
    // An empty composer has no draft worth preserving across a remount --
    // and staging "" here would otherwise permanently win over a later
    // initialComposerText (a seed pushed in after this first empty mount),
    // since the lookup below only falls through on null/undefined, not "".
    if (composerText) {
      composerTextByTabId.set(tabId, composerText);
    } else {
      composerTextByTabId.delete(tabId);
    }
  }, [tabId, composerText]);
  const [attachedFiles, setAttachedFilesState] = useState<File[]>(
    () => attachmentByTabId.get(tabId) ?? []
  );
  function setAttachedFiles(files: File[]) {
    if (files.length > 0) attachmentByTabId.set(tabId, files);
    else attachmentByTabId.delete(tabId);
    setAttachedFilesState(files);
  }
  function addAttachedFiles(newFiles: File[]) {
    setAttachedFilesState((current) => {
      const next = [...current, ...newFiles];
      attachmentByTabId.set(tabId, next);
      return next;
    });
  }
  function removeAttachedFile(index: number) {
    setAttachedFilesState((current) => {
      const next = current.filter((_, i) => i !== index);
      if (next.length > 0) attachmentByTabId.set(tabId, next);
      else attachmentByTabId.delete(tabId);
      return next;
    });
  }
  const [imagePreviewIndex, setImagePreviewIndex] = useState<number | null>(null);
  useEffect(() => {
    if (imagePreviewIndex === null) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setImagePreviewIndex(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [imagePreviewIndex]);
  const [isRecording, setIsRecording] = useState(false);
  // Agent-assisted prompt rewrite (2026-08-06 for Channels, ported here
  // 2026-08-07, Marcelo: "no ChatPane (Conversations) o icone de melhoria
  // do prompt que foi construido no ChatPane (Canais)"). See
  // useStreamImprovePrompt's docstring: private rewrite-only call, never a
  // real turn -- applying the result only replaces the compose draft,
  // sending is still a separate, explicit Enter afterward.
  const [improveOpen, setImproveOpen] = useState(false);
  const improvePrompt = useStreamImprovePrompt(sessionId);
  // Só o que ESTE cliente está transmitindo agora. O turno em si pertence ao
  // servidor (core/active_turns.py) e é lido por useActiveTurn abaixo, então
  // nada aqui precisa sobreviver à desmontagem -- que é justamente o que um
  // F5 ou um travamento da aba não dariam chance de salvar.
  const [queue, setQueue] = useState<ChatQueueItem[]>([]);
  const queueDrainingRef = useRef(false);
  // Mirrors `queue` synchronously for processQueueItem's completion handler
  // -- it closes over the `item` argument from when the turn started, whose
  // `.steps` is always `[]` (steps arrive later via handleStreamEvent's own
  // setQueue calls), so reading the live array through this ref is the only
  // way to grab the finished trail before the item is dropped.
  const queueRef = useRef<ChatQueueItem[]>([]);
  useEffect(() => {
    queueRef.current = queue;
    // Só os controllers ficam fora do React: são a conexão desta aba, e é o
    // que `clearChatTabQueue` precisa abortar quando a aba fecha.
    const controllers = queue.map((i) => i.abortController).filter(Boolean) as AbortController[];
    if (controllers.length > 0) abortByTabId.set(tabId, controllers);
    else abortByTabId.delete(tabId);
  }, [queue, tabId]);
  // Hidden items (e.g. the priming turn's long "Contexto: ..." text) render
  // as nothing in the chat screen by design -- clicking one in the summary
  // strip below reveals that specific item's bubble/details inline, right
  // where it already sits among the other queue items, instead of a modal
  // that would cover the rest of the screen. Multiple can be revealed at
  // once; revealing one never hides another.
  const [revealedQueueIds, setRevealedQueueIds] = useState<Set<string>>(new Set());
  const queueItemRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const pendingScrollToRevealedRef = useRef<string | null>(null);
  function toggleQueueItemRevealed(id: string) {
    setRevealedQueueIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
        pendingScrollToRevealedRef.current = id;
      }
      return next;
    });
  }
  // Process detail (tool-call steps) for a turn that has already finished,
  // keyed by the persisted assistant message it belongs to -- captured in
  // processQueueItem right before that turn's queue item (and its `steps`)
  // is dropped. The detail must survive the response arriving, not be
  // erased by it (2026-07-29, Marcelo: "não é preciso apagar o detalhe do
  // processamento") -- rendered by FinishedStepsTrail above the matching
  // MessageBubble. Lives only for this mounted session (not persisted by
  // the backend -- see chatMessageSchema, no steps field).
  const [finishedStepsByMessageId, setFinishedStepsByMessageId] = useState<Map<string, ChatQueueStep[]>>(
    new Map()
  );
  // Jump straight to the item just revealed -- with several queued items,
  // scrolling to the bottom of the transcript wouldn't necessarily put an
  // earlier one (still processing) in view.
  useEffect(() => {
    const id = pendingScrollToRevealedRef.current;
    if (!id) return;
    pendingScrollToRevealedRef.current = null;
    queueItemRefs.current.get(id)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [revealedQueueIds]);
  const [composerWarning, setComposerWarning] = useState<string | null>(null);
  const [composerDragActive, setComposerDragActive] = useState(false);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [slashOpen, setSlashOpen] = useState(false);
  const { data: promptCommands = [] } = usePromptCommands();
  const [agentMentionOpen, setAgentMentionOpen] = useState(false);
  const [agentMentionQuery, setAgentMentionQuery] = useState("");
  const [artifactMentionOpen, setArtifactMentionOpen] = useState(false);
  const [artifactMentionQuery, setArtifactMentionQuery] = useState("");
  const mentionPickerRef = useRef<MentionFilePickerHandle>(null);
  const slashPickerRef = useRef<SlashCommandPickerHandle>(null);
  const agentPickerRef = useRef<AgentMentionPickerHandle>(null);
  const artifactPickerRef = useRef<ArtifactMentionPickerHandle>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const composerTextareaRef = useRef<HTMLTextAreaElement>(null);

  // Voice conversation state
  type VoicePhase = "idle" | "checking" | "active" | "error";
  type CheckItem = { id: string; label: string; ok: boolean; detail?: string };

  const [voiceActive, setVoiceActive] = useState(false);
  const [voicePhase, setVoicePhase] = useState<VoicePhase>("idle");
  const [, setVoiceChecklist] = useState<CheckItem[]>([]);
  const [voiceStatus, setVoiceStatus] = useState<"listening" | "processing" | "speaking">("listening");
  const [voiceLiveText, setVoiceLiveText] = useState("");
  const [voiceMsgs, setVoiceMsgs] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [micLevel, setMicLevel] = useState(0);
  const [recRunning, setRecRunning] = useState(false);
  const [voiceInterim, setVoiceInterim] = useState(""); // real-time interim text
  const voiceMsgsEndRef = useRef<HTMLDivElement>(null);
  // refs — callbacks never see stale React state
  const voiceActiveRef = useRef(false);
  const voiceStatusRef = useRef<"listening" | "processing" | "speaking">("listening");
  const ttsVoicesRef = useRef<SpeechSynthesisVoice[]>([]);
  // SpeechRecognition refs
  const srRef = useRef<any>(null);
  const srRestartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track consecutive SR sessions with no result; after 1 we switch to VAD permanently
  const srEmptyStreakRef = useRef(0);
  const srBrokenRef = useRef(false); // once true, skip SR and use VAD directly
  const [, setUsingVAD] = useState(false);
  // MediaRecorder + VAD fallback refs (used only when SR is unavailable)
  const voiceStreamRef = useRef<MediaStream | null>(null);
  const voiceRecorderRef = useRef<MediaRecorder | null>(null);
  const voiceChunksRef = useRef<Blob[]>([]);
  const voiceVadRafRef = useRef<number>(0);
  const voiceVadActiveRef = useRef(false);
  // Barge-in: mic monitor during TTS, abort signal for active SSE stream
  const bargeInCtxRef = useRef<AudioContext | null>(null);
  const bargeInRafRef = useRef<number>(0);
  const voiceBargeInRef = useRef(false); // set true when user interrupts agent TTS
  const voiceMsgAbortRef = useRef<AbortController | null>(null); // cancel active SSE fetch

  // Guards primingMessage against re-sends within the same session -- see
  // the priming effect below.
  const primingSentRef = useRef(false);

  useEffect(() => {
    // Switching agents starts a fresh session -- the new agent hasn't seen
    // the priming context, so allow it to be sent again. Session reset
    // itself lives in useChatSessionViewModel's own [agentId] effect.
    primingSentRef.current = false;
  }, [agentId]);

  // Sends primingMessage as the session's own opening turn as soon as the
  // pane is usable -- see the prop's docstring. Runs before the user can
  // have typed anything (effects fire right after first render), and the
  // serial queue below keeps any user message ordered after it.
  useEffect(() => {
    if (!startNewSession || !primingMessage || !agentId || primingSentRef.current) return;
    primingSentRef.current = true;
    void (async () => {
      try {
        await ensureSession();
      } catch {
        // Session creation failed -- surface nothing here; the user's own
        // first send will retry it and show its error normally.
        primingSentRef.current = false;
        return;
      }
      setQueue((q) => [
        ...q,
        {
          id: crypto.randomUUID(),
          content: primingMessage,
          attachmentName: null,
          files: [],
          liveText: "",
          steps: [],
          status: "queued",
          approval: null,
          abortController: null,
          hidden: true,
        },
      ]);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startNewSession, primingMessage, agentId]);

  const queryClient = useQueryClient();

  // O turno em execução vem do servidor, não da memória desta aba -- é o que
  // sobrevive a um F5, a um travamento e a abrir a conversa em outra máquina,
  // do mesmo jeito que o TerminalPane já re-anexa ao tmux. `queue.length > 0`
  // quer dizer que ESTE cliente é quem transmite: aí não vale perguntar, ele
  // já recebe tudo ao vivo.
  const { data: activeTurn } = useActiveTurn("chat", sessionId || null, queue.length > 0);

  // Quando o turno observado termina no servidor, a resposta acabou de ser
  // persistida: puxa as mensagens para ela aparecer sem precisar de reload.
  const lastActiveTurnIdRef = useRef<string | null>(null);
  useEffect(() => {
    const current = activeTurn?.id ?? null;
    if (lastActiveTurnIdRef.current && !current && sessionId) {
      void queryClient.refetchQueries({ queryKey: chatKeys.messages(sessionId) }).catch(() => {});
    }
    lastActiveTurnIdRef.current = current;
  }, [activeTurn, sessionId, queryClient]);


  const { data: messages } = useChatMessages(sessionId || undefined);
  // Hidden turns are real, stored message content -- there's no
  // hidden/system channel in the send API -- but they're internal
  // grounding, not conversation: a message that is nothing but a
  // HIDDEN_CONTEXT block (a priming turn or its ack, either role) is
  // dropped from the transcript entirely, and a leading block on a user
  // message that still carries text after it (the older piggyback format)
  // is stripped off. Everything else (dedupe-guard, scroll tracking, etc.)
  // still reads the raw `messages` so the agent's reply lines up correctly.
  const visibleMessages = useMemo(
    () =>
      (messages ?? []).flatMap((m) => {
        if (!HIDDEN_CONTEXT_RE.test(m.content)) return [m];
        const content = m.content.replace(HIDDEN_CONTEXT_RE, "");
        if (!content.trim()) return [];
        return [{ ...m, content }];
      }),
    [messages]
  );

  // Notifies onAssistantMessage exactly once per completed assistant turn
  // -- `messages` only gets a turn once it's fully streamed and refetched
  // (see processQueueItem's invalidateQueries below), so this never fires
  // on partial/streaming text.
  const notifiedAssistantIdsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!onAssistantMessage) return;
    for (const m of messages ?? []) {
      if (m.role === "assistant" && !notifiedAssistantIdsRef.current.has(m.id)) {
        notifiedAssistantIdsRef.current.add(m.id);
        onAssistantMessage(m.content);
      }
    }
  }, [messages, onAssistantMessage]);

  const { data: artifacts } = useChatArtifacts(sessionId || undefined);
  const deleteArtifact = useDeleteChatArtifact(sessionId || undefined);
  const [artifactSearchQuery, setArtifactSearchQuery] = useState("");
  const sendMessage = useSendChatMessage(agentId || undefined);
  const streamMessage = useStreamChatMessage(agentId || undefined);
  const execCommand = useExecChatCommand(agentId || undefined);
  const deleteMessage = useDeleteChatMessage(sessionId || undefined);
  const approveChat = useApproveChat();
  const transcribe = useTranscribeAudio();

  // Jump straight to the bottom (no animation) the first time a session's
  // messages load -- e.g. opening the tab or switching sessions -- so the
  // conversation never visibly scrolls from top to bottom on entry. Once
  // that session has had its initial jump, later updates (new messages
  // arriving while the user is already there) animate smoothly instead.
  const scrolledSessionRef = useRef<string | null>(null);
  useEffect(() => {
    if (!messages) return;
    const isInitialForSession = scrolledSessionRef.current !== sessionId;
    messagesEndRef.current?.scrollIntoView({ behavior: isInitialForSession ? "auto" : "smooth" });
    if (isInitialForSession) scrolledSessionRef.current = sessionId;
  }, [messages, queue, sessionId, revealedQueueIds]);

  // Auto-grow the composer with its content -- the single-line height is
  // the floor (never shrinks below it), and it grows up to
  // COMPOSER_MAX_HEIGHT_PX for large pastes/prompts before scrolling
  // internally. Recompute on `active` too: a tab seeded with a draft while
  // hidden (display:none) measures scrollHeight as 0 until shown.
  useEffect(() => {
    const el = composerTextareaRef.current;
    if (!el || !active) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT_PX)}px`;
  }, [composerText, active]);

  const selectedAgent = chatableAgents.find((a) => a.id === agentId);
  const showSelfRestartWarning =
    isForgeHubRepoPath(activeSession?.working_directory_path) && SELF_RESTART_COMMAND_RE.test(composerText);

  // "/testar" (LOCAL_SLASH_COMMANDS) opens this dialog instead of sending a
  // message -- dispatches straight to the background-test endpoint via
  // apiClient, same reasoning as "/new": never depends on the LLM session
  // or MCP tool discovery being available.
  const [testDialogOpen, setTestDialogOpen] = useState(false);

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) addAttachedFiles(files);
    e.target.value = "";
  }

  async function handleSend(overrideText?: string) {
    if (!agentId) {
      setComposerWarning(t("composer.selectAgentFirst"));
      return;
    }
    const isOverride = overrideText !== undefined;

    const trimmed = (isOverride ? overrideText : composerText).trim();
    if (!trimmed && attachedFiles.length === 0) {
      setComposerWarning(t("composer.typeMessageFirst"));
      return;
    }

    // "/new" and "/testar" are local commands (see LOCAL_SLASH_COMMANDS) --
    // catches the paste-then-click-Send path, which never opens the slash
    // picker (that only triggers on typing "/" as a fresh keystroke) so
    // handleSlashSelect never runs for it.
    if (!isOverride && attachedFiles.length === 0 && trimmed.toLowerCase() === "/new") {
      handleNewChat();
      setComposerText("");
      setComposerWarning(null);
      return;
    }
    if (!isOverride && attachedFiles.length === 0 && trimmed.toLowerCase() === "/testar") {
      setTestDialogOpen(true);
      setComposerText("");
      setComposerWarning(null);
      return;
    }

    // The dedupe-guard only makes sense for the normal composer flow --
    // "edit and resend" (isOverride) deliberately allows resending the
    // same text (e.g. user just fixed a typo elsewhere and reverted it).
    const lastUserMessage =
      queue[queue.length - 1]?.content ?? [...(messages ?? [])].reverse().find((m) => m.role === "user")?.content;
    if (!isOverride && attachedFiles.length === 0 && trimmed && lastUserMessage?.trim() === trimmed) {
      setComposerWarning(t("composer.alreadySent"));
      return;
    }

    // Internal grounding never rides on the user's message -- it went out
    // as its own hidden turn when the pane opened (see primingMessage), so
    // what the user typed is exactly what's sent and stored.
    await ensureSession();
    const message = isOverride ? overrideText : composerText;
    const files = isOverride ? [] : attachedFiles;
    if (!isOverride) {
      setComposerText("");
      setAttachedFiles([]);
      setComposerWarning(null);
    }

    // "!command" runs raw bash via the bridge -- no agent/LLM call at all,
    // bypasses mentions/queue-target logic entirely.
    if (files.length === 0 && trimmed.startsWith("!")) {
      setQueue((q) => [
        ...q,
        {
          id: crypto.randomUUID(),
          content: trimmed,
          attachmentName: null,
          files: [],
          liveText: "",
          steps: [],
          status: "queued",
          approval: null,
          abortController: null,
          isExec: true,
        },
      ]);
      return;
    }

    // "#Agente" mentions route this turn away from the tab's own agent
    // entirely (v1: no broadcast-plus-mentions, no shared context -- see
    // ChatSessionParticipant's docstring). Excludes a self-mention (the
    // tab's own agent), which just behaves as a normal send.
    const mentionedAgents =
      files.length > 0 ? [] : extractMentionedAgents(message, chatableAgents).filter((a) => a.id !== agentId);

    if (mentionedAgents.length === 0) {
      setQueue((q) => [
        ...q,
        {
          id: crypto.randomUUID(),
          content: message,
          attachmentName: files.length > 0 ? files.map((f) => f.name).join(", ") : null,
          files,
          liveText: "",
          steps: [],
          status: "queued",
          approval: null,
          abortController: null,
        },
      ]);
    } else {
      setQueue((q) => [
        ...q,
        ...mentionedAgents.map((agent, index) => ({
          id: crypto.randomUUID(),
          content: message,
          attachmentName: null,
          files: [],
          liveText: "",
          steps: [],
          status: "queued" as const,
          approval: null,
          abortController: null,
          targetAgentId: agent.id,
          targetAgentName: agent.name,
          skipUserMessage: index > 0,
        })),
      ]);
    }
  }

  // Drains the queue one request at a time -- a Hermes session is a single
  // ongoing conversation, so requests for the same session must stay in
  // order rather than racing each other.
  useEffect(() => {
    if (queueDrainingRef.current) return;
    const next = queue.find((item) => item.status === "queued");
    if (!next || !sessionId) return;

    queueDrainingRef.current = true;
    processQueueItem(next).finally(() => {
      queueDrainingRef.current = false;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue, sessionId]);

  function handleStreamEvent(itemId: string, event: ChatStreamEvent) {
    setQueue((q) =>
      q.map((item) => {
        if (item.id !== itemId) return item;
        if (event.type === "delta") return { ...item, liveText: item.liveText + event.text };
        if (event.type === "tool_start") {
          return {
            ...item,
            steps: [
              ...item.steps,
              {
                id: event.toolId,
                name: event.name,
                label: event.context || event.name,
                detail: event.detail,
                done: false,
              },
            ],
          };
        }
        if (event.type === "tool_complete") {
          return {
            ...item,
            steps: item.steps.map((s) =>
              s.id === event.toolId
                ? { ...s, label: event.summary || s.label, done: true, demandNumber: event.demandNumber }
                : s
            ),
          };
        }
        if (event.type === "approval_request") {
          return {
            ...item,
            approval: {
              streamId: event.streamId,
              command: event.command,
              description: event.description,
              patternKeys: event.patternKeys,
            },
          };
        }
        return item;
      })
    );
  }

  function handleApprovalChoice(itemId: string, streamId: string, choice: "once" | "session" | "deny") {
    setQueue((q) => q.map((it) => (it.id === itemId ? { ...it, approval: null } : it)));
    approveChat.mutate({ streamId, choice });
  }

  // Attaches a finished turn's tool-call trail to the assistant message it
  // produced, so FinishedStepsTrail can keep showing it after the queue
  // item itself is dropped -- reads queueRef (not the `item` argument,
  // whose .steps is always the empty array it started with) and the query
  // cache directly (not the component's `messages`, which may not have
  // re-rendered with the just-awaited refetch yet).
  function preserveFinishedSteps(itemId: string) {
    const current = queueRef.current.find((it) => it.id === itemId);
    if (!current || current.steps.length === 0) return;
    const fresh = queryClient.getQueryData<ChatMessage[]>(chatKeys.messages(sessionId));
    const lastAssistant = fresh ? [...fresh].reverse().find((m) => m.role === "assistant") : undefined;
    if (!lastAssistant) return;
    const steps = current.steps;
    setFinishedStepsByMessageId((prev) => {
      const next = new Map(prev);
      next.set(lastAssistant.id, steps);
      return next;
    });
  }

  async function processQueueItem(item: ChatQueueItem) {
    const abortController = item.files.length > 0 || item.isExec ? null : new AbortController();
    setQueue((q) =>
      q.map((it) => (it.id === item.id ? { ...it, status: "processing", abortController, startedAt: Date.now() } : it))
    );
    try {
      if (item.isExec) {
        await execCommand.mutateAsync({ sessionId, command: item.content.slice(1), cwd: workingDir });
      } else if (item.files.length > 0) {
        // File uploads only support the one-shot endpoint (the SSE endpoint is GET-only).
        await sendMessage.mutateAsync({ sessionId, message: item.content, files: item.files });
      } else {
        await streamMessage(sessionId, item.content, (event) => handleStreamEvent(item.id, event), abortController!.signal, {
          regenerate: item.isRegenerate,
          targetAgentId: item.targetAgentId,
          skipUserMessage: item.skipUserMessage,
          hidden: item.hidden,
        });
      }
      // Only drop the pending bubbles AFTER the persisted messages have
      // been refetched. Removing first left a window where the sent prompt
      // vanished from the screen (long turns made it very visible); the
      // pending bubble must stay until its persisted twin is rendered.
      await queryClient
        .refetchQueries({ queryKey: chatKeys.messages(sessionId) })
        .catch(() => {});
      preserveFinishedSteps(item.id);
      setQueue((q) => q.filter((it) => it.id !== item.id));
    } catch (err) {
      if ((err as Error).name === "AbortError") {
        // User hit Stop -- the backend already persisted whatever had been
        // generated so far (see chat.py's CancelledError handling), just
        // refresh to pick it up instead of showing a red error. Same rule
        // as the success path: only drop the pending bubbles after the
        // persisted messages are back on screen.
        queryClient.invalidateQueries({ queryKey: chatKeys.artifacts(sessionId) });
        await queryClient
          .refetchQueries({ queryKey: chatKeys.messages(sessionId) })
          .catch(() => {});
        preserveFinishedSteps(item.id);
        setQueue((q) => q.filter((it) => it.id !== item.id));
        return;
      }
      setQueue((q) => q.map((it) => (it.id === item.id ? { ...it, status: "error", error: (err as Error).message } : it)));
    }
  }

  function handleStopGenerating(item: ChatQueueItem) {
    item.abortController?.abort();
  }

  /** Deletes the last assistant reply and re-asks the preceding user
   * message to get a fresh one. Note: the underlying Hermes CLI session
   * (resumed via hermes_session_id) still has the old reply in its own
   * transcript/context -- this only replaces what ForgeHub displays. */
  async function handleRegenerate(lastAssistantMessage: ChatMessage) {
    const list = messages ?? [];
    const idx = list.findIndex((m) => m.id === lastAssistantMessage.id);
    const precedingUser = idx > 0 ? list[idx - 1] : undefined;
    if (!precedingUser || precedingUser.role !== "user") return;

    // If the reply being regenerated came from a "#Agente"-mentioned agent,
    // resend to that SAME agent (not the tab's own) so it stays targeted.
    const targetAgentId = lastAssistantMessage.responding_agent_id ?? undefined;
    const targetAgentName = targetAgentId
      ? chatableAgents.find((a) => a.id === targetAgentId)?.name
      : undefined;

    await deleteMessage.mutateAsync(lastAssistantMessage.id);
    setQueue((q) => [
      ...q,
      {
        id: crypto.randomUUID(),
        content: precedingUser.content,
        attachmentName: null,
        files: [],
        liveText: "",
        steps: [],
        status: "queued",
        approval: null,
        abortController: null,
        isRegenerate: true,
        targetAgentId,
        targetAgentName,
      },
    ]);
  }

  /** Edits the last user message: deletes it (and the reply that followed,
   * if any) and resends the edited text as a fresh turn -- same pattern as
   * regenerate, just starting from the user's side instead of the
   * assistant's. */
  async function handleEditMessage(userMessage: ChatMessage, newContent: string) {
    const trimmed = newContent.trim();
    if (!trimmed) return;
    const list = messages ?? [];
    const idx = list.findIndex((m) => m.id === userMessage.id);
    const following = idx >= 0 ? list[idx + 1] : undefined;

    await deleteMessage.mutateAsync(userMessage.id);
    if (following && following.role === "assistant") {
      await deleteMessage.mutateAsync(following.id);
    }
    await handleSend(trimmed);
  }

  // Errored items stay in `queue` (so their inline "Falhou: ..." message +
  // dismiss button keep rendering in the thread above) but shouldn't keep
  // cluttering this small pending-queue summary panel below.
  const pendingQueue = useMemo(() => queue.filter((item) => item.status !== "error"), [queue]);

  const attachedImagePreviewUrls = useMemo(
    () => attachedFiles.map((f) => (f.type.startsWith("image/") ? URL.createObjectURL(f) : null)),
    [attachedFiles]
  );

  useEffect(() => {
    return () => {
      attachedImagePreviewUrls.forEach((url) => url && URL.revokeObjectURL(url));
    };
  }, [attachedImagePreviewUrls]);

  // Ghost-text suggestion: only when the agent's last message ends with a
  // question (explicit -- no LLM call, no guessing at open-ended answers)
  // AND the composer is empty AND nothing is queued/processing (otherwise
  // the user already replied). Fully derived from existing state, so it
  // naturally disappears the moment real text is typed (native placeholder
  // behavior) or a message is sent (queue becomes non-empty, then the new
  // reply replaces the question that triggered it). Wrapped defensively --
  // any unexpected shape here should fall back to the normal placeholder,
  // never break the composer.
  let suggestedReply: string | null = null;
  try {
    const lastMessage = (messages ?? [])[(messages ?? []).length - 1];
    if (
      composerText === "" &&
      pendingQueue.length === 0 &&
      lastMessage?.role === "assistant" &&
      lastMessage.content.trim().endsWith("?")
    ) {
      suggestedReply = t("composer.suggestedReplyYes");
    }
  } catch {
    suggestedReply = null;
  }

  function handleComposerPaste(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const imageItems = Array.from(e.clipboardData.items).filter((item) => item.type.startsWith("image/"));
    if (imageItems.length === 0) return;
    e.preventDefault();
    const newFiles = imageItems
      .map((item, index) => {
        const file = item.getAsFile();
        if (!file) return null;
        const ext = file.type.split("/")[1] || "png";
        const name =
          file.name && file.name !== "image.png" ? file.name : `pasted-image-${Date.now()}-${index}.${ext}`;
        return new File([file], name, { type: file.type });
      })
      .filter((f): f is File => f !== null);
    if (newFiles.length > 0) addAttachedFiles(newFiles);
  }

  async function handleComposerDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setComposerDragActive(false);
    setComposerWarning(null);

    const internalFile = getAssistantFileDragData(e.dataTransfer);
    if (internalFile) {
      if (internalFile.source === "host-folder") {
        setComposerText((text) => {
          const separator = text.length > 0 && !text.endsWith("\n") ? "\n" : "";
          return `${text}${separator}Folder: ${internalFile.path}\n`;
        });
        composerTextareaRef.current?.focus();
        return;
      }
      try {
        addAttachedFiles([await loadAssistantDraggedFile(internalFile)]);
        composerTextareaRef.current?.focus();
      } catch {
        setComposerWarning(t("composer.couldNotAttach", { name: internalFile.name }));
      }
      return;
    }

    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length > 0) {
      addAttachedFiles(droppedFiles);
      composerTextareaRef.current?.focus();
      return;
    }

    const path = e.dataTransfer.getData("text/plain");
    if (!path) return;
    setComposerText((text) => {
      const needsSpace = text.length > 0 && !/\s$/.test(text);
      return text + (needsSpace ? " " : "") + path + " ";
    });
  }

  function handleComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "ArrowRight" && composerText === "" && suggestedReply) {
      e.preventDefault();
      setComposerText(suggestedReply);
      return;
    }
    if (mentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      mentionPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (mentionOpen && e.key === "Enter") {
      e.preventDefault();
      mentionPickerRef.current?.confirmActive();
      return;
    }
    if (slashOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      slashPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (slashOpen && e.key === "Enter") {
      e.preventDefault();
      slashPickerRef.current?.confirmActive();
      return;
    }
    if (agentMentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      agentPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (agentMentionOpen && e.key === "Enter") {
      e.preventDefault();
      agentPickerRef.current?.confirmActive();
      return;
    }
    if (artifactMentionOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      e.preventDefault();
      artifactPickerRef.current?.moveActive(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    if (artifactMentionOpen && e.key === "Enter") {
      e.preventDefault();
      artifactPickerRef.current?.confirmActive();
      return;
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
      return;
    }
    if (e.key === "Escape" && (mentionOpen || slashOpen || agentMentionOpen || artifactMentionOpen)) {
      setMentionOpen(false);
      setSlashOpen(false);
      setAgentMentionOpen(false);
      setArtifactMentionOpen(false);
    }
  }

  function handleMentionSelect(path: string) {
    setComposerText((t) => (t.endsWith("@") ? t.slice(0, -1) : t) + `${path} `);
    setMentionOpen(false);
    composerTextareaRef.current?.focus();
  }

  function handleSlashSelect(item: SlashCommandItem) {
    setSlashOpen(false);
    // Local commands run immediately -- never sent as a message, and the
    // composer (which may still hold the "/" the user typed to open this
    // picker) is cleared rather than filled with the command text.
    if (item.kind === "local") {
      if (item.command === "/new") handleNewChat();
      if (item.command === "/testar") setTestDialogOpen(true);
      setComposerText("");
      composerTextareaRef.current?.focus();
      return;
    }
    // The backend strips trailing whitespace from a stored prompt (see
    // prompt_command.py's strip_text validator), so a command-style prompt
    // like "/demanda" would otherwise land with no room to keep typing --
    // always leave exactly one trailing space regardless of kind.
    const text = item.kind === "prompt" ? item.prompt : item.command;
    setComposerText(text.endsWith(" ") ? text : `${text} `);
    composerTextareaRef.current?.focus();
  }

  function handleAgentMentionSelect(agent: Agent) {
    setComposerText((t) => {
      const hashIndex = t.lastIndexOf("#");
      const base = hashIndex === -1 ? t : t.slice(0, hashIndex);
      return `${base}#${agent.name} `;
    });
    setAgentMentionOpen(false);
    composerTextareaRef.current?.focus();
  }

  function handleArtifactMentionSelect(path: string) {
    setComposerText((t) => {
      const dollarIndex = t.lastIndexOf("$");
      const base = dollarIndex === -1 ? t : t.slice(0, dollarIndex);
      return `${base}${path} `;
    });
    setArtifactMentionOpen(false);
    composerTextareaRef.current?.focus();
  }

  async function handleToggleRecording() {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      setIsRecording(false);
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const recorder = new MediaRecorder(stream);
    audioChunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
      const result = await transcribe.mutateAsync(blob);
      setComposerText((prev) => (prev ? `${prev} ${result.text}` : result.text));
    };

    mediaRecorderRef.current = recorder;
    recorder.start();
    setIsRecording(true);
  }

  // ── Voice conversation ───────────────────────────────────────────────────

  function setVoiceStatusSync(s: "listening" | "processing" | "speaking") {
    voiceStatusRef.current = s;
    setVoiceStatus(s);
  }

  // Ref to the currently playing Piper audio element (for barge-in cancellation)
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);

  /** Cancel currently playing Piper audio (used by barge-in monitor). */
  function cancelTTS() {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.src = "";
      currentAudioRef.current = null;
    }
    window.speechSynthesis.cancel(); // also cancel any fallback browser TTS
  }

  /** Short acknowledgment TTS using browser speech synthesis — fires-and-forgets.
   *  Plays while the agent API call is in-flight to reduce perceived latency. */

  /** TTS via Piper (natural Brazilian male voice).
   *  Falls back to browser speech synthesis if the fetch fails.
   *  noRestart: caller manages startListening() (used by drainTTS). */
  function speakTTS(text: string, onDone: () => void, noRestart = false) {
    stopListening();
    cancelTTS();

    const resume = () => {
      currentAudioRef.current = null;
      onDone();
      if (!noRestart) setTimeout(() => startListening(), 300);
    };

    const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
    const token = getToken() ?? "";

    fetch(`${apiBase}/api/v1/chat/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ text }),
    })
      .then((r) => {
        if (!r.ok) throw new Error(`TTS HTTP ${r.status}`);
        return r.blob();
      })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        currentAudioRef.current = audio;
        const cleanup = () => { URL.revokeObjectURL(url); resume(); };
        audio.onended = cleanup;
        audio.onerror = cleanup;
        audio.play().catch(cleanup);
      })
      .catch(() => {
        // Fallback to browser TTS if Piper unavailable
        if (!window.speechSynthesis) { resume(); return; }
        const utt = new SpeechSynthesisUtterance(text);
        utt.lang = "pt-BR";
        utt.rate = 1.0;
        utt.onend = resume;
        utt.onerror = resume;
        window.speechSynthesis.speak(utt);
      });
  }

  // ── Primary: SpeechRecognition (real-time, zero-latency) ─────────────────
  // Uses browser's built-in API (Chrome → Google servers).
  // Falls back to VAD+Whisper when SR is unavailable or not responding.

  function stopListening() {
    // Stop SR
    if (srRestartTimerRef.current) { clearTimeout(srRestartTimerRef.current); srRestartTimerRef.current = null; }
    try { srRef.current?.stop(); } catch { /* ignore */ }
    srRef.current = null;
    // Stop VAD fallback
    stopVAD();
    setRecRunning(false);
    setVoiceInterim("");
  }

  function startListening() {
    if (!voiceActiveRef.current) return;
    if (voiceStatusRef.current !== "listening") return;

    const SRCtor = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    // Skip SR if we've already detected it doesn't work (network unreachable)
    if (SRCtor && !srBrokenRef.current) {
      _startSR(SRCtor);
    } else {
      startVAD();
    }
  }

  function _startSR(SRCtor: any) {
    if (!voiceActiveRef.current) return;
    if (voiceStatusRef.current !== "listening") return;

    const sr = new SRCtor();
    sr.lang = navigator.language || "pt-BR";
    sr.interimResults = true;
    sr.continuous = false;
    sr.maxAlternatives = 1;
    srRef.current = sr;
    setRecRunning(true);

    let gotResult = false; // did this session produce a transcript?

    // Don't wait for Chrome's built-in no-speech timeout (~5-7s) — abort after 4s
    const srAbortTimer = setTimeout(() => {
      if (!gotResult) {
        srBrokenRef.current = true;
        try { sr.stop(); } catch { /* onend will call startVAD */ }
      }
    }, 4000);

    sr.onresult = (e: any) => {
      clearTimeout(srAbortTimer);
      if (voiceStatusRef.current !== "listening") return;
      gotResult = true;
      srEmptyStreakRef.current = 0; // SR is working — reset failure counter
      let interim = "";
      let final = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) final += r[0].transcript;
        else interim += r[0].transcript;
      }
      if (interim) setVoiceInterim(interim);
      if (final.trim()) {
        setVoiceInterim("");
        void handleVoiceUserMessage(final.trim());
      }
    };

    sr.onerror = (e: any) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setVoiceError(t("voice.micBlocked"));
        stopVoice();
        return;
      }
      // Any non-permission error means SR won't work this session — go straight to VAD
      srBrokenRef.current = true;
      clearTimeout(srAbortTimer);
    };

    sr.onend = () => {
      clearTimeout(srAbortTimer);
      setRecRunning(false);
      if (!gotResult) {
        srEmptyStreakRef.current += 1;
        if (srEmptyStreakRef.current >= 1) {
          srBrokenRef.current = true;
          // Remember for future sessions — skip SR entirely in this browser
          try { localStorage.setItem("voice_sr_broken", "1"); } catch { /* ignore */ }
        }
      }
      if (!voiceActiveRef.current || voiceStatusRef.current !== "listening") return;
      if (srBrokenRef.current) {
        startVAD();
        return;
      }
      srRestartTimerRef.current = setTimeout(() => _startSR(SRCtor), 200);
    };

    try { sr.start(); } catch { /* already started — onend will retry */ }
  }

  // ── Fallback: VAD + MediaRecorder + Whisper ────────────────────────────
  /**
   * VAD + MediaRecorder voice input.
   * Uses AudioContext to detect speech energy, records with MediaRecorder,
   * and sends audio blobs to the backend Whisper transcription endpoint.
   * No dependency on Google's SpeechRecognition API.
   */
  function startVAD() {
    if (!voiceActiveRef.current) return;
    if (voiceVadActiveRef.current) return; // already running
    setUsingVAD(true);
    const stream = voiceStreamRef.current;
    if (!stream) return;

    voiceVadActiveRef.current = true;
    setRecRunning(true);

    const SILENCE_MS = 500;         // ms of silence = end of utterance
    const MIN_SPEECH_MS = 400;     // ignore bursts shorter than this (TV noise is often short)
    const MAX_RECORD_MS = 12000;   // force stop after 12s

    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);

    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    voiceRecorderRef.current = recorder;
    voiceChunksRef.current = [];

    const flushRecording = () => {
      if (recorder.state === "recording") recorder.stop();
    };

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) voiceChunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      // Pause VAD during transcription + API call — speakTTS will restart it after TTS
      voiceVadActiveRef.current = false;
      cancelAnimationFrame(voiceVadRafRef.current);

      const chunks = [...voiceChunksRef.current];
      voiceChunksRef.current = [];
      if (!chunks.length || !voiceActiveRef.current) { startListening(); return; }
      if (voiceStatusRef.current !== "listening") return;

      const blob = new Blob(chunks, { type: mimeType });
      setVoiceStatusSync("processing");
      setVoiceLiveText(t("voice.transcribing"));
      try {
        const result = await transcribe.mutateAsync(blob);
        const text = result.text?.trim();
        setVoiceLiveText("");
        if (text && voiceActiveRef.current) {
          void handleVoiceUserMessage(text);
        } else {
          setVoiceStatusSync("listening");
          startListening();
        }
      } catch {
        setVoiceLiveText("");
        if (voiceActiveRef.current) { setVoiceStatusSync("listening"); startListening(); }
      }
    };

    // ── Noise-floor calibration (first 600ms) ───────────────────────────
    // Measure ambient noise so we can set a dynamic threshold above it.
    let threshold = 20; // default; overwritten after calibration
    let calibrationSum = 0;
    let calibrationCount = 0;
    const CALIBRATION_TICKS = 24; // ~400ms at 60fps

    let speechStart = 0;
    let silenceStart = 0;
    let speaking = false;
    let maxTimer: ReturnType<typeof setTimeout> | null = null;

    const tick = () => {
      if (!voiceVadActiveRef.current) return;

      try {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((s, v) => s + v, 0) / data.length;
        setMicLevel(Math.min(100, Math.round((avg / 64) * 100)));

        // Calibration phase — just measure, don't start recording
        if (calibrationCount < CALIBRATION_TICKS) {
          calibrationSum += avg;
          calibrationCount++;
          if (calibrationCount === CALIBRATION_TICKS) {
            const floor = calibrationSum / calibrationCount;
            // Threshold well above noise floor to reject background noise
            threshold = Math.max(35, floor * 2.8); // higher floor for TV-noise environments
          }
          voiceVadRafRef.current = requestAnimationFrame(tick);
          return;
        }

        const now = Date.now();
        const isSpeech = avg > threshold;

        if (isSpeech && voiceStatusRef.current === "listening") {
          silenceStart = 0;
          if (!speaking) {
            speaking = true;
            speechStart = now;
            voiceChunksRef.current = [];
            if (recorder.state === "inactive") recorder.start(100);
            setVoiceLiveText(t("voice.recording"));
            maxTimer = setTimeout(() => { if (speaking) { speaking = false; flushRecording(); } }, MAX_RECORD_MS);
          }
        } else if (speaking) {
          if (!silenceStart) silenceStart = now;
          if (now - silenceStart >= SILENCE_MS) {
            speaking = false;
            if (maxTimer) { clearTimeout(maxTimer); maxTimer = null; }
            const duration = now - speechStart;
            flushRecording();
            if (duration < MIN_SPEECH_MS) {
              voiceChunksRef.current = [];
              setVoiceLiveText("");
            }
            silenceStart = 0;
          }
        }
      } catch {
        // AudioContext or analyser error — stop VAD cleanly
        voiceVadActiveRef.current = false;
        setVoiceLiveText("");
        if (voiceActiveRef.current) {
          setVoiceStatusSync("listening");
          setTimeout(() => startListening(), 500);
        }
        return;
      }

      voiceVadRafRef.current = requestAnimationFrame(tick);
    };

    // Expose flush so the "Enviar agora" button can trigger it
    (voiceRecorderRef as any)._flush = flushRecording;

    voiceVadRafRef.current = requestAnimationFrame(tick);
  }

  function stopVAD() {
    voiceVadActiveRef.current = false;
    cancelAnimationFrame(voiceVadRafRef.current);
    try {
      if (voiceRecorderRef.current?.state === "recording") {
        voiceRecorderRef.current.stop();
      }
    } catch { /* ignore */ }
    voiceRecorderRef.current = null;
    voiceChunksRef.current = [];
    setRecRunning(false);
    setMicLevel(0);
  }

  // Barge-in monitor: lightweight mic energy check running in parallel during TTS.
  // When the user speaks while the agent is talking, cancels TTS and hands the mic back.
  function startBargeInMonitor() {
    const stream = voiceStreamRef.current;
    if (!stream || bargeInCtxRef.current) return;
    const ctx = new AudioContext();
    bargeInCtxRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const d = new Uint8Array(analyser.frequencyBinCount);

    // Adaptive barge-in: measure ambient noise while not speaking, then require
    // the user's voice to be clearly above that baseline — avoids TV false triggers.
    const BARGE_FRAMES = 20;          // ~330ms sustained (was 9/150ms)
    const BARGE_MIN_THRESHOLD = 55;   // absolute floor even in quiet rooms
    const BARGE_FACTOR = 2.5;         // voice must be 2.5× louder than ambient
    let frames = 0;
    let ambientSum = 0;
    let ambientCount = 0;
    let bargeThreshold = BARGE_MIN_THRESHOLD;

    const monitor = () => {
      if (!voiceActiveRef.current) { ctx.close(); bargeInCtxRef.current = null; return; }

      try {
        analyser.getByteFrequencyData(d);
        const avg = d.reduce((s, v) => s + v, 0) / d.length;

        if (voiceStatusRef.current !== "speaking") {
          // Calibrate ambient noise level during listening/processing phases
          ambientSum += avg;
          ambientCount++;
          if (ambientCount % 60 === 0) { // recalibrate every ~1s
            const floor = ambientSum / ambientCount;
            bargeThreshold = Math.max(BARGE_MIN_THRESHOLD, floor * BARGE_FACTOR);
            ambientSum = 0; ambientCount = 0;
          }
          frames = 0;
          bargeInRafRef.current = requestAnimationFrame(monitor);
          return;
        }

        // Speaking phase: check for user barge-in above adaptive threshold
        if (avg > bargeThreshold) {
          frames++;
          if (frames >= BARGE_FRAMES) {
            frames = 0;
            voiceBargeInRef.current = true;
            voiceMsgAbortRef.current?.abort();
            cancelTTS();
          }
        } else {
          frames = 0;
        }
      } catch { /* ignore */ }
      bargeInRafRef.current = requestAnimationFrame(monitor);
    };
    bargeInRafRef.current = requestAnimationFrame(monitor);
  }

  function stopBargeInMonitor() {
    cancelAnimationFrame(bargeInRafRef.current);
    bargeInCtxRef.current?.close();
    bargeInCtxRef.current = null;
  }

  async function handleVoiceUserMessage(text: string) {
    if (!text.trim() || !agentId) return;
    setVoiceLiveText("");
    setVoiceStatusSync("processing");
    setVoiceMsgs((prev) => [...prev, { role: "user", text }]);

    let sid = sessionId;
    if (!sid) {
      const s = await createSession.mutateAsync({ agent_id: agentId });
      sid = s.id;
      setSessionId(sid);
    }

    // ── Streaming SSE path ───────────────────────────────────────────────
    let sentenceBuffer = "";
    let fullReply = "";
    let firstSentenceSpoken = false;
    let streamDone = false;          // true once SSE "done" event arrives
    const pendingTTS: string[] = [];
    let ttsRunning = false;

    const SENTENCE_RE = /[^.!?]*[.!?]+(?:\s|$)/;

    voiceBargeInRef.current = false; // reset from any prior barge-in

    function finishListening() {
      if (voiceBargeInRef.current) {
        // User interrupted — switch to listening immediately
        voiceBargeInRef.current = false;
        if (voiceActiveRef.current) {
          setVoiceStatusSync("listening");
          setTimeout(() => startListening(), 150);
        }
        return;
      }
      if (streamDone && pendingTTS.length === 0 && !ttsRunning && voiceActiveRef.current) {
        setVoiceStatusSync("listening");
        setTimeout(() => startListening(), 300);
      }
    }

    function drainTTS() {
      if (voiceBargeInRef.current) return; // barge-in: stop speaking
      if (ttsRunning || pendingTTS.length === 0) return;
      const sentence = pendingTTS.shift()!;
      ttsRunning = true;
      if (!firstSentenceSpoken) {
        firstSentenceSpoken = true;
        cancelTTS(); // cancel ack before first real sentence
        setVoiceStatusSync("speaking");
      }
      // noRestart=true: we manage startListening() via finishListening()
      speakTTS(sentence, () => {
        ttsRunning = false;
        drainTTS();       // start next queued sentence if any
        finishListening(); // no-op unless stream done + queue empty + no TTS
      }, true);
    }

    function flushSentences(final = false) {
      let buf = sentenceBuffer;
      let match;
      while ((match = SENTENCE_RE.exec(buf)) !== null) {
        pendingTTS.push(match[0].trim());
        buf = buf.slice(match[0].length);
        drainTTS();
      }
      sentenceBuffer = buf;
      if (final && buf.trim()) {
        pendingTTS.push(buf.trim());
        sentenceBuffer = "";
        drainTTS();
      }
    }

    // Short ack while waiting for first token (~2-4s)

    const abortCtrl = new AbortController();
    voiceMsgAbortRef.current = abortCtrl;

    try {
      const token = getToken() ?? "";
      const apiBase = (import.meta.env.VITE_API_URL as string | undefined) || window.location.origin;
      // voice=true → backend adds brevity instruction before sending to agent
      const url = `${apiBase}/api/v1/chat/sessions/${sid}/messages/stream?voice=true&message=${encodeURIComponent(text)}`;
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
        signal: abortCtrl.signal,
      });

      if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let lineBuffer = "";

      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        lineBuffer += decoder.decode(value, { stream: true });
        const lines = lineBuffer.split("\n");
        lineBuffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const raw = line.slice(5).trim();
          let data: any;
          try { data = JSON.parse(raw); } catch { continue; }

          if (data.error) throw new Error(data.error);

          if (data.done) {
            streamDone = true;
            flushSentences(true);
            setVoiceMsgs((prev) => [...prev, { role: "assistant", text: fullReply }]);
            finishListening();
            break outer;
          }

          if (data.delta) {
            fullReply += data.delta;
            sentenceBuffer += data.delta;
            flushSentences(false);
          }
        }
      }

      // Stream closed without a "done" event (crash/timeout) — don't leave UI stuck
      if (!streamDone) {
        streamDone = true;
        if (fullReply.trim()) {
          flushSentences(true);
          setVoiceMsgs((prev) => [...prev, { role: "assistant", text: fullReply }]);
        }
        finishListening();
        if (!fullReply.trim() && voiceActiveRef.current) {
          setVoiceStatusSync("listening");
          startListening();
        }
      }

    } catch (err) {
      streamDone = true;
      cancelTTS();
      // AbortError = intentional barge-in; save whatever we accumulated before interrupting
      if ((err as any)?.name === "AbortError") {
        if (fullReply.trim()) {
          setVoiceMsgs((prev) => [...prev, { role: "assistant", text: fullReply }]);
        }
        finishListening();
        return;
      }
      if (voiceActiveRef.current) {
        setVoiceStatusSync("listening");
        startListening();
        setVoiceError(t("voice.failedResponse", { error: String(err) }));
      }
    }
  }

  async function startVoice() {
    // ── Step 1: open overlay immediately ──────────────────────────────────
    setVoiceActive(true);
    setVoicePhase("checking");
    setVoiceChecklist([]);
    setVoiceMsgs([]);
    setVoiceError(null);
    voiceActiveRef.current = true;
    // If SR was already proven broken in this browser, skip straight to VAD
    srBrokenRef.current = localStorage.getItem("voice_sr_broken") === "1";
    srEmptyStreakRef.current = 0;
    setUsingVAD(srBrokenRef.current);

    // Unlock TTS synchronously before any await
    if (window.speechSynthesis) {
      const unlock = new SpeechSynthesisUtterance("");
      window.speechSynthesis.speak(unlock);
      window.speechSynthesis.cancel();
    }

    // ── Step 2: pre-flight checks ─────────────────────────────────────────
    const items: CheckItem[] = [];
    const push = (item: CheckItem) => { items.push(item); setVoiceChecklist([...items]); };

    // MediaRecorder / getUserMedia support
    const hasRecorder = Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia);
    push({ id: "sr", label: t("voice.checklist.audioRecording"), ok: hasRecorder,
      detail: hasRecorder ? t("voice.checklist.audioRecordingOk") : t("voice.checklist.audioRecordingFail") });
    if (!hasRecorder) { setVoicePhase("error"); voiceActiveRef.current = false; return; }

    // SpeechSynthesis API + voices
    const hasTTS = Boolean(window.speechSynthesis);
    let voices = hasTTS ? window.speechSynthesis.getVoices() : [];
    if (hasTTS && voices.length === 0) {
      await new Promise<void>((res) => {
        const voiceTimeout = setTimeout(res, 2000);
        window.speechSynthesis.onvoiceschanged = () => { clearTimeout(voiceTimeout); res(); };
      });
      voices = window.speechSynthesis.getVoices();
    }
    ttsVoicesRef.current = voices;
    push({ id: "tts", label: t("voice.checklist.tts"), ok: hasTTS && voices.length > 0,
      detail: !hasTTS ? t("voice.checklist.ttsNotSupported") : voices.length === 0 ? t("voice.checklist.ttsNoVoices") : t("voice.checklist.ttsVoiceCount", { count: voices.length }) });

    // Microphone permission — open stream and keep it open for the whole conversation
    let micOk = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      voiceStreamRef.current = stream;
      micOk = true;
    } catch {
      micOk = false;
    }
    push({ id: "mic", label: t("voice.checklist.microphone"), ok: micOk,
      detail: micOk ? t("voice.checklist.microphoneOk") : t("voice.checklist.microphoneFail") });
    if (!micOk) { setVoicePhase("error"); voiceActiveRef.current = false; return; }

    // Barge-in monitor runs for the whole voice session
    startBargeInMonitor();

    // Show mic level meter briefly so user can confirm audio is coming in
    {
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(voiceStreamRef.current!);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const d = new Uint8Array(analyser.frequencyBinCount);
      let raf = 0;
      const tick = () => {
        analyser.getByteFrequencyData(d);
        const avg = d.reduce((s, v) => s + v, 0) / d.length;
        setMicLevel(Math.min(100, Math.round((avg / 64) * 100)));
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
      await new Promise((res) => setTimeout(res, 1400));
      cancelAnimationFrame(raf);
      setMicLevel(0);
    }

    // ── Step 3: start conversation ────────────────────────────────────────
    setVoicePhase("active");
    setVoiceStatusSync("speaking");

    const agentName = selectedAgent?.name ?? t("voice.greeting.agentFallback");
    const h = new Date().getHours();
    const period = h < 12 ? t("voice.greeting.goodMorning") : h < 18 ? t("voice.greeting.goodAfternoon") : t("voice.greeting.goodEvening");
    const greeting = t("voice.greeting.text", { period, name: agentName });
    setVoiceMsgs([{ role: "assistant", text: greeting }]);

    if (hasTTS && voices.length > 0) {
      speakTTS(greeting, () => {
        if (voiceActiveRef.current) setVoiceStatusSync("listening");
      });
    } else {
      setVoiceStatusSync("listening");
      startListening();
    }
  }

  function stopVoice() {
    voiceActiveRef.current = false;
    voiceMsgAbortRef.current?.abort();
    cancelTTS();
    stopListening();
    stopBargeInMonitor();
    voiceStreamRef.current?.getTracks().forEach((t) => t.stop());
    voiceStreamRef.current = null;
    setVoiceActive(false);
    setVoicePhase("idle");
    setVoiceLiveText("");
    setVoiceError(null);
    setVoiceChecklist([]);
  }

  // scroll voice transcript to bottom
  useEffect(() => {
    voiceMsgsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [voiceMsgs]);
  // ── end voice ────────────────────────────────────────────────────────────

  // One row renderer shared by the loose list and every Project/Group
  // sub-folder in the tree above -- same row, three possible parents.
  function renderSessionRow(s: ChatSession) {
    return (
      <div
        key={s.id}
        className={cn(
          "group flex items-center justify-between gap-1 rounded-md px-2 py-2 text-sm",
          s.id === sessionId
            ? "bg-accent text-accent-foreground"
            : "cursor-pointer text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )}
        onClick={() => editingSessionId !== s.id && setSessionId(s.id)}
      >
        {editingSessionId === s.id ? (
          <input
            autoFocus
            value={editingTitle}
            onChange={(e) => setEditingTitle(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onBlur={handleCommitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCommitRename();
              if (e.key === "Escape") setEditingSessionId(null);
            }}
            className="min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
        ) : (
          <span className="flex min-w-0 flex-1 flex-col gap-0.5 overflow-hidden">
            <span className="flex min-w-0 items-center gap-1.5 truncate">
              {s.pinned && <Pin className="h-3 w-3 shrink-0 opacity-70" />}
              <span className="truncate">{s.title}</span>
            </span>
          </span>
        )}
        {editingSessionId !== s.id && (
          <ChatItemMenu
            session={s}
            projects={projectsWithPath}
            groups={chatGroups ?? []}
            onRename={() => handleStartRename(s)}
            onTogglePin={() => handleTogglePin(s)}
            onDelete={() => {
              if (!window.confirm(t("itemMenu.confirmDelete", { title: s.title }))) return;
              deleteSession.mutate(s.id, {
                onSuccess: () => {
                  if (s.id === sessionId) setSessionId("");
                },
              });
            }}
            onMoveToProject={(path) => handleMoveSessionToProject(s.id, path)}
            onMoveToGroup={(groupId) => handleMoveSessionToGroup(s.id, groupId)}
            onCreateGroupAndMove={(name) => handleCreateGroupAndMoveSession(s.id, name)}
          />
        )}
      </div>
    );
  }

  return (
    <div className={cn("absolute inset-0 flex gap-2 p-2", !active && "hidden")}>
      {!historyCollapsed && (
        <aside className="flex w-64 shrink-0 flex-col rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border p-3">
            <span className="text-sm font-medium text-muted-foreground">{t("sidebar.chats")}</span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" title={t("sidebar.newChat")} aria-label={t("sidebar.newChat")} onClick={handleNewChat}>
                <Plus className="h-4 w-4" />
              </Button>
              <AgentPickerButton agents={chatableAgents} selectedAgentId={agentId} onSelect={onAgentChange} />
            </div>
          </div>
          <div className="flex items-center border-b border-border px-2 py-1">
            <SessionProjectPicker
              currentPath={activeSession?.working_directory_path}
              disabled={!sessionId}
              onSelect={handleSetSessionWorkingDirectory}
            />
          </div>
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                value={chatSearchInput}
                onChange={(e) => setChatSearchInput(e.target.value)}
                placeholder={t("sidebar.searchConversations")}
                className="h-8 w-full rounded-md border border-border bg-transparent pl-7 pr-2 text-xs outline-none focus:border-primary"
              />
            </div>
          </div>
          <div className="flex-1 space-y-1 overflow-y-auto p-2">
            {chatSearchTerm.trim() && isSearchingChats && (
              <p className="px-2 py-2 text-xs italic text-muted-foreground">{t("sidebar.searching")}</p>
            )}
            {chatSearchTerm.trim() && !isSearchingChats && displayedSessions.length === 0 && (
              <p className="px-2 py-2 text-xs italic text-muted-foreground">{t("sidebar.noConversationsFound")}</p>
            )}
            {chatSearchTerm.trim()
              ? displayedSessions.map((s) => renderSessionRow(s))
              : (
                <>
                  {/* Root folder: Projetos -- always visible, one sub-row
                      per registered Project that has >=1 session (see
                      projectFoldersWithSessions above). */}
                  <div>
                    <button
                      type="button"
                      className="flex w-full items-center gap-1 rounded-md px-1 py-1.5 text-left text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                      onClick={() => setProjectsRootOpen((v) => !v)}
                    >
                      {projectsRootOpen ? (
                        <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                      )}
                      <FolderKanban className="h-3.5 w-3.5 shrink-0" />
                      <span>{t("groups.projectsRoot")}</span>
                    </button>
                    {projectsRootOpen && (
                      <div className="ml-2 space-y-1 border-l border-border pl-2">
                        {projectFoldersWithSessions.length === 0 && (
                          <p className="px-2 py-1 text-xs italic text-muted-foreground">{t("groups.noProjectChats")}</p>
                        )}
                        {projectFoldersWithSessions.map((p) => {
                          const isOpen = openProjectPaths.has(p.working_directory_path);
                          const sessionsHere = sessionsByProjectPath.get(p.working_directory_path) ?? [];
                          return (
                            <div key={p.id} className="group/p">
                              <div className="flex items-center gap-1">
                                <button
                                  type="button"
                                  className="flex min-w-0 flex-1 items-center gap-1 rounded-md px-1 py-1 text-left text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                                  onClick={() => setOpenProjectPaths((s) => toggleOpenPath(s, p.working_directory_path))}
                                >
                                  {isOpen ? (
                                    <ChevronDown className="h-3 w-3 shrink-0" />
                                  ) : (
                                    <ChevronRight className="h-3 w-3 shrink-0" />
                                  )}
                                  <span className="truncate">{p.name}</span>
                                  <span className="ml-auto shrink-0 opacity-60">{sessionsHere.length}</span>
                                </button>
                                <button
                                  type="button"
                                  title={t("groups.clearProjectChats")}
                                  aria-label={t("groups.clearProjectChats")}
                                  className="shrink-0 rounded-md p-1 opacity-0 hover:bg-accent group-hover/p:opacity-100"
                                  onClick={() =>
                                    handleClearSessions(
                                      sessionsHere,
                                      t("groups.confirmClearProject", { count: sessionsHere.length, name: p.name })
                                    )
                                  }
                                >
                                  <Eraser className="h-3 w-3" />
                                </button>
                              </div>
                              {isOpen && <div className="space-y-1">{sessionsHere.map((s) => renderSessionRow(s))}</div>}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Root folder: Grupos -- user-created named folders, no
                      link to Project/disk path (see ChatGroup docstring). */}
                  <div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 items-center gap-1 rounded-md px-1 py-1.5 text-left text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                        onClick={() => setGroupsRootOpen((v) => !v)}
                      >
                        {groupsRootOpen ? (
                          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                        )}
                        <Folder className="h-3.5 w-3.5 shrink-0" />
                        <span>{t("groups.groupsRoot")}</span>
                      </button>
                      <button
                        type="button"
                        title={t("groups.newGroup")}
                        aria-label={t("groups.newGroup")}
                        className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                        onClick={() => {
                          setGroupsRootOpen(true);
                          setCreatingGroup(true);
                        }}
                      >
                        <Plus className="h-3.5 w-3.5" />
                      </button>
                    </div>
                    {groupsRootOpen && (
                      <div className="ml-2 space-y-1 border-l border-border pl-2">
                        {creatingGroup && (
                          <div className="flex items-center gap-1 px-1 py-1">
                            <input
                              autoFocus
                              value={newGroupNameRoot}
                              onChange={(e) => setNewGroupNameRoot(e.target.value)}
                              onBlur={() => {
                                if (!newGroupNameRoot.trim()) setCreatingGroup(false);
                              }}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && newGroupNameRoot.trim()) {
                                  createChatGroup.mutate(newGroupNameRoot.trim());
                                  setNewGroupNameRoot("");
                                  setCreatingGroup(false);
                                }
                                if (e.key === "Escape") {
                                  setNewGroupNameRoot("");
                                  setCreatingGroup(false);
                                }
                              }}
                              placeholder={t("groups.newGroupPlaceholder")}
                              className="h-7 min-w-0 flex-1 rounded-md border border-border bg-transparent px-2 text-xs outline-none focus:border-primary"
                            />
                          </div>
                        )}
                        {(chatGroups ?? []).length === 0 && !creatingGroup && (
                          <p className="px-2 py-1 text-xs italic text-muted-foreground">{t("groups.noGroupsYet")}</p>
                        )}
                        {(chatGroups ?? []).map((g) => {
                          const isOpen = openGroupIds.has(g.id);
                          const sessionsHere = sessionsByGroupId.get(g.id) ?? [];
                          return (
                            <div key={g.id}>
                              <div className="group/g flex items-center gap-1">
                                <button
                                  type="button"
                                  className="flex min-w-0 flex-1 items-center gap-1 rounded-md px-1 py-1 text-left text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                                  onClick={() => setOpenGroupIds((s) => toggleOpenPath(s, g.id))}
                                >
                                  {isOpen ? (
                                    <ChevronDown className="h-3 w-3 shrink-0" />
                                  ) : (
                                    <ChevronRight className="h-3 w-3 shrink-0" />
                                  )}
                                  <span className="truncate">{g.name}</span>
                                  <span className="ml-auto shrink-0 opacity-60">{sessionsHere.length}</span>
                                </button>
                                <button
                                  type="button"
                                  title={t("groups.clearGroupChats")}
                                  aria-label={t("groups.clearGroupChats")}
                                  className="shrink-0 rounded-md p-1 opacity-0 hover:bg-accent group-hover/g:opacity-100"
                                  onClick={() =>
                                    handleClearSessions(
                                      sessionsHere,
                                      t("groups.confirmClearGroup", { count: sessionsHere.length, name: g.name })
                                    )
                                  }
                                >
                                  <Eraser className="h-3 w-3" />
                                </button>
                                <button
                                  type="button"
                                  title={t("itemMenu.rename")}
                                  aria-label={t("itemMenu.rename")}
                                  className="shrink-0 rounded-md p-1 opacity-0 hover:bg-accent group-hover/g:opacity-100"
                                  onClick={() => {
                                    const name = window.prompt(t("groups.renamePrompt"), g.name);
                                    if (name && name.trim()) updateChatGroup.mutate({ groupId: g.id, name: name.trim() });
                                  }}
                                >
                                  <Pencil className="h-3 w-3" />
                                </button>
                                <button
                                  type="button"
                                  title={t("itemMenu.delete")}
                                  aria-label={t("itemMenu.delete")}
                                  className="shrink-0 rounded-md p-1 text-destructive opacity-0 hover:bg-accent group-hover/g:opacity-100"
                                  onClick={() => {
                                    if (window.confirm(t("groups.confirmDeleteGroup", { name: g.name }))) {
                                      deleteChatGroup.mutate(g.id);
                                    }
                                  }}
                                >
                                  <Trash2 className="h-3 w-3" />
                                </button>
                              </div>
                              {isOpen && <div className="space-y-1">{sessionsHere.map((s) => renderSessionRow(s))}</div>}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Loose conversations -- no Project, no Group ("geral").
                      Same flat list the sidebar always showed before this
                      tree existed, now with its own independent clear icon. */}
                  <div className="space-y-1 pt-1">
                    {looseSessions.length > 0 && (
                      <div className="group/loose flex items-center gap-1 px-1">
                        <span className="min-w-0 flex-1 truncate text-xs font-medium text-muted-foreground">
                          {t("groups.generalRoot")}
                        </span>
                        <button
                          type="button"
                          title={t("groups.clearGeneralChats")}
                          aria-label={t("groups.clearGeneralChats")}
                          className="shrink-0 rounded-md p-1 opacity-0 hover:bg-accent group-hover/loose:opacity-100"
                          onClick={() =>
                            handleClearSessions(
                              looseSessions,
                              t("groups.confirmClearGeneral", { count: looseSessions.length })
                            )
                          }
                        >
                          <Eraser className="h-3 w-3" />
                        </button>
                      </div>
                    )}
                    {looseSessions.map((s) => renderSessionRow(s))}
                    {looseSessions.length === 0 && (sessions ?? []).length === 0 && (
                      <p className="px-2 py-2 text-xs italic text-muted-foreground">{t("sidebar.noConversationsYet")}</p>
                    )}
                  </div>
                </>
              )}
          </div>
        </aside>
      )}

      <div className="relative flex flex-1 flex-col overflow-hidden rounded-lg border border-border bg-card">
        {/* ── Voice conversation overlay ──────────────────────────── */}
        <AnimatePresence>
          {voiceActive && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="absolute inset-0 z-20 flex flex-col rounded-lg bg-card"
            >
              {/* Header */}
              <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-2">
                <span className="text-sm font-medium text-muted-foreground">
                  {t("voice.conversationWith", { name: selectedAgent?.name })}
                </span>
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={stopVoice}>
                  <X className="h-4 w-4" />
                </Button>
              </div>

              {/* ── Checklist phase ────────────────────────────────────── */}
              {voicePhase === "checking" && (
                <div className="flex flex-1 flex-col items-center justify-center gap-3">
                  <motion.div
                    className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
                  />
                  <p className="text-xs text-muted-foreground">{t("voice.starting")}</p>
                </div>
              )}
              {voicePhase === "error" && (
                <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
                  <p className="text-sm text-destructive text-center">
                    {voiceError ?? t("voice.couldNotStart")}
                  </p>
                  <Button variant="outline" size="sm" onClick={stopVoice}>
                    {t("composer.close")}
                  </Button>
                </div>
              )}

              {/* ── Active conversation phase: transcript left + orb right ── */}
              {voicePhase === "active" && (
                <div className="relative flex flex-1 overflow-hidden">

                  {/* Transcript — recoils to 68%, stays scrollable */}
                  <motion.div
                    className="flex flex-col overflow-hidden border-r border-border/40"
                    initial={{ width: "100%" }}
                    animate={{ width: "68%" }}
                    transition={{ duration: 0.55, ease: [0.4, 0, 0.2, 1] }}
                  >
                    <div className="flex-1 space-y-3 overflow-y-auto p-4">
                      {voiceMsgs.length === 0 && (
                        <p className="py-10 text-center text-sm italic text-muted-foreground">
                          {t("voice.waitingFor", { name: selectedAgent?.name })}
                        </p>
                      )}
                      {voiceMsgs.map((m, i) => (
                        <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                          <div className={cn(
                            "max-w-[88%] rounded-2xl px-4 py-2 text-sm shadow-sm",
                            m.role === "user"
                              ? "bg-indigo-600 text-white"
                              : "bg-muted text-foreground"
                          )}>
                            {m.text}
                          </div>
                        </div>
                      ))}
                      {/* SR interim — real-time transcription as user speaks */}
                      {voiceInterim && (
                        <div className="flex justify-end">
                          <div className="max-w-[88%] rounded-2xl border border-indigo-500/40 px-4 py-2 text-sm italic text-indigo-300/80">
                            {voiceInterim}
                          </div>
                        </div>
                      )}
                      {/* VAD / status text (Gravando…, Transcrevendo…) */}
                      {voiceLiveText && !voiceInterim && (
                        <div className="flex justify-end">
                          <div className="max-w-[88%] rounded-2xl border border-border px-4 py-2 text-sm italic text-muted-foreground">
                            {voiceLiveText}
                          </div>
                        </div>
                      )}
                      <div ref={voiceMsgsEndRef} />
                    </div>

                    {voiceError && (
                      <div className="shrink-0 mx-3 mb-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                        {voiceError}
                      </div>
                    )}
                  </motion.div>

                  {/* Agent orb — slides in from right, covers 32% */}
                  <motion.div
                    className="absolute right-0 top-0 bottom-0 flex flex-col items-center justify-center gap-4 overflow-hidden bg-card/90 backdrop-blur-sm"
                    initial={{ width: "0%", opacity: 0 }}
                    animate={{ width: "32%", opacity: 1 }}
                    transition={{ duration: 0.55, ease: [0.4, 0, 0.2, 1] }}
                  >
                    <VoiceOrb status={voiceStatus} compact />
                    <p className="text-center text-xs leading-relaxed text-muted-foreground px-3">
                      {{
                        listening: t("voice.listening"),
                        processing: t("voice.thinking", { name: selectedAgent?.name }),
                        speaking: t("voice.replying", { name: selectedAgent?.name }),
                      }[voiceStatus]}
                    </p>
                    {/* Mic level + status */}
                    <div className="flex flex-col items-center gap-1 w-full px-4">
                      <div className="flex items-center gap-1.5">
                        <span className={cn(
                          "h-2 w-2 rounded-full",
                          recRunning ? "bg-green-500 animate-pulse" : "bg-muted-foreground/40"
                        )} />
                        <span className="text-[10px] text-muted-foreground">
                          {recRunning
                            ? t("voice.micActive")
                            : voiceStatus === "speaking" ? t("voice.agentSpeaking") : t("voice.waiting")}
                        </span>
                      </div>
                      {recRunning && (
                        <div className="h-1 w-full overflow-hidden rounded-full bg-muted/60">
                          <motion.div
                            className={cn("h-full rounded-full",
                              micLevel > 20 ? "bg-green-500" : "bg-muted-foreground/40")}
                            animate={{ width: `${micLevel}%` }}
                            transition={{ duration: 0.05 }}
                          />
                        </div>
                      )}
                    </div>
                  </motion.div>
                </div>
              )}

              {/* ── Footer — always visible inside the overlay ──────────── */}
              <div className="shrink-0 border-t border-border p-3 space-y-2">
                <div className="flex justify-center">
                  <Button variant="outline" size="sm" onClick={stopVoice} className="gap-2">
                    <X className="h-4 w-4" />
                    {t("voice.endConversation")}
                  </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {/* ── end voice overlay ───────────────────────────────────── */}

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {visibleMessages.length === 0 && (
            <p className="py-12 text-center text-sm italic text-muted-foreground">
              {emptyStateText ?? languageTexts.emptyState(selectedAgent?.name ?? "agent")}
            </p>
          )}
          {visibleMessages.map((m, i, list) => {
            const prev = list[i - 1];
            const isCommandReply =
              m.role === "assistant" && prev?.role === "user" && isPlainTextReply(prev.content);
            const canRegenerate =
              i === list.length - 1 && m.role === "assistant" && !isCommandReply && pendingQueue.length === 0;
            const isLastUserMessage =
              m.role === "user" && !list.slice(i + 1).some((later) => later.role === "user");
            const canEdit = isLastUserMessage && pendingQueue.length === 0 && !isPlainTextReply(m.content);
            const respondingAgentName = m.responding_agent_id
              ? chatableAgents.find((a) => a.id === m.responding_agent_id)?.name
              : undefined;
            const finishedSteps = m.role === "assistant" ? finishedStepsByMessageId.get(m.id) : undefined;
            return (
              <div key={m.id} className="space-y-1">
                {finishedSteps && <FinishedStepsTrail steps={finishedSteps} />}
                <MessageBubble
                  message={m}
                  isCommandReply={isCommandReply}
                  onRegenerate={canRegenerate ? () => handleRegenerate(m) : undefined}
                  regenerateDisabled={deleteMessage.isPending}
                  respondingAgentName={respondingAgentName}
                  onEdit={canEdit ? (newContent) => handleEditMessage(m, newContent) : undefined}
                  editDisabled={deleteMessage.isPending}
                />
              </div>
            );
          })}
          {/* Turno em execução observado do servidor. Só aparece quando esta
              aba NÃO é a que transmite -- senão a fila abaixo já o desenha ao
              vivo e o mesmo turno sairia duas vezes. É o que se vê depois de
              um F5, de um travamento, ou ao abrir a conversa em outra
              máquina: a execução continua e a tela acompanha. */}
          {queue.length === 0 && activeTurn && (
            <div className="space-y-2">
              <div className="flex justify-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                  {activeTurn.prompt}
                </div>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                {t("activeTurn.running")}
              </div>
              {activeTurn.steps.length > 0 && (
                <QueueStepsList
                  // O backend guarda `status` (texto); a UI usa `done`
                  // (booleano). A conversão fica aqui, no ponto de leitura,
                  // em vez de mudar o formato gravado -- que também serve ao
                  // canal e a quem for depurar a linha.
                  steps={activeTurn.steps.map((step) => ({
                    id: step.id,
                    name: step.name ?? "",
                    label: step.label ?? step.name ?? "",
                    done: step.status === "done",
                  }))}
                />
              )}
              {activeTurn.live_text && (
                <div className="whitespace-pre-wrap text-sm text-foreground">{activeTurn.live_text}</div>
              )}
              {activeTurn.pending_approval && (
                <p className="text-xs text-amber-500">{t("activeTurn.awaitingApproval")}</p>
              )}
            </div>
          )}
          {queue.map((item) => {
            const revealed = revealedQueueIds.has(item.id);
            // A hidden priming turn renders as nothing at all while it
            // works (the transcript never shows it either way) -- only an
            // error is surfaced, so a failed priming isn't silently lost.
            // The user can still reveal it by clicking its line in the
            // summary strip below (see revealedQueueIds), which shows it
            // right here in the chat screen rather than anywhere else.
            if (item.hidden && item.status !== "error" && !revealed) return null;
            return (
            <div
              key={item.id}
              ref={(el) => {
                if (el) queueItemRefs.current.set(item.id, el);
                else queueItemRefs.current.delete(item.id);
              }}
              className={cn(
                "space-y-1",
                item.hidden && revealed && "rounded-lg border border-dashed border-border/60 bg-muted/20 p-2"
              )}
            >
              {item.hidden && revealed && (
                <p className="pl-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                  {t("queue.internalContext")}
                </p>
              )}
              {!item.isRegenerate && !item.skipUserMessage && (!item.hidden || revealed) && (
                <MessageBubble
                  message={{
                    id: `pending-${item.id}`,
                    session_id: sessionId,
                    role: "user",
                    content: item.content,
                    attachment_names: item.attachmentName,
                    created_at: new Date().toISOString(),
                  }}
                />
              )}
              {item.status === "queued" && (
                <p className="pl-1 text-xs italic text-muted-foreground">{t("queue.queued")}</p>
              )}
              {item.status === "processing" && (
                <div className="flex max-w-[85%] flex-col gap-1">
                  {(item.startedAt && !item.isExec) || item.abortController ? (
                    <div className="flex items-center gap-2">
                      {item.startedAt && !item.isExec && <LiveThinkingLabel startedAt={item.startedAt} />}
                      {item.abortController && (
                        <button
                          type="button"
                          className="flex w-fit items-center gap-1 rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                          onClick={() => handleStopGenerating(item)}
                        >
                          <Square className="h-2.5 w-2.5" />
                          {t("queue.stop")}
                        </button>
                      )}
                    </div>
                  ) : null}
                  {item.targetAgentName && (
                    <span className="flex w-fit items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">
                      <Bot className="h-2.5 w-2.5" />
                      {item.targetAgentName}
                    </span>
                  )}
                  <QueueStepsList steps={item.steps} />
                  {item.liveText &&
                    (isPlainTextReply(item.content) ? (
                      <pre className="whitespace-pre-wrap break-words rounded-lg bg-muted/50 px-3 py-2 font-mono text-xs">
                        {item.liveText}
                      </pre>
                    ) : (
                      <Markdown content={item.liveText} />
                    ))}
                  {!item.approval && (
                    <p className="flex items-center gap-1.5 py-1 text-xs text-muted-foreground">
                      {item.isExec ? (
                        <>
                          <span aria-hidden>💻</span> {t("queue.runningCommand")}
                        </>
                      ) : (
                        <>
                          <span aria-hidden>✍️</span>
                          {t("queue.agentIsTyping", { name: item.targetAgentName ?? selectedAgent?.name ?? t("queue.agentFallback") })}
                        </>
                      )}
                      <TypingDots />
                    </p>
                  )}
                </div>
              )}
              {item.approval && (
                <div className="space-y-2 rounded-2xl border border-amber-500/40 bg-amber-500/10 px-4 py-3">
                  <p className="text-xs font-medium text-amber-600 dark:text-amber-400">
                    {t("queue.approvalRequest", { name: item.targetAgentName ?? selectedAgent?.name ?? t("queue.agentFallback") })}
                  </p>
                  {item.approval.description && (
                    <p className="text-xs text-muted-foreground">{item.approval.description}</p>
                  )}
                  {item.approval.command && (
                    <code className="block overflow-x-auto whitespace-pre-wrap break-all rounded bg-background/60 px-2 py-1 text-xs">
                      {item.approval.command}
                    </code>
                  )}
                  {item.approval.patternKeys && item.approval.patternKeys.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {item.approval.patternKeys.map((key) => (
                        <span
                          key={key}
                          className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] text-amber-700 dark:text-amber-300"
                        >
                          {key}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      onClick={() => handleApprovalChoice(item.id, item.approval!.streamId, "once")}
                    >
                      {t("queue.approveOnce")}
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      title={t("queue.approveSessionTitle")}
                      onClick={() => handleApprovalChoice(item.id, item.approval!.streamId, "session")}
                    >
                      {t("queue.approveSession")}
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleApprovalChoice(item.id, item.approval!.streamId, "deny")}
                    >
                      {t("queue.deny")}
                    </Button>
                  </div>
                </div>
              )}
              {item.status === "error" && (
                <p className="flex items-center gap-2 pl-1 text-xs text-destructive">
                  {t("queue.failed", { error: item.error })}
                  <button
                    type="button"
                    aria-label={t("queue.dismiss")}
                    onClick={() => setQueue((q) => q.filter((it) => it.id !== item.id))}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </p>
              )}
            </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>

        <div className="space-y-2 border-t border-border p-3">
          {pendingQueue.length > 1 && (
            <div className="space-y-1 rounded-lg border border-border bg-muted/30 px-2.5 py-1.5 text-xs">
              {pendingQueue.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={revealedQueueIds.has(item.id)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded text-left text-muted-foreground hover:text-foreground",
                    revealedQueueIds.has(item.id) && "text-foreground"
                  )}
                  onClick={() => toggleQueueItemRevealed(item.id)}
                >
                  {item.status === "processing" ? (
                    <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                  ) : (
                    <span className="h-2 w-2 shrink-0 rounded-full border border-current" />
                  )}
                  <span className="flex-1 truncate">{item.content || item.attachmentName}</span>
                  {revealedQueueIds.has(item.id) ? (
                    <ChevronDown className="h-3 w-3 shrink-0" />
                  ) : (
                    <ChevronRight className="h-3 w-3 shrink-0" />
                  )}
                </button>
              ))}
            </div>
          )}
          {composerWarning && (
            <p className="px-1 text-xs text-destructive">{composerWarning}</p>
          )}
          {!composerWarning && showSelfRestartWarning && (
            <p className="flex items-center gap-1.5 px-1 text-xs text-amber-500">
              <AlertCircle className="h-3 w-3 shrink-0" />
              {t("composer.selfRestartWarning")}
            </p>
          )}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {attachedFiles.map((file, index) => (
                <div key={index} className="flex w-fit items-center gap-2 rounded-md bg-muted px-2 py-1 text-xs">
                  {attachedImagePreviewUrls[index] ? (
                    <button
                      type="button"
                      aria-label={t("composer.viewAttachedImage")}
                      onClick={() => setImagePreviewIndex(index)}
                      className="shrink-0"
                    >
                      <img src={attachedImagePreviewUrls[index]!} alt="" className="h-6 w-6 rounded object-cover" />
                    </button>
                  ) : (
                    <Paperclip className="h-3 w-3" />
                  )}
                  {file.name}
                  <button type="button" aria-label={t("composer.removeAttachment")} onClick={() => removeAttachedFile(index)}>
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ))}
            </div>
          )}
          {imagePreviewIndex !== null && attachedImagePreviewUrls[imagePreviewIndex] && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center p-4"
              role="dialog"
              aria-modal="true"
              onClick={() => setImagePreviewIndex(null)}
            >
              <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
              <div
                className="relative z-10 flex max-h-[80vh] max-w-[80vw] flex-col items-center gap-3"
                onClick={(e) => e.stopPropagation()}
              >
                <img
                  src={attachedImagePreviewUrls[imagePreviewIndex]!}
                  alt={attachedFiles[imagePreviewIndex]?.name ?? ""}
                  className="max-h-[70vh] max-w-[80vw] rounded-lg object-contain shadow-2xl"
                />
                <Button
                  type="button"
                  variant="secondary"
                  className="gap-2"
                  onClick={() => {
                    removeAttachedFile(imagePreviewIndex);
                    setImagePreviewIndex(null);
                  }}
                >
                  <X className="h-4 w-4" />
                  {t("composer.remove")}
                </Button>
                <button
                  type="button"
                  aria-label={t("composer.close")}
                  onClick={() => setImagePreviewIndex(null)}
                  className="absolute -right-3 -top-3 rounded-full border border-border bg-card p-1.5 shadow-md hover:bg-accent"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
          <ComposerShell
            ref={composerTextareaRef}
            value={composerText}
            onChange={(e) => {
              const value = e.target.value;
              setComposerText(value);
              if (composerWarning) setComposerWarning(null);
              const last = value.slice(-1);
              const beforeLast = value.slice(-2, -1);
              if (last === "@" && (beforeLast === "" || /\s/.test(beforeLast))) {
                setMentionOpen(true);
              }
              if (value === "/") {
                setSlashOpen(true);
              } else if (slashOpen && !value.startsWith("/")) {
                setSlashOpen(false);
              }
              if (last === "#" && (beforeLast === "" || /\s/.test(beforeLast))) {
                setAgentMentionOpen(true);
                setAgentMentionQuery("");
              } else if (agentMentionOpen) {
                const hashIndex = value.lastIndexOf("#");
                if (hashIndex === -1 || /\s/.test(value.slice(hashIndex + 1))) {
                  setAgentMentionOpen(false);
                } else {
                  setAgentMentionQuery(value.slice(hashIndex + 1));
                }
              }
              if (last === "$" && (beforeLast === "" || /\s/.test(beforeLast))) {
                setArtifactMentionOpen(true);
                setArtifactMentionQuery("");
              } else if (artifactMentionOpen) {
                const dollarIndex = value.lastIndexOf("$");
                if (dollarIndex === -1 || /\s/.test(value.slice(dollarIndex + 1))) {
                  setArtifactMentionOpen(false);
                } else {
                  setArtifactMentionQuery(value.slice(dollarIndex + 1));
                }
              }
            }}
            onKeyDown={handleComposerKeyDown}
            onPaste={handleComposerPaste}
            placeholder={
              suggestedReply
                ? t("composer.completeHint", { text: suggestedReply })
                : languageTexts.ask(selectedAgent?.name ?? "agent")
            }
            textareaClassName="min-h-0 overflow-y-auto"
            textareaStyle={{ maxHeight: COMPOSER_MAX_HEIGHT_PX }}
            dragActive={composerDragActive}
            dropHint={
              <>
                <Paperclip className="mr-2 h-4 w-4" /> {t("composer.dropIntoAssistant")}
              </>
            }
            onDragEnter={(e) => {
              e.preventDefault();
              setComposerDragActive(true);
            }}
            onDragOver={(e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = "copy";
              setComposerDragActive(true);
            }}
            onDragLeave={(e) => {
              if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setComposerDragActive(false);
            }}
            onDrop={handleComposerDrop}
            leading={
              <>
                {mentionOpen && (
                  <MentionFilePicker
                    ref={mentionPickerRef}
                    onSelectPath={handleMentionSelect}
                    onClose={() => setMentionOpen(false)}
                  />
                )}
                {slashOpen && (
                  <SlashCommandPicker
                    ref={slashPickerRef}
                    promptCommands={promptCommands}
                    onSelect={handleSlashSelect}
                    onClose={() => setSlashOpen(false)}
                  />
                )}
                {agentMentionOpen && (
                  <AgentMentionPicker
                    ref={agentPickerRef}
                    agents={chatableAgents}
                    query={agentMentionQuery}
                    onSelect={handleAgentMentionSelect}
                    onClose={() => setAgentMentionOpen(false)}
                  />
                )}
                {artifactMentionOpen && (
                  <ArtifactMentionPicker
                    ref={artifactPickerRef}
                    query={artifactMentionQuery}
                    onSelectPath={handleArtifactMentionSelect}
                    onClose={() => setArtifactMentionOpen(false)}
                  />
                )}
                <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleFilePick} />
                <AttachMenuButton
                  onPickFile={() => fileInputRef.current?.click()}
                  onInsertTrigger={(char) => {
                    if (char === "!") {
                      // Must be the very first character (see handleSend's
                      // trimmed.startsWith("!") check) -- prefix, don't append.
                      setComposerText((t) => (t.startsWith("!") ? t : `!${t}`));
                      composerTextareaRef.current?.focus();
                      return;
                    }
                    setComposerText((t) => {
                      const needsSpace = t.length > 0 && !/\s$/.test(t);
                      return t + (needsSpace ? " " : "") + char;
                    });
                    if (char === "@") setMentionOpen(true);
                    if (char === "/") setSlashOpen(true);
                    if (char === "#") {
                      setAgentMentionOpen(true);
                      setAgentMentionQuery("");
                    }
                    if (char === "$") {
                      setArtifactMentionOpen(true);
                      setArtifactMentionQuery("");
                    }
                    composerTextareaRef.current?.focus();
                  }}
                />
              </>
            }
            trailing={
              <>
                {!lockAgent && (
                  <AgentSelectorPill agents={chatableAgents} selectedAgentId={agentId} onSelect={onAgentChange} />
                )}
                {agentId && <AgentMcpInfoButton agentId={agentId} />}
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 rounded-full shrink-0"
                  aria-label={t("composer.improvePrompt", { agent: selectedAgent?.name ?? t("agentPicker.agentFallback") })}
                  title={t("composer.improvePrompt", { agent: selectedAgent?.name ?? t("agentPicker.agentFallback") })}
                  onClick={() => {
                    // A brand-new conversation has no session yet (only
                    // created lazily on first send/message) -- lazily
                    // create one here too instead of disabling the button,
                    // same ensureSession() the composer's own send path
                    // already uses (2026-08-07, Marcelo: "o botão continua
                    // desabilitado" on a fresh conversation).
                    void ensureSession();
                    setImproveOpen(true);
                  }}
                >
                  <Sparkles className="h-4 w-4" />
                </Button>
                <Button
                  variant={isRecording ? "destructive" : "ghost"}
                  size="icon"
                  className="h-8 w-8 rounded-full shrink-0"
                  aria-label={isRecording ? t("composer.stopRecording") : t("composer.recordVoiceMessage")}
                  onClick={handleToggleRecording}
                  disabled={transcribe.isPending}
                >
                  {transcribe.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : isRecording ? (
                    <Square className="h-4 w-4" />
                  ) : (
                    <Mic className="h-4 w-4" />
                  )}
                </Button>
                <Button
                  variant={voiceActive ? "default" : "ghost"}
                  size="icon"
                  className="h-8 w-8 rounded-full shrink-0"
                  aria-label={voiceActive ? t("voice.endConversation") : t("voice.conversationWithAgent", { name: selectedAgent?.name ?? t("agentPicker.agentFallback") })}
                  title={voiceActive ? t("voice.endConversation") : t("voice.conversationWithAgent", { name: selectedAgent?.name ?? t("agentPicker.agentFallback") })}
                  onClick={voiceActive ? stopVoice : startVoice}
                  disabled={isRecording}
                >
                  <AudioLines className="h-4 w-4" />
                </Button>
              </>
            }
          />
        </div>
        {improveOpen && (
          <ImprovePromptDialog
            initialDraft={composerText}
            subject={selectedAgent?.name ?? t("agentPicker.agentFallback")}
            agents={chatableAgents}
            improvePrompt={improvePrompt}
            onApply={(improved) => {
              setComposerText(improved);
              setImproveOpen(false);
              composerTextareaRef.current?.focus();
            }}
            onClose={() => setImproveOpen(false)}
          />
        )}
      </div>

      {artifactsOpen && (
        <aside className="flex w-72 shrink-0 flex-col rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border p-3">
            <span className="text-sm font-medium text-muted-foreground">{t("artifactsPanel.title")}</span>
          </div>
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                value={artifactSearchQuery}
                onChange={(e) => setArtifactSearchQuery(e.target.value)}
                placeholder={t("artifactsPanel.searchArtifacts")}
                className="h-8 w-full rounded-md border border-border bg-transparent pl-7 pr-2 text-xs outline-none focus:border-primary"
              />
            </div>
          </div>
          <div className="flex-1 space-y-1 overflow-y-auto p-2">
            {(artifacts ?? [])
              .filter((artifact) => artifact.name.toLowerCase().includes(artifactSearchQuery.trim().toLowerCase()))
              .map((artifact) => (
                <div
                  key={artifact.id}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData("text/plain", artifact.path);
                    e.dataTransfer.effectAllowed = "copy";
                  }}
                  title={t("artifactsPanel.dragToReference", { path: artifact.path })}
                  className="group flex cursor-grab items-center justify-between gap-1 rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground active:cursor-grabbing"
                >
                  <div className="flex min-w-0 flex-1 items-center gap-1.5">
                    <Paperclip className="h-3.5 w-3.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="truncate">{artifact.name}</p>
                      <p className="truncate text-[10px] opacity-70">{formatTime(artifact.created_at)}</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 group-hover:opacity-100">
                    <button
                      type="button"
                      aria-label={t("artifactsPanel.download", { name: artifact.name })}
                      title={t("artifactsPanel.downloadTitle")}
                      onClick={() => downloadChatArtifact(artifact.id)}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label={t("artifactsPanel.removeFromList", { name: artifact.name })}
                      title={t("artifactsPanel.removeFromListTitle")}
                      onClick={() => deleteArtifact.mutate(artifact.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            {(artifacts ?? []).length === 0 && (
              <p className="px-2 py-2 text-xs italic text-muted-foreground">
                {t("artifactsPanel.noArtifactsYet")}
              </p>
            )}
            {(artifacts ?? []).length > 0 &&
              artifactSearchQuery.trim() &&
              (artifacts ?? []).filter((a) => a.name.toLowerCase().includes(artifactSearchQuery.trim().toLowerCase()))
                .length === 0 && (
                <p className="px-2 py-2 text-xs italic text-muted-foreground">{t("artifactsPanel.noArtifactsFound")}</p>
              )}
          </div>
        </aside>
      )}
      <TestApplicationDialog open={testDialogOpen} onClose={() => setTestDialogOpen(false)} />
      <ConfirmDialog
        open={pendingClearSessions !== null}
        description={pendingClearSessions?.message}
        loading={deleteSession.isPending}
        onConfirm={confirmClearSessions}
        onCancel={() => setPendingClearSessions(null)}
      />
    </div>
  );
}

