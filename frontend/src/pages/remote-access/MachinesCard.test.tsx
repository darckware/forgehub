import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { buildMachineSections, unregisteredDevices } from "@/hooks/useMachinesViewModel";
import type { HostReadinessEntry } from "@/hooks/useHostInventory";
import type { Server } from "@/hooks/useServers";
import type { VpnNode } from "@/hooks/useVpn";
import { apiClient } from "@/lib/api";
import { useAuthStore, type AuthUser } from "@/store/authStore";
import { MachinesCard } from "./MachinesCard";
import type { QuickActions } from "./quickActions";

const user = (isAdmin: boolean): AuthUser => ({
  id: "11111111-1111-4111-8111-111111111111",
  username: isAdmin ? "admin" : "operator",
  email: null,
  full_name: null,
  avatar_data_url: null,
  totp_enabled: false,
  is_active: true,
  is_admin: isAdmin,
  profile_id: null,
  ui_language: "pt-BR",
});

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
  { ...base, id: "m1", name: "GAT-ADM-PC01", remote_user: "darckware", kind: "workstation", os_family: "windows",
    darckware_client_id: "c1", darckware_client_name: "Gatling", group_ids: ["g1"], tailnet_node_id: "nPC1",
    rustdesk_id: "217385777", ssh_key_in_vault: true, login_password_in_vault: true, access_verified_at: "2026-11-13T18:00:00Z" },
  { ...base, id: "s1", name: "srv-sup", ip_address: "172.15.2.9", remote_user: "aegis", kind: "server", os_family: "linux",
    darckware_client_id: null, darckware_client_name: null, tailnet_node_id: "nSUP" },
  { ...base, id: "s2", name: "srv-ad03", ip_address: "172.15.1.3", remote_user: "aegis", kind: "server", os_family: null,
    darckware_client_id: null, darckware_client_name: null },
  { ...base, id: "s3", name: "srv-old", ip_address: "10.9.9.9", remote_user: "aegis", kind: "server", os_family: null,
    darckware_client_id: null, darckware_client_name: null },
] as unknown as Server[];
const GROUPS = [
  { id: "g1", name: "Secretaria", darckware_client_id: "c1", darckware_client_name: "Gatling", description: null, server_ids: ["m1"], created_at: "", updated_at: "" },
];
const entry = (server_id: string, readiness: string, access_path: string, extra: Partial<HostReadinessEntry> = {}) =>
  ({ server_id, readiness, tailnet_online: null, ssh: null, detail: null, access_path,
     access_via_node_id: null, access_via_name: null, tailscale_ipv4: null, ...extra }) as HostReadinessEntry;
const READINESS = {
  checked_at: "2026-10-17T15:00:00Z", tailnet_available: true, ssh_checked_at: null,
  entries: [
    entry("m1", "ready", "tailscale", { status: "partial", tailscale_ipv4: "100.64.0.1" }),
    entry("s1", "ready", "subnet", { status: "complete", access_via_node_id: "nSUP", access_via_name: "srv-sup", tailscale_ipv4: "100.107.175.100" }),
    entry("s2", "not_prepared", "subnet", { status: "not_prepared", access_via_node_id: "nSUP", access_via_name: "srv-sup" }),
    entry("s3", "offline", "none", { status: "offline" }),
  ],
};
const node = (id: string, name: string, extra: Partial<VpnNode> = {}) =>
  ({ id, name, hostname: name, dns_name: null, os: "linux", tags: [], tailscale_ipv4: "100.64.9.9", subnet_routes: [],
     state: "online", online: true, active: false, last_seen: null, key_expiry: null, rx_bytes: 0, tx_bytes: 0,
     connection: null, daemon_state: null, posture: null, ...extra }) as VpnNode;
const PEERS = [
  node("nPC1", "gat-adm-pc01", { os: "windows" }),
  node("nSUP", "srv-sup", { subnet_routes: ["172.15.0.0/16"] }),
  node("nPHONE", "POCO F5 Pro", { os: "android", tailscale_ipv4: "100.101.8.102", state: "offline", online: false }),
];
const VPN = {
  backend_state: "Running", checked_at: "", sources: [], peers: PEERS,
  server: { ...node("self", "vmi3547248"), posture: { accept_dns: false, accept_routes: true, advertise_exit_node: false, tailscale_ssh: false, exit_node: false, restricted: false } },
};

