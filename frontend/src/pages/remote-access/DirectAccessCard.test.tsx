import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient, ApiError } from "@/lib/api";
import { DirectAccessCard } from "./DirectAccessCard";
vi.mock("@/lib/api", async (original) => ({ ...(await original<typeof import("@/lib/api")>()), apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));
const ACTIVE = { paused: false, paused_at: null, paused_by: null, reason: null };
const config = { id: "d1", agent_id: "a1", agent_name: "Porthus", purpose: null, allow_elevation: false, reason: null, machines: [], granted_by: "marcelo", opened_at: new Date().toISOString(), expires_at: null, open_ended: true, all_machines: true, duration_hours: 0 };
function setup(configuration: unknown = null, control: unknown = ACTIVE, failInventory = false) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url.endsWith("/direct/control")) return control as never;
    if (url.endsWith("/direct/agents")) return [
      { id: "a1", name: "Porthus", runtime_type: "claude", allowed: true, unsupported_reason: null, configuration },
      { id: "a2", name: "Aramis", runtime_type: "codex", allowed: false, unsupported_reason: null, configuration: null },
      { id: "a3", name: "Lara", runtime_type: "hermes", allowed: false, unsupported_reason: "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS", configuration: null },
    ] as never;
    if (url === "/api/v1/servers") { if (failInventory) throw new Error("inventory unavailable"); return [{ id: "m1", name: "lab-1" }, { id: "m2", name: "srv-app02" }] as never; }
    return [] as never;
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><DirectAccessCard /></QueryClientProvider>);
}
async function edit(name = "Porthus") { fireEvent.click(await screen.findByRole("button", { name: `Configurar ${name}` })); return within(await screen.findByRole("form", { name: `Configurar ${name}` })); }
describe("DirectAccessCard per-agent configuration", () => {
  beforeEach(async () => { vi.clearAllMocks(); await i18n.changeLanguage("pt-BR"); });
  it("replaces opening and closing with per-agent configuration and safe defaults", async () => {
    setup(); expect(await screen.findByText("Aguardando configuração")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abrir acesso" })).not.toBeInTheDocument(); expect(screen.queryByRole("button", { name: "Encerrar" })).not.toBeInTheDocument();
    const form = await edit(); expect(form.getByRole("checkbox", { name: "Todas as máquinas" })).toBeChecked(); expect(form.getByRole("checkbox", { name: "Permitir sudo/docker" })).not.toBeChecked(); expect(form.getByLabelText("Duração")).toHaveValue("0"); expect(form.getByRole("button", { name: "Salvar configuração" })).toBeEnabled();
  });
  it("confirms all coverage once and saves with optional reason and purpose", async () => {
    vi.mocked(apiClient.put).mockRejectedValueOnce(new ApiError("conflict", 409, { detail: { code: "SENSITIVE_CONFIRMATION_REQUIRED", all_machines: true, machines: [] } })).mockResolvedValueOnce({} as never);
    setup(); const form = await edit("Aramis"); fireEvent.click(form.getByRole("button", { name: "Salvar configuração" }));
    expect(await screen.findByText("Inclui todas as máquinas, inclusive produção e clientes.")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(2)); expect(vi.mocked(apiClient.put).mock.calls[1]).toEqual(["/api/v1/remote-access/direct/agents/a2", { all_machines: true, server_ids: [], group_ids: [], duration_hours: 0, allow_elevation: false, purpose: null, reason: null, confirm_sensitive: true }]); await waitFor(() => expect(screen.queryByRole("form")).not.toBeInTheDocument());
  });
  it("drops confirmation when machine selection changes", async () => {
    vi.mocked(apiClient.put).mockRejectedValue(new ApiError("conflict", 409, { detail: { code: "SENSITIVE_CONFIRMATION_REQUIRED", machines: ["srv-app02"] } }));
    setup(); const form = await edit(); fireEvent.click(form.getByRole("checkbox", { name: "Todas as máquinas" })); fireEvent.click(await form.findByRole("checkbox", { name: "srv-app02" })); fireEvent.click(form.getByRole("button", { name: "Salvar configuração" }));
    const dialog = await screen.findByRole("dialog"); fireEvent.click(within(dialog).getByRole("button", { name: "Cancelar" })); fireEvent.click(form.getByRole("checkbox", { name: "lab-1" })); fireEvent.click(form.getByRole("button", { name: "Salvar configuração" }));
    await waitFor(() => expect(apiClient.put).toHaveBeenCalledTimes(2)); expect(vi.mocked(apiClient.put).mock.calls[1][1]).toMatchObject({ confirm_sensitive: false, all_machines: false, server_ids: ["m2", "m1"] });
  });
  it("allows explicit empty coverage and explains denied access", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({} as never); setup(); const form = await edit(); fireEvent.click(form.getByRole("checkbox", { name: "Todas as máquinas" })); expect(form.getByText("Sem máquinas selecionadas, o agente não terá acesso.")).toBeInTheDocument(); fireEvent.click(form.getByRole("button", { name: "Salvar configuração" })); await waitFor(() => expect(apiClient.put).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ all_machines: false, server_ids: [] })));
  });
  it("shows indefinite scope, age warning and saved settings", async () => {
    setup({ ...config, opened_at: new Date(Date.now() - 8 * 86400000).toISOString() }); expect(await screen.findByText("0 h (indeterminado)")).toBeInTheDocument(); expect(screen.getByText("Aberto há mais de 7 dias")).toBeInTheDocument(); const form = await edit(); expect(form.getByLabelText("Duração")).toHaveValue("0"); expect(screen.queryByText(/9999/)).not.toBeInTheDocument();
  });
  it("keeps expired configuration visible as expired", async () => {
    setup({ ...config, open_ended: false, duration_hours: 1, expires_at: "2020-01-01T00:00:00Z", all_machines: false, machines: [{ id: "m2", name: "srv-app02", sensitive: true }] }); expect(await screen.findByText("Prazo encerrado")).toBeInTheDocument(); const form = await edit(); expect(form.getByLabelText("Duração")).toHaveValue("1"); expect(form.getByRole("checkbox", { name: "srv-app02" })).toBeChecked();
  });
  it("preserves edits after a refused save", async () => {
    vi.mocked(apiClient.put).mockRejectedValue(new ApiError("refused", 422, { detail: "Refused configuration" })); setup(); const form = await edit(); fireEvent.change(form.getByLabelText("Motivo (opcional)"), { target: { value: "Corrigir deploy" } }); fireEvent.click(form.getByRole("button", { name: "Salvar configuração" })); expect(await form.findByRole("alert")).toHaveTextContent("Refused configuration"); expect(form.getByLabelText("Motivo (opcional)")).toHaveValue("Corrigir deploy");
  });
  it("blocks save when inventory fails", async () => {
    setup(config, ACTIVE, true); const form = await edit(); expect(await form.findByRole("alert")).toHaveTextContent("Não foi possível carregar as máquinas e grupos"); expect(form.getByRole("button", { name: "Salvar configuração" })).toBeDisabled();
  });
  it("removes after confirmation and preserves running-command notice", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({ agent_id: "a1", closed_accesses: 1, running_commands: 1, notice: "" } as never); setup(config); fireEvent.click(await screen.findByRole("button", { name: "Excluir Porthus da lista" })); expect(apiClient.delete).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "Excluir" })); await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith("/api/v1/remote-access/direct/agents/a1")); expect(await screen.findByText(/1 comando continua em execução/)).toBeInTheDocument();
  });
  it("reactivates paused access without changing configuration", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(ACTIVE as never); setup(config, { paused: true, paused_at: "2026-11-06T12:00:00Z", paused_by: "marcelo", reason: "Incidente" }); expect(await screen.findByText(/pausado por marcelo/)).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "Ativar" })); await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/control:resume", {})); expect(apiClient.put).not.toHaveBeenCalled();
  });
  it("disables unsupported profiles with an explanation", async () => { setup(); expect(await screen.findByRole("button", { name: "Configurar Lara" })).toBeDisabled(); expect(screen.getByText(/não expõe as ferramentas de manutenção/)).toBeInTheDocument(); });
});
