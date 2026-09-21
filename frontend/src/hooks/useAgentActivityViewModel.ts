import type {
  ActivityAgent,
  ActivityContext,
  ActivityMessageEdge,
  ActivityProject,
  ActivityResource,
} from "./useAgentActivity";

export type ActivityGraphNodeKind = "agent" | "conception" | "project" | "resource";

export interface GraphPosition {
  xPct: number;
  yPct: number;
}

export interface ActivityGraphNode extends GraphPosition {
  id: string;
  sourceId: string;
  kind: ActivityGraphNodeKind;
  label: string;
}

const GRAPH_POSITION_STORAGE_PREFIX = "forgehub:agent-activity:topology:v1";

export function graphNodeId(kind: ActivityGraphNodeKind, sourceId: string): string {
  return kind === "resource" ? sourceId : `${kind}:${sourceId}`;
}

export function graphPositionStorageKey(projectId: string | null): string {
  return `${GRAPH_POSITION_STORAGE_PREFIX}:${projectId ?? "all"}`;
}

export function clampGraphPosition(position: GraphPosition): GraphPosition {
  return {
    xPct: Math.min(96, Math.max(4, position.xPct)),
    yPct: Math.min(94, Math.max(6, position.yPct)),
  };
}

function layoutBand(
  records: readonly { sourceId: string; label: string }[],
  kind: ActivityGraphNodeKind,
  top: number,
  bottom: number,
): ActivityGraphNode[] {
  if (records.length === 0) return [];
  const columns = Math.min(7, Math.max(1, Math.ceil(Math.sqrt(records.length * 1.8))));
  const rows = Math.ceil(records.length / columns);
  return records.map((record, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    // Alternate x stagger for adjacent rows to prevent vertical blocking
    const countInRow = row === rows - 1 ? records.length - row * columns : columns;
    const xPct = ((column + 1) * 100) / (countInRow + 1);
    const yPct = rows === 1 ? (top + bottom) / 2 : top + (row * (bottom - top)) / (rows - 1);
    return {
      id: graphNodeId(kind, record.sourceId),
      sourceId: record.sourceId,
      kind,
      label: record.label,
      xPct: roundPercent(clampGraphPosition({ xPct, yPct: 50 }).xPct),
      yPct: roundPercent(clampGraphPosition({ xPct: 50, yPct }).yPct),
    };
  });
}

export function distributeActivityGraph(
  nodes: readonly ActivityGraphNode[],
): ActivityGraphNode[] {
  const result = nodes.map((node) => ({ ...node }));
  const minX = 18;
  const minY = 12;

  for (let iter = 0; iter < 20; iter++) {
    let moved = false;
    for (let i = 0; i < result.length; i++) {
      for (let j = i + 1; j < result.length; j++) {
        const dx = result[j].xPct - result[i].xPct;
        const dy = result[j].yPct - result[i].yPct;
        const absX = Math.abs(dx);
        const absY = Math.abs(dy);

        if (absX < minX && absY < minY) {
          const overlapX = (minX - absX) / 2;
          const overlapY = (minY - absY) / 2;
          const signX = dx >= 0 ? 1 : -1;
          const signY = dy >= 0 ? 1 : -1;

          result[i].xPct = clampGraphPosition({ xPct: result[i].xPct - signX * overlapX, yPct: 50 }).xPct;
          result[j].xPct = clampGraphPosition({ xPct: result[j].xPct + signX * overlapX, yPct: 50 }).xPct;
          result[i].yPct = clampGraphPosition({ xPct: 50, yPct: result[i].yPct - signY * overlapY }).yPct;
          result[j].yPct = clampGraphPosition({ xPct: 50, yPct: result[j].yPct + signY * overlapY }).yPct;
          moved = true;
        }
      }
    }
    if (!moved) break;
  }
  return result.map((node) => ({
    ...node,
    xPct: roundPercent(node.xPct),
    yPct: roundPercent(node.yPct),
  }));
}