function renderCard(quickActions?: QuickActions, machines: Server[] = MACHINES) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") return machines as never;
    if (url === "/api/v1/host-groups") return GROUPS as never;
    if (url.startsWith("/api/v1/servers/readiness")) return READINESS as never;
    if (url === "/api/v1/vpn/status") return VPN as never;
    return { items: [{ id: "c1", company_name: "Gatling" }] } as never;
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<MemoryRouter><QueryClientProvider client={qc}><MachinesCard quickActions={quickActions} /></QueryClientProvider></MemoryRouter>);
}

describe("buildMachineSections", () => {
  const readinessById = new Map(READINESS.entries.map((e) => [e.server_id, e]));
  const nodesById = new Map(PEERS.map((p) => [p.id, p]));
  const all = { query: "", kind: "all", client: "all", readiness: "all", path: "all" } as const;

  it("sections by access path, one section per subnet router, in a fixed order", () => {
    const sections = buildMachineSections(MACHINES, readinessById, nodesById, all);
    expect(sections.map((s) => [s.key, s.rows.map((r) => r.machine.name)])).toEqual([
      ["tailscale", ["GAT-ADM-PC01"]],
      ["subnet:nSUP", ["srv-ad03", "srv-sup"]],
      ["none", ["srv-old"]],
    ]);
    expect(sections[1]).toMatchObject({ routerName: "srv-sup", routes: ["172.15.0.0/16"], notAccepted: false });
  });

  it("applies kind, client, path and search filters together", () => {
    expect(buildMachineSections(MACHINES, readinessById, nodesById, { ...all, kind: "workstation" })
      .flatMap((s) => s.rows.map((r) => r.machine.id))).toEqual(["m1"]);
    expect(buildMachineSections(MACHINES, readinessById, nodesById, { ...all, client: "none", path: "subnet" })
      .flatMap((s) => s.rows.map((r) => r.machine.id))).toEqual(["s2", "s1"]);
    // The linked device's Tailscale IP is searchable too.
    expect(buildMachineSections(MACHINES, readinessById, nodesById, { ...all, query: "100.107" })
      .flatMap((s) => s.rows.map((r) => r.machine.id))).toEqual(["s1"]);
    expect(buildMachineSections(MACHINES, readinessById, nodesById, { ...all, path: "unregistered" })).toEqual([]);
  });

  it("lists only tailnet devices with no inventory row", () => {
    expect(unregisteredDevices(MACHINES, PEERS, "").map((p) => p.id)).toEqual(["nPHONE"]);
    expect(unregisteredDevices(MACHINES, PEERS, "zzz")).toEqual([]);
  });
});

