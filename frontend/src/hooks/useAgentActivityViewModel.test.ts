import { describe, expect, it } from "vitest";
import type { ActivityAgent, ActivityProject, ActivityResource } from "./useAgentActivity";
import {
  clampGraphPosition,
  graphPositionStorageKey,
  layoutActivityGraph,
  mergeSavedGraphPositions,
} from "./useAgentActivityViewModel";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";

const agent = {
  id: AGENT_ID,
  name: "Aramis",
  availability: "available",
} as ActivityAgent;

const project = {
  id: PROJECT_ID,
  name: "ForgeHub",
  status: "active",
  canonical_path: `/projects/${PROJECT_ID}`,
} satisfies ActivityProject;

const resource = {
  key: "database:company_postgres/company",
  kind: "database",
  label: "company_postgres",
  detail: "company",
  status: "available",
} satisfies ActivityResource;

describe("agent activity graph layout", () => {
  it("is stable across input order and assigns semantic vertical bands", () => {
    const secondAgent = { ...agent, id: "33333333-3333-4333-8333-333333333333", name: "Athos" };
    const forward = layoutActivityGraph([agent, secondAgent], [project], [resource]);
    const reversed = layoutActivityGraph([secondAgent, agent], [project], [resource]);

    expect(forward).toEqual(reversed);
    expect(forward.find((node) => node.kind === "agent")?.yPct).toBeLessThan(50);
    expect(forward.find((node) => node.kind === "project")?.yPct).toBeGreaterThanOrEqual(54);
    expect(forward.find((node) => node.kind === "resource")?.yPct).toBeGreaterThanOrEqual(82);
  });

  it("clamps positions inside the usable canvas", () => {
    expect(clampGraphPosition({ xPct: -4, yPct: 108 })).toEqual({ xPct: 4, yPct: 94 });
  });

  it("reconciles saved positions without retaining stale or unsafe coordinates", () => {
    const nodes = layoutActivityGraph([agent], [project], [resource]);
    const merged = mergeSavedGraphPositions(nodes, {
      [`agent:${AGENT_ID}`]: { xPct: 22, yPct: 31 },
      [`project:${PROJECT_ID}`]: { xPct: Number.NaN, yPct: 70 },
      "agent:removed": { xPct: 44, yPct: 44 },
    });

    expect(merged.find((node) => node.id === `agent:${AGENT_ID}`)).toMatchObject({ xPct: 22, yPct: 31 });
    expect(merged.find((node) => node.id === `project:${PROJECT_ID}`)).toEqual(
      nodes.find((node) => node.id === `project:${PROJECT_ID}`),
    );
    expect(merged.some((node) => node.id === "agent:removed")).toBe(false);
  });

  it("scopes browser positions by the active project filter", () => {
    expect(graphPositionStorageKey(null)).toBe("forgehub:agent-activity:topology:v1:all");
    expect(graphPositionStorageKey(PROJECT_ID)).toBe(`forgehub:agent-activity:topology:v1:${PROJECT_ID}`);
  });
});