export function layoutActivityGraph(
  agents: readonly ActivityAgent[],
  projects: readonly ActivityProject[],
  resources: readonly ActivityResource[],
  contexts: readonly ActivityContext[] = [],
): ActivityGraphNode[] {
  const seenAgentKeys = new Set<string>();
  const dedupedAgents: ActivityAgent[] = [];
  for (const agent of agents) {
    const key = agent.name.split("@")[0].trim().toLowerCase();
    if (seenAgentKeys.has(key) || seenAgentKeys.has(agent.id)) continue;
    seenAgentKeys.add(key);
    seenAgentKeys.add(agent.id);
    dedupedAgents.push(agent);
  }
  const orderedAgents = dedupedAgents
    .sort((left, right) => left.id.localeCompare(right.id))
    .map((agent) => ({ sourceId: agent.id, label: agent.name }));
  const orderedProjects = [...projects]
    .sort((left, right) => left.id.localeCompare(right.id))
    .map((project) => ({ sourceId: project.id, label: project.name }));
  const orderedConceptions = contexts
    .filter((context) => context.context_kind === "conception")
    .sort((left, right) => left.context_id.localeCompare(right.context_id))
    .map((context) => ({ sourceId: context.context_id, label: context.title }));
  const orderedResources = [...resources]
    .sort((left, right) => left.key.localeCompare(right.key))
    .map((resource) => ({ sourceId: resource.key, label: resource.label }));

  return [
    ...layoutBand(orderedAgents, "agent", 10, 34),
    ...layoutBand(orderedConceptions, "conception", 43, 53),
    ...layoutBand(orderedProjects, "project", 62, 74),
    ...layoutBand(orderedResources, "resource", 82, 90),
  ];
}

export function mergeSavedGraphPositions(
  nodes: readonly ActivityGraphNode[],
  saved: Record<string, GraphPosition> | null | undefined,
): ActivityGraphNode[] {
  if (!saved) return [...nodes];
  return nodes.map((node) => {
    const position = saved[node.id];
    if (!position || !Number.isFinite(position.xPct) || !Number.isFinite(position.yPct)) {
      return node;
    }
    return { ...node, ...clampGraphPosition(position) };
  });
}

export interface ActivityNode {
  id: string;
  label: string;
  availability: ActivityAgent["availability"];
  xPct: number;
  yPct: number;
}

export interface FlightPacket {
  key: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
  /** Packets are rendered only for the canonical in-flight statuses. */
  status: "dispatched" | "running";
  /** Kept for the renderer's tooltip; it is never parsed to infer state. */
  subject: string | null;
}

const RING_RADIUS_PCT = 38;
const RING_VERTICAL_SCALE = 0.82;

function roundPercent(value: number): number {
  return Math.round(value * 100) / 100;
}

/**
 * Places the canonical agent records in stable-id order around a ring. This
 * is deliberately a presentation-only transform: it neither derives nor
 * rewrites availability, ownership, work, reply, or waiting state.
 */
export function layoutActivityNodes(agents: readonly ActivityAgent[]): ActivityNode[] {
  const seenAgentKeys = new Set<string>();
  const dedupedAgents: ActivityAgent[] = [];
  for (const agent of agents) {
    const key = agent.name.split("@")[0].trim().toLowerCase();
    if (seenAgentKeys.has(key) || seenAgentKeys.has(agent.id)) continue;
    seenAgentKeys.add(key);
    seenAgentKeys.add(agent.id);
    dedupedAgents.push(agent);
  }
  const orderedAgents = dedupedAgents.sort((left, right) => left.id.localeCompare(right.id));
  const total = Math.max(orderedAgents.length, 1);

  return orderedAgents.map((agent, index) => {
    const angle = -Math.PI / 2 + (index * 2 * Math.PI) / total;
    return {
      id: agent.id,
      label: agent.name,
      availability: agent.availability,
      xPct: roundPercent(50 + RING_RADIUS_PCT * Math.cos(angle)),
      yPct: roundPercent(50 + RING_RADIUS_PCT * Math.sin(angle) * RING_VERTICAL_SCALE),
    };
  });
}

function isInFlightPacket(edge: ActivityMessageEdge): edge is ActivityMessageEdge & { dispatch_status: FlightPacket["status"] } {
  return edge.dispatch_status === "dispatched" || edge.dispatch_status === "running";
}

/** A packet identity changes only when the canonical message state changes. */
export function activityPacketKey(edge: Pick<ActivityMessageEdge, "message_id" | "dispatch_status" | "updated_at">): string {
  return `${edge.message_id}:${edge.dispatch_status}:${edge.updated_at}`;
}

/**
 * Resolves packet endpoints from canonical agent ids. Edges without two known
 * canonical endpoints stay absent rather than fabricating a system node.
 */
export function layoutActivityPackets(
  edges: readonly ActivityMessageEdge[],
  nodes: readonly ActivityNode[]
): FlightPacket[] {
  const positionByAgentId = new Map(nodes.map((node) => [node.id, { x: node.xPct, y: node.yPct }]));

  return edges.flatMap((edge) => {
    if (!isInFlightPacket(edge) || !edge.from_agent_id || !edge.target_agent_id) return [];
    const from = positionByAgentId.get(edge.from_agent_id);
    const to = positionByAgentId.get(edge.target_agent_id);
    if (!from || !to) return [];
    return [{ key: activityPacketKey(edge), from, to, status: edge.dispatch_status, subject: edge.subject }];
  });
}
