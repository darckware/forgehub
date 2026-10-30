import { fireEvent, render, screen } from "@testing-library/react";
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
vi.mock("@/hooks/useAgent", () => ({ useAgents: () => ({ data: [] }) }));
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
  fireEvent.click(screen.getByRole("button", { name: /^Em execução/ }));
  expect(screen.queryByRole("button", { name: /^Falhas/ })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Dartan.*Aguardando correção/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Dartan.*Aguardando correção/ }));
  expect(screen.getByText(item.dispatch_error!)).toBeInTheDocument();
  expect(screen.getByText("Trabalho parcial")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Clean up Em execução" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reprocess all in Em execução" })).toBeInTheDocument();
  state.rows = [{ ...item, dispatch_status: "completed", dispatch_error: null }];
  view.rerender(<DemandsPage />);
  expect(screen.queryByRole("button", { name: /Dartan.*Aguardando correção/ })).not.toBeInTheDocument();
});
