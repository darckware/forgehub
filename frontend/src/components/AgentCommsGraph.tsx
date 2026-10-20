import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Table2, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { NO_AGENT_ID } from "@/components/AgentInboxTree";
import { useAgents } from "@/hooks/useAgent";
import type { Demand } from "@/hooks/useDemands";

type EdgeStatus = "critical" | "warning" | "success" | "plain";

interface EdgeAgg {
  key: string;
  from: string;
  to: string;
  count: number;
  completed: number;
  failed: number;
  inFlight: number;
  plain: number;
}

interface NodeAgg {
  id: string;
  label: string;
  sent: number;
  received: number;
  failed: number;
  pending: number;
}

const IN_FLIGHT_STATUSES = new Set(["pending", "dispatched", "running"]);

/** Aggregates the raw demand list into a directed multigraph -- one edge per
 * (from, to) participant pair, where a participant is either a registered
 * agent id or the NO_AGENT_ID sentinel (shared with AgentInboxTree's
 * "System" row, so this graph's vocabulary matches the sidebar's). Demands
 * with no agent on either side (a plain unaddressed note) never routed
 * anywhere, so they're excluded -- this is a map of actual inter-party
 * traffic, not every row in the table. */
function aggregate(demands: Demand[], agentNames: Map<string, string>, systemLabel: string) {
  const edges = new Map<string, EdgeAgg>();
  const nodes = new Map<string, NodeAgg>();

  function ensureNode(id: string): NodeAgg {
    let node = nodes.get(id);
    if (!node) {
      node = { id, label: id === NO_AGENT_ID ? systemLabel : agentNames.get(id) ?? id, sent: 0, received: 0, failed: 0, pending: 0 };
      nodes.set(id, node);
    }
    return node;
  }

  for (const d of demands) {
    const from = d.from_agent_id ?? NO_AGENT_ID;
    const to = d.target_agent_id ?? NO_AGENT_ID;
    if (from === NO_AGENT_ID && to === NO_AGENT_ID) continue;

    const key = `${from}=>${to}`;
    let edge = edges.get(key);
    if (!edge) {
      edge = { key, from, to, count: 0, completed: 0, failed: 0, inFlight: 0, plain: 0 };
      edges.set(key, edge);
    }
    edge.count += 1;
    if (d.dispatch_status === "completed") edge.completed += 1;
    else if (d.dispatch_status === "failed") edge.failed += 1;
    else if (d.dispatch_status && IN_FLIGHT_STATUSES.has(d.dispatch_status)) edge.inFlight += 1;
    else edge.plain += 1;

    const fromNode = ensureNode(from);
    const toNode = ensureNode(to);
    fromNode.sent += 1;
    // "Received" mirrors the sidebar's *original* Incoming rule (2026-07-27,
    // the "letter" model: a message only counts as arrived once dispatch
    // has actually started, and a self-addressed one never visits its own
    // Incoming). Deliberately NOT narrowed further to match
    // isIncomingItem's 2026-07-28 update (which also excludes
    // Running/Completed/Failed, so a message counts in exactly one sidebar
    // group at a time) -- this graph answers "has this ever arrived here,"
    // a standing traffic fact, not "is it sitting in Incoming right now";
    // narrowing it the same way would collapse "received" to ~0 for every
    // real dispatch. System (to === NO_AGENT_ID) stays ungated, same
    // reasoning as Incoming's own System row: an unaddressed item never
    // enters dispatch at all, so gating it the same way would erase it
    // from this count entirely instead of leaving it as the human-note
    // catch-all it is.
    if (to === NO_AGENT_ID || (from !== to && d.dispatch_status != null)) {
      toNode.received += 1;
    }
    if (d.dispatch_status === "failed") {
      fromNode.failed += 1;
      toNode.failed += 1;
    }
    if (d.dispatch_status && IN_FLIGHT_STATUSES.has(d.dispatch_status)) {
      fromNode.pending += 1;
      toNode.pending += 1;
    }
  }

  return { edges: [...edges.values()], nodes: [...nodes.values()] };
}

