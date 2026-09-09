import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import NexoAgentsPage from ".";

vi.mock("@/lib/api", async (original) => ({ ...await original<typeof import("@/lib/api")>(), apiClient: { get: vi.fn(), post: vi.fn(), postDownload: vi.fn() } }));
const time = "2026-09-08T12:00:00Z";
const build = { id: "build-1", git_sha: "a".repeat(40), agent_version: "1.2", os_kind: "linux", status: "ready", completed_at: time, sha256: "b".repeat(64) };
const installation = { id: "install-1", workstation_id: "ws-1", client_id: "client-1", client_name: "Acme", workstation_hostname: "desk-01", os_kind: "linux", status: "outdated", build_id: "build-1", expected_version: "1.2", detected_version: "1.1", package_generated_at: time, last_report_at: time };
let payloads: Record<string, unknown>;
let failures: Set<string>;
let queryClient: QueryClient;
function Location() { return <output data-testid="location">{useLocation().search}</output>; }
function renderPage(path = "/nexo-agents") {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[path]}><NexoAgentsPage /><Location /></MemoryRouter></QueryClientProvider>);
}
beforeEach(async () => {
  await i18n.changeLanguage("pt-BR");
  failures = new Set();
  payloads = {
    "/api/v1/nexo-agent-builds": { source: { git_sha: build.git_sha, agent_version: "1.2" }, builds: [build] },
    "/api/v1/nexo-installations": [installation],
    "/api/v1/clients": [{ id: "client-1", name: "Acme" }],
    "/api/v1/workstations": [{ id: "ws-1", client_id: "client-1", hostname: "desk-01", os_kind: "linux" }, { id: "ws-2", client_id: "client-1", hostname: "desk-02", os_kind: "windows" }],
    "/api/v1/nexo-installations/install-1": { ...installation, events: [{ id: "event-1", event_type: "package_generated", to_status: "package_ready", created_at: time }, { id: "event-2", event_type: "first_report", to_status: "outdated", created_at: time }] },
  };
  vi.mocked(apiClient.get).mockImplementation(async (path) => {
    if (failures.has(path)) throw new Error("unavailable");
    return payloads[path] as never;
  });
  vi.mocked(apiClient.post).mockResolvedValue([build]);
  vi.mocked(apiClient.postDownload).mockResolvedValue({ blob: new Blob(["archive"]), filename: "nexo-agent.zip" });
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:nexo"), revokeObjectURL: vi.fn() }));
});
afterEach(() => { queryClient?.clear(); vi.restoreAllMocks(); vi.clearAllMocks(); });

