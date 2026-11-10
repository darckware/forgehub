import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { Demand } from "@/hooks/useDemands";
import { AgentTasksTab } from "./AgentTasksTab";

const mocks = vi.hoisted(() => ({ demands: vi.fn(), post: vi.fn(), approvals: vi.fn(), questions: vi.fn(), answerQuestion: vi.fn() }));
vi.mock("@/hooks/useDemands", async importOriginal => ({ ...await importOriginal<object>(), useAgentWork: mocks.demands }));
vi.mock("@/hooks/useAgent", () => ({ useAgents: () => ({ data: [] }), useStreamTelegramImprovePrompt: () => vi.fn() }));
vi.mock("@/hooks/useProject", () => ({ useProjects: () => ({ data: [] }) }));
vi.mock("@/hooks/useTask", () => ({ useTasks: () => ({ data: [] }), useTaskDependencies: () => ({ data: [] }) }));
vi.mock("@/hooks/useGovernance", () => ({
  useGovernedApprovalRequests: mocks.approvals,
  useDecideGovernedApproval: () => ({ reset: vi.fn() }),
}));
vi.mock("@/hooks/useOperationsViewModel", () => ({ useOperationsViewModel: () => ({ questions: mocks.questions(), answerQuestion: { reset: vi.fn(), mutate: mocks.answerQuestion } }) }));
vi.mock("@/components/Markdown", () => ({ Markdown: ({ content }: { content: string }) => <div>{content}</div> }));

function item(overrides: Partial<Demand> = {}): Demand {
  return {
    id: "work-1", number: 42, subject: "Revisar backup", body: "Verificar a evidência antes de executar",
    from_agent: "Athos", status: "new", origin_type: "task", origin_id: null,
    target_agent_id: "agent-1", requires_approval: true, approval_status: "pending", dispatch_status: null,
    dispatch_attempts: 0, dispatch_error: null, context_area: "Backup", project_id: null, agent_run_id: null,
    matures_at: null, updated_at: "2026-10-20T00:00:00Z", allowed_actions: ["approve", "reject", "archive", "delete"], ...overrides,
  } as Demand;
}

function open(entry = "/personal?tab=agent-work") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[entry]}><AgentTasksTab /></MemoryRouter></QueryClientProvider>);
}

beforeEach(async () => {
  await i18n.changeLanguage("pt-BR");
  mocks.approvals.mockReturnValue({ data: [] }); mocks.questions.mockReturnValue({ data: [] });
  mocks.demands.mockReturnValue({ data: { items: [item()], total: 1, page: 1, page_size: 25, counts: {}, contexts: [] }, isLoading: false, isError: false });
  mocks.post.mockReset(); mocks.post.mockResolvedValue({});
  vi.spyOn(apiClient, "post").mockImplementation(mocks.post);
  vi.spyOn(apiClient, "get").mockResolvedValue([]);
});

