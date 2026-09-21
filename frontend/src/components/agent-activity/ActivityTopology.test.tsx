import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type {
  ActivityAgent,
  ActivityContext,
  ActivityMessageEdge,
  ActivityProject,
  ActivityResource,
  ActivityTopologyRelation,
} from "@/hooks/useAgentActivity";
import { ActivityTopology } from "./ActivityTopology";

const AGENT_ID = "11111111-1111-4111-8111-111111111111";
const PROJECT_ID = "22222222-2222-4222-8222-222222222222";
const RESOURCE_ID = "database:forgehub_postgres/company";
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
  { key: RESOURCE_ID, kind: "database", label: "forgehub_postgres", detail: "company", status: "available" },
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
    expect(screen.getByRole("button", { name: /forgehub_postgres.*database.*available/i })).toBeVisible();
    const relationList = screen.getByRole("list", { name: /topology relationships/i });
    expect(within(relationList).getByText(/Aramis.*ForgeHub.*Working now/i)).toBeVisible();
    expect(within(relationList).getByText(/ForgeHub.*forgehub_postgres.*Persists in company schema/i)).toBeVisible();
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

  it("shows one conception transitioning into every linked delivery project", () => {
    const conceptId = "66666666-6666-4666-8666-666666666666";
    const secondProjectId = "77777777-7777-4777-8777-777777777777";
    const contexts = [
      {
        context_kind: "conception",
        context_id: conceptId,
        product_id: "55555555-5555-4555-8555-555555555555",
        product_name: "ForgeHub",
        development_request_id: REQUEST_ID,
        concept_id: conceptId,
        concept_revision_id: "88888888-8888-4888-8888-888888888888",
        project_id: null,
        project_name: null,
        working_directory_path: "/root/project/forgehub",
        title: "Agent Activity continuity",
        status: "approved",
        canonical_path: `/conception?request=${REQUEST_ID}`,
        created_at: "2026-08-30T12:00:00Z",
        updated_at: "2026-08-30T12:00:00Z",
      },
    ] satisfies ActivityContext[];
    const deliveryProjects = [
      ...projects,
      { id: secondProjectId, name: "ForgeRouter", status: "active", canonical_path: `/projects/${secondProjectId}` },
    ] satisfies ActivityProject[];
    const transitions = deliveryProjects.map((project) => ({
      key: `transition:${conceptId}:${project.id}`,
      kind: "transition" as const,
      from_type: "conception" as const,
      from_id: conceptId,
      to_type: "project" as const,
      to_id: project.id,
      label: "Transitioned to delivery",
    }));

    render(
      <ActivityTopology
        agents={[]}
        contexts={contexts}
        projects={deliveryProjects}
        resources={[]}
        relations={transitions}
        edges={[]}
        projectScopeId={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
        onOpenMessage={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: /Agent Activity continuity.*conception.*approved/i })).toBeVisible();
    const relationList = screen.getByRole("list", { name: /topology relationships/i });
    expect(within(relationList).getByText(/Agent Activity continuity.*ForgeHub.*Transitioned to delivery/i)).toBeVisible();
    expect(within(relationList).getByText(/Agent Activity continuity.*ForgeRouter.*Transitioned to delivery/i)).toBeVisible();
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

  it("distributes entities when clicking the distribute button", () => {
    renderTopology();
    const distributeBtn = screen.getByRole("button", { name: /distribute entities/i });
    expect(distributeBtn).toBeVisible();

    fireEvent.click(distributeBtn);
    expect(screen.getByRole("status", { name: /topology movement/i })).toHaveTextContent(/distributed with optimized spacing/i);
    expect(localStorage.getItem("forgehub:agent-activity:topology:v1:all")).not.toBeNull();
  });

  it("toggles fullscreen mode when clicking the fullscreen button", () => {
    renderTopology();
    const fullscreenBtn = screen.getByRole("button", { name: /fullscreen/i });
    expect(fullscreenBtn).toBeVisible();

    fireEvent.click(fullscreenBtn);
    expect(screen.getByRole("button", { name: /exit fullscreen/i })).toBeVisible();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: /fullscreen/i })).toBeVisible();
  });

  it("marks an entity and highlights connected communicating entities", () => {
    renderTopology();
    const projectBtn = screen.getByRole("button", { name: /ForgeHub.*project/i });
    fireEvent.click(projectBtn);

    const aramisBtn = screen.getByRole("button", { name: /Aramis.*agent/i });
    expect(aramisBtn.className).toContain("scale-[1.02]");

    const canvas = screen.getByTestId("topology-canvas");
    fireEvent.click(canvas);
  });

  it("deduplicates duplicate agents in the topology", () => {
    const duplicateAgents = [
      ...agents,
      { ...agents[0], id: "duplicate-id-1", name: "Aramis" },
      { ...agents[0], id: "duplicate-id-2", name: "Aramis @ VPS" },
    ];
    render(
      <ActivityTopology
        agents={duplicateAgents}
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
    const aramisButtons = screen.getAllByRole("button", { name: /Aramis/i });
    expect(aramisButtons).toHaveLength(1);
  });

  it("animates in-flight message exchange between agents when active", () => {
    const targetAgentId = "99999999-9999-4999-8999-999999999999";
    const twoAgents = [
      ...agents,
      {
        id: targetAgentId,
        name: "Athos",
        avatar_data_url: null,
        runtime_type: "hermes",
        availability: "busy",
        current_work: null,
      } as ActivityAgent,
    ];

    const inFlightEdge: ActivityMessageEdge = {
      message_id: "edge-in-flight-1",
      from_agent_id: AGENT_ID,
      from_agent_name: "Aramis",
      target_agent_id: targetAgentId,
      target_agent_name: "Athos",
      reply_to_id: null,
      project_id: PROJECT_ID,
      development_request_id: null,
      product_id: null,
      task_id: null,
      subject: "Execute deployment check",
      dispatch_status: "running",
      requires_response: false,
      response_status: null,
      waiting_for_response: false,
      waiting_on_agent_id: null,
      sent_at: "2026-08-30T12:00:00Z",
      updated_at: "2026-08-30T12:00:00Z",
      responded_at: null,
      canonical_path: "/demands?message=edge-in-flight-1",
      factory_context_path: null,
    };

    render(
      <ActivityTopology
        agents={twoAgents}
        projects={projects}
        resources={resources}
        relations={relations}
        edges={[inFlightEdge]}
        projectScopeId={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
        onOpenMessage={vi.fn()}
      />,
    );

    expect(screen.getByTestId("active-packet-edge-in-flight-1")).toBeInTheDocument();
  });

  it("does not render moving packet animation when edge is completed or idle", () => {
    const targetAgentId = "99999999-9999-4999-8999-999999999999";
    const twoAgents = [
      ...agents,
      {
        id: targetAgentId,
        name: "Athos",
        avatar_data_url: null,
        runtime_type: "hermes",
        availability: "available",
        current_work: null,
      } as ActivityAgent,
    ];

    const completedEdge: ActivityMessageEdge = {
      message_id: "edge-completed-1",
      from_agent_id: AGENT_ID,
      from_agent_name: "Aramis",
      target_agent_id: targetAgentId,
      target_agent_name: "Athos",
      reply_to_id: null,
      project_id: PROJECT_ID,
      development_request_id: null,
      product_id: null,
      task_id: null,
      subject: "Check completed",
      dispatch_status: "completed",
      requires_response: false,
      response_status: "responded",
      waiting_for_response: false,
      waiting_on_agent_id: null,
      sent_at: "2026-08-30T12:00:00Z",
      updated_at: "2026-08-30T12:00:00Z",
      responded_at: "2026-08-30T12:05:00Z",
      canonical_path: "/demands?message=edge-completed-1",
      factory_context_path: null,
    };

    render(
      <ActivityTopology
        agents={twoAgents}
        projects={projects}
        resources={resources}
        relations={relations}
        edges={[completedEdge]}
        projectScopeId={null}
        selectedAgentId={null}
        onSelectAgent={vi.fn()}
        onOpenMessage={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("active-packet-edge-completed-1")).not.toBeInTheDocument();
  });
});
