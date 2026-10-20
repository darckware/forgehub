import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { Demand } from "@/hooks/useDemands";
import { AgentTasksTab } from "./AgentTasksTab";

const mocks = vi.hoisted(() => ({ demands: vi.fn(), post: vi.fn() }));
vi.mock("@/hooks/useDemands", async importOriginal => ({ ...await importOriginal<object>(), useAgentWork: mocks.demands }));
vi.mock("@/hooks/useAgent", () => ({ useAgents: () => ({ data: [] }) }));
vi.mock("@/hooks/useProject", () => ({ useProjects: () => ({ data: [] }) }));
vi.mock("@/hooks/useTask", () => ({ useTasks: () => ({ data: [] }), useTaskDependencies: () => ({ data: [] }) }));
vi.mock("@/hooks/useGovernance", () => ({
  useGovernedApprovalRequests: () => ({ data: [] }),
  useDecideGovernedApproval: () => ({ reset: vi.fn() }),
}));
vi.mock("@/hooks/useOperationsViewModel", () => ({ useOperationsViewModel: () => ({ questions: { data: [] }, answerQuestion: { reset: vi.fn() } }) }));
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

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/personal?tab=agent-work"]}><AgentTasksTab /></MemoryRouter></QueryClientProvider>);
}

beforeEach(async () => {
  await i18n.changeLanguage("pt-BR");
  mocks.demands.mockReturnValue({ data: { items: [item()], total: 1, page: 1, page_size: 25, counts: {}, contexts: [] }, isLoading: false, isError: false });
  mocks.post.mockReset(); mocks.post.mockResolvedValue({});
  vi.spyOn(apiClient, "post").mockImplementation(mocks.post);
  vi.spyOn(apiClient, "get").mockResolvedValue([]);
});

describe("operator deliberation", () => {
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