describe("MachinesCard", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    useAuthStore.setState({ user: user(true), permissions: {} });
    await i18n.changeLanguage("pt-BR");
  });

  it("shows servers and workstations together, sectioned by path, with the router's routes", async () => {
    renderCard();
    const tailscale = await screen.findByRole("region", { name: "Tailscale" });
    expect(within(tailscale).getByText("GAT-ADM-PC01")).toBeInTheDocument();

    const subnet = screen.getByRole("region", { name: "Via sub-rede · srv-sup" });
    expect(within(subnet).getByText("srv-ad03")).toBeInTheDocument();
    expect(within(subnet).getByText("Roteia 172.15.0.0/16")).toBeInTheDocument();
    // A LAN-addressed row that also has Tailscale shows its 100.x address.
    expect(within(subnet).getByText("Tailscale 100.107.175.100")).toBeInTheDocument();

    expect(within(screen.getByRole("region", { name: "Sem caminho" })).getByText("srv-old")).toBeInTheDocument();
  });

  it("offers the terminal and the shared configuration workflow", async () => {
    renderCard();
    await screen.findByText("srv-ad03");
    expect(screen.getByRole("button", { name: "Abrir terminal SSH em srv-sup" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Configurar acesso a GAT-ADM-PC01" })).not.toBeInTheDocument();
    // A server: the same darckware preparation panel.
    fireEvent.click(screen.getByRole("button", { name: "Configurar acesso a srv-ad03" }));
    expect(await screen.findByRole("dialog", { name: "Configurar acesso da máquina" })).toBeInTheDocument();
  });

  it("no longer offers moving key files to ForgeVault", async () => {
    // The keys:to-vault migration route was retired with ForgeVault-only keys.
    renderCard();
    await screen.findByText("srv-ad03");
    expect(screen.queryByRole("button", { name: /Migrar chaves para a ForgeVault/ })).not.toBeInTheDocument();
  });

  it("registers an unregistered tailnet device through the tailnet sync", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ entries: [], missing_server_ids: [] } as never);
    renderCard();
    const section = await screen.findByRole("region", { name: "Na tailnet, não cadastrados" });
    expect(within(section).getByText("POCO F5 Pro")).toBeInTheDocument();
    fireEvent.click(within(section).getByRole("button", { name: /Cadastrar/ }));
    await screen.findByText("Nada mudou na tailnet.");
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/servers/tailnet:sync", { import_node_ids: ["nPHONE"] });
  });

  it("filters by readiness", async () => {
    renderCard();
    await screen.findByText("srv-ad03");
    // Attention = a channel is missing: not prepared, or a station without RustDesk.
    fireEvent.change(screen.getByLabelText("Filtrar por prontidão"), { target: { value: "attention" } });
    expect(screen.getByText("srv-ad03")).toBeInTheDocument();
    expect(screen.getByText("GAT-ADM-PC01")).toBeInTheDocument();
    expect(screen.queryByText("srv-old")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filtrar por prontidão"), { target: { value: "ready" } });
    expect(screen.getAllByText("srv-sup").length).toBeGreaterThan(0);
    expect(screen.queryByText("srv-ad03")).not.toBeInTheDocument();
    expect(screen.queryByText("GAT-ADM-PC01")).not.toBeInTheDocument();
  });

  it("colors each machine by what can be done with it and shows its channels", async () => {
    renderCard();
    await screen.findByText("srv-ad03");
    expect(screen.getAllByText("Sem RustDesk").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Reconfiguração necessária").length).toBeGreaterThan(0);
    expect(screen.queryByText("Online sem acesso")).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Sem RustDesk registrado").length).toBeGreaterThan(0);
  });

  it("shows the RustDesk ID with a copy button", async () => {
    renderCard();
    await screen.findByText("srv-ad03");
    expect(screen.getAllByText("217 385 777").length).toBeGreaterThan(0);
    expect(screen.getAllByTitle("Copiar o ID do RustDesk").length).toBeGreaterThan(0);
  });

  it("gives a view-only servers user the sections without admin actions or the tailnet", async () => {
    useAuthStore.setState({ user: user(false), permissions: { servers: { can_view: true, can_query: true, can_write: false, can_delete: false } } });
    renderCard();
    await screen.findByText("srv-ad03");
    expect(screen.getByRole("region", { name: "Via sub-rede · srv-sup" })).toBeInTheDocument();
    expect(apiClient.get).not.toHaveBeenCalledWith("/api/v1/vpn/status");
    expect(screen.queryByRole("region", { name: "Na tailnet, não cadastrados" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir terminal SSH em srv-sup" })).toBeInTheDocument();
    for (const name of ["Configurar acesso a srv-ad03", "Excluir srv-ad03"]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: /Nova máquina/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Migrar chaves/ })).not.toBeInTheDocument();
  });

  it("edits a machine in a right-hand panel that Escape closes", async () => {
    renderCard();
    await screen.findByText("srv-ad03");
    fireEvent.click(screen.getByRole("button", { name: "Editar srv-ad03" }));
    const panel = await screen.findByRole("dialog", { name: "Editar servidor" });
    // role="dialog" sits on the panel itself (SidePanel); its wrapper pins it right.
    expect(panel.className).toContain("slide-in-from-right");
    expect(panel.parentElement?.className).toContain("justify-end");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Editar servidor" })).not.toBeInTheDocument();
  });

  it("Ações: the toolbar menu lists the quick actions, opens by keyboard, and Esc closes it", async () => {
    const run = vi.fn();
    renderCard({ run, detectOsPending: false });
    await screen.findByText("srv-ad03");
    const trigger = screen.getByRole("button", { name: "Ações" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu", { name: "Ações" });
    expect(within(menu).getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Configurar acesso da máquina", "Rotacionar senha", "Rotacionar chave SSH", "Detectar sistemas operacionais",
      "Instalador Darckware Remoto", "Instalar Tailscale", "Instalar RustDesk", "Obter ID do RustDesk",
      "Liberar RustDesk no firewall", "Trocar senha do RustDesk",
    ]);
    const items = within(menu).getAllByRole("menuitem");
    expect(items[0]).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(items[1]).toHaveFocus();
    fireEvent.keyDown(menu, { key: "End" });
    expect(items[9]).toHaveFocus();
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(items[0]).toHaveFocus();
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.click(within(screen.getByRole("menu")).getByRole("menuitem", { name: "Instalar Tailscale" }));
    expect(run).toHaveBeenCalledWith("tailscale_install", undefined);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "Rotacionar chave SSH" }));
    expect(run.mock.lastCall?.[0]).toBe("rotate_ssh_key");
    expect(run.mock.lastCall?.[1]).toBeUndefined();
  });

  it("Ações: a machine's row menu runs the action with that machine; preparation includes servers, rotation only when Ready with a key", async () => {
    const run = vi.fn();
    const machines = MACHINES.map((m) => (m.id === "s1" ? { ...m, ssh_key_path: "/root/.ssh/id_srv" } : m)) as Server[];
    renderCard({ run, detectOsPending: false }, machines);
    await screen.findByText("srv-ad03");

    fireEvent.click(screen.getByRole("button", { name: "Ações em srv-sup" }));
    let menu = screen.getByRole("menu", { name: "Ações em srv-sup" });
    expect(within(menu).getByRole("menuitem", { name: "Configurar acesso da máquina" })).toBeInTheDocument();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Rotacionar senha" }));
    expect(run).toHaveBeenCalledWith("rotate_login_password", expect.objectContaining({ id: "s1" }));

    fireEvent.click(screen.getByRole("button", { name: "Ações em GAT-ADM-PC01" }));
    menu = screen.getByRole("menu", { name: "Ações em GAT-ADM-PC01" });
    expect(within(menu).queryByRole("menuitem", { name: "Rotacionar senha" })).not.toBeInTheDocument(); // no key on record
    expect(within(menu).queryByRole("menuitem", { name: "Detectar sistemas operacionais" })).not.toBeInTheDocument();
    fireEvent.click(within(menu).getByRole("menuitem", { name: "Configurar acesso da máquina" }));
    expect(run).toHaveBeenLastCalledWith("prepare", expect.objectContaining({ id: "m1" }));

    fireEvent.click(screen.getByRole("button", { name: "Ações em GAT-ADM-PC01" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Instalar RustDesk" }));
    expect(run).toHaveBeenLastCalledWith("rustdesk_install", expect.objectContaining({ id: "m1" }));
  });

  it("Ações: a click outside closes the menu without running anything", async () => {
    const run = vi.fn();
    renderCard({ run, detectOsPending: false });
    await screen.findByText("srv-ad03");
    fireEvent.click(screen.getByRole("button", { name: "Ações" }));
    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(run).not.toHaveBeenCalled();
  });

  it("Ações: without quick actions (a non-admin page) there is no menu", async () => {
    useAuthStore.setState({ user: user(false), permissions: { servers: { can_view: true, can_query: true, can_write: false, can_delete: false } } });
    renderCard({ run: vi.fn(), detectOsPending: false });
    await screen.findByText("srv-ad03");
    expect(screen.queryByRole("button", { name: "Ações" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Ações em/ })).not.toBeInTheDocument();
  });

  it("opens the shared preparation panel for a Ready server using a legacy SSH login", async () => {
    renderCard();
    const button = await screen.findByRole("button", { name: "Reconfigurar acesso a srv-sup" });
    expect(screen.getAllByText("Login antigo: aegis · reconfigurar para darckware").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Pedir ao agente uma tarefa em srv-sup" })).not.toBeInTheDocument();
    fireEvent.click(button);
    await screen.findByRole("dialog", { name: "Configurar acesso da máquina" });
    expect(screen.getByLabelText("Máquina")).toHaveValue("s1");
    expect(screen.getByRole("radio", { name: "Conta cadastrada: aegis" })).toBeInTheDocument();
  });


  it("requires explicit login verification before offering an agent task", async () => {
    const unverified = MACHINES.map((machine) => ({ ...machine, access_verified_at: null }));
    renderCard(undefined, unverified);
    await screen.findByText("srv-ad03");
    expect(screen.queryByRole("button", { name: "Pedir ao agente uma tarefa em GAT-ADM-PC01" })).not.toBeInTheDocument();
    const row = screen.getByText("GAT-ADM-PC01").closest("tr")!;
    expect(within(row).getAllByText("Reconfiguração necessária").length).toBeGreaterThan(0);
    expect(within(row).getByRole("button", { name: "Abrir terminal SSH em GAT-ADM-PC01" })).toBeInTheDocument();
  });

});
