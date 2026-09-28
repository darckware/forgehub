import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { AgentActivity } from "@/hooks/useAgentActivity";
import type { ActivityTraceViewModel } from "@/hooks/useActivityTraceViewModel";
import type { ActivityTimeline } from "@/hooks/useAgentActivityTimeline";
import AgentActivityPage from ".";

const hookMocks = vi.hoisted(() => ({
  useAgentActivity: vi.fn(),
  mutateAsync: vi.fn(),
  syncHermesAsync: vi.fn(),
  useReducedMotion: vi.fn(),
  useAgentActivityStream: vi.fn(),
  useActivityTrace: vi.fn(),
}));

vi.mock("@/hooks/useActivityTraceViewModel", () => ({
  useActivityTraceViewModel: hookMocks.useActivityTrace,
}));

vi.mock("@/hooks/useAgentActivityStreamViewModel", () => ({
  useAgentActivityStreamViewModel: hookMocks.useAgentActivityStream,
}));

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  motion: {
    li: ({ layout: _layout, transition: _transition, ...props }: React.HTMLAttributes<HTMLLIElement> & {
      layout?: unknown;
      transition?: unknown;
    }) => <li {...props} />,
    span: ({
      animate: _animate,
      initial,
      transition,
      ...props
    }: React.HTMLAttributes<HTMLSpanElement> & {
      animate?: unknown;
      initial?: unknown;
      transition?: { duration?: number };
    }) => (
      <span
        {...props}
        data-motion-duration={transition?.duration}
        data-motion-initial={String(initial)}
      />
    ),
  },
  useReducedMotion: hookMocks.useReducedMotion,
}));