describe("operator deliberation", () => {
  it("defaults incubations to operator decisions while preserving promotion", () => {
    mocks.demands.mockReturnValue({ data: { items: [item({ origin_type: "incubation" })], total: 1, page: 1, counts: {}, contexts: [] } });
    open(); fireEvent.click(screen.getByRole("tab", { name: "Incubações" }));
    expect(mocks.demands).toHaveBeenLastCalledWith(expect.objectContaining({ group: "incubation", view: "decision" }), true);
    expect((screen.getByRole("combobox", { name: "Situação" }) as HTMLSelectElement).value).toBe("decision");
    expect(screen.getByRole("option", { name: "Em tratamento" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Precisam de atenção" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    expect(screen.getByRole("button", { name: "Transformar em tarefa" })).toBeInTheDocument();
  });
  it("shows and answers the exact blocking question in incubation and Moodle destinations", () => {
    const question = { id: "question-42", number: 42, agent_id: "agent-1", agent_name: "Athos", relay_agent_id: null,
      relay_agent_name: null, question: "Which destination should I use?", context: "Current task", recommendation: null,
      blocking: true, urgent: false, status: "pending", notify_after: "2026-11-09T00:00:00Z", telegram_sent_at: null,
      telegram_error: null, answer: null, answered_at: null, answered_via: null, answered_by: null, reply_demand_id: null,
      origin_demand_id: "work-1", created_at: "2026-11-09T00:00:00Z" };
    mocks.questions.mockReturnValue({ data: [question], isLoading: false, isError: false });
    open("/personal?tab=agent-work&workGroup=incubation&incubationView=decision&questionId=question-42");
    const questionCard = screen.getByText("Which destination should I use?").closest("section");
    expect(questionCard).toHaveAttribute("id", "operator-question-question-42");
    expect(within(questionCard!).getByRole("button", { name: "Responder" })).toBeInTheDocument();
  });
  it("keeps the question answer path visible in Moodle approvals", () => {
    mocks.questions.mockReturnValue({ data: [{ id: "question-43", number: 43, agent_id: "agent-1", agent_name: "Athos",
      question: "Confirm the Moodle scope?", blocking: true, status: "pending", origin_demand_id: "work-1", created_at: "2026-11-09T00:00:00Z" }], isLoading: false, isError: false });
    open("/personal?tab=agent-work&workGroup=moodle&questionId=question-43");
    const questionCard = screen.getByText("Confirm the Moodle scope?").closest("section");
    expect(questionCard).toHaveAttribute("id", "operator-question-question-43");
    const trigger = within(questionCard!).getByRole("button", { name: "Responder" });
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "Use o ambiente de teste" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Responder" }));
    expect(mocks.answerQuestion).toHaveBeenCalledWith({ id: "question-43", answer: "Use o ambiente de teste" }, expect.anything());
  });
  it("preserves explicit legacy incubation URLs", () => {
    open("/personal?tab=agent-work&workGroup=incubation&incubationView=attention");
    expect(mocks.demands).toHaveBeenLastCalledWith(expect.objectContaining({ group: "incubation", view: "attention" }), true);
    expect((screen.getByRole("combobox", { name: "Situação" }) as HTMLSelectElement).value).toBe("attention");
  });
  it("uses readable instructor context labels without changing filter identity", () => {
    mocks.demands.mockReturnValue({ data: { items: [item()], total: 1, page: 1, counts: {}, contexts: [{ project_id: null, area: "instructor:bcaa8b44-418a-493d-a55b-f80aa3dbf79f" }] } });
    open();
    const option = screen.getByRole("option", { name: "Contexto de instrutor" });
    expect(option).toHaveValue("area:instructor:bcaa8b44-418a-493d-a55b-f80aa3dbf79f");
    expect(screen.queryByText(/bcaa8b44/)).not.toBeInTheDocument();
  });
  it("defaults to operator decisions", () => {
    open();
    expect(mocks.demands).toHaveBeenLastCalledWith(expect.objectContaining({ view: "decision" }), true);
    expect(screen.getByRole("button", { name: "Analisar e encaminhar" })).toBeInTheDocument();
  });
  it("analyzes all pending work beyond page/search/date filters", async () => {
    mocks.post.mockResolvedValue({ id: "job-1", status: "queued", total: 90, processed: 0, applied: 0 });
    open("/personal?tab=agent-work&workAgent=agent-7&workContext=area:Backup&workPage=3&workSearch=backup&workFrom=2026-11-01");
    const button = screen.getByRole("button", { name: "Analisar e encaminhar" });
    await waitFor(() => expect(button).toBeEnabled()); fireEvent.click(button);
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/v1/demands/agent-work/analyze", { agent_id: "agent-7", context: "area:Backup" }));
    expect(button).toBeDisabled();
  });
  it("recovers running progress and prevents duplicate starts", async () => {
    vi.mocked(apiClient.get).mockImplementation(async url => url.includes("/analysis") ? { id: "job-1", status: "running", total: 90, processed: 26, applied: 8 } : []);
    open(); expect(await screen.findByText(/26 de 90/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analisar e encaminhar" })).toBeDisabled();
  });
  it("shows provider failure while keeping approvals available", async () => {
    vi.mocked(apiClient.get).mockImplementation(async url => url.includes("/analysis") ? { id: "job-1", status: "failed", total: 90, processed: 26, applied: 8, error: "Provider unavailable" } : []);
    open(); expect(await screen.findByText("Provider unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analisar e encaminhar" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    expect(screen.getByRole("button", { name: "Aprovar e liberar" })).toBeInTheDocument();
  });
  it("polls the durable job until completion and then releases the action", async () => {
    let polls = 0;
    vi.mocked(apiClient.get).mockImplementation(async url => {
      if (url.endsWith("/analysis")) return { id: "poll-job", status: "running", total: 90, processed: 26, applied: 8 };
      if (url.endsWith("/analysis/poll-job")) return { id: "poll-job", status: ++polls > 1 ? "completed" : "running", total: 90, processed: polls > 1 ? 90 : 26, applied: 8 };
      return [];
    });
    open(); expect(await screen.findByText(/26 de 90/)).toBeInTheDocument();
    expect(await screen.findByText(/Análise concluída · 90 de 90/, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(polls).toBe(2);
    expect(screen.getByRole("button", { name: "Analisar e encaminhar" })).toBeEnabled();
  });
  it("refreshes work after analysis completes and reports an empty scope honestly", async () => {
    const invalidate = vi.spyOn(QueryClient.prototype, "invalidateQueries");
    vi.mocked(apiClient.get).mockImplementation(async url => url.includes("/analysis") ? { id: "empty-job", status: "completed", total: 0, processed: 0, applied: 0 } : []);
    open(); expect(await screen.findByText(/Análise concluída · 0 de 0/)).toBeInTheDocument();
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["demands"] })));
  });
  it("shows an unavailable analysis service without suppressing operator decisions", async () => {
    vi.mocked(apiClient.get).mockImplementation(async url => { if (url.includes("/analysis")) throw new Error("503"); return []; });
    open(); expect(await screen.findByText(/Análise indisponível/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analisar e encaminhar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Revisar backup/ })).toBeInTheDocument();
  });
  it("presents a readable source and recommendation for waiting work", () => {
    mocks.demands.mockReturnValue({ data: { items: [item({ operator_state: "waiting", display_context: "CoreTI · Atendimento", analysis: { summary: "A execução aguarda capacidade", reason: "Janela indisponível", recommendation: "Aguardar a próxima janela" }, dispatch_status: "failed", requires_approval: false, allowed_actions: ["archive"] } as Partial<Demand>)], total: 1, page: 1, counts: {}, contexts: [] } });
    open(); expect(screen.getByText("CoreTI · Atendimento")).toBeInTheDocument();
    expect(screen.getByText("Aguardar a próxima janela")).toBeInTheDocument();
    expect(screen.getByText("Janela indisponível")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Aguardando")).toBeInTheDocument();
  });
  it("does not report zero decisions when their sources cannot load", () => {
    mocks.approvals.mockReturnValue({ isError: true }); mocks.questions.mockReturnValue({ isLoading: true });
    open();
    expect(screen.queryByText("Conclusões para revisar (0)")).not.toBeInTheDocument();
    expect(screen.queryByText("Perguntas para responder (0)")).not.toBeInTheDocument();
  });

  it("links a promoted task by identity regardless of whether it has already left the queue", async () => {
    mocks.demands.mockReturnValue({ data: { items: [item({ origin_type: "incubation" })], total: 1, page: 1, page_size: 25, counts: {}, contexts: [] } });
    open(); fireEvent.click(screen.getByRole("tab", { name: "Incubações" }));
    fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    fireEvent.click(screen.getByRole("button", { name: "Transformar em tarefa" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Transformar em tarefa" }));
    expect(await screen.findByRole("link", { name: /Ver tarefa #42/ })).toHaveAttribute("href", "/demands?message=work-1");
  });
  it("separates Moodle, incubations and tasks using server group filters", async () => {
    open();
    expect(mocks.demands).toHaveBeenLastCalledWith(expect.objectContaining({ group: "tasks" }), expect.any(Boolean));
    fireEvent.click(screen.getByRole("tab", { name: "Incubações" }));
    expect(mocks.demands).toHaveBeenLastCalledWith(expect.objectContaining({ group: "incubation" }), true);
    fireEvent.click(screen.getByRole("tab", { name: "Aprovações Moodle" }));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Aprovações Moodle" })).toBeInTheDocument();
  });

  it("offers archive on the task row before opening its details", async () => {
    open();
    fireEvent.click(screen.getByRole("checkbox", { name: "Selecionar mensagem #42" }));
    fireEvent.click(screen.getByRole("button", { name: "Arquivar tarefa #42" }));
    expect(mocks.post).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Arquivar" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/v1/demands/work-1/decision", expect.objectContaining({ action: "archive" })));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Selecionar mensagem #42" })).not.toBeChecked());
  });

  it("calls incubation promotion Transformar em tarefa and explains that it queues work", () => {
    mocks.demands.mockReturnValue({ data: { items: [item({ origin_type: "incubation" })], total: 1, page: 1, page_size: 25, counts: {}, contexts: [] } });
    open();
    fireEvent.click(screen.getByRole("tab", { name: "Incubações" }));
    fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    fireEvent.click(screen.getByRole("button", { name: "Transformar em tarefa" }));
    expect(within(screen.getByRole("dialog")).getByText(/entrará na fila/)).toBeInTheDocument();
  });
  it("shows pending work and excludes archived history from attention", () => {
    // The server returns only the selected lifecycle view.
    open();
    expect(within(screen.getByRole("table")).getByText("Aguardando sua decisão")).toBeInTheDocument();
    expect(screen.queryByText("Histórico antigo")).not.toBeInTheDocument();
  });

  it("requires confirmation before releasing the selected content", async () => {
    open(); fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    fireEvent.click(screen.getByRole("button", { name: "Aprovar e liberar" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/autorizando o conteúdo atual/)).toBeInTheDocument();
    expect(mocks.post).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Aprovar e liberar" }));
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/v1/demands/work-1/decision", expect.objectContaining({ action: "approve", expected_updated_at: "2026-10-20T00:00:00Z" })));
  });

  it("requires a reason when rejecting and preserves it on failure", async () => {
    mocks.post.mockRejectedValue(new Error("Conflito: a tarefa mudou"));
    open(); fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    fireEvent.click(screen.getByRole("button", { name: "Reprovar" }));
    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Reprovar" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Motivo ou comentário"), { target: { value: "Falta evidência de restauração" } });
    fireEvent.click(confirm);
    await screen.findByText("Conflito: a tarefa mudou");
    expect(within(dialog).getByLabelText("Motivo ou comentário")).toHaveValue("Falta evidência de restauração");
  });

  it("does not offer deletion or retries for uncertain execution", () => {
    mocks.demands.mockReturnValue({ data: { items: [item({ dispatch_status: "failed", dispatch_error: "Dispatch outcome is uncertain", agent_run_id: "known-run", allowed_actions: ["reconcile", "archive"] } as Partial<Demand>)], total: 1, page: 1, page_size: 25, counts: {}, contexts: [] } });
    open(); fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    expect(screen.getByRole("button", { name: "Reconciliar execução" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Excluir" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tentar novamente" })).not.toBeInTheDocument();
  });

  it("confirms an uncertain run inactive only with evidence and the run identifier typed back", async () => {
    mocks.demands.mockReturnValue({ data: { items: [item({ dispatch_status: "failed", dispatch_error: "Dispatch outcome is uncertain", agent_run_id: "run-7", allowed_actions: ["reconcile", "record_investigation", "confirm_inactive"] } as Partial<Demand>)], total: 1, page: 1, page_size: 25, counts: {}, contexts: [] } });
    open(); fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar execução inativa" }));
    const dialog = screen.getByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Confirmar execução inativa" });
    fireEvent.change(within(dialog).getByLabelText("Motivo ou comentário"), { target: { value: "Processo ausente no host" } });
    fireEvent.change(within(dialog).getByLabelText("Referência da evidência"), { target: { value: "ps aux 11:40" } });
    const typed = within(dialog).getByLabelText(/Digite o identificador/);
    fireEvent.change(typed, { target: { value: "run-8" } });
    expect(confirm).toBeDisabled();
    fireEvent.change(typed, { target: { value: "run-7" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/v1/demands/work-1/decision", expect.objectContaining({ action: "confirm_inactive", confirmation: "run-7", evidence_ref: "ps aux 11:40" })));
  });

  it("offers an explicit authorization after the retry budget is exhausted", () => {
    mocks.demands.mockReturnValue({ data: { items: [item({ dispatch_status: "failed", dispatch_error: "Known failure", dispatch_attempts: 3, retry_limit: 3, allowed_actions: ["authorize_retry", "archive", "delete"] } as Partial<Demand>)], total: 1, page: 1, page_size: 25, counts: {}, contexts: [] } });
    open(); fireEvent.click(screen.getByRole("button", { name: /Revisar backup/ }));
    expect(screen.getByRole("button", { name: "Autorizar nova tentativa" })).toBeInTheDocument();
  });

  it("exposes server filters and confirms only the selected page items", async () => {
    mocks.post.mockResolvedValue({ results: [{ id: "work-1", status: "blocked", detail: "Execution active" }] });
    open();
    expect(screen.getByLabelText("Agente responsável")).toBeInTheDocument();
    expect(screen.getByLabelText("Criadas a partir de")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Selecionar página" }));
    fireEvent.click(screen.getByRole("button", { name: "Arquivar selecionadas" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Arquivar selecionadas" }));
    await screen.findByText(/Execution active/);
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/demands/agent-work/bulk", expect.objectContaining({ action: "archive", items: [{ id: "work-1", updated_at: "2026-10-20T00:00:00Z" }] }));
  });
});
