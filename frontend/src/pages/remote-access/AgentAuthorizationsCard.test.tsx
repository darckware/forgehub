import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient, ApiError } from "@/lib/api";
import { AgentAuthorizationsCard } from "./AgentAuthorizationsCard";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const DELEG = "/api/v1/governed/authority-delegations";
const DIRECT = "/api/v1/remote-access/direct/agents";
const future = new Date(Date.now() + 30 * 86_400_000).toISOString();
const agent = (id: string, name: string, runtime_type: string) => ({ id, name, is_active: true, status: "active", agent_type: "executor", runtime_type });
const delegation = (grantee: string, risk: string, servers = ["w1"]) => ({
  servers, host_groups: [], id: `d-${grantee}`, grantee_id: grantee, scope_type: "organization", allowed_actions: ["remote_access.execute"],
  expires_at: future, status: "active", reason: null, max_risk: risk, product_id: null, project_id: null,
});
const config = (agentId: string, extra: Record<string, unknown> = {}) => ({
  id: `c-${agentId}`, agent_id: agentId, agent_name: "", purpose: null, allow_elevation: true, reason: null, machines: [],
  granted_by: "marcelo", opened_at: new Date().toISOString(), expires_at: null, open_ended: true, all_machines: true, duration_hours: 0, ...extra,
});
const direct = (id: string, name: string, runtime: string, extra: Record<string, unknown> = {}) => ({
  id, name, runtime_type: runtime, allowed: false, unsupported_reason: null, scripts_unsupported_reason: null, configuration: null, ...extra,
});

interface World {
  delegations: unknown[];
  delegationsError?: boolean;
  serversError?: boolean;
  directAgents: unknown[];
  w1Readiness: string;
  control: unknown;
}
let world: World;

function mockApi() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers" && world.serversError) throw new Error("inventory unavailable");
    if (url === "/api/v1/servers") return [{ id: "w1", name: "pc-ready" }, { id: "w2", name: "pc-off" }, { id: "w3", name: "pc-new" }] as never;
    if (url === "/api/v1/host-groups") return [{ id: "g1", name: "Gatling", server_ids: ["w2"] }] as never;
    if (url === "/api/v1/servers/readiness") {
      return { entries: [
        { server_id: "w1", readiness: world.w1Readiness, status: world.w1Readiness === "ready" ? "complete" : "not_prepared" },
        { server_id: "w2", readiness: "offline", status: "offline" },
        { server_id: "w3", readiness: "not_prepared", status: "not_prepared" },
      ], checked_at: "", tailnet_available: true, ssh_checked_at: null } as never;
    }
    if (url === "/api/v1/remote-access/direct/control") return world.control as never;
    if (url === DIRECT) return world.directAgents as never;
    if (url.startsWith("/api/v1/agents")) {
      return [agent("a1", "Aegis", "codex"), agent("a2", "Porthus", "claude"), agent("a3", "Atlas", "codex"),
        agent("a4", "Maia", "hermes"), agent("a5", "Kairos", "hermes")] as never;
    }
    if (url.startsWith(DELEG)) {
      if (world.delegationsError) throw new Error("delegations unavailable");
      return world.delegations as never;
    }
    return [] as never;
  });
}

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><MemoryRouter><AgentAuthorizationsCard /></MemoryRouter></QueryClientProvider>);
  return qc;
}

const posts = (url = DELEG) => vi.mocked(apiClient.post).mock.calls.filter(([u]) => u === url).map(([, body]) => body as Record<string, unknown>);
const panel = () => screen.getByRole("dialog", { name: /Autorização de|Adicionar agente/ });

async function openEdit(name: string) {
  fireEvent.click(await screen.findByRole("button", { name: `Editar ${name}` }));
  const p = panel();
  await vi.waitFor(() => expect(within(p).getByRole("checkbox", { name: "pc-new" })).toBeDisabled());
  return within(p);
}

async function clickAdd() {
  const add = await screen.findByRole("button", { name: "Adicionar agente" });
  await vi.waitFor(() => expect(add).toBeEnabled());
  fireEvent.click(add);
}

async function openAdd(name: string) {
  await clickAdd();
  const p = within(panel());
  await p.findByRole("option", { name });
  fireEvent.change(p.getByLabelText("Agente"), { target: { value: (await p.findByRole("option", { name }) as HTMLOptionElement).value } });
  await vi.waitFor(() => expect(p.getByRole("checkbox", { name: "pc-new" })).toBeDisabled());
  return p;
}

