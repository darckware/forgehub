/** ChatPane -- the single chat component (extracted verbatim from
 * pages/workspace/index.tsx on 2026-07-07). The Workspace consumes it for
 * its chat tabs; other pages (Docs, ...) open it inside a side drawer to
 * assist creation/filling, always with the same behavior: queue, SSE
 * streaming, elevation approvals, Telegram-style processing feed, voice.
 * One component, no forks -- fix bugs here, every surface gets them. */
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  AudioLines,
  Bot,
  Check,
  ChevronDown,
  Copy,
  Download,
  Folder,
  Loader2,
  Mic,
  MoreVertical,
  Paperclip,
  Pencil,
  Pin,
  PinOff,
  Plus,
  RotateCcw,
  Search,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/Markdown";
import { useFsList, type FsEntry } from "@/hooks/useTerminalBrowse";
import { getToken } from "@/lib/api";
import { cn } from "@/lib/utils";
import { type Agent } from "@/hooks/useAgent";
import { useClickOutside } from "@/hooks/useClickOutside";
import { usePromptCommands, type PromptCommand } from "@/hooks/usePromptCommands";
import { useQueryClient } from "@tanstack/react-query";
import {
  chatKeys,
  useChatArtifacts,
  useChatMessages,
  useDeleteChatArtifact,
  useExecChatCommand,
  useSearchChatArtifacts,
  useChatSessions,
  useCreateChatSession,
  useSearchChatSessions,
  useDeleteChatMessage,
  useDeleteChatSession,
  useUpdateChatSession,
  useApproveChat,
  useSendChatMessage,
  useStreamChatMessage,
  useTranscribeAudio,
  downloadChatArtifact,
  type ChatMessage,
  type ChatSession,
  type ChatStreamEvent,
} from "@/hooks/useChat";

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

/** Drop a closed tab's staged draft/attachments (the Workspace calls this
 * when the user closes a chat tab -- the maps are module-private here). */
export function clearChatTabStaging(tabId: string): void {
  attachmentByTabId.delete(tabId);
  composerTextByTabId.delete(tabId);
}

// Composer auto-grow ceiling -- past this it scrolls internally instead
// of taking over the message area.
const COMPOSER_MAX_HEIGHT_PX = 240;
type ChatQueueStep = { id: string; name: string; label: string; detail?: string; done: boolean };

/** Tool-name → emoji, mirroring the Telegram gateway's processing feed
 * (🔍 search_files, 📖 Reading …, 💻 terminal, 🐍 Running code, …). */
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
  /** True for a "!command" raw bash execution -- no agent/LLM call, see
   * exec_chat_command. content keeps the "!" prefix. */
  isExec?: boolean;
  /** Date.now() when this item entered "processing" -- powers the live
   * "Pensando há mm:ss" ticker (see ThinkingLabel). */
  startedAt?: number;
};

function formatThinkingDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Ticks every second while processing -- shown above the steps/Parar
 * button, same spot the frozen "Pensou por mm:ss" occupies once the
 * reply is persisted (see MessageBubble). */
