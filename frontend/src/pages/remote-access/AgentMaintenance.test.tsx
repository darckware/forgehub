import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { Server } from "@/hooks/useServers";
import { AgentRequestDialog } from "./AgentRequestDialog";
import { AuthorizedAgentsCard } from "./AuthorizedAgentsCard";
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

  it("grants several agents at once (one delegation each) and revokes one", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({} as never);
    wrap(<AuthorizedAgentsCard />);
    expect(await screen.findByText("Aegis")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Conceder acesso a agentes" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Atlas" }));
    expect(screen.getByRole("button", { name: "Conceder a 1 agente" })).toBeDisabled();
    fireEvent.click(await screen.findByRole("checkbox", { name: "Test machine" }));
    expect(screen.queryByRole("checkbox", { name: "Aegis" })).not.toBeInTheDocument(); // already authorized
    fireEvent.click(screen.getByRole("button", { name: "Conceder a 1 agente" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/governed/authority-delegations", expect.objectContaining({
      servers: ["w1"], host_groups: [], grantee_agent_id: "a3", allowed_actions: ["remote_access.execute"], max_risk: "medium",
    })));
    fireEvent.click(screen.getAllByRole("button", { name: "Revogar" })[0]);
    const confirm = await screen.findByText("Revogar o acesso de Aegis?");
    const dialog = confirm.closest("[role=dialog],[role=alertdialog]") as HTMLElement;
    fireEvent.click(within(dialog).getByRole("button", { name: "Revogar" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/governed/authority-delegations/d-a1:revoke"));
  });

  it("grant panel: right-hand, ineligible agents and unprepared machines disabled with the reason, search, select all, summary", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({} as never);
    const base = vi.mocked(apiClient.get).getMockImplementation()!;
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/api/v1/servers") {
        return [
          { id: "w1", name: "gat-adm-pc01", ip_address: "100.64.0.1", darckware_client_name: "Gatling" },
          { id: "w2", name: "gat-ges-nb01", ip_address: "100.64.0.2", darckware_client_name: "Gatling" },
          { id: "w3", name: "srv-app02", ip_address: "172.15.2.2" },
        ] as never;
      }
      if (url === "/api/v1/servers/readiness") {
        return { entries: [
          { server_id: "w1", readiness: "ready", status: "complete" },
          { server_id: "w2", readiness: "busy", status: "partial", rustdesk_id: null },
          { server_id: "w3", readiness: "not_prepared", status: "not_prepared" },
        ], checked_at: "", tailnet_available: true, ssh_checked_at: null } as never;
      }
      if (url === "/api/v1/remote-access/direct/agents") {
        return [
          { id: "a3", name: "Atlas", runtime_type: "codex", allowed: false, unsupported_reason: null, configuration: null },
          { id: "a4", name: "Maia", runtime_type: "hermes", allowed: false, unsupported_reason: "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS", configuration: null },
        ] as never;
      }
      if (url.startsWith("/api/v1/agents")) return [agent("a1", "Aegis"), agent("a2", "Vector"), agent("a3", "Atlas"), agent("a4", "Maia")] as never;
      return base(url);
    });
    wrap(<AuthorizedAgentsCard />);
    const opener = await screen.findByRole("button", { name: "Conceder acesso a agentes" });
    opener.focus();
    fireEvent.click(opener);
    const panel = screen.getByRole("dialog", { name: "Conceder acesso a agentes" });
    expect(panel.className).toContain("slide-in-from-right");

    const maia = await screen.findByRole("checkbox", { name: "Maia" });
    await vi.waitFor(() => expect(maia).toBeDisabled());
    expect(maia).toHaveAccessibleDescription("o MCP forgehub do perfil não expõe as ferramentas de manutenção.");
    expect(screen.getByRole("checkbox", { name: "Atlas" })).toBeEnabled();

    const srv = await screen.findByRole("checkbox", { name: "srv-app02" });
    await vi.waitFor(() => expect(srv).toBeDisabled());
    expect(screen.getByText("preparar primeiro")).toBeInTheDocument();
    expect(screen.getByText("Pronta")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "gat-ges-nb01" })).toBeEnabled(); // busy = login works

    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar máquina" }), { target: { value: "gatling" } });
    expect(screen.queryByRole("checkbox", { name: "srv-app02" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Selecionar todas as visíveis" }));
    expect(screen.getByRole("checkbox", { name: "gat-adm-pc01" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "gat-ges-nb01" })).toBeChecked();

    fireEvent.click(screen.getByRole("checkbox", { name: "Atlas" }));
    fireEvent.click(maia); // disabled: ignored
    expect(screen.getByTestId("grant-summary")).toHaveTextContent("1 agente · 2 máquinas · risco até médio · 1 dia");

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Conceder acesso a agentes" })).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("grant panel: nothing loaded yet about eligibility or readiness never blocks", async () => {
    const base = vi.mocked(apiClient.get).getMockImplementation()!;
    vi.mocked(apiClient.get).mockImplementation(async (url: string) =>
      url === "/api/v1/remote-access/direct/agents" || url === "/api/v1/servers/readiness" ? new Promise(() => undefined) : base(url));
    wrap(<AuthorizedAgentsCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Conceder acesso a agentes" }));
    expect(screen.getByRole("checkbox", { name: "Atlas" })).toBeEnabled();
    expect(await screen.findByRole("checkbox", { name: "Test machine" })).toBeEnabled();
    expect(screen.getByText("Verificando o estado das máquinas…")).toBeInTheDocument();
    expect(screen.getByText("Verificando quais agentes podem usar o acesso…")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Atlas" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Test machine" }));
    expect(screen.getByRole("button", { name: "Conceder a 1 agente" })).toBeEnabled();
  });

  function mockGrantWorld(state: { kairosReason: string | null; w1Readiness: string }) {
    const base = vi.mocked(apiClient.get).getMockImplementation()!;
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/api/v1/servers") {
        return [
          { id: "w1", name: "pc-ready" }, { id: "w2", name: "pc-off" },
          { id: "w3", name: "pc-new" }, { id: "w4", name: "pc-unread" },
        ] as never;
      }
      if (url === "/api/v1/host-groups") return [{ id: "g1", name: "Gatling", server_ids: [] }] as never;
      if (url === "/api/v1/servers/readiness") {
        return { entries: [
          { server_id: "w1", readiness: state.w1Readiness, status: state.w1Readiness === "ready" ? "complete" : "not_prepared" },
          { server_id: "w2", readiness: "offline", status: "offline" },
          { server_id: "w3", readiness: "not_prepared", status: "not_prepared" },
          { server_id: "w4", readiness: "unknown", status: "unknown" },
        ], checked_at: "", tailnet_available: true, ssh_checked_at: null } as never;
      }
      if (url === "/api/v1/remote-access/direct/agents") {
        return [
          { id: "a3", name: "Atlas", runtime_type: "codex", allowed: false, unsupported_reason: null, configuration: null },
          { id: "a4", name: "Maia", runtime_type: "hermes", allowed: false, unsupported_reason: "PROFILE_WITHOUT_FORGEHUB_MCP", configuration: null },
          { id: "a5", name: "Kairos", runtime_type: "hermes", allowed: false, unsupported_reason: state.kairosReason, configuration: null },
        ] as never;
      }
      if (url.startsWith("/api/v1/agents")) {
        return [agent("a1", "Aegis"), agent("a2", "Vector"), agent("a3", "Atlas"), agent("a4", "Maia"), agent("a5", "Kairos")] as never;
      }
      return base(url);
    });
  }

  function wrapWithClient(node: React.ReactNode) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
    return qc;
  }

  const grantBodies = () => vi.mocked(apiClient.post).mock.calls
    .filter(([url]) => url === "/api/v1/governed/authority-delegations")
    .map(([, body]) => body as Record<string, unknown>);

  it("grant: one POST per eligible agent with exactly the chosen machines, groups, risk and expiry", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({} as never);
    mockGrantWorld({ kairosReason: null, w1Readiness: "ready" });
    wrap(<AuthorizedAgentsCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Conceder acesso a agentes" }));
    const maia = await screen.findByRole("checkbox", { name: "Maia" });
    await vi.waitFor(() => expect(maia).toBeDisabled());

    // offline and unknown stay pickable, with their own note; never-prepared doesn't
    await vi.waitFor(() => expect(screen.getByRole("checkbox", { name: "pc-new" })).toBeDisabled());
    expect(screen.getByRole("checkbox", { name: "pc-off" })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: "pc-off" })).toHaveAccessibleDescription("offline agora");
    expect(screen.getByRole("checkbox", { name: "pc-unread" })).toHaveAccessibleDescription("estado desconhecido");
    expect(screen.getByRole("checkbox", { name: "pc-new" })).toHaveAccessibleDescription("preparar primeiro");

    fireEvent.click(screen.getByRole("checkbox", { name: "Atlas" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Kairos" }));
    fireEvent.click(maia);
    fireEvent.click(screen.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "pc-off" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "pc-new" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "Gatling" }));
    fireEvent.change(screen.getByLabelText("Risco máximo"), { target: { value: "high" } });
    fireEvent.change(screen.getByLabelText("Validade"), { target: { value: "7" } });
    expect(screen.getByTestId("grant-summary")).toHaveTextContent("2 agentes · 2 máquinas · 1 grupo · risco até alto · 7 dias");

    const before = Date.now();
    fireEvent.click(screen.getByRole("button", { name: "Conceder a 2 agentes" }));
    await vi.waitFor(() => expect(grantBodies()).toHaveLength(2));
    await vi.waitFor(() => expect(screen.queryByRole("dialog", { name: "Conceder acesso a agentes" })).not.toBeInTheDocument());
    const bodies = grantBodies();
    expect(bodies.map((b) => b.grantee_agent_id)).toEqual(["a3", "a5"]);
    for (const body of bodies) {
      expect(body).toMatchObject({
        allowed_actions: ["remote_access.execute"], scope_type: "organization",
        servers: ["w1", "w2"], host_groups: ["g1"], max_risk: "high",
      });
      const expires = Date.parse(body.expires_at as string);
      expect(expires).toBeGreaterThanOrEqual(before + 7 * 86_400_000);
      expect(expires).toBeLessThanOrEqual(Date.now() + 7 * 86_400_000);
    }
  });

  it("grant: a choice that becomes ineligible before the click is unchecked, announced and not sent", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({} as never);
    const state = { kairosReason: null as string | null, w1Readiness: "ready" };
    mockGrantWorld(state);
    const qc = wrapWithClient(<AuthorizedAgentsCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Conceder acesso a agentes" }));
    await vi.waitFor(() => expect(screen.getByRole("checkbox", { name: "pc-new" })).toBeDisabled());
    fireEvent.click(screen.getByRole("checkbox", { name: "Atlas" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Kairos" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "pc-off" }));

    // the next refresh: Kairos lost its maintenance tools, pc-ready lost ForgeHub's login
    state.kairosReason = "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS";
    state.w1Readiness = "not_prepared";
    await act(async () => { await qc.invalidateQueries(); });

    await vi.waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("1 agente(s), 1 máquina(s)"));
    expect(screen.getByRole("checkbox", { name: "Kairos" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Kairos" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "pc-ready" })).not.toBeChecked();
    expect(screen.getByTestId("grant-summary")).toHaveTextContent("1 agente · 1 máquina ·");

    fireEvent.click(screen.getByRole("button", { name: "Conceder a 1 agente" }));
    await vi.waitFor(() => expect(grantBodies()).toHaveLength(1));
    expect(grantBodies()[0]).toMatchObject({ grantee_agent_id: "a3", servers: ["w2"], host_groups: [] });
  });

  it("grant: the panel doesn't close while the grant is being saved", async () => {
    vi.mocked(apiClient.post).mockReturnValue(new Promise(() => undefined) as never);
    mockGrantWorld({ kairosReason: null, w1Readiness: "ready" });
    wrap(<AuthorizedAgentsCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Conceder acesso a agentes" }));
    await vi.waitFor(() => expect(screen.getByRole("checkbox", { name: "pc-new" })).toBeDisabled());
    fireEvent.click(screen.getByRole("checkbox", { name: "Atlas" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(screen.getByRole("button", { name: "Conceder a 1 agente" }));
    const panel = screen.getByRole("dialog", { name: "Conceder acesso a agentes" });
    await vi.waitFor(() => expect(panel).toHaveAttribute("aria-busy", "true"));
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByTestId("side-panel-overlay"));
    expect(screen.getByRole("dialog", { name: "Conceder acesso a agentes" })).toBeInTheDocument();
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
