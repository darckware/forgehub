import { describe, expect, it } from "vitest";
import { OUTER_POINTS, layoutAgents, linkOpacity, linkPath } from "./constellationLayout";

const NAMES = ["Aegis", "Athos", "Atlas", "Daedalus", "Hephaestus", "Kairos", "Lara", "Mnemosyne", "Scriba", "Themis", "Porthus", "Aramis", "Dartan"];
const AGENTS = NAMES.map((name, index) => ({
  id: `00000000-0000-4000-8000-${String(index).padStart(12, "0")}`,
  name,
  profile_slug: name.toLowerCase(),
}));

describe("layoutAgents", () => {
  it("puts the orchestrator in the centre and is deterministic regardless of input order", () => {
    const first = layoutAgents(AGENTS);
    const shuffled = layoutAgents([...AGENTS].reverse());
    expect(first.get(AGENTS[1].id)).toEqual({ x: 500, y: 380 });
    for (const agent of AGENTS) expect(shuffled.get(agent.id)).toEqual(first.get(agent.id));
  });

  it("never overlaps nodes for 1 to 12 ring agents plus the outer nodes", () => {
    // A 96 px node (avatar, name, state line ~76 px tall) in a ~770 px wide panel is about
    // 125 x 100 viewBox units: two nodes may be close on one axis only if apart on the other.
    for (let count = 2; count <= AGENTS.length; count += 1) {
      const points = [...layoutAgents(AGENTS.slice(0, count)).values(), ...Object.values(OUTER_POINTS)];
      for (let i = 0; i < points.length; i += 1) {
        for (let j = i + 1; j < points.length; j += 1) {
          const dx = Math.abs(points[i].x - points[j].x);
          const dy = Math.abs(points[i].y - points[j].y);
          expect(dx >= 125 || dy >= 100, `${count} agents: node ${i} vs ${j}`).toBe(true);
        }
      }
    }
  });
});

describe("links", () => {
  it("curves agent chords toward the centre and puts the badge on the curve", () => {
    const { d, badge } = linkPath({ x: 200, y: 380 }, { x: 800, y: 380 }, true);
    expect(d).toBe("M 200 380 Q 500 380 800 380");
    expect(badge).toEqual({ x: 500, y: 380 });
  });

  it("bows outer-to-agent lines outside the ring", () => {
    const { badge } = linkPath({ x: 500, y: 26 }, { x: 790, y: 268 }, false);
    const straightMid = { x: 645, y: 147 };
    // The curve's midpoint lies farther from the centre than the straight line's.
    const dist = (p: { x: number; y: number }) => Math.hypot(p.x - 500, p.y - 380);
    expect(dist(badge)).toBeGreaterThan(dist(straightMid));
  });

  it("fades a finished interaction but keeps a faint trace", () => {
    const now = Date.parse("2026-09-28T12:05:00Z");
    expect(linkOpacity(true, "2026-09-28T12:00:00Z", now)).toBe(1);
    expect(linkOpacity(false, "2026-09-28T12:02:30Z", now)).toBeCloseTo(0.5);
    expect(linkOpacity(false, "2026-09-28T11:00:00Z", now)).toBe(0.15);
  });
});
