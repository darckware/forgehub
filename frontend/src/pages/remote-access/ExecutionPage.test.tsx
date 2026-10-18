import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { formatDuration, shellForOs } from "@/hooks/useHostExecutions";
import ExecutionPage from "./ExecutionPage";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const result = (over: Record<string, unknown>) => ({
  id: "r1", server_id: "m1", server_name: "GAT-ADM-PC01", status: "succeeded", failure: null, skip_reason: null,
  exit_code: 0, stdout: "Windows 11 Pro", stderr: null, truncated: false, duration_ms: 1530,
  started_at: null, finished_at: null, ...over,
});

const EXECUTION = {
  id: "e1", parent_execution_id: null, shell: "powershell", command: "Get-ComputerInfo", timeout_seconds: 300,
  status: "completed", requested_by: "marcelodarck", target_summary: "Secretaria", started_at: "2026-10-15T15:00:00Z",
  finished_at: "2026-10-15T15:00:05Z", verdict: "failed", follow_up_ids: [],
  counts: { total: 3, pending: 0, running: 0, succeeded: 1, failed: 1, skipped: 1 },
  results: [
    result({}),
    result({ id: "r2", server_id: "m2", server_name: "GAT-ADM-PC02", status: "failed", failure: "command", exit_code: 1, stdout: null, stderr: "Access denied", duration_ms: 40 }),
    result({ id: "r3", server_id: "m3", server_name: "GAT-GES-NB01", status: "skipped", skip_reason: "No login set for this machine yet", exit_code: null, stdout: null, duration_ms: null }),
  ],
};

function renderPage() {
  vi.mocked(apiClient.get).mockResolvedValue(EXECUTION as never);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/remote-access/executions/e1"]}>
        <Routes>
          <Route path="/remote-access/executions/:id" element={<ExecutionPage />} />
          <Route path="/remote-access/executions/e2" element={<p>follow-up page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ExecutionPage", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("shows each machine's verdict, exit code, duration and reasons", async () => {
    renderPage();
    expect(await screen.findByText("GAT-ADM-PC01")).toBeInTheDocument();
    expect(screen.getAllByText("Concluída com sucesso").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Falhou").length).toBeGreaterThan(0);
    expect(screen.getByText("código 1")).toBeInTheDocument();
    expect(screen.getByText("1.5 s")).toBeInTheDocument();
    expect(screen.getByText("· No login set for this machine yet")).toBeInTheDocument();
    expect(screen.getByText("· O comando terminou com erro")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /GAT-ADM-PC02/ }));
    expect(screen.getByText("Access denied")).toBeInTheDocument();
  });

  it("copies the command to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Copiar o comando/ }));
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledWith("Get-ComputerInfo"));
  });

  it("runs a fix only on the failed machines", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...EXECUTION, id: "e2" } as never);
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Corrigir as que falharam (1)" }));
    fireEvent.change(screen.getByLabelText("Comando"), { target: { value: "Restart-Service wuauserv" } });
    fireEvent.click(screen.getByRole("button", { name: "Executar correção (1)" }));
    expect(await screen.findByText("follow-up page")).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-executions/e1:follow-up", {
      command: "Restart-Service wuauserv", shell: "powershell", timeout_seconds: 300,
    });
  });
});

describe("execution helpers", () => {
  it("picks the shell that fits every machine", () => {
    expect(shellForOs(["windows", "windows"])).toBe("powershell");
    expect(shellForOs(["linux", null, "macos"])).toBe("sh");
    expect(shellForOs(["windows", "linux"])).toBeNull();
    expect(shellForOs([])).toBeNull();
  });

  it("formats durations", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(450)).toBe("450 ms");
    expect(formatDuration(75_000)).toBe("1 min 15 s");
  });
});
