import { useState, type ComponentType, type ReactNode } from "react";
import {
  Archive,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Inbox as InboxIcon,
  SendHorizontal,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAgents } from "@/hooks/useAgent";
import { ActionIcon } from "@/components/InboxGroupTree";

// Namespaced custom MIME type so dropping something dragged from elsewhere
// on the page (or another app) is a no-op instead of misreading unrelated
// drag data. Shared with InboxGroupTree.tsx (re-exported from there too).
export const DEMAND_DRAG_MIME = "application/x-forgehub-demand-id";

/** A top-level group that breaks down by agent. "completed" joins the two
 * directions here (2026-07-27) because finished work is read the same way:
 * per agent, not as one flat pile. */
export type AgentDirection = "inbox" | "outbox" | "completed";

/** Sentinel `agentId` for the no-agent ("System") row -- items with no agent on that
 * side (no target_agent_id for Inbox, no from_agent_id for Outbox). Not a
 * real agent id, never collides with a UUID. */
export const NO_AGENT_ID = "__no_agent__";

/** Which node is selected within a direction tree -- `agentId: null` means
 * the root (every item, unfiltered) is selected; `NO_AGENT_ID` means the
 * no-agent ("System") row (no agent); any other string means that specific agent's
 * sub-row. `undefined` (from the parent) means this direction tree isn't
 * the active selection at all. */
export interface AgentTreeSelection {
  agentId: string | null;
}

const DIRECTION_ICON: Record<AgentDirection, typeof InboxIcon> = {
  inbox: InboxIcon,
  outbox: SendHorizontal,
  completed: CheckCircle2,
};

/** Inline message list rendered directly under whichever tree node (Admin,
 * agent, or Archived subfolder) is both expanded and the active selection
 * -- there's exactly one such node at a time across the whole sidebar,
 * since selection is a single piece of page state, so every node can
 * safely receive the same `messages`/`renderMessage` props and just gate
 * on its own active+expanded check before rendering them. Generic over the
 * row type so this presentational component doesn't need to import the
 * Demand type.
 *
 * Deliberately never rendered for the direction root itself (Incoming/
 * Outgoing) -- see AgentDirectionTree below: only a specific agent row (or
 * Admin) shows messages inline, so they always read as "inside" an agent,
 * never as one big undifferentiated dump above the per-agent breakdown. */
export function InlineMessageList<T>({
  messages,
  renderMessage,
  emptyMessage,
}: {
  messages: T[];
  renderMessage: (item: T) => ReactNode;
  emptyMessage: string;
}) {
  return (
    <div className="my-1 overflow-hidden rounded-md border border-border/40">
      {messages.length === 0 ? (
        <p className="px-3 py-2 text-center text-xs italic text-muted-foreground">{emptyMessage}</p>
      ) : (
        messages.map((m) => renderMessage(m))
      )}
    </div>
  );
}

/** A flat, non-agent-broken-down top-level group -- Backlog (dispatch_status
 * "pending", i.e. queued/scheduled but not fired yet) and Failed
 * (dispatch_status "failed") both use this instead of AgentDirectionTree,
 * since neither needs a per-agent breakdown, just a single selectable/
 * collapsible row with its own inline message list and cleanup icon
 * (added 2026-07-25, same visual language as AgentDirectionTree's root row). */
