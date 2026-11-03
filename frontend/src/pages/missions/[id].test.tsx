import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { ApiError, apiClient } from "@/lib/api";
import { missionBoard, missionTask } from "@/test/fixtures/missionBoard";
import MissionDetailPage from "./[id]";

function viewport(phone: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: phone && query.includes("max-width"), media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/missions/m07-mission"]}>
        <Routes><Route path="/missions/:projectId" element={<MissionDetailPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockGet(board: unknown) {
  vi.spyOn(apiClient, "get").mockImplementation(async (path: string) => {
    if (path.endsWith("/timeline")) return { items: [], next_before: null };
    if (board instanceof Error) throw board;
    return board;
  });
}

beforeEach(async () => {
  await i18n.changeLanguage("pt-BR");
  viewport(false);
});
afterEach(() => vi.restoreAllMocks());

describe("mission executions page (M0.7)", () => {
  it("shows a skeleton while loading", () => {
    vi.spyOn(apiClient, "get").mockReturnValue(new Promise(() => {}));
    open();
    expect(screen.getByTestId("board-loading")).toBeInTheDocument();
  });

  it.each([[404, "not_found", "Missão não encontrada."], [403, "forbidden", "Você não tem permissão para ver missões."],
    [500, "server", "Erro ao carregar a missão."]])("renders HTTP %s as %s", async (code, kind, text) => {
    mockGet(new ApiError("x", code, {}));
    open();
    expect(await screen.findByTestId(`board-error-${kind}`)).toHaveTextContent(text);
    if (kind === "server") expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeInTheDocument();
  });

  it("renders an empty plan with a link to Planejamento", async () => {
    mockGet(missionBoard({ tasks: [], conflicts: [] }));
    open();
    expect(await screen.findByText(/Plano sem tarefas/)).toBeInTheDocument();
  });

  it("renders the seven points at 1440 px: order, people, state+timer, evidence, conflicts, environments, actions", async () => {
    mockGet(missionBoard());
    open();
    const table = await screen.findByTestId("task-table");
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("9001");
    expect(rows[2]).toHaveTextContent("9002");
    expect(rows[2]).toHaveTextContent("#9001 ✓");
    expect(rows[2]).toHaveTextContent("Revisor = executor");
    expect(rows[2]).toHaveTextContent("Rodando");
    expect(rows[2]).toHaveTextContent("21m de 45m");
    expect(rows[2]).toHaveTextContent("contexto desatualizado");
    expect(rows[2]).toHaveTextContent("python ✓/✗");
    expect(within(rows[2]).getByLabelText("verified")).toBeInTheDocument();
    expect(screen.getByTestId("conflicts-banner")).toHaveTextContent("1 conflito");
    expect(screen.getByTestId("conflicts-banner")).toHaveTextContent("mesmo worktree");
    const strip = screen.getByTestId("environments-strip");
    expect(strip).toHaveTextContent("6e8fce4");
    expect(strip).toHaveTextContent("produção forgehub · sem registro");
    expect(screen.getByRole("button", { name: "Pausar" })).toBeEnabled();

    fireEvent.click(rows[2]);
    const detail = await screen.findByTestId("task-detail");
    // Blocked actions show the backend's reason, never a click-through.
    const dispatch = within(detail).getByRole("button", { name: "Despachar agora" });
    expect(dispatch).toBeDisabled();
    expect(dispatch).toHaveAttribute("title", "Bloqueada: TASK_RUN_IN_FLIGHT");
    expect(within(detail).getByRole("button", { name: "Pedir revisão" })).toHaveAttribute("title", "Bloqueada: REVIEWER_IS_EXECUTOR");
  });

  it("switches to the dependency graph and opens a task from it", async () => {
    mockGet(missionBoard());
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Grafo" }));
    const graph = screen.getByTestId("task-graph");
    expect(graph).toHaveTextContent("#9001");
    expect(graph).toHaveTextContent("#9002");
    expect(within(graph).getByTestId("graph-task-t-running")).toHaveTextContent("#9001");
    fireEvent.click(within(graph).getByRole("button", { name: /9002/ }));
    expect(await screen.findByTestId("task-detail")).toHaveTextContent("9002");
    fireEvent.click(screen.getByRole("button", { name: "Lista" }));
    expect(screen.getByTestId("task-table")).toBeInTheDocument();
  });

  it("asks a reason before returning, disables the button while pending and keeps the backend's refusal", async () => {
    mockGet(missionBoard({ tasks: [missionTask({ allowed_actions: ["return"], blocked_actions: [],
      execution: { ...missionBoard().tasks[1].execution! } })] }));
    let reject: (e: unknown) => void = () => {};
    const post = vi.spyOn(apiClient, "post").mockImplementation(() => new Promise((_, r) => { reject = r; }));
    open();
    fireEvent.click(await screen.findByTestId("task-row-t-ready"));
    fireEvent.click(within(await screen.findByTestId("task-detail")).getByRole("button", { name: "Recusar / devolver" }));
    // Modal policy: the reason is typed on the page; the modal only confirms.
    expect(screen.queryByRole("dialog")).toBeNull();
    const form = screen.getByTestId("mission-action-form");
    const review = within(form).getByRole("button", { name: "Revisar: Recusar / devolver" });
    expect(review).toBeDisabled();
    fireEvent.change(within(form).getByLabelText("Motivo"), { target: { value: "sem teste" } });
    expect(review).toBeEnabled();
    fireEvent.click(review);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("textbox")).toBeNull();
    expect(dialog).toHaveTextContent("sem teste");
    const confirm = within(dialog).getByRole("button", { name: "Recusar / devolver" });
    fireEvent.click(confirm);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/m07-mission/tasks/t-ready:return",
      expect.objectContaining({ reason: "sem teste", execution_id: "e-2" })));
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Recusar / devolver" })).toBeDisabled());
    reject(new ApiError("x", 409, { detail: { code: "TASK_RUN_IN_FLIGHT", message: "run active" } }));
    expect(await within(dialog).findByText("TASK_RUN_IN_FLIGHT: run active")).toBeInTheDocument();
    expect(within(form).getByLabelText("Motivo")).toHaveValue("sem teste");
  });

  it("is read-only for a viewer who cannot act", async () => {
    mockGet(missionBoard({ viewer: { principal_type: "user", is_admin: false, can_act: false } }));
    open();
    expect(await screen.findByText(/Somente leitura/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Pausar" })).toBeNull();
  });

  it("renders the planning pipeline with pending decisions", async () => {
    mockGet(missionBoard({
      tasks: [], mission: { ...missionBoard().mission, state: "planning", planning_stage: "consolidation", baseline: null },
      planning: {
        stages: ["draft_plan", "auto_check", "critical_review", "consolidation", "cross_review", "decisions", "application", "baseline"],
        current: "consolidation", status: "ok", unmet: [{ code: "ITEM_WITHOUT_DISPOSITION", message: "item sem disposição" }],
        not_evaluated: [], layers: [{ layer: "security", reviewed: false, waived: false }], reviews: [],
        items: [{ item_id: "i-1", text: "Falta rollback", origin: "security", disposition: null, reason: null, needs_decision: true, decision: null }],
        pending_decisions: [{ item_id: "i-1", text: "Falta rollback", origin: "security", disposition: null, reason: null,
          needs_decision: true, decision: null, can_decide: false, blocked_reason: "STAGE_DOES_NOT_DECIDE" }],
      },
    }));
    open();
    const view = await screen.findByTestId("planning-view");
    expect(view).toHaveTextContent("P4 Consolidação");
    expect(view).toHaveTextContent("ITEM_WITHOUT_DISPOSITION");
    expect(view).toHaveTextContent("security: faltando");
    expect(within(view).getByRole("button", { name: "Decidir" })).toBeDisabled();
  });

  it("shows cards at 390 px and the detail full-width with a back bar", async () => {
    viewport(true);
    mockGet(missionBoard());
    open();
    expect(await screen.findByTestId("task-cards")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("task-card-t-running"));
    const detail = await screen.findByTestId("task-detail");
    expect(screen.queryByTestId("task-cards")).toBeNull();
    fireEvent.click(within(detail).getByRole("button", { name: /Voltar às tarefas/ }));
    expect(await screen.findByTestId("task-cards")).toBeInTheDocument();
  });

  it("keeps the dependency view when returning from a task on a phone", async () => {
    viewport(true);
    mockGet(missionBoard());
    open();
    fireEvent.click(await screen.findByRole("button", { name: "Grafo" }));
    fireEvent.click(within(screen.getByTestId("task-graph")).getByRole("button", { name: /9002/ }));
    const detail = await screen.findByTestId("task-detail");
    expect(screen.queryByTestId("task-graph")).toBeNull();
    fireEvent.click(within(detail).getByRole("button", { name: /Voltar às tarefas/ }));
    expect(screen.getByTestId("task-graph")).toBeInTheDocument();
  });

  it("has every missions key in pt-BR, en and es", async () => {
    const flatten = (obj: Record<string, unknown>, prefix = ""): string[] => Object.entries(obj).flatMap(([k, v]) =>
      v && typeof v === "object" ? flatten(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`]);
    const keys = ["pt-BR", "en", "es"].map((lng) => flatten(i18n.getResourceBundle(lng, "missions")).sort());
    expect(keys[1]).toEqual(keys[0]);
    expect(keys[2]).toEqual(keys[0]);
    expect(keys[0].length).toBeGreaterThan(100);
  });
});
