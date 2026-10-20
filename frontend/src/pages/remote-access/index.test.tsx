import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/i18n";
import i18n from "@/i18n";
import type { VpnNode, VpnStatus } from "@/hooks/useVpn";
import { useAuthStore, type AuthUser } from "@/store/authStore";
import RemoteAccessPage from ".";

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

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  reset: vi.fn(),
  refetch: vi.fn(),
  status: vi.fn(),
  operations: vi.fn(),
}));

vi.mock("@/hooks/useVpn", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useVpn")>();
  return {
    ...actual,
    useVpnStatus: mocks.status,
    useVpnOperations: mocks.operations,
    useVpnAction: () => ({ mutate: mocks.mutate, reset: mocks.reset, isPending: false, error: null, variables: undefined }),
  };
});

// The machines card has its own test (MachinesCard.test.tsx).
vi.mock("./MachinesCard", () => ({ MachinesCard: () => null }));
vi.mock("./AuthorizedAgentsCard", () => ({ AuthorizedAgentsCard: () => null }));
vi.mock("./TailscaleApiKeyCard", () => ({ TailscaleApiKeyCard: () => null }));
vi.mock("@/hooks/useHostInventory", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useHostInventory")>()),
  useDetectMissingOs: () => ({ mutate: vi.fn(), isPending: false, data: undefined, error: null }),
}));
vi.mock("./ExecutionsCard", () => ({ ExecutionsCard: () => null }));
vi.mock("./TailnetPolicyCard", () => ({ TailnetPolicyCard: () => null }));
vi.mock("./ExecutionComposer", () => ({
  ExecutionComposer: ({ initialSystem }: { initialSystem?: string | null }) => <p>composer:{initialSystem ?? "none"}</p>,
}));
vi.mock("./ScriptLibrary", () => ({ ScriptLibrary: () => <p>library</p> }));
vi.mock("./SchedulesPanel", () => ({ SchedulesPanel: () => <p>schedules</p> }));

function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.search}</p>;
}

function renderAt(search = "?tab=network") {
  return render(
    <MemoryRouter initialEntries={[`/remote-access${search}`]}>
      <Routes>
        <Route path="/remote-access" element={<><RemoteAccessPage /><Where /></>} />
      </Routes>
    </MemoryRouter>,
  );
}

function node(overrides: Partial<VpnNode>): VpnNode {
  return {
    id: "nAAA11CNTRL",
    name: "gat-adm-pc01",
    hostname: "GAT-ADM-PC01",
    dns_name: "gat-adm-pc01.tail0000.ts.net",
    os: "windows",
    tags: ["tag:gatling-users"],
    tailscale_ipv4: "100.82.42.10",
    state: "online",
    online: true,
    active: true,
    last_seen: null,
    key_expiry: null,
    rx_bytes: 0,
    tx_bytes: 0,
    connection: { kind: "direct", relay: null },
    daemon_state: null,
    posture: null,
    ...overrides,
  };
}

const STATUS: VpnStatus = {
  backend_state: "Running",
  checked_at: "2026-10-15T15:00:00Z",
  source_error: null,
  sources: [],
  server: node({
    id: "self",
    name: "darckware-srv",
    hostname: "vmi3547248",
    os: "linux",
    tags: [],
    tailscale_ipv4: "100.105.235.114",
    connection: null,
    daemon_state: "active",
    posture: { accept_dns: true, accept_routes: false, advertise_exit_node: false, tailscale_ssh: false, exit_node: false, restricted: false },
  }),
  peers: [
    node({}),
    node({ id: "nBBB11CNTRL", name: "srv-sup", hostname: "srv-sup", os: "linux", tags: ["tag:semed-srv"], tailscale_ipv4: "100.107.175.100", subnet_routes: ["172.15.0.0/16"] }),
    node({
      id: "nCCC11CNTRL",
      name: "desk-semed-admin",
      hostname: "88480281099",
      tags: ["tag:semed-users"],
      tailscale_ipv4: "100.79.188.83",
      state: "offline",
      online: false,
      last_seen: "2026-10-14T19:42:15Z",
      connection: { kind: "unavailable", relay: null },
    }),
  ],
};

