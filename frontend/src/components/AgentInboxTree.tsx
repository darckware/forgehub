import { useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, Inbox as InboxIcon, SendHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAgents } from "@/hooks/useAgent";

// Namespaced custom MIME type so dropping something dragged from elsewhere
// on the page (or another app) is a no-op instead of misreading unrelated
// drag data. Shared with InboxGroupTree.tsx (re-exported from there too).
export const DEMAND_DRAG_MIME = "application/x-forgehub-demand-id";

export type AgentDirection = "inbox" | "outbox";

/** Sentinel `agentId` for the "Admin" row -- items with no agent on that
 * side (no target_agent_id for Inbox, no from_agent_id for Outbox). Not a
 * real agent id, never collides with a UUID. */
export const NO_AGENT_ID = "__no_agent__";

/** Which node is selected within a direction tree -- `agentId: null` means
 * the root (every item, unfiltered) is selected; `NO_AGENT_ID` means the
 * "Admin" row (no agent); any other string means that specific agent's
 * sub-row. `undefined` (from the parent) means this direction tree isn't
 * the active selection at all. */
export interface AgentTreeSelection {
  agentId: string | null;
}

const DIRECTION_ICON: Record<AgentDirection, typeof InboxIcon> = {
  inbox: InboxIcon,
  outbox: SendHorizontal,
};

/** Inline message list rendered directly under whichever tree node (root,
 * Admin, agent, or Archived subfolder) is both expanded and the active
 * selection -- there's exactly one such node at a time across the whole
 * sidebar, since selection is a single piece of page state, so every node
 * can safely receive the same `messages`/`renderMessage` props and just
 * gate on its own active+expanded check before rendering them. Generic
 * over the row type so this presentational component doesn't need to
 * import the Demand type. */
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

function AgentRow({
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
 * a selectable, collapsible root row (every item for that direction,
 * unfiltered by agent) with an "Admin" sub-row (items with no agent) and
 * one sub-row per registered agent (PROPOSTA-INBOX-DISPATCH §6). Rendered
 * twice by the Inbox page -- once per direction -- alongside the Archived
 * tree (InboxGroupTree). Whichever row is the active selection renders its
 * message list inline, right under itself, instead of in a separate pane.
 */
export function AgentDirectionTree<T>({
  direction,
  label,
  rootCount,
  adminCount,
  agentCounts,
  selected,
  onSelectRoot,
  onSelectAgent,
  onDropDemand,
  messages,
  renderMessage,
  emptyMessage,
}: {
  direction: AgentDirection;
  label: string;
  /** Badge shown on the root row. */
  rootCount: number;
  /** Badge shown on the "Admin" (no agent) row. */
  adminCount: number;
  /** agentId -> count of demands under this direction for that agent. */
  agentCounts: Record<string, number>;
  /** undefined = this direction tree isn't the active selection at all. */
  selected: AgentTreeSelection | undefined;
  onSelectRoot: () => void;
  onSelectAgent: (agentId: string) => void;
  /** Optional drop handler for the root row (only wired for Inbox, to move
   * an archived message back to Incoming). */
  onDropDemand?: (demandId: string) => void;
  /** The already-filtered list for whichever node is currently active --
   * only rendered under that one node. */
  messages: T[];
  renderMessage: (item: T) => ReactNode;
  emptyMessage: string;
}) {
  const { data: agents } = useAgents();
  const [expanded, setExpanded] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const Icon = DIRECTION_ICON[direction];
  // Every registered agent gets a row -- Hermes core agents (no
  // runtime_type, can't be dispatch targets yet) included alongside the
  // CLI-based ones, so the tree always shows the full roster, not just
  // whoever already has activity or a dispatchable runtime.
  const allAgents = [...(agents ?? [])].sort((a, b) => a.name.localeCompare(b.name));
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
          "flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
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
            setExpanded((v) => !v);
            onSelectRoot();
          }}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
        >
          {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
          <Icon className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate font-medium">{label}</span>
          {rootCount > 0 && <span className="text-[10px] text-muted-foreground">{rootCount}</span>}
        </button>
      </div>
      {expanded && (
        <div className="ml-3 space-y-0.5 border-l pl-2">
          {isRootActive && messagesSlot}
          <AgentRow agentId={NO_AGENT_ID} name="Admin" count={adminCount} active={selected?.agentId === NO_AGENT_ID} onSelect={onSelectAgent}>
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