function edgeStatus(edge: EdgeAgg): EdgeStatus {
  if (edge.failed > 0) return "critical";
  if (edge.inFlight > 0) return "warning";
  if (edge.completed > 0) return "success";
  return "plain";
}

const EDGE_STROKE: Record<EdgeStatus, string> = {
  critical: "stroke-destructive",
  warning: "stroke-amber-500",
  success: "stroke-emerald-600",
  plain: "stroke-muted-foreground/50",
};

const EDGE_MARKER: Record<EdgeStatus, string> = {
  critical: "url(#comms-arrow-critical)",
  warning: "url(#comms-arrow-warning)",
  success: "url(#comms-arrow-success)",
  plain: "url(#comms-arrow-plain)",
};

const MARKER_FILL: Record<EdgeStatus, string> = {
  critical: "fill-destructive",
  warning: "fill-amber-500",
  success: "fill-emerald-600",
  plain: "fill-muted-foreground/50",
};

function edgeWidth(count: number, maxCount: number): number {
  if (maxCount <= 1) return 2.5;
  const ratio = count / maxCount;
  return 2 + ratio * 6;
}

interface Point {
  x: number;
  y: number;
}

function layout(nodeIds: string[], width: number, height: number) {
  const cx = width / 2;
  const cy = height / 2;
  const hasSystem = nodeIds.includes(NO_AGENT_ID);
  const ring = nodeIds.filter((id) => id !== NO_AGENT_ID);
  const radius = Math.min(width, height) / 2 - 70;
  const positions = new Map<string, Point>();
  if (hasSystem) positions.set(NO_AGENT_ID, { x: cx, y: cy });
  ring.forEach((id, i) => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / Math.max(ring.length, 1);
    positions.set(id, { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) });
  });
  // No system participant at all -- fall back to placing every node on the
  // ring (still deterministic, just no hub in the middle).
  if (!hasSystem && ring.length === 0 && nodeIds.length > 0) {
    positions.set(nodeIds[0], { x: cx, y: cy });
  }
  return positions;
}

/** Bends a straight A->B line into a quadratic curve when the reverse edge
 * (B->A) also exists, offsetting each direction to the opposite side of the
 * line so the two arrows never overlap. */
function pathFor(from: Point, to: Point, bend: number): string {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;
  if (bend === 0) return `M ${from.x} ${from.y} L ${to.x} ${to.y}`;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len;
  const ny = dx / len;
  const cx = mx + nx * bend;
  const cy = my + ny * bend;
  return `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`;
}

/** Pulls the curve's endpoint back along the line so the arrowhead lands on
 * the node's ring instead of under its label. */
function shrinkToward(from: Point, to: Point, offset: number): Point {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: to.x - (dx / len) * offset, y: to.y - (dy / len) * offset };
}

const NODE_RADIUS = 26;

