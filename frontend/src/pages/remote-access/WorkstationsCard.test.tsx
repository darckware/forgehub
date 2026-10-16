import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { WorkstationsCard } from "./WorkstationsCard";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const base = {
  ip_address: "100.64.0.1", ssh_port: 22, ssh_key_path: null, public_key: null, private_key_stored: false,
  key_passphrase_stored: false, access_enabled: true, description: null, environment: "client",
  admin_user: null, location: null, tailnet_node_id: null, tailnet_name: null, group_ids: [],
  created_at: "", updated_at: "",
};
const MACHINES = [
  { ...base, id: "m1", name: "GAT-ADM-PC01", remote_user: "darckware-adm", kind: "workstation", os_family: "windows",
    darckware_client_id: "c1", darckware_client_name: "Gatling", location: "Recepção", group_ids: ["g1"] },
  { ...base, id: "m2", name: "GAT-ADM-PC02", remote_user: "", kind: "workstation", os_family: "windows",
    darckware_client_id: "c1", darckware_client_name: "Gatling" },
  { ...base, id: "s1", name: "srv-app01", remote_user: "aegis", kind: "server", os_family: "linux",
    darckware_client_id: null, darckware_client_name: null },
];
const GROUPS = [
  { id: "g1", name: "Secretaria", darckware_client_id: "c1", darckware_client_name: "Gatling", description: null, server_ids: ["m1"], created_at: "", updated_at: "" },
];
const READINESS = {
  checked_at: "2026-10-15T15:00:00Z", tailnet_available: true, ssh_checked_at: null,
  entries: [
    { server_id: "m1", readiness: "ready", tailnet_online: true, ssh: "active", detail: null },
    { server_id: "m2", readiness: "not_prepared", tailnet_online: true, ssh: null, detail: "No login set" },
  ],
};

function renderCard() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") return MACHINES as never;
    if (url === "/api/v1/host-groups") return GROUPS as never;
    if (url.startsWith("/api/v1/servers/readiness")) return READINESS as never;
    return { items: [{ id: "c1", company_name: "Gatling" }] } as never;
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={qc}><WorkstationsCard /></QueryClientProvider></MemoryRouter>);
}

describe("WorkstationsCard", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("groups workstations by client with readiness, leaving servers out", async () => {
    renderCard();
    const section = await screen.findByRole("region", { name: "Gatling" });
    expect(within(section).getByText("GAT-ADM-PC01")).toBeInTheDocument();
    expect(within(section).getByText("Pronta")).toBeInTheDocument();
    expect(within(section).getByText("Não preparada")).toBeInTheDocument();
    expect(within(section).getAllByText("Secretaria").length).toBeGreaterThan(0);
    expect(screen.queryByText("srv-app01")).not.toBeInTheDocument();
  });

  it("filters to the machines that need attention", async () => {
    renderCard();
    await screen.findByText("GAT-ADM-PC01");
    fireEvent.change(screen.getByLabelText("Filtrar por prontidão"), { target: { value: "attention" } });
    expect(screen.queryByText("GAT-ADM-PC01")).not.toBeInTheDocument();
    expect(screen.getByText("GAT-ADM-PC02")).toBeInTheDocument();
  });

  it("summarizes a sync and imports only the devices picked", async () => {
    const entry = (node_id: string, outcome: string, server_id: string | null) => ({
      node_id, name: node_id, tailscale_ipv4: "100.64.0.9", os: "windows", online: true, tags: [],
      outcome, server_id, suggested_client_tag: null,
    });
    vi.mocked(apiClient.post)
      .mockResolvedValueOnce({
        entries: [entry("pc-a", "available", null), entry("pc-b", "available", null), entry("srv", "linked", "s1")],
        missing_server_ids: ["m2"],
      } as never)
      .mockResolvedValueOnce({
        entries: [entry("pc-a", "created", "m9"), entry("pc-b", "available", null)],
        missing_server_ids: [],
      } as never);
    renderCard();
    await screen.findByText("GAT-ADM-PC01");

    fireEvent.click(screen.getByRole("button", { name: /Sincronizar da tailnet/ }));
    expect(await screen.findByText(
      "1 vinculada(s) · 2 disponível(is) para importar · 1 fora da tailnet (mantidas)",
    )).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/servers/tailnet:sync", { import_node_ids: [] });

    fireEvent.click(screen.getByRole("checkbox", { name: /pc-a/ }));
    fireEvent.click(screen.getByRole("button", { name: "Importar selecionadas (1)" }));
    expect(await screen.findByText("1 nova(s) · 1 disponível(is) para importar")).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/servers/tailnet:sync", { import_node_ids: ["pc-a"] });
  });

  it("has no per-row Run or Prepare buttons (they live in the Scripts tab and the Prepare action)", async () => {
    renderCard();
    await screen.findByText("GAT-ADM-PC02");
    expect(screen.queryByRole("button", { name: /Preparar GAT-ADM-PC02/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Executar comando em/ })).not.toBeInTheDocument();
  });
});
