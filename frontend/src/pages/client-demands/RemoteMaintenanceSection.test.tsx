import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { WorkItemDetail, WorkItemMaintenance } from "@/hooks/useClientOps";
import { RemoteMaintenanceSection } from "./RemoteMaintenanceSection";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const DETAIL = {
  kind: "ticket", id: "t1", title: "PC lento", tipo: "servico", status: "em_andamento", stage: "em_andamento",
  client_account_id: "c1", company_name: "ACME", timeline: [], emails: [], project: null,
  time_entries: [{ id: "te1", billable_hours: 1.5, description: "Visita anterior", recorded_by: "admin" }],
} as unknown as WorkItemDetail;

const SERVERS = [
  { id: "w1", name: "acme-pc01", os_family: "windows", darckware_client_id: "c1" },
  { id: "w2", name: "acme-pc02", os_family: "windows", darckware_client_id: "c1" },
  { id: "x9", name: "other-pc", os_family: "linux", darckware_client_id: "c2" },
];

const MAINTENANCE: WorkItemMaintenance = {
  executions: [
    { id: "e1", started_at: "2026-11-12T10:00:00Z", finished_at: "2026-11-12T10:35:00Z", duration_seconds: 2100, status: "completed", in_progress: false,
      verdict: "succeeded", machines: [{ name: "acme-pc01", server_id: "w1", verdict: "succeeded" }], requested_by: "Aegis",
      trigger: "agent", agent_id: "a1", agent_name: "Aegis", script_name: "Reiniciar spooler", what: "script Reiniciar spooler v1",
      reason: "lento", agent_demand_id: "m1", demand_number: 42 },
    { id: "e2", started_at: "2026-11-12T09:00:00Z", finished_at: "2026-11-12T09:05:00Z", duration_seconds: 300, status: "completed", in_progress: false,
      verdict: "failed", machines: [{ name: "acme-pc02", server_id: "w2", verdict: "failed" }], requested_by: "marcelo",
      trigger: "manual", agent_id: null, agent_name: null, script_name: null, what: "comando ipconfig", reason: null,
      agent_demand_id: null, demand_number: null },
  ],
  tasks: [
    { demand_id: "m1", number: 42, subject: "Manutenção em acme-pc01", agent_id: "a1", agent_name: "Aegis", dispatch_status: "completed",
      status: "read", created_at: "2026-11-12T09:59:00Z", finished: true, runs_in_progress: false, execution_ids: ["e1"],
      client_ids: ["c1"], recorded: null, uncertain: null,
      proposal: { minutes: 60, note: "Manutenção remota realizada em: acme-pc01.", start_time: null,
        end_time: "2026-11-12T10:35:00Z", execution_count: 1 } },
    { demand_id: "m2", number: 43, subject: "Outra", agent_id: "a1", agent_name: "Aegis", dispatch_status: "completed",
      status: "read", created_at: "2026-11-12T08:00:00Z", finished: true, runs_in_progress: false, execution_ids: [],
      client_ids: ["c1"], recorded: null, proposal: null,
      uncertain: { attempt_id: "at1", mode: "resolve", minutes: 30, note: "Visita anterior", at: "2026-11-12T11:00:00Z", by: "marcelo" } },
  ],
};

function mockApi(servers = SERVERS) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") return servers as never;
    if (url.endsWith("/maintenance")) return MAINTENANCE as never;
    if (url.startsWith("/api/v1/client-ops/work-items")) return { items: [], total: 0, by_stage: {} } as never;
    return [] as never;
  });
}

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

