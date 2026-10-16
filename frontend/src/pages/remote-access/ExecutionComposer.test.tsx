import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { ExecutionComposer } from "./ExecutionComposer";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const machine = (id: string, name: string, os: string) => ({
  id, name, os_family: os, ip_address: "100.64.0.1", kind: "workstation", group_ids: [],
  darckware_client_id: "c1", darckware_client_name: "Gatling", location: null,
});
const script = (over: Record<string, unknown>) => ({
  id: "s1", name: "Reiniciar spooler", category_id: "cat", description: "desc", platform: "windows", risk: "change",
  timeout_seconds: 60, parameters: [{ name: "SERVICE", label: "Serviço", required: true, default: null, secret: false }],
  content: "x", current_version: 3, is_system: false, system_key: null, archived: false, ...over,
});
const SCRIPTS = [
  script({}),
  script({ id: "rw", name: "Instalar RustDesk", system_key: "rustdesk_install:windows", parameters: [], is_system: true }),
  script({ id: "rl", name: "Instalar RustDesk", platform: "linux", system_key: "rustdesk_install:linux", parameters: [], is_system: true }),
];

function renderComposer(props: Partial<Parameters<typeof ExecutionComposer>[0]> = {}) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") return [machine("w1", "PC-01", "windows"), machine("l1", "srv-lin", "linux")] as never;
    if (url.startsWith("/api/v1/host-scripts/categories")) return [{ id: "cat", slug: "diag", label: "Diagnóstico", description: null }] as never;
    if (url.startsWith("/api/v1/host-scripts")) return SCRIPTS as never;
    if (url.startsWith("/api/v1/servers/readiness")) return { entries: [{ server_id: "w1", readiness: "ready" }], tailnet_available: true } as never;
    return [] as never;
  });
  const onRan = vi.fn();
  const onScheduled = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><ExecutionComposer onRan={onRan} onScheduled={onScheduled} {...props} /></QueryClientProvider>);
  return { onRan, onScheduled };
}

describe("ExecutionComposer", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("runs a library script with parameters on the selected machines", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: "e1" } as never);
    const { onRan } = renderComposer();
    fireEvent.click(await screen.findByRole("checkbox", { name: /PC-01/ }));
    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "s1" } });
    expect(screen.getByText("Preencha os parâmetros obrigatórios.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Serviço *"), { target: { value: "spooler" } });
    fireEvent.click(screen.getByRole("button", { name: "Revisar" }));
    expect(screen.getByText("Será executado agora em 1 máquina:")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Executar agora" }));
    await vi.waitFor(() => expect(onRan).toHaveBeenCalled());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-executions", {
      script_id: "s1", parameter_values: { SERVICE: "spooler" }, server_ids: ["w1"], group_ids: [], timeout_seconds: 60,
    });
  });

  it("schedules a weekly run", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: "sch" } as never);
    const { onScheduled } = renderComposer();
    fireEvent.click(await screen.findByRole("checkbox", { name: /PC-01/ }));
    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "s1" } });
    fireEvent.change(screen.getByLabelText("Serviço *"), { target: { value: "spooler" } });
    fireEvent.click(screen.getByRole("button", { name: "Toda semana" }));
    fireEvent.change(screen.getByLabelText("Nome do agendamento"), { target: { value: "Spooler segunda" } });
    fireEvent.click(screen.getByRole("button", { name: "Seg" }));
    fireEvent.click(screen.getByRole("button", { name: "Revisar" }));
    fireEvent.click(screen.getByRole("button", { name: "Agendar" }));
    await vi.waitFor(() => expect(onScheduled).toHaveBeenCalled());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-schedules", expect.objectContaining({
      name: "Spooler segunda", script_id: "s1", kind: "weekly", weekdays: [1], time_of_day: "22:00",
      timezone: "America/Sao_Paulo", server_ids: ["w1"],
    }));
  });

  it("picks the system script variant that matches the selected machines", async () => {
    renderComposer({ initialSystem: "rustdesk_install" });
    expect(await screen.findByDisplayValue(/Instalar RustDesk · Windows/)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("checkbox", { name: /srv-lin/ }));
    expect(await screen.findByDisplayValue(/Instalar RustDesk · Linux/)).toBeInTheDocument();
  });

  it("copies the ready script for a machine without SSH", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ script_id: "s1", version: 3, shell: "powershell", script: "$SERVICE = 'x'\nRestart" } as never);
    renderComposer();
    await screen.findByRole("option", { name: /Reiniciar spooler/ });
    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "s1" } });
    fireEvent.change(screen.getByLabelText("Serviço *"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: /Copiar script pronto/ }));
    expect(await screen.findByText(/Restart/)).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-scripts/s1:render", { parameter_values: { SERVICE: "x" } });
  });
});