vi.mock("@/hooks/useAgent", () => ({
  useSyncHermesAgents: () => ({
    mutateAsync: hookMocks.syncHermesAsync,
    isPending: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/hooks/useAgentActivity", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useAgentActivity")>();
  return {
    ...actual,
    useAgentActivity: hookMocks.useAgentActivity,
    useRequestAthosMonitoring: () => ({
      mutateAsync: hookMocks.mutateAsync,
      isPending: false,
    }),
  };
});

const IDS = {
  dartan: "11111111-1111-4111-8111-111111111111",
  athos: "22222222-2222-4222-8222-222222222222",
  project: "33333333-3333-4333-8333-333333333333",
  task: "44444444-4444-4444-8444-444444444444",
  execution: "55555555-5555-4555-8555-555555555555",
  checkpoint: "66666666-6666-4666-8666-666666666666",
  message: "77777777-7777-4777-8777-777777777777",
  incident: "88888888-8888-4888-8888-888888888888",
  timeline: "99999999-9999-4999-8999-999999999999",
} as const;

const PROFILE = {
  status: "healthy" as const,
  checked_at: "2026-08-29T17:32:18Z",
  runtime_native: true,
  canonical_path: "/profiles/runtime-native",
  profile_path: "/root/.hermes/agents/dartan",
  last_heartbeat_at: "2026-08-29T17:31:50Z",
  issues: [],
};

export const ACTIVITY_FIXTURE: AgentActivity = {
  contract_version: "forge-agent-activity/v1",
  generated_at: "2026-08-29T17:32:18Z",
  project_id: IDS.project,
  agents: [
    {
      id: IDS.dartan,
      name: "Dartan",
      avatar_data_url: "data:image/png;base64,AA==",
      profile_slug: "dartan",
      runtime_type: "runtime-native",
      availability: "degraded",
      availability_reason: "Resposta de Athos e decisão humana",
      last_heartbeat_at: "2026-08-29T17:31:50Z",
      canonical_path: `/agents/${IDS.dartan}`,
      current_work: {
        project_id: IDS.project,
        project_name: "ForgeHub",
        project_path: `/projects/${IDS.project}`,
        task_id: IDS.task,
        task_title: "Consolidar continuidade",
        task_path: `/tasks/${IDS.task}`,
        assignment_id: null,
        work_package_id: null,
        execution_id: IDS.execution,
        execution_path: `/executions/${IDS.execution}`,
        action: "Execução pausada; contexto preservado",
        branch: "feature/agent-activity-continuity",
        working_directory_path: "/root/project/forgehub",
        requested_by_agent_id: null,
        source_message_id: IDS.message,
        source_message_path: `/demands?message=${IDS.message}`,
      },
      latest_checkpoint: {
        id: IDS.checkpoint,
        execution_id: IDS.execution,
        occurred_at: "2026-08-29T17:24:06Z",
        status: "saved",
        resume_from_step_key: "step-06/09",
        summary: "CP-771 · Estado e evidências persistidos",
        evidence_summary: "Transferência de ownership pendente",
        verification_summary: "Contexto preservado",
        error_code: "EXEC_RUNTIME_502",
        blocker_code: "APR-109",
        canonical_path: `/checkpoints/${IDS.checkpoint}`,
      },
      profile_summary: PROFILE,
    },
    {
      id: IDS.athos,
      name: "Athos",
      avatar_data_url: null,
      profile_slug: "athos",
      runtime_type: "hermes",
      availability: "busy",
      availability_reason: "Avaliando continuidade de Dartan",
      last_heartbeat_at: "2026-08-29T17:32:00Z",
      canonical_path: `/agents/${IDS.athos}`,
      current_work: null,
      latest_checkpoint: null,
      profile_summary: { ...PROFILE, runtime_native: false },
    },
  ],
  contexts: [],
  projects: [
    {
      id: IDS.project,
      name: "ForgeHub",
      status: "active",
      canonical_path: `/projects/${IDS.project}`,
    },
  ],
  resources: [
    {
      key: "database:forgehub_postgres/company",
      kind: "database",
      label: "forgehub_postgres",
      detail: "company",
      status: "available",
    },
  ],
  topology_relations: [
    {
      key: `current-work:${IDS.dartan}:${IDS.project}`,
      kind: "current_work",
      from_type: "agent",
      from_id: IDS.dartan,
      to_type: "project",
      to_id: IDS.project,
      label: "Working now",
    },
    {
      key: `persistence:${IDS.project}:database:forgehub_postgres/company`,
      kind: "persistence",
      from_type: "project",
      from_id: IDS.project,
      to_type: "resource",
      to_id: "database:forgehub_postgres/company",
      label: "Persists in company schema",
    },
  ],
  flow_items: [
    {
      key: `task_execution:${IDS.execution}`,
      stage: "attention",
      source_type: "task_execution",
      source_id: IDS.execution,
      source_status: "failed",
      title: "Consolidar continuidade",
      occurred_at: "2026-08-29T17:24:06Z",
      updated_at: "2026-08-29T17:24:11Z",
      canonical_path: `/executions/${IDS.execution}`,
      agent_id: IDS.dartan,
      project_id: IDS.project,
      task_id: IDS.task,
      execution_id: IDS.execution,
    },
  ],
  message_edges: [
    {
      message_id: IDS.message,
      from_agent_id: IDS.dartan,
      from_agent_name: "Dartan",
      target_agent_id: IDS.athos,
      target_agent_name: "Athos",
      reply_to_id: null,
      project_id: IDS.project,
      development_request_id: null,
      product_id: null,
      task_id: IDS.task,
      subject: "Solicitar correção e continuidade",
      dispatch_status: "dispatched",
      requires_response: true,
      response_status: "pending",
      waiting_for_response: true,
      waiting_on_agent_id: IDS.athos,
      sent_at: "2026-08-29T17:25:00Z",
      updated_at: "2026-08-29T17:25:00Z",
      responded_at: null,
      canonical_path: `/demands?message=${IDS.message}`,
      factory_context_path: null,
    },
  ],
  incidents: [
    {
      key: "execution-failed:284",
      kind: "execution_failed",
      severity: "critical",
      title: "Falha da execução #284",
      occurred_at: "2026-08-29T17:24:11Z",
      source_type: "execution",
      source_id: IDS.incident,
      affected_agent_id: IDS.dartan,
      project_id: IDS.project,
      task_id: IDS.task,
      execution_id: IDS.execution,
      checkpoint_id: IDS.checkpoint,
      resume_from_step_key: "step-06/09",
      error_code: "EXEC_RUNTIME_502",
      blocker_code: "APR-109",
      summary: "A execução parou com contexto preservado.",
      recommended_action: "request_athos_monitoring",
      prior_attempts: [],
      last_observed_at: "2026-08-29T17:32:18Z",
      impact: "Continuidade depende de correção e decisão humana.",
      runtime_type: "runtime-native",
      provider: "ForgeRouter",
      current_owner_agent_id: IDS.dartan,
      canonical_path: `/executions/${IDS.execution}`,
      related_records: [],
    },
  ],
  timeline: [
    {
      key: "checkpoint:CP-771",
      kind: "checkpoint_saved",
      occurred_at: "2026-08-29T17:24:06Z",
      source_type: "checkpoint",
      source_id: IDS.timeline,
      source_status: "saved",
      lane: "checkpoint",
      title: "CP-771 · Checkpoint salvo",
      canonical_path: `/checkpoints/${IDS.checkpoint}`,
      summary: "Estado e evidências persistidos",
      agent_id: IDS.dartan,
      project_id: IDS.project,
      task_id: IDS.task,
      execution_id: IDS.execution,
      checkpoint_id: IDS.checkpoint,
      approval_id: null,
      notification_id: null,
      related_records: [],
    },
  ],
  source_freshness: [
    {
      name: "messages",
      status: "fresh",
      checked_at: "2026-08-29T17:32:18Z",
      observed_at: "2026-08-29T17:32:00Z",
      age_seconds: 18,
      detail: null,
      error_code: null,
    },
  ],
};

function renderPage(activity: AgentActivity = ACTIVITY_FIXTURE) {
  hookMocks.useAgentActivity.mockReturnValue({
    data: activity,
    isLoading: false,
    isError: false,
    error: null,
  });
  return render(<AgentActivityPage />);
}

function traceVM(overrides: Partial<ActivityTraceViewModel> = {}): ActivityTraceViewModel {
  return {
    status: "ready",
    preset: "2h",
    customRange: { start: "2026-08-29T13:00", end: "2026-08-29T15:00" },
    rangeError: null,
    window: { start: "2026-08-29T13:00:00Z", end: "2026-08-29T15:00:00Z" },
    windowStartMs: Date.parse("2026-08-29T13:00:00Z"),
    windowEndMs: Date.parse("2026-08-29T15:00:00Z"),
    timeline: null,
    isFetching: false,
    cursor: null,
    playing: false,
    replaySnapshot: null,
    replayLoading: false,
    selectedBlock: null,
    setPreset: vi.fn(),
    setCustomRange: vi.fn(),
    setCursor: vi.fn(),
    backToLive: vi.fn(),
    togglePlay: vi.fn(),
    selectBlock: vi.fn(),
    ...overrides,
  };
}

describe("AgentActivityPage", () => {
  beforeEach(async () => {
    localStorage.clear();
    // These cases exercise the constellation view; live cards have their own cases below.
    localStorage.setItem("forgehub:agent-activity:main:v1", "constellation");
    // The pre-phase-4 operational views (flow/history); lanes/events have their own cases.
    localStorage.setItem("forgehub:agent-activity:view:v1", "flow");
    hookMocks.useActivityTrace.mockReset();
    hookMocks.useActivityTrace.mockReturnValue(traceVM());
    hookMocks.useAgentActivityStream.mockReset();
    hookMocks.useAgentActivityStream.mockReturnValue({ status: "idle", snapshot: null, receivedAt: null, attempts: 0 });
    hookMocks.useAgentActivity.mockReset();
    hookMocks.mutateAsync.mockReset();
    hookMocks.useReducedMotion.mockReset();
    hookMocks.useReducedMotion.mockReturnValue(false);
    await i18n.changeLanguage("pt-BR");
  });

  it("selects an agent and exposes waits, checkpoint, and authorization", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /Dartan/i }));

    expect(screen.getByText(/Resposta de Athos e decisão humana/i)).toBeVisible();
    expect(screen.getAllByText(/CP-771/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Transferência de ownership pendente/i)).toBeVisible();
  });

  it("exposes the selected agent's canonical work context", () => {
    renderPage();
    const inspector = screen.getByRole("region", { name: "Dartan" });

    expect(within(inspector).getByRole("link", { name: "ForgeHub" })).toHaveAttribute(
      "href",
      `/projects/${IDS.project}`,
    );
    expect(within(inspector).getByRole("link", { name: IDS.execution })).toHaveAttribute(
      "href",
      `/executions/${IDS.execution}`,
    );
    expect(within(inspector).getByText("feature/agent-activity-continuity")).toBeVisible();
    expect(within(inspector).getByText("/root/project/forgehub")).toBeVisible();
  });

  it("confirms the exact context before requesting Athos monitoring", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /solicitar monitoramento ao Athos/i }));

    expect(screen.getByRole("dialog")).toHaveTextContent("EXEC_RUNTIME_502");
    expect(screen.getByRole("dialog")).toHaveTextContent("#284");
  });

  it("exposes canonical message and timeline records as links", () => {
    renderPage();

    expect(screen.getByRole("link", { name: /Dartan.*Athos/i })).toHaveAttribute(
      "href",
      `/demands?message=${IDS.message}`,
    );
    fireEvent.click(screen.getByRole("tab", { name: /Histórico/i }));
    const timeline = screen.getByRole("region", { name: /timeline de continuidade/i });
    expect(within(timeline).getByRole("link", { name: /CP-771/i })).toHaveAttribute(
      "href",
      `/checkpoints/${IDS.checkpoint}`,
    );
  });

  it("reports record availability honestly across request states", () => {
    hookMocks.useAgentActivity.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    });
    const { rerender } = render(<AgentActivityPage />);
    expect(screen.getByText(/carregando registros/i)).toBeVisible();
    expect(screen.queryByText(/^Registros ao vivo$/i)).not.toBeInTheDocument();

    hookMocks.useAgentActivity.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("network"),
    });
    rerender(<AgentActivityPage />);
    expect(screen.getByText(/registros indisponíveis/i)).toBeVisible();
    expect(screen.queryByText(/^Registros ao vivo$/i)).not.toBeInTheDocument();

    hookMocks.useAgentActivity.mockReturnValue({
      data: {
        ...ACTIVITY_FIXTURE,
        source_freshness: [
          {
            ...ACTIVITY_FIXTURE.source_freshness[0],
            status: "stale",
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
    });
    rerender(<AgentActivityPage />);
    expect(screen.getByText(/registros com defasagem/i)).toBeVisible();
    expect(screen.queryByText(/^Registros ao vivo$/i)).not.toBeInTheDocument();
  });

  it("closes monitoring with Escape and restores focus to its trigger", () => {
    renderPage();
    const trigger = screen.getByRole("button", { name: /solicitar monitoramento ao Athos/i });

    trigger.focus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(screen.getByRole("button", { name: /^Cancelar$/i })).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("keeps keyboard focus inside the monitoring dialog", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /solicitar monitoramento ao Athos/i }));

    const dialog = screen.getByRole("dialog");
    const close = screen.getByRole("button", { name: /fechar solicitação de monitoramento/i });
    const confirm = screen.getByRole("button", { name: /^Confirmar solicitação$/i });
    close.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();

    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(close).toHaveFocus();
  });

  it("makes the background inert while monitoring confirmation is open", () => {
    const { container } = renderPage();
    fireEvent.click(screen.getByRole("button", { name: /solicitar monitoramento ao Athos/i }));

    expect(screen.getByRole("dialog")).toBeVisible();
    expect(container).toHaveAttribute("inert");
    expect(document.body).toHaveStyle({ overflow: "hidden" });

    fireEvent.click(screen.getByRole("button", { name: /^Cancelar$/i }));
    expect(container).not.toHaveAttribute("inert");
    expect(document.body).not.toHaveStyle({ overflow: "hidden" });
  });

  it("orders timeline records by their actual instant across UTC offsets", () => {
    renderPage({
      ...ACTIVITY_FIXTURE,
      timeline: [
        {
          ...ACTIVITY_FIXTURE.timeline[0],
          key: "later-instant",
          source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
          title: "Evento posterior",
          occurred_at: "2026-08-29T10:30:00-03:00",
        },
        {
          ...ACTIVITY_FIXTURE.timeline[0],
          key: "earlier-instant",
          source_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
          title: "Evento anterior",
          occurred_at: "2026-08-29T13:00:00Z",
        },
      ],
    });

    fireEvent.click(screen.getByRole("tab", { name: /Histórico/i }));
    const timeline = screen.getByRole("region", { name: /timeline de continuidade/i });
    expect(within(timeline).getAllByRole("link").map((link) => link.textContent)).toEqual([
      expect.stringContaining("Evento anterior"),
      expect.stringContaining("Evento posterior"),
    ]);
  });

  it("announces timeline records related to the selected agent without relying on color", () => {
    renderPage();

    fireEvent.click(screen.getByRole("tab", { name: /Histórico/i }));
    const timeline = screen.getByRole("region", { name: /timeline de continuidade/i });
    expect(within(timeline).getByRole("link", { name: /CP-771.*agente selecionado/i })).toBeVisible();
  });

  it("removes the travelling particles while preserving the textual records for reduced motion", () => {
    const activeLink = {
      key: "message:dartan:athos", kind: "message" as const, source_type: "agent" as const,
      source_agent_id: IDS.dartan, target_agent_id: IDS.athos, channel: "messages", active: true,
      last_at: new Date().toISOString(), count: 1, message_number: 284,
    };
    hookMocks.useAgentActivityStream.mockReturnValue({
      status: "live", receivedAt: Date.now(), attempts: 0,
      snapshot: {
        generated_at: new Date().toISOString(),
        agents: [],
        links: [activeLink],
        pulse: {
          agents_total: 2, agents_reporting: 0, agents_active: 0, agents_in_turn: 0, agents_degraded: 0,
          turns_last_hour: 0, tools_last_hour: 0, failures_last_hour: 0, pending_total: 0,
          llm_calls_last_hour: null, tokens_last_hour: null, cost_today: null, turns_per_minute: [],
        },
      },
    });
    const { unmount } = renderPage();
    expect(screen.getAllByTestId("constellation-particle").length).toBeGreaterThan(0);
    unmount();

    hookMocks.useReducedMotion.mockReturnValue(true);
    renderPage();
    expect(screen.queryByTestId("constellation-particle")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Dartan.*Athos/i })).toBeVisible();
    expect(screen.getByRole("list", { name: /interações recentes/i })).toHaveTextContent("Dartan → Athos");
  });

  it("orders the incident inbox by severity before recency", () => {
    renderPage({
      ...ACTIVITY_FIXTURE,
      incidents: [
        {
          ...ACTIVITY_FIXTURE.incidents[0],
          key: "approval-pending:newer",
          kind: "approval_pending",
          severity: "warning",
          title: "Aprovação recente",
          occurred_at: "2026-08-29T17:31:00Z",
          execution_id: null,
          recommended_action: "open_approval",
        },
        {
          ...ACTIVITY_FIXTURE.incidents[0],
          occurred_at: "2026-08-29T17:24:11Z",
        },
      ],
    });

    const inbox = screen.getByRole("region", { name: /caixa de severidade/i });
    expect(within(inbox).getAllByRole("button")[0]).toHaveTextContent("Falha da execução #284");
  });

  it("keeps the constellation region reserved while reporting no active work", () => {
    renderPage({
      ...ACTIVITY_FIXTURE,
      agents: [],
      projects: [],
      resources: [],
      topology_relations: [],
      flow_items: [],
      message_edges: [],
      incidents: [],
      timeline: [],
    });

    expect(screen.getByRole("region", { name: /constelação de atividade/i })).toHaveTextContent(
      /nenhum trabalho ativo/i,
    );
  });

  it("renders a pre-project conception and switches between current flow and history", () => {
    const conceptId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const conceptionActivity = {
      ...ACTIVITY_FIXTURE,
      project_id: null,
      projects: [],
      contexts: [{
        context_kind: "conception",
        context_id: conceptId,
        product_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        product_name: "ForgeHub",
        development_request_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        concept_id: conceptId,
        concept_revision_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        project_id: null,
        project_name: null,
        working_directory_path: "/root/project/forgehub",
        title: "Agent Activity continuity",
        status: "in_review",
        canonical_path: "/conception",
        created_at: "2026-08-30T12:00:00Z",
        updated_at: "2026-08-30T12:00:00Z",
      }],
      flow_items: [{
        ...ACTIVITY_FIXTURE.flow_items[0],
        key: `product_concept:${conceptId}`,
        context_kind: "conception",
        context_id: conceptId,
        concept_id: conceptId,
        concept_revision_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        source_type: "product_concept",
        source_id: conceptId,
        source_status: "in_review",
        title: "Agent Activity continuity",
        stage: "attention",
        project_id: null,
      }],
    } as AgentActivity;

    renderPage(conceptionActivity);

    const flowPanel = screen.getByRole("tabpanel", { name: /Fluxo atual/i });
    expect(flowPanel).toHaveTextContent("Agent Activity continuity");
    expect(flowPanel).toHaveTextContent("Concepção");
    fireEvent.click(screen.getByRole("tab", { name: /Histórico/i }));
    expect(screen.getByRole("tabpanel", { name: /Histórico/i })).toBeVisible();
  });

  it("distinguishes request failure from optional source degradation", () => {
    hookMocks.useAgentActivity.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("network"),
    });
    const { rerender } = render(<AgentActivityPage />);
    expect(screen.getByRole("alert")).toHaveTextContent(/não foi possível carregar/i);

    hookMocks.useAgentActivity.mockReturnValue({
      data: {
        ...ACTIVITY_FIXTURE,
        source_freshness: [
          {
            name: "notifications",
            status: "unavailable",
            checked_at: "2026-08-29T17:32:18Z",
            observed_at: null,
            age_seconds: null,
            detail: "Notifications fora do ar",
            error_code: "SOURCE_UNAVAILABLE",
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
    });
    rerender(<AgentActivityPage />);
    expect(screen.getByText(/fonte opcional indisponível/i)).toBeVisible();
  });

  it("reports stale source data without treating the page as failed", () => {
    renderPage({
      ...ACTIVITY_FIXTURE,
      source_freshness: [
        {
          name: "messages",
          status: "stale",
          checked_at: "2026-08-29T17:32:18Z",
          observed_at: "2026-08-29T16:32:18Z",
          age_seconds: 3600,
          detail: "Última leitura há uma hora",
          error_code: null,
        },
      ],
    });

    const sourceHealth = screen.getByRole("status", { name: /estado das fontes/i });
    expect(within(sourceHealth).getByText(/dados desatualizados/i)).toBeVisible();
    expect(screen.getByRole("region", { name: /constelação de atividade/i })).toBeVisible();
  });

  it("keeps a failed monitoring request recoverable in the dialog", async () => {
    hookMocks.mutateAsync.mockRejectedValue(new Error("request failed"));
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /solicitar monitoramento ao Athos/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Confirmar solicitação$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/monitoramento não foi solicitado/i);
    expect(screen.getByRole("dialog")).toBeVisible();
  });

  it("announces when the monitoring request is created", async () => {
    hookMocks.mutateAsync.mockResolvedValue({
      message_id: IDS.message,
      message_number: 4832,
      notification_id: IDS.timeline,
      created: true,
    });
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: /solicitar monitoramento ao Athos/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Confirmar solicitação$/i }));

    expect(await screen.findByText(/solicitação de monitoramento criada/i)).toHaveAttribute("role", "status");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("renders the sync agents button and triggers synchronization when clicked", async () => {
    hookMocks.syncHermesAsync.mockResolvedValue({});
    renderPage();

    const syncButton = screen.getByRole("button", { name: /atualizar agentes/i });
    expect(syncButton).toBeVisible();

    fireEvent.click(syncButton);
    expect(hookMocks.syncHermesAsync).toHaveBeenCalled();
  });

  it("filters severity inbox by selected agent and toggles showing all", () => {
    renderPage();
    const inbox = screen.getByRole("region", { name: /caixa de severidade/i });
    expect(within(inbox).getByText("Dartan")).toBeInTheDocument();

    const showAllLink = within(inbox).getByRole("link", { name: /ver todos/i });
    fireEvent.click(showAllLink);
    expect(within(inbox).getByText("Dartan")).toBeInTheDocument();
  });

  it("allows deselecting agent from the inspector", () => {
    renderPage();
    const deselectButton = screen.getByRole("button", { name: /desmarcar agente/i });
    fireEvent.click(deselectButton);

    expect(screen.getByText(/selecione um agente nos cartões ou na constelação/i)).toBeInTheDocument();
  });
});