describe("RemoteMaintenanceSection", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("disables the ask button with a reason when the item has no client or the client no machine", async () => {
    mockApi();
    const { unmount } = wrap(<RemoteMaintenanceSection detail={{ ...DETAIL, client_account_id: null }} />);
    expect(screen.getByRole("button", { name: /Pedir manutenção ao agente/ })).toBeDisabled();
    expect(screen.getByText("Item sem cliente: não há máquinas a oferecer.")).toBeInTheDocument();
    unmount();

    mockApi([SERVERS[2]]);
    wrap(<RemoteMaintenanceSection detail={DETAIL} />);
    expect(await screen.findByText("O cliente não tem máquina cadastrada no Acesso Remoto.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Pedir manutenção ao agente/ })).toBeDisabled();
  });

  it("opens Pedir ao agente with the client's machines, none ticked, and the item preselected", async () => {
    mockApi();
    wrap(<RemoteMaintenanceSection detail={DETAIL} />);
    const button = screen.getByRole("button", { name: /Pedir manutenção ao agente/ });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    const panel = await screen.findByRole("dialog");
    const pc1 = within(panel).getByRole("checkbox", { name: /acme-pc01/ });
    const pc2 = within(panel).getByRole("checkbox", { name: /acme-pc02/ });
    expect(within(panel).queryByRole("checkbox", { name: /other-pc/ })).toBeNull();
    expect(pc1).not.toBeChecked();
    expect(pc2).not.toBeChecked();
    expect(within(panel).getByText("Escolha ao menos uma máquina para ver os agentes.")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: /Enviar/ })).toBeDisabled();
    fireEvent.click(pc2);
    expect(pc2).toBeChecked();
    expect(within(panel).queryByText("Escolha ao menos uma máquina para ver os agentes.")).toBeNull();
    const item = within(panel).getByLabelText("Atendimento do cliente") as HTMLSelectElement;
    expect(item.value).toBe("ticket:t1");
  });

  it("lists runs and tasks, and writes only after the operator confirms", async () => {
    mockApi();
    vi.mocked(apiClient.post).mockResolvedValue({ ...DETAIL } as never);
    wrap(<RemoteMaintenanceSection detail={DETAIL} />);
    expect(await screen.findByText("Tarefa #42")).toBeInTheDocument();
    expect(screen.getByText("script Reiniciar spooler v1")).toBeInTheDocument();
    expect(screen.getByText(/Por marcelo/)).toBeInTheDocument();
    expect(screen.getByText(/não entram na proposta/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Revisar e registrar/ }));
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByLabelText("Nota")).toHaveValue("Manutenção remota realizada em: acme-pc01.");
    expect(within(panel).getByText(/O cliente vê este texto/)).toBeInTheDocument();
    expect(within(panel).getByText(/datada no fim da última execução/)).toBeInTheDocument();
    expect(within(panel).getByText(/Horas já apontadas neste item · total 1,5/)).toBeInTheDocument();
    expect(within(panel).getByText("Visita anterior")).toBeInTheDocument();
    const minutes = within(panel).getByLabelText("Minutos");
    expect(minutes).toHaveValue("60");
    fireEvent.change(minutes, { target: { value: "0" } });
    expect(within(panel).getByRole("button", { name: "Registrar horas" })).toBeDisabled();
    fireEvent.change(minutes, { target: { value: "45" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Registrar e dar baixa" }));
    expect(apiClient.post).not.toHaveBeenCalled(); // reviewing is not writing
    expect(within(panel).getByText(/Dar baixa neste item com 45 min/)).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole("button", { name: "Confirmar e gravar" }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(1));
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/client-ops/work-items/ticket/t1/maintenance/m1:record", {
      mode: "resolve", note: "Manutenção remota realizada em: acme-pc01.", minutes: 45, service_type: "remoto",
    });
    expect(await screen.findByText("Registrado na Darckware.")).toBeInTheDocument();
  });

  it("offers only Registrar horas when the item is no longer open", async () => {
    mockApi();
    wrap(<RemoteMaintenanceSection detail={{ ...DETAIL, stage: "resolvido" } as WorkItemDetail} />);
    fireEvent.click(await screen.findByRole("button", { name: /Revisar e registrar/ }));
    const panel = await screen.findByRole("dialog");
    expect(within(panel).queryByRole("button", { name: "Registrar e dar baixa" })).toBeNull();
    expect(within(panel).getByRole("button", { name: "Registrar horas" })).toBeEnabled();
  });

  it("an uncertain attempt is settled by the operator, with a reason, never automatically", async () => {
    mockApi();
    vi.mocked(apiClient.post).mockResolvedValue(MAINTENANCE as never);
    wrap(<RemoteMaintenanceSection detail={DETAIL} />);
    expect(await screen.findByText(/pode ter chegado à Darckware/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolver tentativa" }));
    const panel = await screen.findByRole("dialog");
    // The item already holds an entry with that text: a hint, not a decision.
    expect(within(panel).getByText(/Há uma entrada neste item com o mesmo texto/)).toBeInTheDocument();
    const confirm = within(panel).getByRole("button", { name: "Confirmar e gravar" });
    expect(confirm).toBeDisabled();
    fireEvent.click(within(panel).getByRole("radio", { name: /Foi registrado/ }));
    expect(confirm).toBeDisabled(); // a reason is required
    fireEvent.change(within(panel).getByLabelText(/O que você conferiu/), { target: { value: "Entrada de 0,5 h está lá" } });
    expect(apiClient.post).not.toHaveBeenCalled();
    fireEvent.click(confirm);
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(
      "/api/v1/client-ops/work-items/ticket/t1/maintenance/m2:settle", { outcome: "recorded", reason: "Entrada de 0,5 h está lá" }));
    expect(await screen.findByText("Tentativa resolvida.")).toBeInTheDocument();
  });
});
