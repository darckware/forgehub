import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import type { AgentActivity } from "@/hooks/useAgentActivity";
import AgentActivityPage from ".";

const hookMocks = vi.hoisted(() => ({
  useAgentActivity: vi.fn(),
  mutateAsync: vi.fn(),
  useReducedMotion: vi.fn(),
}));

vi.mock("framer-motion", () => ({
  motion: {
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

describe("AgentActivityPage", () => {
  beforeEach(async () => {
    localStorage.clear();
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

  it("removes packet animation while preserving its textual record for reduced motion", () => {
    hookMocks.useReducedMotion.mockReturnValue(true);
    const { container } = renderPage();

    expect(container.querySelector('[data-motion-duration="0"]')).toHaveAttribute(
      "data-motion-initial",
      "false",
    );
    expect(screen.getByRole("link", { name: /Dartan.*Athos/i })).toBeVisible();
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

  it("keeps the topology region reserved while reporting no active work", () => {
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

    expect(screen.getByRole("region", { name: /topologia operacional/i })).toHaveTextContent(
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

    expect(screen.getByRole("button", { name: /Agent Activity continuity.*Concepção.*in_review/i })).toBeVisible();
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
    expect(screen.getByRole("region", { name: /topologia operacional/i })).toBeVisible();
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
});
