import { describe, expect, it } from "vitest";
import type { ActivityAgent, ActivityContext, ActivityProject, ActivityResource } from "./useAgentActivity";
import {
  clampGraphPosition,
  graphPositionStorageKey,
  layoutActivityGraph,
  mergeSavedGraphPositions,
} from "./useAgentActivityViewModel";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const CONCEPT_ID = "44444444-4444-4444-8444-444444444444";

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

const conception = {
  context_kind: "conception",
  context_id: CONCEPT_ID,
  product_id: "55555555-5555-4555-8555-555555555555",
  product_name: "ForgeHub",
  development_request_id: "66666666-6666-4666-8666-666666666666",
  concept_id: CONCEPT_ID,
  concept_revision_id: "77777777-7777-4777-8777-777777777777",
  project_id: null,
  project_name: null,
  working_directory_path: "/root/project/forgehub",
  title: "Agent Activity continuity",
  status: "in_review",
  canonical_path: "/conception",
  created_at: "2026-08-30T12:00:00Z",
  updated_at: "2026-08-30T12:00:00Z",
} satisfies ActivityContext;

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

  it("creates a stable conception node in its own semantic band", () => {
    const nodes = layoutActivityGraph([agent], [project], [resource], [conception]);
    expect(nodes.find((node) => node.id === `conception:${CONCEPT_ID}`)).toMatchObject({
      kind: "conception",
      sourceId: CONCEPT_ID,
      label: "Agent Activity continuity",
    });
  });
});