describe("Agentes autorizados (one card, one panel per agent)", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    world = {
      delegations: [delegation("a1", "medium")],
      directAgents: [
        direct("a1", "Aegis", "codex"),
        direct("a2", "Porthus", "claude", { allowed: true, configuration: config("a2") }),
        direct("a3", "Atlas", "codex"),
        direct("a4", "Maia", "hermes", { unsupported_reason: "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS", scripts_unsupported_reason: "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS" }),
        direct("a5", "Kairos", "hermes", { unsupported_reason: "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS" }),
      ],
      w1Readiness: "ready",
      control: { paused: false, paused_at: null, paused_by: null, reason: null },
    };
    mockApi();
    vi.mocked(apiClient.post).mockImplementation(async (url: string, body?: unknown) =>
      (url === DELEG ? { ...(body as object), id: "d-new", expires_at: (body as { expires_at: string }).expires_at } : {}) as never);
    vi.mocked(apiClient.put).mockResolvedValue({} as never);
    vi.mocked(apiClient.delete).mockResolvedValue({ agent_id: "x", closed_accesses: 1, running_commands: 0, notice: "" } as never);
    await i18n.changeLanguage("pt-BR");
  });

  it("shows one row per agent with any permission, both permissions at a glance", async () => {
    wrap();
    const aegis = await screen.findByTestId("authz-row-a1");
    expect(within(aegis).getByText("até Alteração")).toBeInTheDocument();
    expect(within(aegis).getByText("1 máquina")).toBeInTheDocument();
    expect(within(aegis).getAllByText("Não autorizado")).toHaveLength(1); // no free commands
    const porthus = await screen.findByTestId("authz-row-a2");
    expect(within(porthus).getByText("Todas as máquinas")).toBeInTheDocument();
    expect(within(porthus).getByText(/0 h \(indeterminado\)/)).toBeInTheDocument();
    expect(within(porthus).getByText("sudo/docker")).toBeInTheDocument();
    // agents with no permission aren't rows
    expect(screen.queryByTestId("authz-row-a3")).not.toBeInTheDocument();
    expect(screen.queryByText("Agentes autorizados a fazer manutenção")).not.toBeInTheDocument();
    expect(screen.queryByText("Acesso direto")).not.toBeInTheDocument();
  });

  it("adds an agent with library scripts only: one delegation POST with the chosen scope, nothing else", async () => {
    wrap();
    const p = await openAdd("Atlas");
    expect(p.getByRole("checkbox", { name: /Permitir scripts da biblioteca/ })).toBeChecked();
    expect(p.getByRole("checkbox", { name: /Permitir comandos livres/ })).not.toBeChecked();
    expect(p.getByLabelText("Risco máximo")).toHaveValue("medium");
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Scripts da biblioteca: conceder · até Alteração · nenhuma máquina · 1 dia");
    expect(p.getByRole("button", { name: "Salvar" })).toBeDisabled(); // scripts need a scope
    fireEvent.click(p.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(p.getByRole("checkbox", { name: "Gatling" }));
    fireEvent.change(p.getByLabelText("Risco máximo"), { target: { value: "high" } });
    fireEvent.change(p.getByLabelText("Validade"), { target: { value: "7" } });
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Scripts da biblioteca: conceder · até Destrutivo · 1 máquina · 1 grupo · 7 dias");
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Comandos livres: sem alteração");
    const before = Date.now();
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts()).toHaveLength(1);
    const body = posts()[0];
    expect(body).toMatchObject({
      grantee_agent_id: "a3", allowed_actions: ["remote_access.execute"], scope_type: "organization",
      servers: ["w1"], host_groups: ["g1"], max_risk: "high", reason: "Manutenção de máquinas pelo Acesso Remoto",
    });
    expect(Date.parse(body.expires_at as string)).toBeGreaterThanOrEqual(before + 7 * 86_400_000);
    expect(apiClient.put).not.toHaveBeenCalled();
    expect(apiClient.delete).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Autorização de Atlas salva.");
  });

  it("changing the scripts risk creates the new delegation first, then revokes the old one; commands untouched", async () => {
    wrap();
    const p = await openEdit("Aegis");
    expect(p.getByLabelText("Validade")).toHaveValue("0"); // keep current expiry
    expect(p.getByRole("checkbox", { name: "pc-ready" })).toBeChecked();
    expect(p.getByRole("button", { name: "Salvar" })).toBeDisabled(); // nothing changed yet
    fireEvent.change(p.getByLabelText("Risco máximo"), { target: { value: "low" } });
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const urls = vi.mocked(apiClient.post).mock.calls.map(([u]) => u);
    expect(urls).toEqual([DELEG, `${DELEG}/d-a1:revoke`]);
    expect(posts()[0]).toMatchObject({ grantee_agent_id: "a1", servers: ["w1"], host_groups: [], max_risk: "low", expires_at: future });
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("turning free commands on saves the direct configuration, with the sensitive-coverage confirmation", async () => {
    vi.mocked(apiClient.put)
      .mockRejectedValueOnce(new ApiError("conflict", 409, { detail: { code: "SENSITIVE_CONFIRMATION_REQUIRED", all_machines: true, machines: [] } }))
      .mockResolvedValueOnce({} as never);
    wrap();
    const p = await openEdit("Aegis");
    fireEvent.click(p.getByRole("checkbox", { name: /Permitir comandos livres/ }));
    fireEvent.click(p.getByRole("checkbox", { name: "Todas as máquinas, inclusive as preparadas depois" }));
    fireEvent.change(p.getByLabelText("Duração"), { target: { value: "4" } });
    fireEvent.change(p.getByLabelText("Motivo (opcional)"), { target: { value: "Suporte do chamado" } });
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Comandos livres: salvar · Todas as máquinas · 4 horas · sem sudo/docker");
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Inclui todas as máquinas, inclusive produção e clientes.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(vi.mocked(apiClient.put).mock.calls).toEqual([
      [`${DIRECT}/a1`, { all_machines: true, server_ids: [], group_ids: [], reason: "Suporte do chamado", purpose: null, duration_hours: 4, allow_elevation: false, confirm_sensitive: false }],
      [`${DIRECT}/a1`, { all_machines: true, server_ids: [], group_ids: [], reason: "Suporte do chamado", purpose: null, duration_hours: 4, allow_elevation: false, confirm_sensitive: true }],
    ]);
    // The reason belongs to the commands: the scripts delegation is untouched.
    expect(posts()).toHaveLength(0);
  });

  it("reports a partial failure per permission and retries only what failed", async () => {
    vi.mocked(apiClient.put)
      .mockRejectedValueOnce(new ApiError("refused", 422, { detail: "Refused configuration" }))
      .mockResolvedValueOnce({} as never);
    wrap();
    const p = await openAdd("Atlas");
    fireEvent.click(p.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(p.getByRole("checkbox", { name: /Permitir comandos livres/ }));
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    const alert = await p.findByRole("alert");
    expect(alert).toHaveTextContent("Scripts da biblioteca: salvo.");
    expect(alert).toHaveTextContent("Comandos livres: não salvo: Refused configuration");
    expect(posts()).toHaveLength(1);
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Scripts da biblioteca: sem alteração");
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts()).toHaveLength(1); // scripts not granted twice
    expect(apiClient.put).toHaveBeenCalledTimes(2);
    expect(vi.mocked(apiClient.put).mock.calls[1][1]).toMatchObject({ all_machines: false, server_ids: ["w1"], group_ids: [] });
  });

  it("turning free commands off removes the direct configuration only", async () => {
    wrap();
    const p = await openEdit("Porthus");
    expect(p.getByRole("checkbox", { name: /Permitir scripts da biblioteca/ })).not.toBeChecked();
    fireEvent.click(p.getByRole("checkbox", { name: /Permitir comandos livres/ }));
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Comandos livres: remover");
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith(`${DIRECT}/a2`));
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("disables each permission with its own reason when the agent can't use it", async () => {
    wrap();
    let p = await openAdd("Maia");
    const scripts = p.getByRole("checkbox", { name: /Permitir scripts da biblioteca/ });
    const commands = p.getByRole("checkbox", { name: /Permitir comandos livres/ });
    expect(scripts).toBeDisabled();
    expect(scripts).not.toBeChecked();
    expect(scripts).toHaveAccessibleDescription("o MCP forgehub do perfil não expõe as ferramentas de manutenção.");
    expect(commands).toBeDisabled();
    fireEvent.keyDown(window, { key: "Escape" });
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    p = await openAdd("Kairos");
    expect(p.getByRole("checkbox", { name: /Permitir scripts da biblioteca/ })).toBeEnabled();
    expect(p.getByRole("checkbox", { name: /Permitir comandos livres/ })).toBeDisabled();
    expect(p.getByRole("checkbox", { name: /Permitir comandos livres/ }))
      .toHaveAccessibleDescription("o MCP forgehub do perfil não expõe as ferramentas de manutenção.");
  });

  it("a Hermes agent starts on Somente leitura, and turning commands on asks for a confirmation", async () => {
    world.directAgents = [...world.directAgents.slice(0, 4), direct("a5", "Kairos", "hermes")];
    wrap();
    const p = await openAdd("Kairos");
    expect(p.getByRole("checkbox", { name: /Permitir scripts da biblioteca/ })).toBeChecked();
    expect(p.getByLabelText("Risco máximo")).toHaveValue("low");
    expect(p.getByRole("checkbox", { name: /Permitir comandos livres/ })).not.toBeChecked();
    expect(p.getByRole("button", { name: "Somente leitura (monitoramento)" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(p.getByRole("checkbox", { name: /Permitir comandos livres/ }));
    const confirm = await screen.findByText("Liberar comandos livres para Kairos?");
    const dialog = confirm.closest("[role=dialog],[role=alertdialog]") as HTMLElement;
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(p.getByRole("checkbox", { name: /Permitir comandos livres/ })).not.toBeChecked();

    fireEvent.click(p.getByRole("checkbox", { name: /Permitir comandos livres/ }));
    const again = (await screen.findByText("Liberar comandos livres para Kairos?")).closest("[role=dialog],[role=alertdialog]") as HTMLElement;
    fireEvent.click(within(again).getByRole("button", { name: "Liberar mesmo assim" }));
    expect(p.getByRole("checkbox", { name: /Permitir comandos livres/ })).toBeChecked();
    expect(p.getByRole("button", { name: "Somente leitura (monitoramento)" })).toHaveAttribute("aria-pressed", "false");
  });

  it("the Somente leitura preset sets scripts on at read risk and commands and sudo/docker off", async () => {
    wrap();
    const p = await openEdit("Porthus"); // commands on, with sudo/docker
    expect(p.getByRole("checkbox", { name: "Permitir sudo/docker" })).toBeChecked();
    fireEvent.click(p.getByRole("button", { name: "Somente leitura (monitoramento)" }));
    expect(p.getByRole("checkbox", { name: /Permitir scripts da biblioteca/ })).toBeChecked();
    expect(p.getByLabelText("Risco máximo")).toHaveValue("low");
    expect(p.getByRole("checkbox", { name: /Permitir comandos livres/ })).not.toBeChecked();
    fireEvent.click(p.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(posts()).toHaveLength(1);
    expect(posts()[0]).toMatchObject({ grantee_agent_id: "a2", max_risk: "low", servers: ["w1"] });
    expect(apiClient.delete).toHaveBeenCalledWith(`${DIRECT}/a2`);
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("machine scope: unprepared machines disabled with the reason, search, select visible", async () => {
    wrap();
    const p = await openAdd("Atlas");
    expect(p.getByRole("checkbox", { name: "pc-new" })).toHaveAccessibleDescription("preparar primeiro");
    expect(p.getByRole("checkbox", { name: "pc-off" })).toBeEnabled();
    expect(p.getByRole("checkbox", { name: "pc-off" })).toHaveAccessibleDescription("offline agora");
    fireEvent.change(p.getByRole("searchbox", { name: "Buscar máquina" }), { target: { value: "pc-" } });
    fireEvent.click(p.getByRole("button", { name: "Selecionar todas as visíveis" }));
    expect(p.getByRole("checkbox", { name: "pc-ready" })).toBeChecked();
    expect(p.getByRole("checkbox", { name: "pc-off" })).toBeChecked();
    expect(p.getByRole("checkbox", { name: "pc-new" })).not.toBeChecked();
    expect(p.getByTestId("authz-summary")).toHaveTextContent("2 máquinas");
  });

  it("a machine that becomes unprepared while the panel is open is unchecked, announced and not sent", async () => {
    const qc = wrap();
    const p = await openAdd("Atlas");
    fireEvent.click(p.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(p.getByRole("checkbox", { name: "pc-off" }));
    world.w1Readiness = "not_prepared";
    await act(async () => { await qc.invalidateQueries(); });
    await vi.waitFor(() => expect(p.getByText("1 máquina deixou de poder receber o acesso e foi desmarcada.")).toBeInTheDocument());
    expect(p.getByRole("checkbox", { name: "pc-ready" })).not.toBeChecked();
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0]).toMatchObject({ servers: ["w2"] });
  });

  it("the panel doesn't close while saving", async () => {
    vi.mocked(apiClient.post).mockReturnValue(new Promise(() => undefined) as never);
    wrap();
    const p = await openAdd("Atlas");
    fireEvent.click(p.getByRole("checkbox", { name: "pc-ready" }));
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(panel()).toHaveAttribute("aria-busy", "true"));
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByTestId("side-panel-overlay"));
    expect(panel()).toBeInTheDocument();
  });

  it("removes every permission of an agent after a confirmation", async () => {
    world.delegations = [delegation("a2", "low")];
    wrap();
    fireEvent.click(await screen.findByRole("button", { name: "Remover as permissões de Porthus" }));
    expect(apiClient.delete).not.toHaveBeenCalled();
    const dialog = (await screen.findByText("Remover as permissões de Porthus?")).closest("[role=dialog],[role=alertdialog]") as HTMLElement;
    fireEvent.click(within(dialog).getByRole("button", { name: "Excluir" }));
    await vi.waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith(`${DIRECT}/a2`));
    expect(apiClient.post).toHaveBeenCalledWith(`${DELEG}/d-a2:revoke`);
    expect(await screen.findByText(/Permissões de Porthus removidas\./)).toBeInTheDocument();
  });

  it("pauses from the card header after a confirmation, and resumes", async () => {
    wrap();
    const pauseButton = await screen.findByRole("button", { name: "Pausar" });
    await vi.waitFor(() => expect(pauseButton).toBeEnabled());
    fireEvent.click(pauseButton);
    expect(apiClient.post).not.toHaveBeenCalled();
    const dialog = (await screen.findByText("Pausar o acesso dos agentes?")).closest("[role=dialog],[role=alertdialog]") as HTMLElement;
    fireEvent.change(within(dialog).getByLabelText("Motivo (opcional)"), { target: { value: "Incidente" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Pausar" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/control:pause", { reason: "Incidente" }));
  });

  it("resumes a paused access without touching any permission", async () => {
    world.control = { paused: true, paused_at: "2026-11-06T12:00:00Z", paused_by: "marcelo", reason: "Incidente" };
    wrap();
    expect(await screen.findByText(/pausado por marcelo/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ativar" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/control:resume", {}));
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("changing only a commands setting keeps the commands' own machines, even when the scripts have others", async () => {
    world.directAgents = [
      direct("a1", "Aegis", "codex", { allowed: true, configuration: config("a1", {
        all_machines: false, allow_elevation: false, machines: [{ id: "w2", name: "pc-off", sensitive: false }] }) }),
      ...world.directAgents.slice(1),
    ];
    wrap();
    const p = await openEdit("Aegis");
    expect(p.getByText(/Os comandos e os scripts têm máquinas diferentes/)).toBeInTheDocument();
    expect(p.getByRole("checkbox", { name: "pc-ready" })).toBeChecked(); // the picker shows the scripts' machines
    fireEvent.change(p.getByLabelText("Duração"), { target: { value: "24" } });
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Scripts da biblioteca: sem alteração");
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1));
    expect(vi.mocked(apiClient.put).mock.calls[0]).toEqual([`${DIRECT}/a1`, {
      all_machines: false, server_ids: ["w2"], group_ids: [], reason: null, purpose: null, duration_hours: 24,
      allow_elevation: false, confirm_sensitive: false,
    }]);
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("changing only the commands' reason doesn't touch the scripts delegation", async () => {
    world.directAgents = [direct("a1", "Aegis", "codex", { allowed: true, configuration: config("a1", { allow_elevation: false }) }),
      ...world.directAgents.slice(1)];
    wrap();
    const p = await openEdit("Aegis");
    fireEvent.change(p.getByLabelText("Motivo (opcional)"), { target: { value: "Chamado 12" } });
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(1));
    expect(vi.mocked(apiClient.put).mock.calls[0][1]).toMatchObject({ all_machines: true, reason: "Chamado 12" });
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it("when the old delegation can't be revoked, says so, keeps the new one and retries only the revoke", async () => {
    let revokeFails = true;
    vi.mocked(apiClient.post).mockImplementation(async (url: string, body?: unknown) => {
      if (url.endsWith(":revoke") && revokeFails) throw new ApiError("boom", 500, { detail: "revoke failed" });
      return (url === DELEG ? { ...(body as object), id: "d-new" } : {}) as never;
    });
    wrap();
    const p = await openEdit("Aegis");
    fireEvent.change(p.getByLabelText("Risco máximo"), { target: { value: "high" } });
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    const alert = await p.findByRole("alert");
    expect(alert).toHaveTextContent("nova permissão gravada; a anterior continua ativa até ser revogada. Tente salvar de novo.");
    expect(p.getByTestId("authz-summary")).toHaveTextContent("Scripts da biblioteca: revogar a permissão anterior");
    expect(posts()).toHaveLength(1);
    revokeFails = false;
    vi.mocked(apiClient.post).mockClear();
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(vi.mocked(apiClient.post).mock.calls.map(([u]) => u)).toEqual([`${DELEG}/d-a1:revoke`]); // no second grant
  });

  it("several different script delegations: one line each, and replacing them needs an explicit confirmation", async () => {
    const soon = new Date(Date.now() + 2 * 86_400_000).toISOString();
    world.delegations = [
      { ...delegation("a1", "medium"), id: "d-1" },
      { ...delegation("a1", "low", ["w2"]), id: "d-2", expires_at: soon },
    ];
    wrap();
    const row = await screen.findByTestId("authz-row-a1");
    expect(within(row).getAllByTestId("authz-script-grant")).toHaveLength(2);
    const p = await openEdit("Aegis");
    expect(p.getByTestId("authz-irregular")).toHaveTextContent("Este agente tem 2 permissões de scripts diferentes:");
    fireEvent.change(p.getByLabelText("Risco máximo"), { target: { value: "low" } });
    expect(p.getByRole("button", { name: "Salvar" })).toBeDisabled();
    const confirm = p.getByRole("checkbox", { name: /Substituir as 2 permissões de scripts por uma só: até Leitura · 2 máquinas/ });
    fireEvent.click(confirm);
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // "Manter" keeps the earliest expiry, never the latest
    expect(posts()[0]).toMatchObject({ max_risk: "low", expires_at: soon });
    expect(vi.mocked(apiClient.post).mock.calls.map(([u]) => u)).toEqual([DELEG, `${DELEG}/d-2:revoke`, `${DELEG}/d-1:revoke`]);
  });

  it("turning commands off reports the commands still running; the row shows since, purpose and reason", async () => {
    world.directAgents = [world.directAgents[0], direct("a2", "Porthus", "claude", { allowed: true,
      configuration: config("a2", { purpose: "support", reason: "Plantão" }) }), ...world.directAgents.slice(2)];
    vi.mocked(apiClient.delete).mockResolvedValue({ agent_id: "a2", closed_accesses: 1, running_commands: 2, notice: "" } as never);
    wrap();
    const row = await screen.findByTestId("authz-row-a2");
    expect(within(row).getByText(/Configurado em/)).toBeInTheDocument();
    expect(within(row).getByText("Suporte")).toBeInTheDocument();
    expect(within(row).getByText("Plantão")).toBeInTheDocument();
    const p = await openEdit("Porthus");
    fireEvent.click(p.getByRole("checkbox", { name: /Permitir comandos livres/ }));
    fireEvent.click(p.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText(/2 comandos continuam em execução/)).toBeInTheDocument();
  });

  it("blocks a save that needs the machines when the inventory fails, but not a pure revoke", async () => {
    world.serversError = true;
    wrap();
    await clickAdd();
    const p = within(panel());
    fireEvent.change(p.getByLabelText("Agente"), { target: { value: (await p.findByRole("option", { name: "Atlas" }) as HTMLOptionElement).value } });
    expect(await p.findByText(/Não foi possível carregar as máquinas e grupos/)).toBeInTheDocument();
    expect(p.getByRole("button", { name: "Salvar" })).toBeDisabled();
    fireEvent.keyDown(window, { key: "Escape" });

    fireEvent.click(await screen.findByRole("button", { name: "Editar Aegis" }));
    const q = within(panel());
    fireEvent.click(q.getByRole("checkbox", { name: /Permitir scripts da biblioteca/ }));
    expect(q.getByRole("button", { name: "Salvar" })).toBeEnabled();
    fireEvent.click(q.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalledWith(`${DELEG}/d-a1:revoke`));
  });

  it("removal retry skips what was done and takes 'not on the list' as done", async () => {
    world.delegations = [delegation("a2", "low")];
    vi.mocked(apiClient.delete)
      .mockRejectedValueOnce(new ApiError("down", 502, { detail: "bridge down" }))
      .mockRejectedValueOnce(new ApiError("gone", 404, { detail: "This agent is not on the list" }));
    wrap();
    fireEvent.click(await screen.findByRole("button", { name: "Remover as permissões de Porthus" }));
    const dialog = (await screen.findByText("Remover as permissões de Porthus?")).closest("[role=dialog],[role=alertdialog]") as HTMLElement;
    fireEvent.click(within(dialog).getByRole("button", { name: "Excluir" }));
    expect(await within(dialog).findByText(/bridge down/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Excluir" }));
    expect(await screen.findByText(/Permissões de Porthus removidas\./)).toBeInTheDocument();
    expect(vi.mocked(apiClient.post).mock.calls.filter(([u]) => u === `${DELEG}/d-a2:revoke`)).toHaveLength(1);
    expect(apiClient.delete).toHaveBeenCalledTimes(2);
  });

  it("removal revokes future and project-scoped script delegations too, and the row shows them", async () => {
    const later = new Date(Date.now() + 86_400_000).toISOString();
    world.delegations = [
      { ...delegation("a1", "medium"), id: "d-future", valid_from: later },
      { ...delegation("a1", "low"), id: "d-project", project_id: "p1" },
    ];
    wrap();
    const row = await screen.findByTestId("authz-row-a1");
    expect(within(row).getByText(/a partir de/)).toBeInTheDocument();
    expect(within(row).getByText("só em um produto/projeto")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remover as permissões de Aegis" }));
    const dialog = (await screen.findByText("Remover as permissões de Aegis?")).closest("[role=dialog],[role=alertdialog]") as HTMLElement;
    fireEvent.click(within(dialog).getByRole("button", { name: "Excluir" }));
    await vi.waitFor(() => expect(screen.getByText(/Permissões de Aegis removidas\./)).toBeInTheDocument());
    const revoked = vi.mocked(apiClient.post).mock.calls.map(([u]) => u).sort();
    expect(revoked).toEqual([`${DELEG}/d-future:revoke`, `${DELEG}/d-project:revoke`]);
  });

  it("when the permissions can't be read, says so and offers nothing to add or edit", async () => {
    world.delegationsError = true;
    wrap();
    expect(await screen.findByText(/Não foi possível ler as permissões dos agentes/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Adicionar agente" })).toBeDisabled();
    expect(screen.queryByText(/Nenhum agente autorizado/)).not.toBeInTheDocument();
  });
});

describe("count strings use plurals (pt-BR 0 is not singular)", () => {
  it.each([
    ["remoteAccess:agents.summary.machines", 0, "nenhuma máquina"],
    ["remoteAccess:agents.summary.machines", 1, "1 máquina"],
    ["remoteAccess:agents.summary.machines", 2, "2 máquinas"],
    ["remoteAccess:rotation.selected", 0, "Nenhuma máquina selecionada"],
    ["remoteAccess:rotation.selected", 1, "1 máquina selecionada"],
    ["remoteAccess:rotation.selected", 3, "3 máquinas selecionadas"],
  ])("%s with %i", async (key, count, expected) => {
    await i18n.changeLanguage("pt-BR");
    expect(i18n.t(key, { count })).toBe(expected);
  });

  it("English and Spanish too", async () => {
    await i18n.changeLanguage("en");
    expect(i18n.t("remoteAccess:agents.summary.machines", { count: 0 })).toBe("no machines");
    expect(i18n.t("remoteAccess:agents.summary.machines", { count: 1 })).toBe("1 machine");
    await i18n.changeLanguage("es");
    expect(i18n.t("remoteAccess:rotation.selected", { count: 0 })).toBe("Ninguna máquina seleccionada");
    await i18n.changeLanguage("pt-BR");
  });
});
