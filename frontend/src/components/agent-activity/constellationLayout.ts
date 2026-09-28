/**
 * Deterministic radial layout for the agent constellation (Agent Activity, phase 3).
 *
 * Same input, same picture -- no force simulation, nothing random, nothing for the viewer
 * to drag. People and systems sit on fixed outer points, agents on an inner ellipse in name
 * order, and the orchestrator (Athos) in the centre, because most traffic goes through it.
 * Coordinates are in a 1000x760 viewBox; the component renders nodes as HTML placed by
 * percentage over an SVG of the same box. The ring size was chosen (by search, see the
 * layout test) so 1 to 12 ring agents plus the outer nodes never overlap with 96 px nodes
 * at a ~770 px wide panel -- the desktop width of this view.
 */

export const VIEWBOX = { width: 1000, height: 760 } as const;
export const CENTER = { x: 500, y: 380 };
export const AGENT_RING = { rx: 310, ry: 250 };

export type OuterNodeKind = "owner" | "human" | "system" | "forgerouter";

export interface ConstellationPoint {
  x: number;
  y: number;
}

/** Fixed homes of the outer nodes: you on top, outside contacts left, the ecosystem right. */
export const OUTER_POINTS: Record<OuterNodeKind, ConstellationPoint> = {
  owner: { x: 500, y: 26 },
  human: { x: 60, y: 380 },
  system: { x: 940, y: 380 },
  forgerouter: { x: 500, y: 734 },
};

export const ORCHESTRATOR_SLUG = "athos";

export function layoutAgents(
  agents: ReadonlyArray<{ id: string; name: string; profile_slug: string | null }>,
): Map<string, ConstellationPoint> {
  const positions = new Map<string, ConstellationPoint>();
  const center = agents.find((agent) => agent.profile_slug?.toLowerCase() === ORCHESTRATOR_SLUG);
  if (center) positions.set(center.id, { ...CENTER });
  const ring = agents
    .filter((agent) => agent !== center)
    .sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
  ring.forEach((agent, index) => {
    // Clockwise from just past the top, offset by half a step so no agent sits right under
    // "You" (top) or over ForgeRouter (bottom); a single agent still sits on the ring.
    const step = (2 * Math.PI) / Math.max(ring.length, 1);
    const angle = -Math.PI / 2 + step / 2 + step * index;
    positions.set(agent.id, {
      x: Math.round(CENTER.x + AGENT_RING.rx * Math.cos(angle)),
      y: Math.round(CENTER.y + AGENT_RING.ry * Math.sin(angle)),
    });
  });
  return positions;
}

/**
 * Quadratic curve between two nodes. Agent-to-agent curves bow toward the centre (inside the
 * ring); outer-to-agent curves bow away from it (outside the ring). Either way a line runs
 * through the empty space on its side of the ring instead of over the agents on it.
 */
export function linkPath(from: ConstellationPoint, to: ConstellationPoint, bowToCenter: boolean) {
  const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
  let control: ConstellationPoint;
  if (bowToCenter) {
    control = { x: mid.x + (CENTER.x - mid.x) * 0.45, y: mid.y + (CENTER.y - mid.y) * 0.45 };
  } else {
    control = { x: mid.x + (mid.x - CENTER.x) * 0.45, y: mid.y + (mid.y - CENTER.y) * 0.45 };
  }
  // Point at t = 0.5 on the quadratic curve: where the channel badge goes.
  const badge = {
    x: 0.25 * from.x + 0.5 * control.x + 0.25 * to.x,
    y: 0.25 * from.y + 0.5 * control.y + 0.25 * to.y,
  };
  return { d: `M ${from.x} ${from.y} Q ${control.x} ${control.y} ${to.x} ${to.y}`, badge };
}

/** 1 while active, then fading to a faint trace over the link window. */
export function linkOpacity(active: boolean, lastAt: string, now: number, windowMs = 5 * 60_000): number {
  if (active) return 1;
  const age = Math.max(0, now - Date.parse(lastAt));
  return Math.max(0.15, 1 - age / windowMs);
}

export function toPercent(point: ConstellationPoint) {
  return { left: `${(point.x / VIEWBOX.width) * 100}%`, top: `${(point.y / VIEWBOX.height) * 100}%` };
}