export function AgentCommsGraph({ demands }: { demands: Demand[] }) {
  const { t } = useTranslation("demands");
  const { data: agents } = useAgents();
  const [showTable, setShowTable] = useState(false);
  const [active, setActive] = useState<{ kind: "node" | "edge"; id: string } | null>(null);

  const agentNames = useMemo(() => new Map((agents ?? []).map((a) => [a.id, a.name])), [agents]);
  const { edges, nodes } = useMemo(
    () => aggregate(demands, agentNames, t("systemLabel")),
    [demands, agentNames, t]
  );

  const width = 640;
  const height = 520;
  const nodeIds = nodes.map((n) => n.id);
  const positions = useMemo(() => layout(nodeIds, width, height), [nodeIds.join(","), width, height]);
  const maxCount = Math.max(1, ...edges.map((e) => e.count));
  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  const isEdgeActive = (edge: EdgeAgg) =>
    active === null ||
    (active.kind === "edge" && active.id === edge.key) ||
    (active.kind === "node" && (active.id === edge.from || active.id === edge.to));
  const isNodeActive = (id: string) =>
    active === null || (active.kind === "node" && active.id === id) || (active.kind === "edge" && active.id.startsWith(`${id}=>`)) || (active.kind === "edge" && active.id.endsWith(`=>${id}`));

  const activeDetail = useMemo(() => {
    if (!active) return null;
    if (active.kind === "node") {
      const n = nodeById.get(active.id);
      return n ?? null;
    }
    return edges.find((e) => e.key === active.id) ?? null;
  }, [active, edges, nodes]);

  if (nodes.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border/60 text-sm text-muted-foreground">
        {t("overview.emptyState")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Workflow className="h-4 w-4 text-muted-foreground" />
            {t("overview.title")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("overview.subtitle")}</p>
        </div>
        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setShowTable((v) => !v)}>
          <Table2 className="h-3.5 w-3.5" />
          {showTable ? t("overview.tableToggleHide") : t("overview.tableToggleShow")}
        </Button>
      </div>

      {showTable ? (
        <div className="rounded-lg border border-border/60">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("overview.table.from")}</TableHead>
                <TableHead>{t("overview.table.to")}</TableHead>
                <TableHead>{t("overview.table.total")}</TableHead>
                <TableHead>{t("overview.table.completed")}</TableHead>
                <TableHead>{t("overview.table.inFlight")}</TableHead>
                <TableHead>{t("overview.table.failed")}</TableHead>
                <TableHead>{t("overview.table.plain")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...edges]
                .sort((a, b) => b.count - a.count)
                .map((e) => (
                  <TableRow key={e.key}>
                    <TableCell>{nodeById.get(e.from)?.label ?? e.from}</TableCell>
                    <TableCell>{nodeById.get(e.to)?.label ?? e.to}</TableCell>
                    <TableCell className="font-medium">{e.count}</TableCell>
                    <TableCell className="text-emerald-600">{e.completed || "-"}</TableCell>
                    <TableCell className="text-amber-600">{e.inFlight || "-"}</TableCell>
                    <TableCell className="text-destructive">{e.failed || "-"}</TableCell>
                    <TableCell className="text-muted-foreground">{e.plain || "-"}</TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          <div className="min-w-0 flex-1 rounded-lg border border-border/60 bg-muted/10 p-2">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              className="h-auto w-full"
              role="img"
              aria-label={t("overview.title")}
              onMouseLeave={() => setActive(null)}
            >
              <defs>
                {(["critical", "warning", "success", "plain"] as EdgeStatus[]).map((s) => (
                  <marker
                    key={s}
                    id={`comms-arrow-${s}`}
                    viewBox="0 0 10 10"
                    refX="8"
                    refY="5"
                    markerWidth="7"
                    markerHeight="7"
                    orient="auto-start-reverse"
                  >
                    <path d="M 0 0 L 10 5 L 0 10 z" className={MARKER_FILL[s]} />
                  </marker>
                ))}
              </defs>

              {edges.map((edge) => {
                const from = positions.get(edge.from);
                const to = positions.get(edge.to);
                if (!from || !to) return null;
                const reverseExists = edges.some((e) => e.from === edge.to && e.to === edge.from);
                const bend = reverseExists ? 22 : 0;
                const trimmedTo = shrinkToward(from, to, NODE_RADIUS + 6);
                const status = edgeStatus(edge);
                const active_ = isEdgeActive(edge);
                return (
                  <path
                    key={edge.key}
                    d={pathFor(from, trimmedTo, bend)}
                    fill="none"
                    strokeWidth={edgeWidth(edge.count, maxCount)}
                    strokeLinecap="round"
                    markerEnd={EDGE_MARKER[status]}
                    className={cn(EDGE_STROKE[status], "cursor-pointer transition-opacity", active_ ? "opacity-100" : "opacity-20")}
                    onMouseEnter={() => setActive({ kind: "edge", id: edge.key })}
                    onClick={() => setActive({ kind: "edge", id: edge.key })}
                  >
                    <title>
                      {t("overview.tooltip", {
                        from: nodeById.get(edge.from)?.label ?? edge.from,
                        to: nodeById.get(edge.to)?.label ?? edge.to,
                        count: edge.count,
                      })}
                    </title>
                  </path>
                );
              })}

              {nodes.map((node) => {
                const p = positions.get(node.id);
                if (!p) return null;
                const isSystem = node.id === NO_AGENT_ID;
                const dim = !isNodeActive(node.id);
                return (
                  <g
                    key={node.id}
                    transform={`translate(${p.x}, ${p.y})`}
                    className={cn("cursor-pointer transition-opacity", dim ? "opacity-30" : "opacity-100")}
                    onMouseEnter={() => setActive({ kind: "node", id: node.id })}
                    onClick={() => setActive({ kind: "node", id: node.id })}
                  >
                    <circle
                      r={NODE_RADIUS}
                      className={cn(
                        "fill-card stroke-2",
                        isSystem ? "stroke-primary" : "stroke-border",
                        active?.kind === "node" && active.id === node.id && "stroke-primary"
                      )}
                    />
                    <text textAnchor="middle" dy="0.35em" className="fill-foreground text-[11px] font-semibold">
                      {node.label.length > 8 ? `${node.label.slice(0, 7)}…` : node.label}
                    </text>
                    {node.failed > 0 && (
                      <circle cx={NODE_RADIUS - 6} cy={-NODE_RADIUS + 6} r={6} className="fill-destructive" />
                    )}
                    <text textAnchor="middle" y={NODE_RADIUS + 16} className="fill-muted-foreground text-[10px]">
                      {node.label}
                    </text>
                  </g>
                );
              })}
            </svg>

            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border/40 px-2 pt-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="h-0.5 w-4 rounded-full bg-emerald-600" /> {t("overview.legend.completed")}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-0.5 w-4 rounded-full bg-amber-500" /> {t("overview.legend.inFlight")}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-0.5 w-4 rounded-full bg-destructive" /> {t("overview.legend.failed")}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-0.5 w-4 rounded-full bg-muted-foreground/50" /> {t("overview.legend.plain")}
              </span>
              <span className="ml-auto italic">{t("overview.legend.thickness")}</span>
            </div>
          </div>

          <div className="w-full shrink-0 rounded-lg border border-border/60 p-3 text-sm lg:w-64">
            {activeDetail ? (
              "label" in activeDetail ? (
                <div className="space-y-2">
                  <p className="font-semibold">{activeDetail.label}</p>
                  <dl className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t("overview.nodeSummary.sent")}</dt>
                      <dd>{activeDetail.sent}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t("overview.nodeSummary.received")}</dt>
                      <dd>{activeDetail.received}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t("overview.nodeSummary.pending")}</dt>
                      <dd className="text-amber-600">{activeDetail.pending || "-"}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t("overview.nodeSummary.failed")}</dt>
                      <dd className="text-destructive">{activeDetail.failed || "-"}</dd>
                    </div>
                  </dl>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="font-semibold">
                    {nodeById.get(activeDetail.from)?.label ?? activeDetail.from} → {nodeById.get(activeDetail.to)?.label ?? activeDetail.to}
                  </p>
                  <dl className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t("overview.table.total")}</dt>
                      <dd>{activeDetail.count}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-emerald-600">{t("overview.table.completed")}</dt>
                      <dd>{activeDetail.completed || "-"}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-amber-600">{t("overview.table.inFlight")}</dt>
                      <dd>{activeDetail.inFlight || "-"}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt className="text-destructive">{t("overview.table.failed")}</dt>
                      <dd>{activeDetail.failed || "-"}</dd>
                    </div>
                  </dl>
                </div>
              )
            ) : (
              <p className="text-xs text-muted-foreground">{t("overview.hoverHint")}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