describe("Nexo agents administration", () => {
  it("blocks duplicate package generation and dismissal while saving", async () => {
    let complete!: (result: { blob: Blob; filename: string }) => void;
    vi.mocked(apiClient.postDownload).mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderPage();
    fireEvent.click(within((await within(screen.getByRole("table")).findByText("desk-01")).closest("tr")!).getByRole("button", { name: /Gerar e baixar/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirmar geração" }));
    await waitFor(() => expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true"));
    expect(screen.getByRole("button", { name: "Confirmar geração" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await act(async () => complete({ blob: new Blob(["zip"]), filename: "nexo.zip" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(apiClient.postDownload).toHaveBeenCalledTimes(1);
  });
  it("shows build progress and prevents duplicate refresh requests", async () => {
    let complete!: (result: unknown) => void;
    vi.mocked(apiClient.post).mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    renderPage();
    await screen.findByText("Pronto");
    fireEvent.click(screen.getByRole("button", { name: "Atualizar builds" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Atualizar builds" })).toBeDisabled());
    expect(screen.getByText("Compilando as plataformas. Aguarde a conclusão.")).toBeInTheDocument();
    await act(async () => complete([build]));
    await waitFor(() => expect(screen.getByRole("button", { name: "Atualizar builds" })).toBeEnabled());
  });
  it("recovers history after a failed detail request", async () => {
    failures.add("/api/v1/nexo-installations/install-1");
    renderPage();
    fireEvent.click(within((await within(screen.getByRole("table")).findByText("desk-01")).closest("tr")!).getByRole("button", { name: /Histórico/ }));
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText("Não foi possível carregar o histórico.")).toBeInTheDocument();
    failures.clear();
    fireEvent.click(within(dialog).getByRole("button", { name: "Tentar novamente" }));
    expect(await within(dialog).findByText("Primeiro reporte")).toBeInTheDocument();
  });
  it("provides all page translation keys in each supported language", async () => {
    const en = await import("@/i18n/locales/en/nexoAgents.json");
    const pt = await import("@/i18n/locales/pt-BR/nexoAgents.json");
    const es = await import("@/i18n/locales/es/nexoAgents.json");
    const keys = (value: object, prefix = ""): string[] => Object.entries(value).flatMap(([key, item]) => typeof item === "object" ? keys(item, `${prefix}${key}.`) : [`${prefix}${key}`]).sort();
    expect(keys(en.default)).toEqual(keys(pt.default));
    expect(keys(es.default)).toEqual(keys(pt.default));
    await i18n.changeLanguage("es");
    renderPage();
    expect(screen.getByRole("heading", { name: "Agentes Nexo" })).toBeInTheDocument();
    expect(screen.getByLabelText("Sistema operativo")).toBeInTheDocument();
  });
  it("filters installations with labeled URL-backed controls and text states", async () => {
    renderPage();
    expect(await within(screen.getByRole("table")).findByText("desk-01")).toBeInTheDocument();
    expect(document.title).toBe("Agentes Nexo — ForgeHub");
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "outdated" } });
    expect(screen.getByRole("table")).toHaveTextContent("Desatualizado");
    expect(within(screen.getByRole("table")).queryByText("desk-02")).not.toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("status=outdated");
    fireEvent.change(screen.getByLabelText("Sistema operacional"), { target: { value: "windows" } });
    expect(screen.getByText("Nenhuma estação corresponde aos filtros.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Limpar filtros" }));
    expect(within(screen.getByRole("table")).getByText("desk-02")).toBeInTheDocument();
  });
  it("restores client and workstation filters from the URL", async () => {
    renderPage("/nexo-agents?client=client-1&workstation=ws-1");
    expect(await screen.findByText("desk-01", { selector: "td p" })).toBeInTheDocument();
    expect(screen.getByLabelText("Cliente")).toHaveValue("client-1");
    expect(screen.getByLabelText("Estação")).toHaveValue("ws-1");
    expect(within(screen.getByRole("table")).queryByText("desk-02")).not.toBeInTheDocument();
  });
  it("confirms token rotation before generating and saving the server filename", async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { expect(this.download).toBe("nexo-agent.zip"); });
    renderPage();
    const row = (await within(screen.getByRole("table")).findByText("desk-01")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: /Gerar e baixar/ }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("desk-01");
    expect(dialog).toHaveTextContent("token anterior deixará de funcionar");
    expect(apiClient.postDownload).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("button", { name: "Cancelar" })).toHaveFocus();
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirmar geração" }));
    await waitFor(() => expect(apiClient.postDownload).toHaveBeenCalledWith("/api/v1/workstations/ws-1/installation-package?build_id=build-1"));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:nexo");
    expect(await screen.findByText("Pacote gerado. Download iniciado.")).toBeInTheDocument();
  });
  it("keeps generation failure in a stable dialog region and allows retry", async () => {
    vi.mocked(apiClient.postDownload).mockRejectedValue(new Error("secret diagnostic"));
    renderPage();
    fireEvent.click(within((await within(screen.getByRole("table")).findByText("desk-01")).closest("tr")!).getByRole("button", { name: /Gerar e baixar/ }));
    const errorRegion = screen.getByTestId("generation-feedback");
    fireEvent.click(screen.getByRole("button", { name: "Confirmar geração" }));
    await waitFor(() => expect(errorRegion).toHaveTextContent("Não foi possível gerar ou baixar"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByText("secret diagnostic")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirmar geração" })).toBeEnabled();
  });
  it("renders lifecycle history and restores focus after Escape", async () => {
    renderPage();
    const trigger = within((await within(screen.getByRole("table")).findByText("desk-01")).closest("tr")!).getByRole("button", { name: /Histórico/ });
    trigger.focus(); fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog");
    expect(await within(dialog).findByText("Primeiro reporte")).toBeInTheDocument();
    expect(within(dialog).getByText("Pacote gerado")).toBeInTheDocument();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });
  it("shows loading with stable table geometry", () => {
    vi.mocked(apiClient.get).mockImplementation(() => new Promise(() => {}));
    renderPage();
    expect(screen.getByText("Carregando instalações…")).toBeInTheDocument();
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Atualizar builds" })).toBeDisabled();
  });
  it("shows an actionable empty state", async () => {
    payloads["/api/v1/workstations"] = []; payloads["/api/v1/nexo-installations"] = [];
    renderPage();
    expect(await screen.findByText("Nenhuma estação cadastrada.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir clientes" })).toHaveAttribute("href", "/clients");
  });
  it("preserves installation rows if optional workstation or client data fails", async () => {
    failures.add("/api/v1/workstations"); failures.add("/api/v1/clients");
    renderPage();
    expect(await within(screen.getByRole("table")).findByText("desk-01")).toBeInTheDocument();
    expect(screen.getByText("Alguns dados não puderam ser atualizados.")).toBeInTheDocument();
  });
  it("distinguishes missing installation state from no package after a failure", async () => {
    failures.add("/api/v1/nexo-installations"); renderPage();
    expect(await screen.findAllByText("Estado indisponível")).not.toHaveLength(0);
    expect(within(screen.getByRole("table")).queryByText("Sem pacote")).not.toBeInTheDocument();
  });
  it("retries build failure while retaining installation data", async () => {
    failures.add("/api/v1/nexo-agent-builds"); renderPage();
    expect(await screen.findByText("Não foi possível carregar os builds.")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("desk-01")).toBeInTheDocument();
    failures.clear(); fireEvent.click(screen.getByRole("button", { name: "Tentar carregar builds novamente" }));
    expect(await screen.findByText("Pronto")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Atualizar builds" }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/nexo-agent-builds"));
  });
});
