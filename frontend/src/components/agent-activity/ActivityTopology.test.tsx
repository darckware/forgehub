import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type {
  ActivityAgent,
  ActivityMessageEdge,
  ActivityProject,
  ActivityResource,
  ActivityTopologyRelation,
} from "@/hooks/useAgentActivity";
import { ActivityTopology } from "./ActivityTopology";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const RESOURCE_ID = "database:company_postgres/company";
const REQUEST_ID = "33333333-3333-4333-8333-333333333334";

const agents = [
  {
    id: AGENT_ID,
    name: "Aramis",
    avatar_data_url: "data:image/png;base64,AA==",
    runtime_type: "codex",
    availability: "busy",
    current_work: { project_name: "ForgeHub", task_title: "Topology" },
  },
] as ActivityAgent[];

const projects = [
  { id: PROJECT_ID, name: "ForgeHub", status: "active", canonical_path: `/projects/${PROJECT_ID}` },
] satisfies ActivityProject[];

const resources = [
  { key: RESOURCE_ID, kind: "database", label: "company_postgres", detail: "company", status: "available" },
] satisfies ActivityResource[];

const relations = [
  {
    key: `current-work:${AGENT_ID}:${PROJECT_ID}`,
    kind: "current_work",
    from_type: "agent",
    from_id: AGENT_ID,
    to_type: "project",
    to_id: PROJECT_ID,
    label: "Working now",
  },
  {
    key: `persistence:${PROJECT_ID}:${RESOURCE_ID}`,
    kind: "persistence",
    from_type: "project",
    from_id: PROJECT_ID,
    to_type: "resource",
    to_id: RESOURCE_ID,
    label: "Persists in company schema",
  },
] satisfies ActivityTopologyRelation[];

function renderTopology() {
  return render(
    <ActivityTopology
      agents={agents}
      projects={projects}
      resources={resources}
      relations={relations}
      edges={[]}
      projectScopeId={null}
      selectedAgentId={null}
      onSelectAgent={vi.fn()}
      onOpenMessage={vi.fn()}
    />,
  );
}

function dispatchPointer(target: HTMLElement, type: string, x: number, y: number) {
  const event = new Event(type, { bubbles: true });
  Object.defineProperties(event, {
    pointerId: { value: 1 },
    clientX: { value: x },
    clientY: { value: y },
  });
  fireEvent(target, event);
}

describe("ActivityTopology", () => {
  beforeEach(async () => {
    localStorage.clear();
    await i18n.changeLanguage("en");
  });

  it("renders registered images, project/database objects, and textual relationships", () => {
    renderTopology();

    expect(screen.getByRole("img")).toHaveAttribute("src", agents[0].avatar_data_url);
    expect(screen.getByRole("button", { name: /Aramis.*agent.*Running/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /ForgeHub.*project.*active/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /company_postgres.*database.*available/i })).toBeVisible();
    const relationList = screen.getByRole("list", { name: /topology relationships/i });
    expect(within(relationList).getByText(/Aramis.*ForgeHub.*Working now/i)).toBeVisible();
    expect(within(relationList).getByText(/ForgeHub.*company_postgres.*Persists in company schema/i)).toBeVisible();
  });

  it("exposes the canonical Software Factory context attached to a Message", () => {
    const edge = {
      message_id: "44444444-4444-4444-8444-444444444444",
      from_agent_id: AGENT_ID,
      from_agent_name: "Aramis",
      target_agent_id: AGENT_ID,
      target_agent_name: "Aramis",
      reply_to_id: null,
      project_id: PROJECT_ID,
      development_request_id: REQUEST_ID,
      product_id: "55555555-5555-4555-8555-555555555555",
      task_id: null,
      subject: "Continue conception",
      dispatch_status: "completed",
      requires_response: false,
      response_status: null,
      waiting_for_response: false,
      waiting_on_agent_id: null,
      sent_at: "2026-08-30T12:00:00Z",
      updated_at: "2026-08-30T12:00:00Z",
      responded_at: null,
      canonical_path: "/demands?message=44444444-4444-4444-8444-444444444444",
      factory_context_path: `/conception?request=${REQUEST_ID}`,
    } satisfies ActivityMessageEdge;

    render(
      <ActivityTopology
        agents={agents}
        projects={projects}
        resources={resources}
        relations={relations}
        edges={[edge]}
        projectScopeId={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
        onOpenMessage={vi.fn()}
      />,
    );

    expect(screen.getByRole("link", { name: /open software factory context: conception/i }))
      .toHaveAttribute("href", `/conception?request=${REQUEST_ID}`);
  });

  it("moves a focused node with the keyboard and restores automatic organization", async () => {
    renderTopology();
    const projectNode = screen.getByRole("button", { name: /ForgeHub.*project.*active/i });
    const initialLeft = projectNode.style.left;

    fireEvent.keyDown(projectNode, { key: "ArrowRight" });
    expect(projectNode.style.left).not.toBe(initialLeft);
    expect(screen.getByRole("status", { name: /topology movement/i })).toHaveTextContent(/ForgeHub moved/i);
    expect(localStorage.getItem("forgehub:agent-activity:topology:v1:all")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /organize objects/i }));
    expect(projectNode.style.left).toBe(initialLeft);
    expect(localStorage.getItem("forgehub:agent-activity:topology:v1:all")).toBeNull();
  });

  it("moves a node with pointer dragging without selecting the agent", () => {
    const onSelectAgent = vi.fn();
    render(
      <ActivityTopology
        agents={agents}
        projects={projects}
        resources={resources}
        relations={relations}
        edges={[]}
        projectScopeId={null}
        selectedAgentId={null}
        onSelectAgent={onSelectAgent}
        onOpenMessage={vi.fn()}
      />,
    );
    const canvas = screen.getByTestId("topology-canvas");
    vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({
      x: 0, y: 0, left: 0, top: 0, right: 1000, bottom: 500, width: 1000, height: 500, toJSON: () => ({}),
    });
    const agentNode = screen.getByRole("button", { name: /Aramis.*agent.*Running/i });
    const initialLeft = agentNode.style.left;

    dispatchPointer(agentNode, "pointerdown", 100, 100);
    dispatchPointer(agentNode, "pointermove", 300, 160);
    dispatchPointer(agentNode, "pointerup", 300, 160);

    expect(agentNode.style.left).not.toBe(initialLeft);
    expect(onSelectAgent).not.toHaveBeenCalled();
  });
});
