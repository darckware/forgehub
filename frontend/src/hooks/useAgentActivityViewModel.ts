import type {
  ActivityAgent,
  ActivityMessageEdge,
  ActivityProject,
  ActivityResource,
} from "./useAgentActivity";

export type ActivityGraphNodeKind = "agent" | "project" | "resource";

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
  const columns = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(records.length * 1.6))));
  const rows = Math.ceil(records.length / columns);
  return records.map((record, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    return {
      id: graphNodeId(kind, record.sourceId),
      sourceId: record.sourceId,
      kind,
      label: record.label,
      xPct: roundPercent(((column + 1) * 100) / (Math.min(columns, records.length) + 1)),
      yPct: roundPercent(rows === 1 ? (top + bottom) / 2 : top + (row * (bottom - top)) / (rows - 1)),
    };
  });
}

export function layoutActivityGraph(
  agents: readonly ActivityAgent[],
  projects: readonly ActivityProject[],
  resources: readonly ActivityResource[],
): ActivityGraphNode[] {
  const orderedAgents = [...agents]
    .sort((left, right) => left.id.localeCompare(right.id))
    .map((agent) => ({ sourceId: agent.id, label: agent.name }));
  const orderedProjects = [...projects]
    .sort((left, right) => left.id.localeCompare(right.id))
    .map((project) => ({ sourceId: project.id, label: project.name }));
  const orderedResources = [...resources]
    .sort((left, right) => left.key.localeCompare(right.key))
    .map((resource) => ({ sourceId: resource.key, label: resource.label }));

  return [
    ...layoutBand(orderedAgents, "agent", 12, 44),
    ...layoutBand(orderedProjects, "project", 54, 72),
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
  const orderedAgents = [...agents].sort((left, right) => left.id.localeCompare(right.id));
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