export function SimpleDemandGroup<T>({
  icon: Icon,
  label,
  count,
  active,
  expanded,
  onToggleExpanded,
  onSelect,
  onCleanup,
  onArchive,
  messages,
  renderMessage,
  emptyMessage,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  count: number;
  active: boolean;
  /** Controlled -- lifted to DemandsPage so the toolbar's expand/collapse-
   * all toggle can drive every top-level group at once (2026-07-25). */
  expanded: boolean;
  onToggleExpanded: () => void;
  onSelect: () => void;
  onCleanup: () => void;
  /** Archives every message currently in this group in one action
   * (2026-07-27) -- offered next to the destructive cleanup icon for
   * groups where "I'm done looking at this" is the common case (Failed,
   * Completed): keeps the history under Arquivadas instead of deleting it.
   * Omitted for groups where a bulk archive doesn't make sense (Backlog,
   * Running -- parked/in-flight work isn't "done" yet). */
  onArchive?: () => void;
  messages: T[];
  renderMessage: (item: T) => ReactNode;
  emptyMessage: string;
}) {
  return (
    <div>
      <div
        className={cn(
          "group flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
          active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )}
      >
        <button
          type="button"
          onClick={() => {
            onToggleExpanded();
            onSelect();
          }}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
          <Icon className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate font-medium">{label}</span>
          {count > 0 && <span className="text-[10px] text-muted-foreground">{count}</span>}
        </button>
        <div className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
          {onArchive && <ActionIcon icon={Archive} label={`Archive all in ${label}`} onClick={onArchive} />}
          <ActionIcon icon={Trash2} label={`Clean up ${label}`} destructive onClick={onCleanup} />
        </div>
      </div>
      {/* `active` além de `expanded` (2026-07-26): `messages` é a lista da
          pasta *selecionada* -- é assim que AgentDirectionTree funciona, uma
          única seleção no sidebar inteiro alimentando o nó ativo. Sem checar
          active aqui, todo grupo simples expandido renderizava a lista de
          quem estivesse selecionado, e a mesma mensagem aparecia
          simultaneamente em Backlog, Running e Failed. */}
      {expanded && active && (
        <InlineMessageList messages={messages} renderMessage={renderMessage} emptyMessage={emptyMessage} />
      )}
    </div>
  );
}

export function AgentRow({
  agentId,
  name,
  count,
  active,
  onSelect,
  children,
}: {
  agentId: string;
  name: string;
  count: number;
  active: boolean;
  onSelect: (agentId: string) => void;
  children?: ReactNode;
}) {
  return (
    <div>
      <button
        type="button"
        onClick={() => onSelect(agentId)}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs",
          active ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )}
      >
        <span className="flex-1 truncate">{name}</span>
        {count > 0 && <span className="text-[10px]">{count}</span>}
      </button>
      {active && children}
    </div>
  );
}

/**
 * One top-level direction group in the Inbox sidebar (Inbox or Outbox):
 * a selectable, collapsible root row (badge-only summary for the whole
 * direction, unfiltered by agent -- it never shows a message list of its
 * own, see InlineMessageList's docstring) with an "Admin" sub-row (items
 * with no agent) and one sub-row per registered agent
 * (PROPOSTA-INBOX-DISPATCH §6). Rendered twice by the Inbox page -- once
 * per direction -- alongside the Archived tree (InboxGroupTree). Whichever
 * Admin/agent row is the active selection renders its message list inline,
 * right under itself, instead of in a separate pane.
 */
