import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import AuditorPage from ".";
import { ApiError } from "@/lib/api";

const mocks = vi.hoisted(() => ({ checks: vi.fn(), status: vi.fn(), remediate: vi.fn() }));
vi.mock("@/hooks/useAudit", () => ({
  useAuditChecks: () => mocks.checks(), useAuditStatus: () => mocks.status(),
  useAuditRuns: () => ({ data: [], isLoading: false }),
  useCreateAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useRunAllAuditChecks: () => ({ mutate: vi.fn(), isPending: false }),
  useRunAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useRemediateAuditCheck: () => mocks.remediate(),
}));
vi.mock("@/components/AssistantToggleButton", () => ({ AssistantToggleButton: () => <span /> }));

const check = { id: "c1", name: "ECO-001", description: "Check gateway", category: "infra",
  command: "true", remediation_description: null, remediation_command: null, workdir: null,
  agent_profile: "athos", enabled: true, timeout_seconds: 55, created_at: "2026-10-04T00:00:00Z",
  updated_at: "2026-10-04T00:00:00Z", last_run: { id: "r1", check_id: "c1", status: "fail",
    exit_code: 1, output: "gateway stopped", duration_ms: 12, requested_by: "cron",
    created_at: "2026-10-04T00:00:00Z" } };
const monitor = { state: "healthy", job_id: "weekly", job_name: "ecosystem-weekly-audit",
  script: "ecosystem_weekly_audit.sh", schedule: "0 19 * * 0", enabled: true, health: "ok",
  last_run_at: "2026-10-04T00:00:00Z", last_status: "ok", next_run_at: "2026-10-11T00:00:00Z",
  last_cron_run_at: "2026-10-04T00:00:00Z", issues: [] };

beforeEach(() => {
  void i18n.changeLanguage("pt-BR");
  mocks.checks.mockReturnValue({ data: [check], isLoading: false, isError: false });
  mocks.status.mockReturnValue({ data: { total: 1, enabled: 1, ok: 0, fail: 1, never_ran: 0,
    last_run_at: "2026-10-04T00:00:00Z", athos_monitor: monitor }, isError: false });
  mocks.remediate.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: false, isSuccess: false });
});
const show = () => render(<MemoryRouter><AuditorPage /></MemoryRouter>);

it("renders Athos monitor separately from a failed checklist control", () => {
  show();
  expect(screen.getByText("Agendador saudável")).toBeInTheDocument();
  expect(screen.getByText("Falhos")).toBeInTheDocument();
  expect(screen.getByText("ecosystem-weekly-audit")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Abrir Crons" })).toHaveAttribute("href", "/crons");
});

it("hides remediation when the control has no command", () => {
  show();
  expect(screen.queryByRole("button", { name: /Corrigir ECO-001/ })).not.toBeInTheDocument();
});

it("shows remediation refusal inline", () => {
  mocks.remediate.mockReturnValue({ mutate: vi.fn(), isPending: false, isError: true,
    error: new ApiError("conflict", 409, { detail: { problems: ["Script missing"] } }), isSuccess: false });
  show();
  expect(screen.getByRole("alert")).toHaveTextContent("Script missing");
});

it("renders monitor error without breaking checklist", () => {
  mocks.status.mockReturnValue({ data: undefined, isError: true, error: new Error("offline") });
  show();
  expect(screen.getByText("Monitor indisponível: offline")).toBeInTheDocument();
  expect(screen.getByText("ECO-001")).toBeInTheDocument();
});

it("renders in Spanish", async () => {
  await i18n.changeLanguage("es");
  show();
  expect(screen.getByText("Programador saludable")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Abrir Crons" })).toBeInTheDocument();
});

it("filters the checklist by category and state", () => {
  mocks.checks.mockReturnValue({ data: [check, { ...check, id: "c2", name: "ECO-046", category: "backup", last_run: null }], isLoading: false, isError: false });
  show();
  fireEvent.change(screen.getByRole("combobox", { name: "Categoria" }), { target: { value: "backup" } });
  expect(screen.getByText("ECO-046")).toBeInTheDocument();
  expect(screen.queryByText("ECO-001")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Status" }), { target: { value: "fail" } });
  expect(screen.getByText("Nenhum controle corresponde aos filtros.")).toBeInTheDocument();
});
