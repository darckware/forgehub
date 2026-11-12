import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { Server } from "@/hooks/useServers";
import { AgentRequestDialog } from "./AgentRequestDialog";
import { ScriptCategoriesDialog } from "./ScriptCategoriesDialog";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

const future = new Date(Date.now() + 30 * 86_400_000).toISOString();
const agent = (id: string, name: string) => ({ id, name, is_active: true, status: "active", agent_type: "executor" });
const delegation = (grantee: string, risk: string) => ({
  servers: ["w1"], host_groups: [], id: `d-${grantee}`, grantee_id: grantee, scope_type: "organization", allowed_actions: ["remote_access.execute"],
  expires_at: future, status: "active", reason: null, max_risk: risk, product_id: null, project_id: null,
});
const SCRIPTS = [
  { id: "s-read", name: "Obter ID do RustDesk", category_id: "c1", platform: "windows", risk: "read", parameters: [], archived: false },
  { id: "s-fix", name: "Reiniciar spooler", category_id: "c1", platform: "windows", risk: "change", archived: false,
    parameters: [{ name: "SERVICE", label: "Serviço", required: true, default: null, secret: false }] },
];

function mockApi() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") return [{id: "w1", name: "Test machine"}] as never;
    if (url.startsWith("/api/v1/agents")) return [agent("a1", "Aegis"), agent("a2", "Vector"), agent("a3", "Atlas")] as never;
    if (url.startsWith("/api/v1/governed/authority-delegations")) return [delegation("a1", "medium"), delegation("a2", "low")] as never;
    if (url.startsWith("/api/v1/host-scripts/categories")) {
      return [{ id: "c1", slug: "rustdesk", label: "RustDesk", description: null, script_count: 2, is_system: true },
        { id: "c2", slug: "impressoras", label: "Impressoras", description: null, script_count: 0, is_system: false }] as never;
    }
    if (url.startsWith("/api/v1/host-scripts")) return SCRIPTS as never;
    return [] as never;
  });
}

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

