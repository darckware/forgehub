import { motion, useReducedMotion } from "framer-motion";
import { ArrowUpRight, LayoutGrid, Maximize2, Minimize2, Radio, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import type {
  ActivityAgent,
  ActivityContext,
  ActivityMessageEdge,
  ActivityProject,
  ActivityResource,
  ActivityTopologyRelation,
} from "@/hooks/useAgentActivity";
import {
  clampGraphPosition,
  graphNodeId,
  layoutActivityGraph,
  type ActivityGraphNode,
  type GraphPosition,
} from "@/hooks/useAgentActivityViewModel";
import { cn } from "@/lib/utils";
import { TopologyNode } from "./TopologyNode";
import { useTopologyPositions } from "./useTopologyPositions";

interface ActivityTopologyProps {
  agents: ActivityAgent[];
  contexts?: ActivityContext[];
  projects: ActivityProject[];
  resources: ActivityResource[];
  relations: ActivityTopologyRelation[];
  edges: ActivityMessageEdge[];
  projectScopeId: string | null;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string) => void;
  onOpenMessage: (edge: ActivityMessageEdge) => void;
}

const EMPTY_CONTEXTS: ActivityContext[] = [];

function handleRecordNavigation(event: React.MouseEvent<HTMLAnchorElement>, openRecord: () => void) {
  if (
    event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey
    || event.shiftKey || event.altKey
  ) return;
  event.preventDefault();
  openRecord();
}

const AVAILABILITY_CLASS: Record<ActivityAgent["availability"], string> = {
  available: "border-emerald-500/60 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
  busy: "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  degraded: "border-orange-500/60 bg-orange-500/10 text-orange-700 dark:text-orange-400",
  unavailable: "border-destructive/60 bg-destructive/10 text-destructive",
  unknown: "border-border bg-muted text-muted-foreground",
};

interface DragState {
  id: string;
  pointerId: number;
  startX: number;
  startY: number;
  moved: boolean;
}