beforeEach(async () => {
  await i18n.changeLanguage("pt-BR");
  vi.clearAllMocks();
  useAuthStore.setState({ user: user(true), permissions: {} });
  mocks.status.mockReturnValue({ data: STATUS, isLoading: false, isError: false, isFetching: false, refetch: mocks.refetch });
  mocks.operations.mockReturnValue({
    data: {
      limit: 25,
      operations: [
        {
          id: "op-1",
          actor_username: "marcelodarck",
          target: "peer",
          target_name: "gat-adm-pc01",
          action: "test",
          status: "succeeded",
          result_code: "ok",
          summary: "gat-adm-pc01 answered in 34 ms (direct).",
          started_at: "2026-10-15T14:00:00Z",
          completed_at: "2026-10-15T14:00:01Z",
          created_at: "2026-10-15T14:00:00Z",
        },
      ],
    },
    isLoading: false,
  });
});

describe("Remote Access page", () => {
  it("shows this server and the subnet routers, not a device list", () => {
    renderAt();

    expect(screen.getByRole("heading", { name: "Acesso Remoto" })).toBeInTheDocument();
    expect(screen.getByText("darckware-srv")).toBeInTheDocument();
    // Devices live in Machines now; the network tab lists only routers.
    expect(screen.queryByText("desk-semed-admin")).not.toBeInTheDocument();
    expect(screen.getByText("srv-sup")).toBeInTheDocument();
    expect(screen.getByText("172.15.0.0/16")).toBeInTheDocument();
    // The VPS does not accept routes in this fixture.
    expect(screen.getByText(/não aceita rotas de sub-rede/)).toBeInTheDocument();
  });

  it("never offers connect/disconnect on this server", () => {
    renderAt();

    expect(screen.queryByRole("button", { name: /conectar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /desconectar/i })).not.toBeInTheDocument();
  });

  it("asks for confirmation before restarting Tailscale on this server", () => {
    renderAt();

    fireEvent.click(screen.getByRole("button", { name: /Reiniciar Tailscale/ }));
    expect(mocks.mutate).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Reiniciar" }));
    expect(mocks.mutate).toHaveBeenCalledWith({ node: "self", action: "restart" }, expect.any(Object));
  });

  it("labels history rows with the device name", () => {
    renderAt();

    expect(screen.getByText("gat-adm-pc01 answered in 34 ms (direct).")).toBeInTheDocument();
  });

  it("degrades to an explicit unavailable state", () => {
    mocks.status.mockReturnValue({ data: undefined, isLoading: false, isError: true, isFetching: false, refetch: mocks.refetch });
    renderAt();

    expect(screen.getByRole("alert")).toHaveTextContent("Acesso Remoto indisponível");
  });

  it("opens on Machines and the install buttons open the execution screen with that script", () => {
    renderAt("");
    expect(screen.getByRole("tab", { name: "Máquinas" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: /Instalar RustDesk/ }));
    expect(screen.getByText("composer:rustdesk_install")).toBeInTheDocument();
    expect(screen.getByTestId("where").textContent).toContain("system=rustdesk_install");
    fireEvent.click(screen.getByRole("tab", { name: "Biblioteca" }));
    expect(screen.getByText("library")).toBeInTheDocument();
  });

  it("shows a non-admin only the machine list: no tabs, no quick actions", () => {
    useAuthStore.setState({ user: user(false), permissions: { servers: { can_view: true, can_query: true, can_write: false, can_delete: false } } });
    renderAt("?tab=network");

    expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Instalar RustDesk/ })).not.toBeInTheDocument();
    expect(screen.queryByText("darckware-srv")).not.toBeInTheDocument();
  });
});
