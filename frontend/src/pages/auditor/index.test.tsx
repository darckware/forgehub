import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import AuditorPage from ".";
import { ApiError } from "@/lib/api";

const mocks = vi.hoisted(() => ({ checks: vi.fn(), status: vi.fn(), remediate: vi.fn(), setFrequency: vi.fn(),
  runAll: vi.fn(), runRoutine: vi.fn(), admin: { value: true } }));
vi.mock("@/store/authStore", () => ({
  useAuthStore: (selector: (s: { user: { is_admin: boolean } }) => unknown) => selector({ user: { is_admin: mocks.admin.value } }),
}));
vi.mock("@/hooks/useAudit", () => ({
  AUDIT_FREQUENCIES: ["daily", "weekly", "monthly", "quarterly"],
  useSetAuditCheckFrequency: () => ({ mutate: mocks.setFrequency, isPending: false }),
  useRunAuditRoutineNow: () => ({ mutate: mocks.runRoutine, isPending: false }),
  useAuditChecks: () => mocks.checks(), useAuditStatus: () => mocks.status(),
  useAuditRuns: () => ({ data: [], isLoading: false }),
  useCreateAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useRunAllAuditChecks: () => ({ mutate: mocks.runAll, isPending: false }),
  useRunAuditCheck: () => ({ mutate: vi.fn(), isPending: false }),
  useRemediateAuditCheck: () => mocks.remediate(),
}));
vi.mock("@/components/AssistantToggleButton", () => ({ AssistantToggleButton: () => <span /> }));

const check = { id: "c1", name: "ECO-001", description: "Check gateway", category: "infra",
  command: "true", remediation_description: null, remediation_command: null, workdir: null,
  agent_profile: "athos", enabled: true, timeout_seconds: 55, frequency: "weekly", created_at: "2026-10-04T00:00:00Z",
  updated_at: "2026-10-04T00:00:00Z", last_run: { id: "r1", check_id: "c1", status: "fail",
    exit_code: 1, output: "gateway stopped", duration_ms: 12, requested_by: "cron",
    created_at: "2026-10-04T00:00:00Z" } };
const monitor = { state: "healthy", job_id: "weekly", job_name: "ecosystem-weekly-audit",
  script: "ecosystem_weekly_audit.sh", schedule: "0 19 * * 0", enabled: true, health: "ok",
  last_run_at: "2026-10-04T00:00:00Z", last_status: "ok", next_run_at: "2026-10-11T00:00:00Z",
  last_cron_run_at: "2026-10-04T00:00:00Z", issues: [] };