export function AgentDirectionTree<T>({
  direction,
  label,
  noAgentLabel,
  rootCount,
  adminCount,
  agentCounts,
  selected,
  expanded,
  onToggleExpanded,
  onSelectRoot,
  onSelectAgent,
  onDropDemand,
  onCleanup,
  onArchive,
  messages,
  renderMessage,
  emptyMessage,
}: {
  direction: AgentDirection;
  label: string;
  /** Label for the NO_AGENT_ID row -- items with no agent on that side.
   * Not really "Admin" (no per-user ownership concept here) -- items land
   * here because nobody/nothing assigned them to a specific registered
   * Agent, i.e. the system's own catch-all, so callers should pass
   * something like "System" rather than a person's name. */
  noAgentLabel: string;
  /** Badge shown on the root row. */
  rootCount: number;
  /** Badge shown on the NO_AGENT_ID row. */
  adminCount: number;
  /** agentId -> count of demands under this direction for that agent. */
  agentCounts: Record<string, number>;
  /** undefined = this direction tree isn't the active selection at all. */
  selected: AgentTreeSelection | undefined;
  /** Controlled -- lifted to DemandsPage so the toolbar's expand/collapse-
   * all toggle can drive every top-level group at once (2026-07-25). */
  expanded: boolean;
  onToggleExpanded: () => void;
  onSelectRoot: () => void;
  onSelectAgent: (agentId: string) => void;
  /** Optional drop handler for the root row (only wired for Inbox, to move
   * an archived message back to Incoming). */
  onDropDemand?: (demandId: string) => void;
  /** Opens the cleanup confirm dialog scoped to every message in this
   * whole direction (all agents + System), shown as a hover icon on the
   * root row (2026-07-25). */
  onCleanup: () => void;
  /** Archives every message in this whole direction in one action
   * (2026-07-27) -- only meaningful for "completed" (Finalizado): a
   * finished run doesn't need to keep cluttering the tree once its result
   * has been seen, but archiving keeps it under Arquivadas instead of
   * deleting it the way the trash icon next to it does. Omitted for
   * inbox/outbox, where a bulk archive of everything sent or received is a
   * much bigger, less obviously-safe action than this button implies. */
  onArchive?: () => void;
  /** The already-filtered list for whichever node is currently active --
   * only rendered under that one node. */
  messages: T[];
  renderMessage: (item: T) => ReactNode;
  emptyMessage: string;
}) {
  const { data: agents } = useAgents();
  const [dragOver, setDragOver] = useState(false);
  const Icon = DIRECTION_ICON[direction];
  // Only agents with at least one message in this direction get a row --
  // showing the full roster (most with count 0) made the tree mostly
  // noise (2026-07-25, Marcelo: "só mostrar os agentes com task ou
  // notes... o restante deixa oculto"). The System/Admin row (NO_AGENT_ID)
  // stays unconditional -- it's the catch-all bucket, not "an agent".
  const allAgents = [...(agents ?? [])]
    .filter((agent) => (agentCounts[agent.id] ?? 0) > 0)
    .sort((a, b) => a.name.localeCompare(b.name));
  const isRootActive = selected?.agentId === null;

  const messagesSlot = <InlineMessageList messages={messages} renderMessage={renderMessage} emptyMessage={emptyMessage} />;

  return (
    <div>
      <div
        onDragOver={
          onDropDemand
            ? (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
              }
            : undefined
        }
        onDragEnter={
          onDropDemand
            ? (e) => {
                e.preventDefault();
                setDragOver(true);
              }
            : undefined
        }
        onDragLeave={onDropDemand ? () => setDragOver(false) : undefined}
        onDrop={
          onDropDemand
            ? (e) => {
                e.preventDefault();
                setDragOver(false);
                const demandId = e.dataTransfer.getData(DEMAND_DRAG_MIME);
                if (demandId) onDropDemand(demandId);
              }
            : undefined
        }
        className={cn(
          "group flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
          dragOver
            ? "bg-accent ring-1 ring-inset ring-primary"
            : isRootActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )}
      >
        <button
          type="button"
          onClick={() => {
            onToggleExpanded();
            onSelectRoot();
          }}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
          <Icon className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate font-medium">{label}</span>
          {rootCount > 0 && <span className="text-[10px] text-muted-foreground">{rootCount}</span>}
        </button>
        <div className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
          {onArchive && <ActionIcon icon={Archive} label={`Archive all in ${label}`} onClick={onArchive} />}
          <ActionIcon icon={Trash2} label={`Clean up ${label}`} destructive onClick={onCleanup} />
        </div>
      </div>
      {expanded && (
        <div className="ml-3 space-y-0.5 border-l pl-2">
          <AgentRow agentId={NO_AGENT_ID} name={noAgentLabel} count={adminCount} active={selected?.agentId === NO_AGENT_ID} onSelect={onSelectAgent}>
            {messagesSlot}
          </AgentRow>
          {allAgents.map((agent) => (
            <AgentRow
              key={agent.id}
              agentId={agent.id}
              name={agent.name}
              count={agentCounts[agent.id] ?? 0}
              active={selected?.agentId === agent.id}
              onSelect={onSelectAgent}
            >
              {messagesSlot}
            </AgentRow>
          ))}
        </div>
      )}
    </div>
  );
}
