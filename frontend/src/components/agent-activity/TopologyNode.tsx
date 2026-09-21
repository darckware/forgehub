import type { KeyboardEvent, PointerEvent, ReactNode } from "react";
import {
  Boxes,
  Cpu,
  Database,
  FolderKanban,
  Globe,
  Lightbulb,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { AgentAvatar } from "@/components/AgentAvatar";
import type {
  ActivityAgent,
  ActivityContext,
  ActivityProject,
  ActivityResource,
} from "@/hooks/useAgentActivity";
import type { ActivityGraphNode } from "@/hooks/useAgentActivityViewModel";
import { cn } from "@/lib/utils";

const AVAILABILITY_CLASS: Record<ActivityAgent["availability"], string> = {
  available: "border-emerald-500/60 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  busy: "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  degraded: "border-orange-500/60 bg-orange-500/10 text-orange-700 dark:text-orange-400",
  unavailable: "border-destructive/60 bg-destructive/10 text-destructive",
  unknown: "border-border bg-muted text-muted-foreground",
};

const RUNTIME_BADGE_CLASS: Record<string, string> = {
  hermes: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  claude: "border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400",
  codex: "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400",
  agy: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400",
};

interface TopologyNodeProps {
  node: ActivityGraphNode;
  agent?: ActivityAgent;
  conception?: ActivityContext;
  project?: ActivityProject;
  resource?: ActivityResource;
  selected: boolean;
  dimmed?: boolean;
  highlighted?: boolean;
  typeLabel: string;
  statusLabel: string;
  onActivate: () => void;
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void;
  onPointerDown: (event: PointerEvent<HTMLButtonElement>) => void;
  onPointerMove: (event: PointerEvent<HTMLButtonElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLButtonElement>) => void;
  onPointerEnter?: () => void;
  onPointerLeave?: () => void;
}

function IconFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-border bg-muted/40 text-muted-foreground shadow-inner",
        className,
      )}
    >
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
  dimmed = false,
  highlighted = false,
  typeLabel,
  statusLabel,
  onActivate,
  onKeyDown,
  onPointerDown,
  onPointerMove,
  onPointerUp,
  onPointerEnter,
  onPointerLeave,
}: TopologyNodeProps) {
  const isPlatform = resource?.kind === "platform" || resource?.key === "platform:forgehub";
  const isGateway = resource?.kind === "gateway" || resource?.key === "gateway:forgerouter";
  const isVault = resource?.kind === "vault" || resource?.key === "vault:forgevault";
  const isPortal = resource?.kind === "portal" || resource?.kind === "site" || resource?.key === "site:darckware" || resource?.key === "portal:darckware";
  const isDatabase = resource?.kind === "database" || (node.kind === "resource" && !isPlatform && !isGateway && !isVault && !isPortal);

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
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
      className={cn(
        "absolute z-10 w-40 -translate-x-1/2 -translate-y-1/2 touch-none cursor-grab rounded-lg border bg-background/95 p-2 text-left shadow-md backdrop-blur-sm transition-all duration-200 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:cursor-grabbing sm:w-44",
        selected
          ? "border-primary ring-2 ring-primary shadow-primary/20 shadow-lg scale-105 z-20"
          : highlighted
          ? "border-primary/80 ring-1 ring-primary/60 scale-[1.02] z-20"
          : isPlatform
          ? "border-indigo-500/40 hover:border-indigo-500/80 bg-indigo-500/[0.03]"
          : isGateway
          ? "border-purple-500/40 hover:border-purple-500/80 bg-purple-500/[0.03]"
          : isVault
          ? "border-emerald-500/40 hover:border-emerald-500/80 bg-emerald-500/[0.03]"
          : isPortal
          ? "border-sky-500/40 hover:border-sky-500/80 bg-sky-500/[0.03]"
          : isDatabase
          ? "border-cyan-500/40 hover:border-cyan-500/80 bg-cyan-500/[0.03]"
          : project
          ? "border-sky-500/40 hover:border-sky-500/80 bg-sky-500/[0.03]"
          : "border-border hover:border-primary/40",
        dimmed && "opacity-35 grayscale-[20%] scale-95",
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
          <IconFrame className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400">
            <Lightbulb className="h-4 w-4" aria-hidden="true" />
          </IconFrame>
        ) : project ? (
          <IconFrame className="border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400">
            <FolderKanban className="h-4 w-4" aria-hidden="true" />
          </IconFrame>
        ) : isPlatform ? (
          <IconFrame className="border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
            <Boxes className="h-4 w-4" aria-hidden="true" />
          </IconFrame>
        ) : isGateway ? (
          <IconFrame className="border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400">
            <Cpu className="h-4 w-4" aria-hidden="true" />
          </IconFrame>
        ) : isVault ? (
          <IconFrame className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          </IconFrame>
        ) : isPortal ? (
          <IconFrame className="border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400">
            <Globe className="h-4 w-4" aria-hidden="true" />
          </IconFrame>
        ) : (
          <IconFrame className="border-cyan-500/30 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400">
            <Database className="h-4 w-4" aria-hidden="true" />
          </IconFrame>
        )}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-semibold tracking-tight text-foreground">{node.label}</span>
          <span className="flex items-center gap-1">
            {agent?.runtime_type ? (
              <span
                className={cn(
                  "inline-block rounded px-1 py-0.2 font-mono text-[8px] uppercase tracking-wide border",
                  RUNTIME_BADGE_CLASS[agent.runtime_type] ?? "border-border bg-muted text-muted-foreground",
                )}
              >
                {agent.runtime_type}
              </span>
            ) : isGateway ? (
              <span className="inline-block rounded px-1 py-0.2 font-mono text-[8px] uppercase tracking-wide border border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400">
                AI Gateway
              </span>
            ) : isPlatform ? (
              <span className="inline-block rounded px-1 py-0.2 font-mono text-[8px] uppercase tracking-wide border border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400">
                Orquestrador
              </span>
            ) : isVault ? (
              <span className="inline-block rounded px-1 py-0.2 font-mono text-[8px] uppercase tracking-wide border border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                Vault
              </span>
            ) : isPortal ? (
              <span className="inline-block rounded px-1 py-0.2 font-mono text-[8px] uppercase tracking-wide border border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400">
                Site & Portal
              </span>
            ) : (
              <span className="block truncate font-mono text-[9px] text-muted-foreground">
                {conception?.status ?? project?.status ?? resource?.detail ?? statusLabel}
              </span>
            )}
          </span>
        </span>
      </span>
      {agent && (
        <>
          <span className="mt-1.5 block truncate text-[10px] font-medium text-foreground">
            {agent.current_work?.project_name ?? typeLabel}
          </span>
          <span className="block truncate text-[9px] text-muted-foreground">
            {agent.current_work?.task_title ?? agent.availability_reason ?? statusLabel}
          </span>
        </>
      )}
      {(isGateway || isPlatform || isPortal || isVault) && (
        <span className="mt-1 flex items-center gap-1 text-[9px] text-muted-foreground">
          <Zap className="h-2.5 w-2.5 text-amber-500" aria-hidden="true" />
          <span className="truncate">{resource?.detail ?? "active service"}</span>
        </span>
      )}
      {agent?.availability === "busy" && (
        <span
          className="absolute right-2 top-2 h-2 w-2 rounded-full bg-amber-500 ring-4 ring-amber-500/20 motion-safe:animate-pulse"
          aria-hidden="true"
        />
      )}
    </button>
  );
}