beforeEach(() => {
  void i18n.changeLanguage("pt-BR");
  mocks.admin.value = true;
  mocks.setFrequency.mockReset();
  mocks.runAll.mockReset();
  mocks.runRoutine.mockReset();
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

it.each([['pt-BR', 'Evidência expirada'], ['en', 'Expired evidence'], ['es', 'Evidencia vencida']])('shows stale evidence and filters it without changing the recorded verdict in %s', async (locale, label) => {
  await i18n.changeLanguage(locale);
  mocks.checks.mockReturnValue({ data: [{ ...check, evidence_state: 'stale', expires_at: '2026-10-12T00:00:00Z', last_run: { ...check.last_run, status: 'ok' } }], isLoading: false, isError: false });
  show();
  expect(screen.getAllByText(label).length).toBeGreaterThan(0);
  const select = screen.getAllByRole('combobox').find(element => element.querySelector('option[value="stale"]'))!;
  fireEvent.change(select, { target: { value: 'stale' } });
  expect(screen.getByText('ECO-001')).toBeInTheDocument();
  fireEvent.change(select, { target: { value: 'ok' } });
  expect(screen.queryByText('ECO-001')).not.toBeInTheDocument();
});

it.each(['pt-BR', 'en', 'es'])('formats evidence expiration and run times using the configured %s UI locale', async (locale) => {
  await i18n.changeLanguage(locale);
  const expiry = '2026-10-12T16:45:30Z';
  mocks.checks.mockReturnValue({ data: [{ ...check, evidence_state: 'stale', expires_at: expiry }], isLoading: false, isError: false });
  show();
  expect(screen.getByText(i18n.t('auditor.expiresAt', { ns: 'auditor', date: new Date(expiry).toLocaleString(locale) }))).toBeInTheDocument();
  expect(screen.getAllByText(new Date(check.last_run.created_at).toLocaleString(locale)).length).toBeGreaterThan(0);
});

const tier = (frequency: string, changes: Record<string, unknown> = {}) => ({ frequency, enabled_checks: 2,
  last_complete_run_at: "2026-11-13T22:00:00Z", routine_id: `r-${frequency}`, routine_title: `Auditoria ${frequency}`,
  routine_enabled: true, schedule: "0 19 * * *", timezone: "America/Sao_Paulo",
  next_due_at: "2026-11-14T22:00:00Z", overdue: false, ...changes });

it("groups checks by frequency and lets an admin move a check between tiers", () => {
  mocks.checks.mockReturnValue({ data: [check, { ...check, id: "c2", name: "ECO-005", frequency: "daily" }],
    isLoading: false, isError: false });
  show();
  const rows = screen.getAllByRole("row").map((row) => row.textContent ?? "");
  const daily = rows.findIndex((text) => text === "Diária");
  const weekly = rows.findIndex((text) => text === "Semanal");
  expect(daily).toBeGreaterThan(0);
  expect(weekly).toBeGreaterThan(daily);
  expect(rows[daily + 1]).toContain("ECO-005");
  fireEvent.change(screen.getByRole("combobox", { name: "Frequência de ECO-001" }), { target: { value: "monthly" } });
  expect(mocks.setFrequency).toHaveBeenCalledWith({ checkId: "c1", frequency: "monthly" });
  fireEvent.change(screen.getByRole("combobox", { name: "Frequência" }), { target: { value: "daily" } });
  expect(screen.queryByText("ECO-001")).not.toBeInTheDocument();
  expect(screen.getByText("ECO-005")).toBeInTheDocument();
});

it("shows the frequency read-only to a non-admin", () => {
  mocks.admin.value = false;
  show();
  expect(screen.queryByRole("combobox", { name: "Frequência de ECO-001" })).not.toBeInTheDocument();
  expect(screen.getAllByText("Semanal").length).toBeGreaterThan(0);
});

it.each([["pt-BR", "Faixas de frequência", "Executar agora a faixa Mensal"],
  ["en", "Frequency tiers", "Run the Monthly tier now"],
  ["es", "Franjas de frecuencia", "Ejecutar ahora la franja Mensual"]])("shows each tier's routine and runs one tier in %s", async (locale, title, runLabel) => {
  await i18n.changeLanguage(locale);
  mocks.status.mockReturnValue({ data: { total: 1, enabled: 1, ok: 0, fail: 1, never_ran: 0, last_run_at: null,
    athos_monitor: { ...monitor, state: "replaced", enabled: false }, schedule_source: "routines",
    tiers: [tier("daily"), tier("weekly", { overdue: true }), tier("monthly", { routine_enabled: false }),
      tier("quarterly", { routine_id: null, routine_title: null, routine_enabled: false, next_due_at: null })] },
    isError: false });
  show();
  expect(screen.getByRole("region", { name: title })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: runLabel }));
  // Through the tier routine's background run-now, never a synchronous batch.
  expect(mocks.runRoutine).toHaveBeenCalledWith("r-monthly", expect.anything());
  expect(mocks.runAll).not.toHaveBeenCalled();
  // A tier with no routine has nothing to run.
  const quarterly = i18n.t("auditor.tiers.runTier", { ns: "auditor", tier: i18n.t("auditor.frequency.quarterly", { ns: "auditor" }) });
  expect(screen.queryByRole("button", { name: quarterly })).not.toBeInTheDocument();
});

it("labels the replaced legacy cron and the tier states", () => {
  mocks.status.mockReturnValue({ data: { total: 1, enabled: 1, ok: 0, fail: 1, never_ran: 0, last_run_at: null,
    athos_monitor: { ...monitor, state: "replaced", enabled: false }, schedule_source: "hermes_cron",
    tiers: [tier("daily"), tier("weekly", { overdue: true }), tier("monthly", { routine_enabled: false }),
      tier("quarterly", { routine_id: null, routine_enabled: false, next_due_at: null })] }, isError: false });
  show();
  expect(screen.getByText("Substituído pelas rotinas")).toBeInTheDocument();
  expect(screen.getByText(/Ainda agendadas pelo cron semanal/)).toBeInTheDocument();
  expect(screen.getByText("Rotina pausada")).toBeInTheDocument();
  expect(screen.getByText("Sem rotina")).toBeInTheDocument();
  expect(screen.getByText(/atrasada/)).toBeInTheDocument();
});

it("hides the tier run buttons from a non-admin", () => {
  mocks.admin.value = false;
  mocks.status.mockReturnValue({ data: { total: 1, enabled: 1, ok: 0, fail: 1, never_ran: 0, last_run_at: null,
    athos_monitor: monitor, schedule_source: "hermes_cron", tiers: [tier("daily")] }, isError: false });
  show();
  expect(screen.queryByRole("button", { name: "Executar agora a faixa Diária" })).not.toBeInTheDocument();
});
