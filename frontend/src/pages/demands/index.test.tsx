import { fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import "@/i18n";
import { demandSchema } from "@/hooks/useDemands";
import DemandsPage from "./index";

const state = vi.hoisted(() => ({ rows: [] as unknown[] }));
vi.mock("@/hooks/useDemands", async importOriginal => ({
  ...await importOriginal<typeof import("@/hooks/useDemands")>(),
  useDemands: () => ({ data: state.rows, isLoading: false, refetch: vi.fn() }),
  useDemandGroups: () => ({ data: [] }),
  useDispatchStatus: () => ({ data: null }),
}));
vi.mock("@/hooks/useAgent", () => ({ useAgents: () => ({ data: [{ id: "athos", name: "Athos", is_active: true }] }) }));
vi.mock("@/hooks/useProject", () => ({ useProjects: () => ({ data: [] }) }));
vi.mock("@/hooks/useAssistant", () => ({ useAssistantContext: () => {} }));
vi.mock("@/components/AgentCommsGraph", () => ({ AgentCommsGraph: () => null }));
vi.mock("@/components/DemandsStatsPanel", () => ({ DemandsStatsPanel: () => null }));
vi.mock("@/components/DemandsControlPanel", () => ({ DemandsControlPanel: () => null }));

it("keeps a failed attempt in execution, exposes its reason and recovery, then moves an accepted completion", () => {
  const item = demandSchema.parse({
    id: "attempt", number: 42, from_agent: "Dartan", subject: "Revisão de teste", body: "Revisar a entrega",
    status: "read", group_id: null, converted_entity_type: null, converted_reference: null,
    created_at: "2026-10-29T10:00:00Z", updated_at: "2026-10-29T10:00:00Z",
    target_agent_id: "dartan", from_agent_id: "athos", project_id: null, command_text: null,
    origin_type: "task", origin_id: null, dispatch_result: "Trabalho parcial", reply_to_id: null,
    requires_response: false, scheduled_at: null, agent_processed_at: null,
    task_execution_at: null, dispatch_status: "failed", agent_run_id: "run", dispatch_attempts: 1,
    dispatch_error: "The agent reported STATUS: PARTIAL; the work is not finished.",
  });
  state.rows = [item];
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={["/demands?message=42"]}>{children}</MemoryRouter></QueryClientProvider>;
  const view = render(<DemandsPage />, { wrapper });
  fireEvent.click(screen.getByRole("button", { name: /^Execução/ }));
  expect(screen.queryByRole("button", { name: /^Falhas/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Dartan.*Aguardando correção/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Dartan.*Aguardando correção/ }));
  expect(screen.getByText(item.dispatch_error!)).toBeInTheDocument();
  expect(screen.getByText("Trabalho parcial")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Clean up Execução" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reprocess all in Execução" })).toBeInTheDocument();
  state.rows = [{ ...item, dispatch_status: "completed", dispatch_error: null }];
  view.rerender(<DemandsPage />);
  expect(screen.queryByRole("button", { name: /Dartan.*Aguardando correção/ })).not.toBeInTheDocument();
});

it("opens the right-side label legend with keyboard dismissal and restores focus", () => {
  state.rows = [];
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><DemandsPage /></MemoryRouter></QueryClientProvider>);
  const opener = screen.getByRole("button", { name: "Legenda das etiquetas" }); opener.focus(); fireEvent.click(opener);
  const dialog = screen.getByRole("dialog", { name: "Legenda das etiquetas" });
  expect(dialog).toHaveAttribute("data-placement", "right");
  expect(within(dialog).getByRole("heading", { name: "Execução" })).toBeInTheDocument();
  expect(within(dialog).getByText("Aguardando executor")).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Fechar" })).toHaveFocus();
  fireEvent.keyDown(dialog, { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
});

function labelItem(overrides: Record<string, unknown> = {}) {
  return demandSchema.parse({ id: "waiting", number: 71, from_agent: "Athos", subject: "Aguardar a janela", body: "Conteúdo autorizado",
    status: "read", group_id: null, converted_entity_type: null, converted_reference: null,
    created_at: "2026-11-09T10:00:00Z", updated_at: "2026-11-09T10:00:00Z", target_agent_id: "athos", from_agent_id: "athos",
    project_id: null, command_text: null, origin_type: "task", origin_id: null, dispatch_result: null, reply_to_id: null,
    requires_response: false, scheduled_at: null, agent_processed_at: null, task_execution_at: null, dispatch_status: null,
    agent_run_id: null, dispatch_attempts: 0, dispatch_error: null, ...overrides });
}
function openLabels() {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><DemandsPage /></MemoryRouter></QueryClientProvider>);
}
it("keeps executor waits only in the existing Execution folder with tags in row and reading pane", () => {
  state.rows = [labelItem({ message_labels: ["awaiting_executor", "quota_unavailable"], execution_wait_reason: "quota", classification_summary: "A autorização está preservada; aguardando cota." })];
  openLabels();
  const execution = screen.getByRole("button", { name: /^Execução/ });
  expect(execution).toHaveTextContent("1");
  expect(screen.getByRole("button", { name: /^Entrada/ })).not.toHaveTextContent("1");
  expect(screen.getByRole("button", { name: /^Saída/ })).not.toHaveTextContent("1");
  fireEvent.click(execution);
  const row = screen.getByRole("button", { name: /Athos.*Aguardando executor.*Sem cota disponível/ });
  fireEvent.click(row);
  expect(screen.getAllByText("Sem cota disponível")).toHaveLength(2);
  expect(screen.getByText("A autorização está preservada; aguardando cota.")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Pessoal/ })).not.toBeInTheDocument();
  expect(screen.queryByText("Aguardando sua autorização")).not.toBeInTheDocument();
});
it.each([
  ["agent_tasks", "Pessoal · Tarefas dos agentes", "workGroup=tasks"],
  ["incubations", "Pessoal · Incubações", "workGroup=incubation"],
  ["moodle_approvals", "Pessoal · Tarefas dos agentes · Aprovações Moodle", "workGroup=moodle"],
])("links genuine authorization to %s from row and reading pane", (destination, label, query) => {
  state.rows = [labelItem({ message_labels: ["authorization_pending"], operator_destination: destination, operator_decision: "authorization" })];
  openLabels(); fireEvent.click(screen.getByRole("button", { name: /^Entrada/ }));
  fireEvent.click(screen.getByRole("button", { name: /^Athos/ }));
  expect(screen.getByRole("link", { name: label })).toHaveAttribute("href", expect.stringContaining(query));
  fireEvent.click(screen.getByRole("button", { name: /Athos.*Aguardando sua autorização/ }));
  expect(screen.getAllByRole("link", { name: label })).toHaveLength(2);
});
