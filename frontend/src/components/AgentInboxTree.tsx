import { useState } from "react";
import { ChevronDown, ChevronRight, Inbox as InboxIcon, SendHorizontal, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAgents } from "@/hooks/useAgent";

export type AgentDirection = "inbox" | "outbox";

/** Which agent+direction node is selected -- mirrors InboxGroupTree's
 * selectedGroupId convention (undefined = this tree isn't the active
 * selection at all). */
export interface AgentTreeSelection {
  agentId: string;
  direction: AgentDirection;
}

function AgentNode({
  agentId,
  name,
  inboxCount,
  outboxCount,
  selection,
  onSelect,
}: {
  agentId: string;
  name: string;
  inboxCount: number;
  outboxCount: number;
  selection: AgentTreeSelection | undefined;
  onSelect: (selection: AgentTreeSelection) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const total = inboxCount + outboxCount;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
        <span className="flex-1 truncate font-medium">{name}</span>
        {total > 0 && <span className="text-[10px] text-muted-foreground">{total}</span>}
      </button>
      {expanded && (
        <div className="ml-3 space-y-0.5 border-l pl-2">
          <button
            type="button"
            onClick={() => onSelect({ agentId, direction: "inbox" })}
            className={cn(
              "flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs",
              selection?.agentId === agentId && selection.direction === "inbox"
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <InboxIcon className="h-3 w-3 shrink-0" />
            <span className="flex-1">Inbox</span>
            <span className="text-[10px]">{inboxCount}</span>
          </button>
          <button
            type="button"
            onClick={() => onSelect({ agentId, direction: "outbox" })}
            className={cn(
              "flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs",
              selection?.agentId === agentId && selection.direction === "outbox"
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <SendHorizontal className="h-3 w-3 shrink-0" />
            <span className="flex-1">Outbox</span>
            <span className="text-[10px]">{outboxCount}</span>
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * "Agent tree" section of the Inbox sidebar (PROPOSTA-INBOX-DISPATCH
 * §6): one node per registered agent, each with an Inbox (items dispatched
 * TO it) and Outbox (items it dispatched onward) sub-list. Sits alongside
 * the existing Incoming/Archived tree (InboxGroupTree), not replacing it --
 * items with no target_agent_id ("sem agente") never appear here, they
 * stay in the plain Incoming/Archived view.
 */
export function AgentInboxTree({
  inboxCounts,
  outboxCounts,
  selection,
  onSelect,
}: {
  /** agentId -> count of demands with target_agent_id === agentId. */
  inboxCounts: Record<string, number>;
  /** agentId -> count of demands with from_agent_id === agentId (and a target set). */
  outboxCounts: Record<string, number>;
  selection: AgentTreeSelection | undefined;
  onSelect: (selection: AgentTreeSelection) => void;
}) {
  const { data: agents } = useAgents();
  const [expanded, setExpanded] = useState(false);
  const withActivity = (agents ?? []).filter(
    (a) => (inboxCounts[a.id] ?? 0) > 0 || (outboxCounts[a.id] ?? 0) > 0 || a.runtime_type
  );

  if (withActivity.length === 0) return null;

  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
        <Users className="h-3.5 w-3.5 shrink-0" />
        <span className="flex-1">Agents</span>
      </button>
      {expanded && (
        <div className="space-y-0.5">
          {withActivity.map((agent) => (
            <AgentNode
              key={agent.id}
              agentId={agent.id}
              name={agent.name}
              inboxCount={inboxCounts[agent.id] ?? 0}
              outboxCount={outboxCounts[agent.id] ?? 0}
              selection={selection}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
