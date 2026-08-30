import type { ActivityAgent, ActivityMessageEdge } from "./useAgentActivity";

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