describe("AgentActivityPage live stream (phase 2)", () => {
  const ARAMIS_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const LIVE_BASE = {
    since: new Date(Date.now() - 42_000).toISOString(),
    source: "runtime" as const,
    platform: "telegram",
    counterpart_kind: "owner" as const,
    counterpart_ref: null,
    model: "claude-sonnet",
    tool_name: "terminal",
    session_id: "s1",
    turn_id: "t1",
    last_event_at: new Date().toISOString(),
    reason: null,
    message_number: null,
    turns_last_hour: 3,
    tools_last_hour: 7,
    failures_last_hour: 0,
    pending_count: 0,
  };
  const PULSE = {
    agents_total: 2, agents_reporting: 1, agents_active: 1, agents_in_turn: 1, agents_degraded: 0,
    turns_last_hour: 3, tools_last_hour: 7, failures_last_hour: 0, pending_total: 0,
    llm_calls_last_hour: 12, tokens_last_hour: 45000, cost_today: 1.5, turns_per_minute: Array(60).fill(0),
  };
  const withExternal: AgentActivity = {
    ...ACTIVITY_FIXTURE,
    agents: [
      ...ACTIVITY_FIXTURE.agents,
      { ...ACTIVITY_FIXTURE.agents[1], id: ARAMIS_ID, name: "Aramis", profile_slug: "aramis", runtime_type: "codex" },
    ],
  };

  function stream(agents: Array<{ agent_id: string; live: unknown }>) {
    hookMocks.useAgentActivityStream.mockReturnValue({
      status: "live",
      receivedAt: Date.now(),
      attempts: 0,
      snapshot: {
        generated_at: new Date().toISOString(),
        pulse: PULSE,
        agents: agents.map((item) => ({ ...item, spark: Array(12).fill(1), tokens_last_hour: 45000, cost_today: 1.5 })),
      },
    });
  }

  beforeEach(async () => {
    localStorage.clear();
    hookMocks.useAgentActivity.mockReset();
    hookMocks.useActivityTrace.mockReset();
    hookMocks.useActivityTrace.mockReturnValue(traceVM());
    hookMocks.useReducedMotion.mockReturnValue(false);
    await i18n.changeLanguage("pt-BR");
  });

  it("defaults to live cards showing what each agent is doing, plus the pulse", () => {
    stream([{ agent_id: IDS.athos, live: { ...LIVE_BASE, state: "executing" } }]);
    renderPage(withExternal);
    const cards = screen.getByTestId("live-agent-cards");
    expect(within(cards).getByText(/executando terminal · 4\d s/i)).toBeInTheDocument();
    expect(within(cards).getByText("Você · Telegram")).toBeInTheDocument();
    expect(screen.getByTestId("activity-pulse")).toHaveTextContent("1/2");
    expect(screen.getByTestId("activity-stream-status")).toHaveTextContent(/ao vivo/i);
  });

  it("hides an idle external executor and shows it while Messages runs it", () => {
    stream([{ agent_id: IDS.athos, live: { ...LIVE_BASE, state: "idle" } }]);
    const { unmount } = renderPage(withExternal);
    expect(within(screen.getByTestId("live-agent-cards")).queryByText("Aramis")).not.toBeInTheDocument();
    unmount();

    stream([
      { agent_id: IDS.athos, live: { ...LIVE_BASE, state: "idle" } },
      {
        agent_id: ARAMIS_ID,
        live: { ...LIVE_BASE, state: "executing", source: "messages", platform: "messages",
                counterpart_kind: "agent", tool_name: null, message_number: 9123 },
      },
    ]);
    renderPage(withExternal);
    const cards = screen.getByTestId("live-agent-cards");
    expect(within(cards).getByText("Aramis")).toBeInTheDocument();
    expect(within(cards).getByText(/executando mensagem #9123/i)).toBeInTheDocument();
  });

  it("shows the reconnecting state of the stream", () => {
    hookMocks.useAgentActivityStream.mockReturnValue({ status: "reconnecting", snapshot: null, receivedAt: null, attempts: 1 });
    renderPage();
    expect(screen.getByTestId("activity-stream-status")).toHaveTextContent(/reconectando/i);
  });
});

describe("AgentActivityPage traceability (phase 4)", () => {
  const T = (minute: number) => new Date(Date.parse("2026-08-29T14:00:00Z") + minute * 60_000).toISOString();
  const TIMELINE: ActivityTimeline = {
    start: "2026-08-29T13:00:00Z",
    end: "2026-08-29T15:00:00Z",
    generated_at: "2026-08-29T15:00:00Z",
    truncated: false,
    lanes: [
      {
        agent_id: IDS.athos,
        blocks: [
          {
            key: "turn:athos:t1", kind: "turn", start: T(0), end: T(5), platform: "telegram",
            counterpart_kind: "owner", counterpart_ref: null, counterpart_agent_id: null, model: "m",
            status: "completed", error_type: null, session_id: "s1", turn_id: "t1", message_number: null,
            tools: [{ start: T(1), end: T(2), tool_name: "terminal", status: "ok", duration_ms: 60_000 }],
            canonical_path: `/agents/${IDS.athos}`,
          },
        ],
      },
      {
        agent_id: IDS.dartan,
        blocks: [
          {
            key: "dispatch:m1", kind: "dispatch", start: T(10), end: T(20), platform: "messages",
            counterpart_kind: "agent", counterpart_ref: null, counterpart_agent_id: IDS.athos, model: null,
            status: "completed", error_type: null, session_id: null, turn_id: null, message_number: 9001,
            tools: [], canonical_path: `/demands?message=${IDS.message}`,
          },
        ],
      },
    ],
    messages: [
      { id: IDS.message, number: 9001, at: T(9), from_agent_id: IDS.athos, target_agent_id: IDS.dartan,
        subject: "handoff", canonical_path: `/demands?message=${IDS.message}` },
    ],
    events: [
      { key: "runtime:2", occurred_at: T(5), agent_id: IDS.athos, profile: "athos", source: "runtime", kind: "turn_ended",
        platform: "telegram", counterpart_kind: null, counterpart_ref: null, model: null, tool_name: null,
        status: "failed", error_type: "provider_error", duration_ms: null, session_id: "s1", turn_id: "t1",
        message_number: null, canonical_path: `/agents/${IDS.athos}` },
      { key: "runtime:1", occurred_at: T(1), agent_id: IDS.athos, profile: "athos", source: "runtime", kind: "tool_started",
        platform: "telegram", counterpart_kind: null, counterpart_ref: null, model: null, tool_name: "terminal",
        status: null, error_type: null, duration_ms: null, session_id: "s1", turn_id: "t1",
        message_number: null, canonical_path: `/agents/${IDS.athos}` },
    ],
  };

  beforeEach(async () => {
    localStorage.clear();
    hookMocks.useAgentActivity.mockReset();
    hookMocks.useAgentActivityStream.mockReturnValue({ status: "live", snapshot: null, receivedAt: null, attempts: 0 });
    hookMocks.useReducedMotion.mockReturnValue(false);
    await i18n.changeLanguage("pt-BR");
  });

  it("opens on the lanes: turns, tools, dispatches and messages between agents", () => {
    const selectBlock = vi.fn();
    const trace = traceVM({ timeline: TIMELINE, selectBlock });
    hookMocks.useActivityTrace.mockReturnValue(trace);
    renderPage();
    const lanes = screen.getByRole("region", { name: "Raias" });
    const turn = within(lanes).getByRole("button", { name: /Você · Telegram/ });
    expect(turn).toHaveAttribute("aria-label", expect.stringMatching(/5 min$/));
    expect(within(lanes).getByRole("button", { name: /Mensagem #9001 de Athos/ })).toBeInTheDocument();
    expect(within(lanes).getByRole("button", { name: /Mensagem #9001: Athos → Dartan/ })).toBeInTheDocument();
    fireEvent.click(turn);
    expect(selectBlock).toHaveBeenCalledWith(IDS.athos, TIMELINE.lanes[0].blocks[0]);
  });

  it("shows a block's detail with its tools and canonical record", () => {
    const setCursor = vi.fn();
    hookMocks.useActivityTrace.mockReturnValue(
      traceVM({ timeline: TIMELINE, setCursor, selectedBlock: { agentId: IDS.athos, block: TIMELINE.lanes[0].blocks[0] } }),
    );
    renderPage();
    const detail = screen.getByRole("region", { name: "Detalhe" });
    expect(detail).toHaveTextContent("terminal");
    expect(detail).toHaveTextContent("Concluído");
    fireEvent.click(within(detail).getByRole("button", { name: /Reproduzir daqui/ }));
    expect(setCursor).toHaveBeenCalledWith(Date.parse(T(0)));
    expect(within(detail).getByRole("button", { name: /Abrir agente/ })).toBeInTheDocument();
  });

  it("lists the events, filters failures, and moves the cursor on a row click", () => {
    localStorage.setItem("forgehub:agent-activity:view:v1", "events");
    const setCursor = vi.fn();
    hookMocks.useActivityTrace.mockReturnValue(traceVM({ timeline: TIMELINE, setCursor }));
    renderPage();
    const table = screen.getByRole("region", { name: "Eventos" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    fireEvent.click(within(table).getByRole("radio", { name: "Falhas" }));
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toHaveTextContent("provider_error");
    fireEvent.click(rows[1]);
    expect(setCursor).toHaveBeenCalledWith(Date.parse(T(5)));
  });

  it("replays: the pulse and cards use the past frame, with a way back to live", () => {
    localStorage.setItem("forgehub:agent-activity:main:v1", "cards");
    const backToLive = vi.fn();
    hookMocks.useActivityTrace.mockReturnValue(traceVM({
      timeline: TIMELINE,
      cursor: Date.parse(T(1)),
      backToLive,
      replaySnapshot: {
        generated_at: T(1),
        links: [],
        pulse: {
          agents_total: 2, agents_reporting: 2, agents_active: 1, agents_in_turn: 1, agents_degraded: 0,
          turns_last_hour: 1, tools_last_hour: 1, failures_last_hour: 0, pending_total: 0,
          llm_calls_last_hour: null, tokens_last_hour: null, cost_today: null, turns_per_minute: Array(60).fill(0),
        },
        agents: [{
          agent_id: IDS.athos, spark: Array(12).fill(0), tokens_last_hour: 0, cost_today: 0,
          live: {
            state: "executing", since: T(1), source: "runtime", platform: "telegram", counterpart_kind: "owner",
            counterpart_ref: null, model: "m", tool_name: "terminal", session_id: "s1", turn_id: "t1",
            last_event_at: T(1), reason: null, message_number: null, turns_last_hour: 1, tools_last_hour: 1,
            failures_last_hour: 0, pending_count: 0,
          },
        }],
      },
    }));
    renderPage();
    expect(screen.getByText(/Replay de/)).toBeInTheDocument();
    expect(within(screen.getByTestId("live-agent-cards")).getByText(/executando terminal/i)).toBeInTheDocument();
    fireEvent.click(within(screen.getByText(/Replay de/).closest("[role=status]") as HTMLElement).getByRole("button", { name: /Ao vivo/ }));
    expect(backToLive).toHaveBeenCalled();
  });
});

describe("AgentActivityPage runtime alerts (phase 5)", () => {
  beforeEach(async () => {
    localStorage.clear();
    hookMocks.useAgentActivity.mockReset();
    hookMocks.useActivityTrace.mockReturnValue(traceVM());
    hookMocks.useAgentActivityStream.mockReturnValue({ status: "live", snapshot: null, receivedAt: null, attempts: 0 });
    hookMocks.useReducedMotion.mockReturnValue(false);
    await i18n.changeLanguage("pt-BR");
  });

  it("lists a hung turn and a fatal Telegram adapter, critical first", () => {
    const base = ACTIVITY_FIXTURE.incidents[0];
    const runtimeAlert = (overrides: Partial<typeof base>) => ({
      ...base,
      execution_id: null, task_id: null, checkpoint_id: null, prior_attempts: [], related_records: [],
      recommended_action: "open_agent" as const,
      affected_agent_id: IDS.athos, canonical_path: `/agents/${IDS.athos}`,
      ...overrides,
    });
    renderPage({
      ...ACTIVITY_FIXTURE,
      incidents: [
        runtimeAlert({ key: "turn_stuck:a", kind: "turn_stuck", severity: "warning", title: "Athos: turn with no end for 12 min",
                       error_code: "turn_stuck", occurred_at: "2026-08-29T17:31:00Z" }),
        runtimeAlert({ key: "adapter_fatal:a", kind: "adapter_fatal", severity: "critical", title: "Athos: Telegram channel fatal",
                       error_code: "telegram_fatal", occurred_at: "2026-08-29T17:00:00Z" }),
      ],
    } as AgentActivity);
    const inbox = screen.getByRole("region", { name: /Caixa de severidade|Severidade|Incidentes/i });
    const items = within(inbox).getAllByRole("button").filter((button) => /Athos:/.test(button.textContent ?? ""));
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining("Telegram channel fatal"),
      expect.stringContaining("turn with no end"),
    ]);
  });
});
