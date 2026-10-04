import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

import "@/i18n";
import i18n from "@/i18n";
import { useAuthStore } from "@/store/authStore";
import OperationsPage from ".";

const mocks = vi.hoisted(() => ({ vm: vi.fn(), runNow: vi.fn() }));
vi.mock("@/hooks/useOperationsViewModel", () => ({
  useOperationsViewModel: () => mocks.vm(),
}));

beforeEach(() => {
  void i18n.changeLanguage("pt-BR");
  mocks.runNow.mockReset();
  useAuthStore.setState({ user: { id: "u1", username: "admin", email: null, full_name: null,
    avatar_data_url: null, totp_enabled: false, is_active: true, is_admin: true,
    profile_id: null, ui_language: "pt-BR" } });
  mocks.vm.mockReturnValue({
    overview: { data: { agents: [{ agent_id: "a1", agent_name: "Athos", profile_slug: "athos",
      runtime_type: "hermes", has_charter: true, routines_enabled: 1, routines_total: 1,
      today: { completed: 2 }, daily_run_budget: 24, runs_counted_today: 2 }], policy_version: 1 },
      isLoading: false, isError: false, refetch: vi.fn() },
    charters: { data: [], isLoading: false, isError: false },
    routines: { data: [{ id: "r1", agent_id: "a1", agent_name: "Athos", title: "Briefing matinal",
      instructions: "Revisar estado", schedule: "30 8 * * *", timezone: "America/Sao_Paulo",
      kind: "report", expected_evidence: "Resumo", linked_audit_checks: [], enabled: true,
      priority: 0, deadline_minutes: 60, next_occurrences: ["2026-10-05T11:30:00Z"],
      last_occurrence_at: null, created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z" }],
      isLoading: false, isError: false },
    runs: { data: [], isLoading: false, isError: false },
    questions: { data: [], isLoading: false, isError: false },
    policy: { data: null, isLoading: false, isError: false },
    policyVersions: { data: [], isLoading: false, isError: false },
    improvements: { data: [], isLoading: false, isError: false },
    refresh: vi.fn(),
    saveCharter: { mutate: vi.fn(), isPending: false, error: null },
    saveRoutine: { mutate: vi.fn(), isPending: false, error: null },
    deleteRoutine: { mutate: vi.fn(), isPending: false, error: null },
    runNow: { mutate: mocks.runNow, isPending: false, error: null },
    answerQuestion: { mutate: vi.fn(), isPending: false, error: null },
    cancelQuestion: { mutate: vi.fn(), isPending: false, error: null },
    publishPolicy: { mutate: vi.fn(), isPending: false, error: null },
  });
});

it("shows the agent health and every planned control tab", () => {
  render(<MemoryRouter><OperationsPage /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "Operação 24x7" })).toBeInTheDocument();
  expect(screen.getByText("Athos")).toBeInTheDocument();
  for (const tab of ["Agentes", "Programação", "Execuções", "Melhorias", "Dúvidas", "Instruções"]) {
    expect(screen.getByRole("tab", { name: tab })).toBeInTheDocument();
  }
});

it("requires confirmation before dispatching an extra routine run", () => {
  render(<MemoryRouter><OperationsPage /></MemoryRouter>);
  fireEvent.click(screen.getByRole("tab", { name: "Programação" }));
  fireEvent.click(screen.getByRole("button", { name: "Executar agora Briefing matinal" }));
  expect(mocks.runNow).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar execução" }));
  expect(mocks.runNow).toHaveBeenCalledWith("r1", expect.any(Object));
});

it("confirms an answer before creating the agent return Task", () => {
  const answer = vi.fn();
  const base = mocks.vm();
  mocks.vm.mockReturnValue({ ...base,
    questions: { data: [{ id: "q1", number: 42, agent_name: "Athos", status: "pending",
      question: "Posso mudar o horário?", context: null, recommendation: null, blocking: true,
      answer: null }], isLoading: false, isError: false },
    answerQuestion: { mutate: answer, isPending: false, error: null },
  });
  render(<MemoryRouter><OperationsPage /></MemoryRouter>);
  fireEvent.click(screen.getByRole("tab", { name: "Dúvidas" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Resposta" }), { target: { value: "Sim, às 09:00." } });
  fireEvent.click(screen.getByRole("button", { name: "Enviar resposta" }));
  expect(answer).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Confirmar envio" }));
  expect(answer).toHaveBeenCalledWith({ id: "q1", answer: "Sim, às 09:00." }, expect.any(Object));
});

it("renders the controls in Spanish", async () => {
  await i18n.changeLanguage("es");
  render(<MemoryRouter><OperationsPage /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "Operación 24/7" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Programación" })).toBeInTheDocument();
});
