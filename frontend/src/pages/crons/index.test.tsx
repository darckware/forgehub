import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "@/lib/api";
import i18n from "@/i18n";
import CronsPage from "./index";

const job = {
  profile: "athos", id: "job-1", name: "ecosystem-weekly-audit", description: null,
  script: "ecosystem_weekly_audit.sh", script_state: "missing", is_audit_job: true,
  schedule_display: "0 19 * * 0", enabled: true, state: "scheduled", status: "active",
  health: "error", next_run_at: null, last_run_at: null, last_status: "error",
  last_error: "exit 1", last_log_at: null, deliver: null,
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><CronsPage /></QueryClientProvider>);
}

describe("Crons page", () => {
  beforeEach(async () => { await i18n.changeLanguage("en"); });
  afterEach(async () => { cleanup(); vi.restoreAllMocks(); await i18n.changeLanguage("pt-BR"); });

  function respond(jobs = [job], store_errors: unknown[] = []) {
    vi.spyOn(apiClient, "get").mockImplementation(async (path) => {
      if (path === "/api/v1/foundation/crons") return { jobs, store_errors };
      if (path === "/api/v1/scripts") return { scripts: [] };
      throw new Error(`Unexpected GET ${path}`);
    });
  }

  it("rendersHealthSummaryAndAuditBadge", async () => {
    respond([job, { ...job, id: "job-2", name: "paused", health: "off", is_audit_job: false }]);
    renderPage();
    const summary = await screen.findByRole("region", { name: "Cron health summary" });
    expect(within(summary).getAllByText("1", { selector: "strong" })).toHaveLength(2);
    expect(screen.getByText("Audit job")).toBeInTheDocument();
  });

  it("rendersMissingScriptWithoutCentralFallback", async () => {
    respond();
    renderPage();
    expect(await screen.findByText("Missing script")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /view file.*ecosystem-weekly-audit/i }));
    await waitFor(() => expect(apiClient.get).toHaveBeenCalledWith(
      "/api/v1/foundation/scripts/athos/ecosystem_weekly_audit.sh/content"
    ));
    await screen.findByText(/Failed to load file/);
    expect(vi.mocked(apiClient.get).mock.calls.some(([path]) => String(path).includes("/central/"))).toBe(false);
  });

  it("showsRunErrorInline", async () => {
    respond();
    vi.spyOn(apiClient, "post").mockRejectedValueOnce(new Error("gateway unavailable"));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /run ecosystem-weekly-audit now/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("gateway unavailable");
  });

  it("opensDeleteConfirmationDialog", async () => {
    respond();
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /delete ecosystem-weekly-audit/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent("ecosystem-weekly-audit");
  });

  it("rendersInSpanish", async () => {
    await i18n.changeLanguage("es");
    respond();
    renderPage();
    expect(await screen.findByRole("heading", { name: "Tareas programadas" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /eliminar ecosystem-weekly-audit/i })).toBeInTheDocument();
  });

  it("shows corrupt stores above the jobs", async () => {
    respond([job], [{ profile: "atlas", store: "/profiles/atlas/cron/jobs.json", error: "invalid JSON" }]);
    renderPage();
    expect(await screen.findByText("Corrupted cron store")).toBeInTheDocument();
    expect(screen.getByText("invalid JSON", { exact: false })).toBeInTheDocument();
  });
});
