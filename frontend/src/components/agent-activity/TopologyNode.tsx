import type { KeyboardEvent, PointerEvent, ReactNode } from "react";
import { Database, FolderKanban, Lightbulb } from "lucide-react";
import { AgentAvatar } from "@/components/AgentAvatar";
import type { ActivityAgent, ActivityContext, ActivityProject, ActivityResource } from "@/hooks/useAgentActivity";
import type { ActivityGraphNode } from "@/hooks/useAgentActivityViewModel";
import { cn } from "@/lib/utils";

const AVAILABILITY_CLASS: Record<ActivityAgent["availability"], string> = {
  available: "border-emerald-500/60 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  busy: "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  degraded: "border-orange-500/60 bg-orange-500/10 text-orange-700 dark:text-orange-400",
  unavailable: "border-destructive/60 bg-destructive/10 text-destructive",
  unknown: "border-border bg-muted text-muted-foreground",
};

interface TopologyNodeProps {
  node: ActivityGraphNode;
  agent?: ActivityAgent;
  conception?: ActivityContext;
  project?: ActivityProject;
  resource?: ActivityResource;
  selected: boolean;
  typeLabel: string;
  statusLabel: string;
  onActivate: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  onPointerDown: (event: PointerEvent<HTMLButtonElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLButtonElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLButtonElement>) => void;
}

function IconFrame({ children }: { children: ReactNode }) {
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-muted/40 text-muted-foreground">
      {children}
    </span>
  );
}

export function TopologyNode({
  node,
  agent,
  conception,
  project,
  resource,
  selected,
  typeLabel,
  statusLabel,
  onActivate,
  onKeyDown,
  onPointerDown,
  onPointerMove,
  onPointerUp,
}: TopologyNodeProps) {
  return (
    <button
      type="button"
      aria-pressed={node.kind === "agent" ? selected : undefined}
      aria-label={`${node.label}, ${typeLabel}, ${statusLabel}`}
      onClick={onActivate}
      onKeyDown={onKeyDown}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      className={cn(
        "absolute z-10 w-40 -translate-x-1/2 -translate-y-1/2 touch-none cursor-grab rounded-md border bg-background p-2 text-left shadow-sm transition-[border-color,background-color] hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:cursor-grabbing sm:w-44",
        selected ? "border-primary ring-1 ring-primary" : "border-border",
      )}
      style={{ left: `${node.xPct}%`, top: `${node.yPct}%` }}
    >
      <span className="flex items-center gap-2">
        {agent ? (
          <AgentAvatar
            name={agent.name}
            avatarDataUrl={agent.avatar_data_url}
            imageAlt={`${agent.name} profile`}
            size="sm"
            className={AVAILABILITY_CLASS[agent.availability]}
          />
        ) : conception ? (
          <IconFrame><Lightbulb className="h-4 w-4" aria-hidden="true" /></IconFrame>
        ) : project ? (
          <IconFrame><FolderKanban className="h-4 w-4" aria-hidden="true" /></IconFrame>
        ) : (
          <IconFrame><Database className="h-4 w-4" aria-hidden="true" /></IconFrame>
        )}
        <span className="min-w-0">
          <span className="block truncate text-xs font-medium">{node.label}</span>
          <span className="block truncate font-mono text-[9px] text-muted-foreground">
            {agent?.runtime_type ?? conception?.status ?? project?.status ?? resource?.detail ?? statusLabel}
          </span>
        </span>
      </span>
      {agent && (
        <>
          <span className="mt-1.5 block truncate text-[10px] text-foreground">
            {agent.current_work?.project_name ?? typeLabel}
          </span>
          <span className="block truncate text-[9px] text-muted-foreground">
            {agent.current_work?.task_title ?? agent.availability_reason ?? statusLabel}
          </span>
        </>
      )}
      {agent?.availability === "busy" && (
        <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-amber-500 motion-safe:animate-pulse" aria-hidden="true" />
      )}
    </button>
  );
}