function LiveThinkingLabel({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const elapsed = Math.max(0, Math.round((now - startedAt) / 1000));
  return (
    <p className="text-xs text-muted-foreground">
      ⏳ Trabalhando — {formatThinkingDuration(elapsed)}
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
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const selected = agents.find((a) => a.id === selectedAgentId);

  useClickOutside(containerRef, () => setOpen(false), open);

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="ghost"
        size="icon"
        aria-label={selected ? `Agent: ${selected.name}` : "Select agent"}
        title={selected?.name ?? "Select agent"}
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

/** Per-chat-item "..." menu: rename / pin / delete. Replaces the lone
 * hover-only trash icon so the row doesn't get cluttered with separate
 * icons per action. */
function ChatItemMenu({
  session,
  onRename,
  onTogglePin,
  onDelete,
}: {
  session: ChatSession;
  onRename: () => void;
  onTogglePin: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useClickOutside(containerRef, () => setOpen(false), open);

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <button
        type="button"
        aria-label="Chat options"
        title="Chat options"
        className="rounded-md p-1 opacity-0 hover:bg-accent group-hover:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <MoreVertical className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 w-40 overflow-hidden rounded-md border border-border bg-card py-1 shadow-md">
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
              onRename();
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
            Renomear
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
              onTogglePin();
            }}
          >
            {session.pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
            {session.pinned ? "Desafixar" : "Fixar"}
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-destructive hover:bg-accent"
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
              onDelete();
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
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
        <span className="max-w-[8rem] truncate">{selected?.name ?? "Agent"}</span>
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

/** Gemini-style "+" attachment menu -- only one action applies in our
 * scope (no Drive/image/video generation), but kept as a menu since
 * that's the requested look. */
/** Discoverability legend for the composer's trigger characters -- lets a
 * user who doesn't know "@"/"/"/"#"/"$" exist find them from the "+" menu
 * instead of stumbling onto them by typing. Each entry inserts its trigger
 * char and opens the same picker typing it would. */
function AttachMenuButton({
  onPickFile,
  onInsertTrigger,
}: {
  onPickFile: () => void;
  onInsertTrigger: (char: "/" | "@" | "#" | "$" | "!") => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useClickOutside(containerRef, () => setOpen(false), open);

  const triggers: { char: "/" | "@" | "#" | "$" | "!"; label: string }[] = [
    { char: "/", label: "Hermes command" },
    { char: "@", label: "Directory/Files" },
    { char: "#", label: "Agents" },
    { char: "$", label: "Artifacts" },
    { char: "!", label: "Direct bash command" },
  ];

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-full"
        aria-label="Add attachment"
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
            Send file
          </button>
          <div className="my-1 border-t border-border" />
          {triggers.map((t) => (
            <button
              key={t.char}
              type="button"
              onClick={() => {
                onInsertTrigger(t.char);
                setOpen(false);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            >
              <span className="flex h-4 w-4 items-center justify-center font-mono text-xs text-muted-foreground">
                {t.char}
              </span>
              {t.label}
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
const MentionFilePicker = forwardRef<
  MentionFilePickerHandle,
  { rootPath?: string; onSelectPath: (path: string) => void; onClose: () => void }
>(function MentionFilePicker({ rootPath, onSelectPath, onClose }, ref) {
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
              Usar pasta
            </Button>
          )}
          {data?.parent && (
            <Button
              size="icon"
              variant="ghost"
              className="h-6 w-6"
              aria-label="Pasta acima"
              onClick={() => setPath(data.parent!)}
            >
              <ArrowUp className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>
      {isLoading && <p className="px-3 py-3 text-xs text-muted-foreground">Loading…</p>}
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
        <p className="px-3 py-3 text-xs italic text-muted-foreground">Pasta vazia</p>
      )}
    </div>
  );
});

/** Slash commands ForgeHub actually executes via Hermes's own process_command()
 * dispatcher (see host-bridge/hermes_stream.py SAFE_SLASH_COMMANDS) instead of
 * forwarding the text to the LLM -- keep this list in sync with that one. */
const SAFE_SLASH_COMMANDS: { command: string; description: string }[] = [
  { command: "/model", description: "Switch model (persists by default)" },
  { command: "/status", description: "Show session, model, tokens and context" },
  { command: "/help", description: "Show available commands" },
  { command: "/version", description: "Show Hermes Agent version" },
  { command: "/title", description: "Set a title for the current session" },
  { command: "/profile", description: "Show active profile and home directory" },
  { command: "/config", description: "Show current configuration" },
  { command: "/toolsets", description: "List available toolsets" },
  { command: "/platforms", description: "Show gateway/messaging platform status" },
  { command: "/plugins", description: "List installed plugins and their status" },
];

type SlashCommandItem =
  | { kind: "hermes"; command: string; description: string }
  | { kind: "prompt"; command: string; description: string; prompt: string };

export interface SlashCommandPickerHandle {
  moveActive: (delta: number) => void;
  confirmActive: () => void;
}

/** Keyboard nav (Arrow Up/Down + Enter) is driven from the composer textarea
 * via this imperative handle, same pattern as MentionFilePickerHandle -- the
 * textarea keeps focus while "/" is open. */
const SlashCommandPicker = forwardRef<
  SlashCommandPickerHandle,
  { promptCommands: PromptCommand[]; onSelect: (item: SlashCommandItem) => void; onClose: () => void }
>(function SlashCommandPicker({ promptCommands, onSelect, onClose }, ref) {
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, onClose);
  const items = useMemo<SlashCommandItem[]>(
    () => [
      ...SAFE_SLASH_COMMANDS.map((cmd) => ({ kind: "hermes" as const, ...cmd })),
      ...promptCommands.map((cmd) => ({
        kind: "prompt" as const,
        command: `/${cmd.name}`,
        description: cmd.description,
        prompt: cmd.prompt,
      })),
    ],
    [promptCommands]
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
      className="absolute bottom-full left-0 z-20 mb-2 max-h-80 w-80 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
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
              {cmd.kind === "hermes" ? "Hermes" : "Prompt"}
            </span>
          </span>
          <span className="text-[11px] text-muted-foreground">{cmd.description}</span>
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
const AgentMentionPicker = forwardRef<
  AgentMentionPickerHandle,
  { agents: Agent[]; query: string; onSelect: (agent: Agent) => void; onClose: () => void }
>(function AgentMentionPicker({ agents, query, onSelect, onClose }, ref) {
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
      className="absolute bottom-full left-0 z-20 mb-2 max-h-72 w-64 overflow-y-auto rounded-lg border border-border bg-card shadow-lg"
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
        <p className="px-3 py-3 text-xs italic text-muted-foreground">No agents found</p>
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
const ArtifactMentionPicker = forwardRef<
  ArtifactMentionPickerHandle,
  { query: string; onSelectPath: (path: string) => void; onClose: () => void }
>(function ArtifactMentionPicker({ query, onSelectPath, onClose }, ref) {
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
      {isLoading && <p className="px-3 py-3 text-xs text-muted-foreground">Loading…</p>}
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
        <p className="px-3 py-3 text-xs italic text-muted-foreground">No artifacts found</p>
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
            Pensou por {formatThinkingDuration(message.thinking_seconds)}
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
            aria-label="Copy message"
            title="Copy message"
            onClick={handleCopyMessage}
            className="flex items-center gap-1 rounded-full px-1 text-[11px] text-muted-foreground hover:text-foreground"
          >
            {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
          </button>
          {onRegenerate && (
            <button
              type="button"
              aria-label="Regenerate reply"
              title="Regenerate reply"
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
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={() => {
                onEdit?.(editText);
                setIsEditing(false);
              }}
            >
              Save and resend
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
          <p className="mt-1 text-[10px] text-primary-foreground/70">{formatTime(message.created_at)}</p>
        </div>
        {onEdit && (
          <button
            type="button"
            aria-label="Edit message"
            title="Edit message"
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
}: {
  tabId: string;
  active: boolean;
  agentId: string;
  chatableAgents: Agent[];
  onAgentChange: (agentId: string) => void;
  initialComposerText?: string;
  historyCollapsed: boolean;
  artifactsOpen: boolean;
  /** Same cwd used by "New Terminal" tabs -- backs the composer's
   * "!command" prefix so it runs in the same project context. */
  workingDir?: string;
}) {
  const [sessionId, setSessionId] = useState<string>("");
  const [composerText, setComposerText] = useState(
    () => composerTextByTabId.get(tabId) ?? initialComposerText ?? ""
  );
  useEffect(() => {
    composerTextByTabId.set(tabId, composerText);
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
    setAttachedFiles([...attachedFiles, ...newFiles]);
  }
  function removeAttachedFile(index: number) {
    setAttachedFiles(attachedFiles.filter((_, i) => i !== index));
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
  const [queue, setQueue] = useState<ChatQueueItem[]>([]);
  const queueDrainingRef = useRef(false);
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [composerWarning, setComposerWarning] = useState<string | null>(null);
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

  const { data: sessions } = useChatSessions(agentId || undefined);

  // Debounced search across session titles + message content (see
  // search_chat_sessions in chat.py) -- 300ms so we're not hitting the DB
  // on every keystroke.
  const [chatSearchInput, setChatSearchInput] = useState("");
  const [chatSearchTerm, setChatSearchTerm] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setChatSearchTerm(chatSearchInput), 300);
    return () => clearTimeout(t);
  }, [chatSearchInput]);
  const { data: chatSearchResults, isFetching: isSearchingChats } = useSearchChatSessions(
    chatSearchTerm,
    agentId || undefined
  );
  const displayedSessions = chatSearchTerm.trim() ? chatSearchResults ?? [] : sessions ?? [];

  useEffect(() => {
    setSessionId("");
  }, [agentId]);

  useEffect(() => {
    if (!sessionId && sessions && sessions.length > 0) {
      setSessionId(sessions[0].id);
    }
  }, [sessionId, sessions]);

  const queryClient = useQueryClient();
  const { data: messages } = useChatMessages(sessionId || undefined);
  const { data: artifacts } = useChatArtifacts(sessionId || undefined);
  const deleteArtifact = useDeleteChatArtifact(sessionId || undefined);
  const [artifactSearchQuery, setArtifactSearchQuery] = useState("");
  const createSession = useCreateChatSession();
  const deleteSession = useDeleteChatSession(agentId || undefined);
  const updateSession = useUpdateChatSession(agentId || undefined);
  const sendMessage = useSendChatMessage(agentId || undefined);
  const streamMessage = useStreamChatMessage(agentId || undefined);
  const execCommand = useExecChatCommand(agentId || undefined);
  const deleteMessage = useDeleteChatMessage(sessionId || undefined);
  const approveChat = useApproveChat();
  const transcribe = useTranscribeAudio();

  function handleStartRename(s: ChatSession) {
    setEditingSessionId(s.id);
    setEditingTitle(s.title);
  }

  function handleCommitRename() {
    if (!editingSessionId) return;
    const title = editingTitle.trim();
    if (title) {
      updateSession.mutate({ sessionId: editingSessionId, title });
    }
    setEditingSessionId(null);
  }

  function handleTogglePin(s: ChatSession) {
    updateSession.mutate({ sessionId: s.id, pinned: !s.pinned });
  }

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
  }, [messages, queue, sessionId]);

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

  function handleNewChat() {
    if (!agentId) return;
    createSession.mutate({ agent_id: agentId }, { onSuccess: (session) => setSessionId(session.id) });
  }

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) addAttachedFiles(files);
    e.target.value = "";
  }

  async function handleSend(overrideText?: string) {
    if (!agentId) return;
    const isOverride = overrideText !== undefined;

    const trimmed = (isOverride ? overrideText : composerText).trim();
    if (!trimmed && attachedFiles.length === 0) {
      setComposerWarning("Digite uma mensagem antes de enviar.");
      return;
    }

    // The dedupe-guard only makes sense for the normal composer flow --
    // "edit and resend" (isOverride) deliberately allows resending the
    // same text (e.g. user just fixed a typo elsewhere and reverted it).
    const lastUserMessage =
      queue[queue.length - 1]?.content ?? [...(messages ?? [])].reverse().find((m) => m.role === "user")?.content;
    if (!isOverride && attachedFiles.length === 0 && trimmed && lastUserMessage?.trim() === trimmed) {
      setComposerWarning("You already sent this message.");
      return;
    }

    let activeSessionId = sessionId;
    if (!activeSessionId) {
      const created = await createSession.mutateAsync({ agent_id: agentId });
      activeSessionId = created.id;
      setSessionId(activeSessionId);
    }

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
            steps: item.steps.map((s) => (s.id === event.toolId ? { ...s, label: event.summary || s.label, done: true } : s)),
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
        });
      }
      // Only drop the pending bubbles AFTER the persisted messages have
      // been refetched. Removing first left a window where the sent prompt
      // vanished from the screen (long turns made it very visible); the
      // pending bubble must stay until its persisted twin is rendered.
      await queryClient
        .refetchQueries({ queryKey: chatKeys.messages(sessionId) })
        .catch(() => {});
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
      suggestedReply = "Yes";
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
    // The backend strips trailing whitespace from a stored prompt (see
    // prompt_command.py's strip_text validator), so a command-style prompt
    // like "/demanda" would otherwise land with no room to keep typing --
    // always leave exactly one trailing space regardless of kind.
    const text = item.kind === "prompt" ? item.prompt : item.command;
    setComposerText(text.endsWith(" ") ? text : `${text} `);
    setSlashOpen(false);
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
        setVoiceError("Microphone blocked. Allow it in your browser settings.");
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
      setVoiceLiveText("Transcrevendo…");
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
            setVoiceLiveText("🔴 Gravando…");
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
        setVoiceError(`Falha ao obter resposta: ${String(err)}`);
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
    push({ id: "sr", label: "Audio recording", ok: hasRecorder,
      detail: hasRecorder ? "Supported" : "Browser does not support MediaRecorder — use Chrome or Edge." });
    if (!hasRecorder) { setVoicePhase("error"); voiceActiveRef.current = false; return; }

    // SpeechSynthesis API + voices
    const hasTTS = Boolean(window.speechSynthesis);
    let voices = hasTTS ? window.speechSynthesis.getVoices() : [];
    if (hasTTS && voices.length === 0) {
      await new Promise<void>((res) => {
        const t = setTimeout(res, 2000);
        window.speechSynthesis.onvoiceschanged = () => { clearTimeout(t); res(); };
      });
      voices = window.speechSynthesis.getVoices();
    }
    ttsVoicesRef.current = voices;
    push({ id: "tts", label: "Speech synthesis (TTS)", ok: hasTTS && voices.length > 0,
      detail: !hasTTS ? "Not supported" : voices.length === 0 ? "No voices — replies will be shown without audio" : `${voices.length} voice(s)` });

    // Microphone permission — open stream and keep it open for the whole conversation
    let micOk = false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      voiceStreamRef.current = stream;
      micOk = true;
    } catch {
      micOk = false;
    }
    push({ id: "mic", label: "Microfone", ok: micOk,
      detail: micOk ? "Authorized" : "Denied — click the padlock in the address bar and allow the microphone." });
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

    const agentName = selectedAgent?.name ?? "Assistente";
    const h = new Date().getHours();
    const period = h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
    const greeting = `${period}! Sou ${agentName}. Como posso ajudar você agora?`;
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

  return (
    <div className={cn("absolute inset-0 flex gap-2 p-2", !active && "hidden")}>
      {!historyCollapsed && (
        <aside className="flex w-64 shrink-0 flex-col rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border p-3">
            <span className="text-sm font-medium text-muted-foreground">Chats</span>
            <div className="flex items-center gap-1">
              <Button variant="ghost" size="icon" title="New chat" aria-label="New chat" onClick={handleNewChat}>
                <Plus className="h-4 w-4" />
              </Button>
              <AgentPickerButton agents={chatableAgents} selectedAgentId={agentId} onSelect={onAgentChange} />
            </div>
          </div>
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                value={chatSearchInput}
                onChange={(e) => setChatSearchInput(e.target.value)}
                placeholder="Search conversations…"
                className="h-8 w-full rounded-md border border-border bg-transparent pl-7 pr-2 text-xs outline-none focus:border-primary"
              />
            </div>
          </div>
          <div className="flex-1 space-y-1 overflow-y-auto p-2">
            {chatSearchTerm.trim() && isSearchingChats && (
              <p className="px-2 py-2 text-xs italic text-muted-foreground">Searching…</p>
            )}
            {chatSearchTerm.trim() && !isSearchingChats && displayedSessions.length === 0 && (
              <p className="px-2 py-2 text-xs italic text-muted-foreground">No conversations found.</p>
            )}
            {displayedSessions.map((s) => (
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
                  <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate">
                    {s.pinned && <Pin className="h-3 w-3 shrink-0 opacity-70" />}
                    <span className="truncate">{s.title}</span>
                  </span>
                )}
                {editingSessionId !== s.id && (
                  <ChatItemMenu
                    session={s}
                    onRename={() => handleStartRename(s)}
                    onTogglePin={() => handleTogglePin(s)}
                    onDelete={() =>
                      deleteSession.mutate(s.id, {
                        onSuccess: () => {
                          if (s.id === sessionId) setSessionId("");
                        },
                      })
                    }
                  />
                )}
              </div>
            ))}
            {!chatSearchTerm.trim() && (sessions ?? []).length === 0 && (
              <p className="px-2 py-2 text-xs italic text-muted-foreground">No conversations yet.</p>
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
                  Conversa por voz · {selectedAgent?.name}
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
                  <p className="text-xs text-muted-foreground">Iniciando…</p>
                </div>
              )}
              {voicePhase === "error" && (
                <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
                  <p className="text-sm text-destructive text-center">
                    {voiceError ?? "Could not start the voice conversation."}
                  </p>
                  <Button variant="outline" size="sm" onClick={stopVoice}>
                    Close
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
                          Waiting for {selectedAgent?.name}…
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
                        listening: "Ouvindo…",
                        processing: `${selectedAgent?.name}\nis thinking…`,
                        speaking: `${selectedAgent?.name}\nis replying…`,
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
                            ? "Mic ativo"
                            : voiceStatus === "speaking" ? "Agent speaking" : "Waiting…"}
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
                    Encerrar conversa por voz
                  </Button>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        {/* ── end voice overlay ───────────────────────────────────── */}

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {(messages ?? []).length === 0 && (
            <p className="py-12 text-center text-sm italic text-muted-foreground">
              Envie uma mensagem para iniciar a conversa com {selectedAgent?.name}.
            </p>
          )}
          {(messages ?? []).map((m, i, list) => {
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
            return (
              <MessageBubble
                key={m.id}
                message={m}
                isCommandReply={isCommandReply}
                onRegenerate={canRegenerate ? () => handleRegenerate(m) : undefined}
                regenerateDisabled={deleteMessage.isPending}
                respondingAgentName={respondingAgentName}
                onEdit={canEdit ? (newContent) => handleEditMessage(m, newContent) : undefined}
                editDisabled={deleteMessage.isPending}
              />
            );
          })}
          {queue.map((item) => (
            <div key={item.id} className="space-y-1">
              {!item.isRegenerate && !item.skipUserMessage && (
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
                <p className="pl-1 text-xs italic text-muted-foreground">📥 Na fila…</p>
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
                          Stop
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
                  {item.steps.map((step) => {
                    // Telegram-gateway style: terminal/code steps show the
                    // tool line plus the EXACT command in a `shell` block
                    // (`detail` is verbatim from tool_args; the label is an
                    // 80-char elision kept only as fallback). Every other
                    // tool is a one-liner with its emoji.
                    const isBlockTool =
                      isTerminalTool(step.name) || step.name.toLowerCase().includes("code");
                    const blockText = isBlockTool
                      ? step.detail ??
                        (step.label !== step.name ? step.label.replace(/^Running\s+/i, "") : null)
                      : null;
                    return (
                      <div key={step.id} className="space-y-1">
                        <p
                          className="flex items-center gap-2 text-xs text-muted-foreground"
                          title={step.detail ?? step.label}
                        >
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
                            <p className="border-b border-border/60 px-2 py-0.5 text-[10px] text-muted-foreground">
                              shell
                            </p>
                            <code className="block max-h-32 overflow-auto whitespace-pre-wrap break-all px-2 py-1 font-mono text-xs">
                              {blockText}
                            </code>
                          </div>
                        )}
                      </div>
                    );
                  })}
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
                          <span aria-hidden>💻</span> Executando comando
                        </>
                      ) : (
                        <>
                          <span aria-hidden>✍️</span>
                          {`${item.targetAgentName ?? selectedAgent?.name ?? "O agente"} está digitando`}
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
                    🔐 {item.targetAgentName ?? selectedAgent?.name ?? "O agente"} pede autorização para executar uma ação privilegiada
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
                      ✅ Aprovar uma vez
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      title="Do not ask again for this same command type in this session"
                      onClick={() => handleApprovalChoice(item.id, item.approval!.streamId, "session")}
                    >
                      ☑️ Aprovar nesta sessão
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleApprovalChoice(item.id, item.approval!.streamId, "deny")}
                    >
                      🚫 Negar
                    </Button>
                  </div>
                </div>
              )}
              {item.status === "error" && (
                <p className="flex items-center gap-2 pl-1 text-xs text-destructive">
                  ❌ Falhou: {item.error}
                  <button
                    type="button"
                    aria-label="Dispensar"
                    onClick={() => setQueue((q) => q.filter((it) => it.id !== item.id))}
                  >
                    <X className="h-3 w-3" />
                  </button>
                </p>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        <div className="space-y-2 border-t border-border p-3">
          {pendingQueue.length > 1 && (
            <div className="space-y-1 rounded-lg border border-border bg-muted/30 px-2.5 py-1.5 text-xs">
              {pendingQueue.map((item) => (
                <div key={item.id} className="flex items-center gap-2 text-muted-foreground">
                  {item.status === "processing" ? (
                    <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                  ) : (
                    <span className="h-2 w-2 shrink-0 rounded-full border border-current" />
                  )}
                  <span className="truncate">{item.content || item.attachmentName}</span>
                </div>
              ))}
            </div>
          )}
          {composerWarning && (
            <p className="px-1 text-xs text-destructive">{composerWarning}</p>
          )}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {attachedFiles.map((file, index) => (
                <div key={index} className="flex w-fit items-center gap-2 rounded-md bg-muted px-2 py-1 text-xs">
                  {attachedImagePreviewUrls[index] ? (
                    <button
                      type="button"
                      aria-label="Visualizar imagem anexada"
                      onClick={() => setImagePreviewIndex(index)}
                      className="shrink-0"
                    >
                      <img src={attachedImagePreviewUrls[index]!} alt="" className="h-6 w-6 rounded object-cover" />
                    </button>
                  ) : (
                    <Paperclip className="h-3 w-3" />
                  )}
                  {file.name}
                  <button type="button" aria-label="Remove attachment" onClick={() => removeAttachedFile(index)}>
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
                  Remover
                </Button>
                <button
                  type="button"
                  aria-label="Fechar"
                  onClick={() => setImagePreviewIndex(null)}
                  className="absolute -right-3 -top-3 rounded-full border border-border bg-card p-1.5 shadow-md hover:bg-accent"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
          <div className="relative flex items-end gap-1 rounded-3xl border border-border bg-muted/50 px-2 py-1.5">
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
            <Textarea
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
              onDragOver={(e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "copy";
              }}
              onDrop={(e) => {
                e.preventDefault();
                const path = e.dataTransfer.getData("text/plain");
                if (!path) return;
                setComposerText((t) => {
                  const needsSpace = t.length > 0 && !/\s$/.test(t);
                  return t + (needsSpace ? " " : "") + path + " ";
                });
              }}
              placeholder={
                suggestedReply
                  ? `${suggestedReply} (→ to complete)`
                  : `Ask ${selectedAgent?.name ?? "agent"}`
              }
              rows={1}
              style={{ maxHeight: COMPOSER_MAX_HEIGHT_PX }}
              className="min-h-0 flex-1 resize-none overflow-y-auto border-0 bg-transparent px-1 py-1.5 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
            />
            <AgentSelectorPill agents={chatableAgents} selectedAgentId={agentId} onSelect={onAgentChange} />
            <Button
              variant={isRecording ? "destructive" : "ghost"}
              size="icon"
              className="h-8 w-8 rounded-full shrink-0"
              aria-label={isRecording ? "Stop recording" : "Record voice message"}
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
              aria-label={voiceActive ? "Encerrar conversa por voz" : `Conversa por voz com ${selectedAgent?.name ?? "agente"}`}
              title={voiceActive ? "Encerrar conversa por voz" : `Conversa por voz com ${selectedAgent?.name ?? "agente"}`}
              onClick={voiceActive ? stopVoice : startVoice}
              disabled={isRecording}
            >
              <AudioLines className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {artifactsOpen && (
        <aside className="flex w-72 shrink-0 flex-col rounded-lg border border-border bg-card">
          <div className="flex items-center justify-between border-b border-border p-3">
            <span className="text-sm font-medium text-muted-foreground">Artifacts</span>
          </div>
          <div className="border-b border-border p-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                value={artifactSearchQuery}
                onChange={(e) => setArtifactSearchQuery(e.target.value)}
                placeholder="Search artifacts…"
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
                  title={`Drag to the message field to reference ${artifact.path}`}
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
                      aria-label={`Download ${artifact.name}`}
                      title="Download"
                      onClick={() => downloadChatArtifact(artifact.id)}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label={`Remove ${artifact.name} from list`}
                      title="Remove from list (does not delete the actual file)"
                      onClick={() => deleteArtifact.mutate(artifact.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            {(artifacts ?? []).length === 0 && (
              <p className="px-2 py-2 text-xs italic text-muted-foreground">
                No artifacts created in this conversation yet.
              </p>
            )}
            {(artifacts ?? []).length > 0 &&
              artifactSearchQuery.trim() &&
              (artifacts ?? []).filter((a) => a.name.toLowerCase().includes(artifactSearchQuery.trim().toLowerCase()))
                .length === 0 && (
                <p className="px-2 py-2 text-xs italic text-muted-foreground">No artifacts found.</p>
              )}
          </div>
        </aside>
      )}
    </div>
  );
}