export function ActivityTopology({
  agents,
  contexts = EMPTY_CONTEXTS,
  projects,
  resources,
  relations,
  edges,
  projectScopeId,
  selectedAgentId,
  onSelectAgent,
  onOpenMessage,
}: ActivityTopologyProps) {
  const { t } = useTranslation("agentActivity");
  const reduceMotion = useReducedMotion();
  const canvasRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);
  const suppressActivationRef = useRef(false);
  const [announcement, setAnnouncement] = useState("");
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(() =>
    selectedAgentId ? graphNodeId("agent", selectedAgentId) : null,
  );
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (selectedAgentId) {
      setSelectedNodeId(graphNodeId("agent", selectedAgentId));
    } else if (selectedNodeId?.startsWith("agent:")) {
      setSelectedNodeId(null);
    }
  }, [selectedAgentId]);

  useEffect(() => {
    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape" && isFullscreen) {
        setIsFullscreen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen]);

  const defaultNodes = useMemo(
    () => layoutActivityGraph(agents, projects, resources, contexts),
    [agents, contexts, projects, resources],
  );
  const { positions: nodes, previewMove, commitMove, organize, distribute } = useTopologyPositions(
    defaultNodes,
    projectScopeId,
  );

  const agentById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents]);
  const conceptionById = useMemo(
    () => new Map(contexts.filter((context) => context.context_kind === "conception").map((context) => [context.context_id, context])),
    [contexts],
  );
  const projectById = useMemo(() => new Map(projects.map((project) => [project.id, project])), [projects]);
  const resourceById = useMemo(() => new Map(resources.map((resource) => [resource.key, resource])), [resources]);
  const nodeById = new Map(nodes.map((node) => [node.id, node]));

  const focusedNodeId = hoveredNodeId ?? selectedNodeId ?? (selectedAgentId ? graphNodeId("agent", selectedAgentId) : null);

  const connectedNodeIds = useMemo(() => {
    if (!focusedNodeId) return null;
    const connected = new Set<string>([focusedNodeId]);
    for (const rel of relations) {
      const fromId = graphNodeId(rel.from_type, rel.from_id);
      const toId = graphNodeId(rel.to_type, rel.to_id);
      if (fromId === focusedNodeId) connected.add(toId);
      if (toId === focusedNodeId) connected.add(fromId);
    }
    for (const edge of edges) {
      if (edge.from_agent_id && edge.target_agent_id) {
        const fromId = graphNodeId("agent", edge.from_agent_id);
        const toId = graphNodeId("agent", edge.target_agent_id);
        if (fromId === focusedNodeId) connected.add(toId);
        if (toId === focusedNodeId) connected.add(fromId);
      }
    }
    return connected;
  }, [focusedNodeId, relations, edges]);

  const sourceLabel = (kind: "agent" | "conception" | "project" | "resource", id: string) => {
    if (kind === "agent") return agentById.get(id)?.name ?? id;
    if (kind === "conception") return conceptionById.get(id)?.title ?? id;
    if (kind === "project") return projectById.get(id)?.name ?? id;
    return resourceById.get(id)?.label ?? id;
  };

  const graphPositionFromPointer = (event: PointerEvent<HTMLButtonElement>): GraphPosition | null => {
    const bounds = canvasRef.current?.getBoundingClientRect();
    if (
      !bounds || bounds.width <= 0 || bounds.height <= 0
      || !Number.isFinite(event.clientX) || !Number.isFinite(event.clientY)
    ) return null;
    return clampGraphPosition({
      xPct: ((event.clientX - bounds.left) / bounds.width) * 100,
      yPct: ((event.clientY - bounds.top) / bounds.height) * 100,
    });
  };

  const announceMove = (node: ActivityGraphNode) => {
    setAnnouncement(t("topology.nodeMoved", { name: node.label }));
  };

  const handlePointerDown = (node: ActivityGraphNode, event: PointerEvent<HTMLButtonElement>) => {
    dragRef.current = {
      id: node.id,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const handlePointerMove = (node: ActivityGraphNode, event: PointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== node.id || drag.pointerId !== event.pointerId) return;
    const position = graphPositionFromPointer(event);
    if (!position) return;
    drag.moved ||= Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) > 3;
    previewMove(node.id, position);
  };

  const handlePointerUp = (node: ActivityGraphNode, event: PointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.id !== node.id || drag.pointerId !== event.pointerId) return;
    const position = graphPositionFromPointer(event) ?? { xPct: node.xPct, yPct: node.yPct };
    if (drag.moved) {
      commitMove(node.id, position);
      announceMove({ ...node, ...position });
      suppressActivationRef.current = true;
    }
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    dragRef.current = null;
  };

  const handleNodeKeyDown = (node: ActivityGraphNode, event: KeyboardEvent<HTMLButtonElement>) => {
    const delta = event.shiftKey ? 5 : 1;
    const direction = {
      ArrowLeft: { xPct: -delta, yPct: 0 },
      ArrowRight: { xPct: delta, yPct: 0 },
      ArrowUp: { xPct: 0, yPct: -delta },
      ArrowDown: { xPct: 0, yPct: delta },
    }[event.key];
    if (!direction) return;
    event.preventDefault();
    const next = clampGraphPosition({ xPct: node.xPct + direction.xPct, yPct: node.yPct + direction.yPct });
    commitMove(node.id, next);
    announceMove({ ...node, ...next });
  };

  const activateNode = (node: ActivityGraphNode) => {
    if (suppressActivationRef.current) {
      suppressActivationRef.current = false;
      return;
    }
    setSelectedNodeId(node.id);
    if (node.kind === "agent") onSelectAgent(node.sourceId);
    setAnnouncement(t("topology.nodeSelected", { name: node.label }));
  };

  const handleCanvasClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (event.target === canvasRef.current || (event.target as HTMLElement).tagName === "svg") {
      setSelectedNodeId(null);
      onSelectAgent("");
    }
  };

  const toggleFullscreen = () => {
    setIsFullscreen((prev) => !prev);
  };

  const organizeNodes = () => {
    organize();
    setAnnouncement(t("topology.organized"));
  };

  const distributeNodes = () => {
    distribute();
    setAnnouncement(t("topology.distributed"));
  };

  return (
    <section
      aria-labelledby="activity-topology-title"
      aria-label={t("topology.title")}
      className={cn(
        "overflow-hidden bg-card transition-all duration-200",
        isFullscreen
          ? "fixed inset-0 z-50 flex h-screen w-screen flex-col rounded-none border-0 p-3 shadow-2xl"
          : "min-h-[30rem] rounded-lg border border-border",
      )}
    >
      <div className="flex min-h-11 flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <Radio className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <h2 id="activity-topology-title" className="text-sm font-medium">{t("topology.title")}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground" aria-label={t("topology.legend")}>
            {(["available", "busy", "degraded", "unavailable"] as const).map((availability) => (
              <span key={availability} className="inline-flex items-center gap-1">
                <span className={cn("h-2 w-2 rounded-full border", AVAILABILITY_CLASS[availability])} aria-hidden="true" />
                {t(`availability.${availability}`)}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={distributeNodes}
              className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-md border border-border px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-muted"
            >
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              {t("topology.distribute")}
            </button>
            <button
              type="button"
              onClick={organizeNodes}
              className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-md border border-border px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-muted"
            >
              <LayoutGrid className="h-3.5 w-3.5" aria-hidden="true" />
              {t("topology.organize")}
            </button>
            <button
              type="button"
              onClick={toggleFullscreen}
              title={isFullscreen ? t("topology.exitFullscreen") : t("topology.fullscreen")}
              aria-label={isFullscreen ? t("topology.exitFullscreen") : t("topology.fullscreen")}
              className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-md border border-border px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-muted"
            >
              {isFullscreen ? (
                <Minimize2 className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              <span>{isFullscreen ? t("topology.exitFullscreen") : t("topology.fullscreen")}</span>
            </button>
          </div>
        </div>
      </div>

      <div
        ref={canvasRef}
        onClick={handleCanvasClick}
        data-testid="topology-canvas"
        className={cn(
          "relative overflow-auto bg-[linear-gradient(to_right,hsl(var(--border)/0.22)_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--border)/0.22)_1px,transparent_1px)] bg-[size:32px_32px]",
          isFullscreen ? "flex-1 min-h-0 h-full w-full" : "min-h-[29rem]",
        )}
      >
        {nodes.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center px-6 text-center text-sm text-muted-foreground">{t("states.empty")}</div>
        ) : (
          <>
            <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 100" aria-hidden="true">
              <defs>
                <style>{`
                  @keyframes activeMessageFlow {
                    from { stroke-dashoffset: 24; }
                    to { stroke-dashoffset: 0; }
                  }
                  .active-message-flow {
                    animation: activeMessageFlow 1.4s linear infinite;
                  }
                `}</style>
                <marker id="activity-arrow" markerHeight="5" markerWidth="5" orient="auto" refX="4" refY="2.5">
                  <path d="M0,0 L5,2.5 L0,5 z" className="fill-muted-foreground/80" />
                </marker>
                <marker id="activity-arrow-violet" markerHeight="5" markerWidth="5" orient="auto" refX="4" refY="2.5">
                  <path d="M0,0 L5,2.5 L0,5 z" className="fill-violet-500" />
                </marker>
                <marker id="activity-arrow-amber" markerHeight="5" markerWidth="5" orient="auto" refX="4" refY="2.5">
                  <path d="M0,0 L5,2.5 L0,5 z" className="fill-amber-500" />
                </marker>
                <marker id="activity-arrow-purple" markerHeight="5" markerWidth="5" orient="auto" refX="4" refY="2.5">
                  <path d="M0,0 L5,2.5 L0,5 z" className="fill-purple-500" />
                </marker>
                <marker id="activity-arrow-indigo" markerHeight="5" markerWidth="5" orient="auto" refX="4" refY="2.5">
                  <path d="M0,0 L5,2.5 L0,5 z" className="fill-indigo-500" />
                </marker>
                <marker id="activity-arrow-emerald" markerHeight="5" markerWidth="5" orient="auto" refX="4" refY="2.5">
                  <path d="M0,0 L5,2.5 L0,5 z" className="fill-emerald-500" />
                </marker>
                <marker id="activity-arrow-sky" markerHeight="5" markerWidth="5" orient="auto" refX="4" refY="2.5">
                  <path d="M0,0 L5,2.5 L0,5 z" className="fill-sky-500" />
                </marker>
              </defs>

              {/* Relações estruturais e de ecossistema */}
              {relations.map((relation) => {
                const from = nodeById.get(graphNodeId(relation.from_type, relation.from_id));
                const to = nodeById.get(graphNodeId(relation.to_type, relation.to_id));
                if (!from || !to) return null;

                const isConnected = connectedNodeIds
                  ? connectedNodeIds.has(from.id) && connectedNodeIds.has(to.id)
                  : true;
                const opacity = connectedNodeIds && !isConnected ? 0.15 : 1;

                const isAiRouting = relation.kind === "ai_routing";
                const isOrch = relation.kind === "orchestration";
                const isVault = relation.kind === "vault_sync";
                const isPortalSync = relation.kind === "portal_sync";
                const isWork = relation.kind === "current_work";
                const isMember = relation.kind === "membership";
                const isPersist = relation.kind === "persistence";
                const isTrans = relation.kind === "transition";

                return (
                  <g key={relation.key} opacity={opacity} className="transition-opacity duration-200">
                    <line
                      x1={from.xPct}
                      y1={from.yPct}
                      x2={to.xPct}
                      y2={to.yPct}
                      className={cn(
                        isAiRouting && "stroke-purple-500/70",
                        isOrch && "stroke-indigo-500/65",
                        isVault && "stroke-emerald-500/65",
                        isPortalSync && "stroke-sky-500/65",
                        isWork && "stroke-emerald-500/80",
                        isMember && "stroke-sky-500/60",
                        isPersist && "stroke-cyan-500/50",
                        isTrans && "stroke-violet-500/70",
                      )}
                      strokeDasharray={
                        isMember || isPersist
                          ? "2 2"
                          : undefined
                      }
                      strokeWidth={isWork || isAiRouting || isOrch || isPortalSync ? "0.55" : "0.45"}
                      markerEnd={
                        isAiRouting
                          ? "url(#activity-arrow-purple)"
                          : isOrch
                          ? "url(#activity-arrow-indigo)"
                          : isVault
                          ? "url(#activity-arrow-emerald)"
                          : isPortalSync
                          ? "url(#activity-arrow-sky)"
                          : undefined
                      }
                    />
                  </g>
                );
              })}

              {/* Mensagens e comunicações inter-agentes */}
              {edges.map((edge) => {
                const from = edge.from_agent_id ? nodeById.get(graphNodeId("agent", edge.from_agent_id)) : undefined;
                const to = edge.target_agent_id ? nodeById.get(graphNodeId("agent", edge.target_agent_id)) : undefined;
                if (!from || !to) return null;

                const isConnected = connectedNodeIds
                  ? connectedNodeIds.has(from.id) && connectedNodeIds.has(to.id)
                  : true;
                const opacity = connectedNodeIds && !isConnected ? 0.15 : 1;
                const isWaiting = edge.waiting_for_response;
                const isRunning = edge.dispatch_status === "running";
                const isDispatched = edge.dispatch_status === "dispatched";
                const isInFlight = isRunning || isDispatched;
                const isDistinctAgents = from.id !== to.id;
                const pathData = `M ${from.xPct} ${from.yPct} L ${to.xPct} ${to.yPct}`;

                return (
                  <g key={edge.message_id} opacity={opacity} className="transition-opacity duration-200">
                    <line
                      x1={from.xPct}
                      y1={from.yPct}
                      x2={to.xPct}
                      y2={to.yPct}
                      className={cn(
                        isWaiting
                          ? "stroke-amber-500/85 animate-pulse"
                          : isInFlight
                          ? "stroke-violet-500 active-message-flow"
                          : "stroke-violet-400/50",
                      )}
                      strokeDasharray={isWaiting ? "2 2" : isInFlight ? "4 2" : undefined}
                      strokeWidth={isInFlight || isWaiting ? "0.65" : "0.45"}
                      markerEnd={isWaiting ? "url(#activity-arrow-amber)" : "url(#activity-arrow-violet)"}
                    />
                    {isInFlight && isDistinctAgents && (
                      <g data-testid={`active-packet-${edge.message_id}`}>
                        <circle r="1.6" className={isRunning ? "fill-violet-400/35" : "fill-sky-400/35"}>
                          <animateMotion
                            path={pathData}
                            dur={isRunning ? "1.8s" : "2.2s"}
                            repeatCount="indefinite"
                          />
                        </circle>
                        <circle r="0.8" className={isRunning ? "fill-violet-300" : "fill-sky-300"}>
                          <animateMotion
                            path={pathData}
                            dur={isRunning ? "1.8s" : "2.2s"}
                            repeatCount="indefinite"
                          />
                        </circle>
                      </g>
                    )}
                  </g>
                );
              })}
            </svg>

            {nodes.map((node) => {
              const agent = node.kind === "agent" ? agentById.get(node.sourceId) : undefined;
              const conception = node.kind === "conception" ? conceptionById.get(node.sourceId) : undefined;
              const project = node.kind === "project" ? projectById.get(node.sourceId) : undefined;
              const resource = node.kind === "resource" ? resourceById.get(node.sourceId) : undefined;
              if (!agent && !conception && !project && !resource) return null;
              const statusLabel = agent
                ? t(`availability.${agent.availability}`)
                : conception?.status ?? project?.status ?? resource?.status ?? t("availability.unknown");

              const isDimmed = connectedNodeIds !== null && !connectedNodeIds.has(node.id);
              const isHighlighted = focusedNodeId === node.id || (connectedNodeIds !== null && connectedNodeIds.has(node.id));

              const typeLabel = node.kind === "resource" && resource
                ? t(`topology.objectType.${resource.kind}`, { defaultValue: t("topology.objectType.resource") })
                : t(`topology.objectType.${node.kind}`);

              return (
                <TopologyNode
                  key={node.id}
                  node={node}
                  agent={agent}
                  conception={conception}
                  project={project}
                  resource={resource}
                  selected={selectedNodeId === node.id || Boolean(agent && agent.id === selectedAgentId)}
                  dimmed={isDimmed}
                  highlighted={isHighlighted}
                  typeLabel={typeLabel}
                  statusLabel={statusLabel}
                  onActivate={() => activateNode(node)}
                  onKeyDown={(event) => handleNodeKeyDown(node, event)}
                  onPointerDown={(event) => handlePointerDown(node, event)}
                  onPointerMove={(event) => handlePointerMove(node, event)}
                  onPointerUp={(event) => handlePointerUp(node, event)}
                  onPointerEnter={() => setHoveredNodeId(node.id)}
                  onPointerLeave={() => setHoveredNodeId(null)}
                />
              );
            })}

            {edges.flatMap((edge) => {
              if (!edge.from_agent_id || !edge.target_agent_id || !["dispatched", "running"].includes(edge.dispatch_status)) return [];
              const from = nodeById.get(graphNodeId("agent", edge.from_agent_id));
              const to = nodeById.get(graphNodeId("agent", edge.target_agent_id));
              if (!from || !to) return [];
              const restingLeft = from.xPct + (to.xPct - from.xPct) * 0.58;
              const restingTop = from.yPct + (to.yPct - from.yPct) * 0.58;
              return [
                <motion.span
                  key={`${edge.message_id}:${edge.dispatch_status}:${edge.updated_at}`}
                  className={cn("pointer-events-none absolute z-20 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full shadow", edge.dispatch_status === "running" ? "bg-amber-500" : "bg-violet-500")}
                  initial={reduceMotion ? false : { left: `${from.xPct}%`, top: `${from.yPct}%`, opacity: 0 }}
                  animate={{ left: `${reduceMotion ? restingLeft : to.xPct}%`, top: `${reduceMotion ? restingTop : to.yPct}%`, opacity: 1 }}
                  transition={reduceMotion ? { duration: 0 } : { duration: 1.05, ease: "easeInOut" }}
                  aria-hidden="true"
                />,
              ];
            })}
          </>
        )}
      </div>

      <div className={cn("grid gap-3 border-t border-border px-3 py-2 sm:grid-cols-2", isFullscreen && "max-h-24 overflow-y-auto")}>
        <div>
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{t("topology.relationships")}</p>
          {relations.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("topology.noRelationships")}</p>
          ) : (
            <ul className="space-y-1 text-[10px] text-muted-foreground" aria-label={t("topology.relationships")}>
              {relations.map((relation) => (
                <li key={relation.key} className="truncate font-mono">
                  {sourceLabel(relation.from_type, relation.from_id)} → {sourceLabel(relation.to_type, relation.to_id)} · {relation.label}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <p className="mb-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{t("topology.messageRecords")}</p>
          {edges.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("topology.noMessages")}</p>
          ) : (
            <ul className="flex flex-wrap gap-2" aria-label={t("topology.messageRecords")}>
              {edges.map((edge, index) => (
                <li key={edge.message_id}>
                  <span className="inline-flex items-center gap-1">
                    <a
                      href={edge.canonical_path}
                      aria-label={t("topology.openMessage", {
                        from: edge.from_agent_name ?? t("topology.unknownAgent"),
                        to: edge.target_agent_name ?? t("topology.unknownAgent"),
                        subject: edge.subject ?? t("topology.noSubject"),
                        index: index + 1,
                      })}
                      onClick={(event) => handleRecordNavigation(event, () => onOpenMessage(edge))}
                      className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-border px-2 py-1 font-mono text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-muted"
                    >
                      {edge.from_agent_name ?? "—"} → {edge.target_agent_name ?? "—"}
                      <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
                    </a>
                    {edge.factory_context_path && (
                      <a
                        href={edge.factory_context_path}
                        aria-label={t("topology.openFactoryContext", {
                          context: edge.development_request_id
                            ? t("topology.conception")
                            : t("topology.project"),
                        })}
                        className="inline-flex min-h-7 cursor-pointer items-center rounded-md border border-border px-2 font-mono text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-muted"
                      >
                        {edge.development_request_id ? t("topology.conception") : t("topology.project")}
                      </a>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <p role="status" aria-label={t("topology.movementStatus")} className="sr-only">{announcement}</p>
    </section>
  );
}
