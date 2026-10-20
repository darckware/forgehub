import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { ExecutionsCard } from "./ExecutionsCard";
import { SchedulesPanel } from "./SchedulesPanel";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const SCHEDULE = {
  id: "sc1", name: "Spooler segunda", script_id: "s1", script_name: "Reiniciar spooler", parameter_values: {},
  server_ids: ["w1"], group_ids: [], kind: "weekly", run_at: null, weekdays: [1], time_of_day: "22:00",
  timezone: "America/Sao_Paulo", window_minutes: 120, enabled: true, next_run_at: "2026-10-20T01:00:00Z",
  last_run_at: null, last_execution_id: null, created_by: "marcelodarck", agent_id: null, created_at: "",
};

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={qc}>{node}</QueryClientProvider></MemoryRouter>);
}

describe("SchedulesPanel and execution log", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("pauses and deletes a schedule after confirmation", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([SCHEDULE] as never);
    vi.mocked(apiClient.put).mockResolvedValue({ ...SCHEDULE, enabled: false } as never);
    vi.mocked(apiClient.delete).mockResolvedValue(undefined as never);
    wrap(<SchedulesPanel onRan={vi.fn()} />);
    expect(await screen.findByText("Seg às 22:00")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pausar Spooler segunda" }));
    await vi.waitFor(() => expect(apiClient.put).toHaveBeenCalledWith("/api/v1/host-schedules/sc1", { enabled: false }));
    fireEvent.click(screen.getByRole("button", { name: "Excluir Spooler segunda" }));
    expect(apiClient.delete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    await vi.waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith("/api/v1/host-schedules/sc1"));
  });

  it("filters the execution log by agent", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.startsWith("/api/v1/agents")) return [{ id: "a1", name: "Aegis" }] as never;
      return [{
        id: "e1", parent_execution_id: null, trigger: "agent", agent_id: "a1", agent_name: "Aegis", schedule_id: null,
        script_id: "s1", script_name: "Reiniciar spooler", script_version: 3, retry_until: null, shell: "powershell",
        command: "x", timeout_seconds: 60, status: "completed", requested_by: "aegis", target_summary: "PC-01",
        started_at: "2026-10-16T12:00:00Z", finished_at: null, verdict: "succeeded",
        counts: { total: 1, pending: 0, running: 0, succeeded: 1, failed: 0, skipped: 0 },
      }] as never;
    });
    wrap(<ExecutionsCard />);
    expect(await screen.findByText("Reiniciar spooler")).toBeInTheDocument();
    expect(screen.getByText("Aegis", { selector: "span" })).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText("Filtrar por agente"), { target: { value: "a1" } });
    await vi.waitFor(() => expect(apiClient.get).toHaveBeenCalledWith("/api/v1/host-executions?limit=50&agent_id=a1"));
  });
});