describe("agent maintenance screens", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockApi();
    await i18n.changeLanguage("pt-BR");
  });

  it("asks agents for a task with chosen scripts; an agent below the scripts' risk can't be picked", async () => {
    vi.mocked(apiClient.post).mockResolvedValue([{ agent_id: "a1", agent_name: "Aegis", demand_id: "m1", demand_number: 42 }] as never);
    const machine = { id: "w1", name: "gat-adm-pc01", os_family: "windows", darckware_client_id: null } as unknown as Server;
    wrap(<AgentRequestDialog machines={[machine]} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("O que fazer"), { target: { value: "Impressora parada, reinicie o spooler" } });
    await screen.findByRole("option", { name: "Reiniciar spooler" });
    fireEvent.change(screen.getByLabelText("Scripts da biblioteca (opcional)"), { target: { value: "s-fix" } });
    fireEvent.change(screen.getByLabelText("Serviço *"), { target: { value: "spooler" } });
    expect(await screen.findByRole("checkbox", { name: /Vector/ })).toBeDisabled(); // low < change
    fireEvent.click(screen.getByRole("checkbox", { name: /Aegis/ }));
    fireEvent.click(screen.getByRole("button", { name: "Enviar a 1 agente" }));
    expect(await screen.findByText("Tarefa enviada a 1 agente.")).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-executions/agent-requests", {
      agent_ids: ["a1"], server_ids: ["w1"], instruction: "Impressora parada, reinicie o spooler",
      scripts: [{ script_id: "s-fix", parameter_values: { SERVICE: "spooler" } }],
    });
  });

  it("lists an agent with only free commands covering the machines; chosen scripts need a script permission", async () => {
    vi.mocked(apiClient.post).mockResolvedValue([{ agent_id: "a3", agent_name: "Atlas", demand_id: "m2", demand_number: 43 }] as never);
    const base = vi.mocked(apiClient.get).getMockImplementation()!;
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/api/v1/remote-access/direct/agents") {
        return [
          { id: "a3", name: "Atlas", runtime_type: "codex", allowed: true, unsupported_reason: null, configuration:
            { id: "c1", agent_id: "a3", all_machines: false, machines: [{ id: "w1", name: "gat-adm-pc01", sensitive: false }], expires_at: null, open_ended: true, duration_hours: 0, opened_at: new Date().toISOString(), allow_elevation: false, purpose: null, reason: null } },
          { id: "a6", name: "Zed", runtime_type: "codex", allowed: true, unsupported_reason: null, configuration:
            { id: "c2", agent_id: "a6", all_machines: false, machines: [{ id: "other", name: "x", sensitive: false }], expires_at: null, open_ended: true, duration_hours: 0, opened_at: new Date().toISOString(), allow_elevation: false, purpose: null, reason: null } },
        ] as never;
      }
      return base(url);
    });
    const machine = { id: "w1", name: "gat-adm-pc01", os_family: "windows", darckware_client_id: null } as unknown as Server;
    wrap(<AgentRequestDialog machines={[machine]} onClose={vi.fn()} />);
    const atlas = await screen.findByRole("checkbox", { name: /Atlas/ });
    expect(atlas).toBeEnabled();
    expect(screen.getByText("(comandos livres)")).toBeInTheDocument();
    // Zed's commands don't cover gat-adm-pc01: it isn't listed at all.
    expect(screen.queryByRole("checkbox", { name: /Zed/ })).not.toBeInTheDocument();

    // With a script chosen, commands alone don't qualify.
    await screen.findByRole("option", { name: "Obter ID do RustDesk" });
    fireEvent.change(screen.getByLabelText("Scripts da biblioteca (opcional)"), { target: { value: "s-read" } });
    expect(screen.getByRole("checkbox", { name: /Atlas/ })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /Atlas/ })).toHaveAccessibleDescription("só tem comandos livres; os scripts escolhidos pedem permissão de scripts.");
    expect(screen.getByRole("checkbox", { name: /Vector/ })).toBeEnabled(); // low covers read

    fireEvent.click(screen.getByRole("button", { name: "Remover Obter ID do RustDesk" }));
    fireEvent.change(screen.getByLabelText("O que fazer"), { target: { value: "Verifique o disco da máquina" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /Atlas/ }));
    fireEvent.click(screen.getByRole("button", { name: "Enviar a 1 agente" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-executions/agent-requests", {
      agent_ids: ["a3"], server_ids: ["w1"], instruction: "Verifique o disco da máquina", scripts: [],
    }));
  });

  it("shows why an agent whose permission doesn't cover every chosen machine can't be picked", async () => {
    const machines = [
      { id: "w1", name: "gat-adm-pc01", os_family: "windows", darckware_client_id: null },
      { id: "w9", name: "gat-ges-nb01", os_family: "windows", darckware_client_id: null },
    ] as unknown as Server[];
    wrap(<AgentRequestDialog machines={machines} onClose={vi.fn()} />);
    const aegis = await screen.findByRole("checkbox", { name: /Aegis/ });
    expect(aegis).toBeDisabled();
    expect(aegis).toHaveAccessibleDescription("nenhuma permissão dele cobre todas as máquinas escolhidas.");
  });

  it("a script delegation doesn't count when the agent's profile can't reach the maintenance tools", async () => {
    const base = vi.mocked(apiClient.get).getMockImplementation()!;
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => url === "/api/v1/remote-access/direct/agents"
      ? [{ id: "a1", name: "Aegis", runtime_type: "hermes", allowed: false, unsupported_reason: "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS",
          scripts_unsupported_reason: "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS", configuration: null }] as never
      : base(url));
    const machine = { id: "w1", name: "gat-adm-pc01", os_family: "windows", darckware_client_id: null } as unknown as Server;
    wrap(<AgentRequestDialog machines={[machine]} onClose={vi.fn()} />);
    expect(await screen.findByRole("checkbox", { name: /Vector/ })).toBeEnabled();
    await vi.waitFor(() => expect(screen.getByRole("checkbox", { name: /Aegis/ })).toBeDisabled());
    expect(screen.getByRole("checkbox", { name: /Aegis/ })).toHaveAccessibleDescription("nenhuma permissão dele cobre todas as máquinas escolhidas.");
  });

  it("renames a classification and only lets an unused, non-system one be deleted", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({} as never);
    wrap(<ScriptCategoriesDialog onClose={vi.fn()} />);
    expect(await screen.findByText("Impressoras")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Excluir RustDesk" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Excluir Impressoras" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Editar Impressoras" }));
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Impressão" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(apiClient.put).toHaveBeenCalledWith("/api/v1/host-scripts/categories/c2", { label: "Impressão", description: null }));
  });
});
