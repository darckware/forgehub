import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/i18n";
import i18n from "@/i18n";
import type { VpnNode, VpnStatus } from "@/hooks/useVpn";
import RemoteAccessPage from ".";

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

// The workstations card has its own test (WorkstationsCard.test.tsx).
vi.mock("./WorkstationsCard", () => ({ WorkstationsCard: () => null }));
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
    node({ id: "nBBB11CNTRL", name: "srv-sup", hostname: "srv-sup", os: "linux", tags: ["tag:semed-srv"], tailscale_ipv4: "100.107.175.100" }),
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
  it("shows this server and every tailnet device grouped by tag", () => {
    renderAt();

    expect(screen.getByRole("heading", { name: "Acesso Remoto" })).toBeInTheDocument();
    expect(screen.getByText("darckware-srv")).toBeInTheDocument();
    for (const group of ["gatling-users", "semed-srv", "semed-users"]) {
      expect(screen.getByRole("region", { name: group })).toBeInTheDocument();
    }
    const offline = screen.getByRole("region", { name: "semed-users" });
    expect(within(offline).getByText("desk-semed-admin")).toBeInTheDocument();
    expect(within(offline).getByText("88480281099")).toBeInTheDocument();
    expect(within(offline).getByText("0 de 1 online")).toBeInTheDocument();
  });

  it("never offers connect/disconnect on this server", () => {
    renderAt();

    expect(screen.queryByRole("button", { name: /conectar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /desconectar/i })).not.toBeInTheDocument();
  });

  it("tests an online device by its stable id and disables offline ones", () => {
    renderAt();

    fireEvent.click(screen.getByRole("button", { name: "Testar conexão com gat-adm-pc01" }));
    expect(mocks.mutate).toHaveBeenCalledWith({ node: "nAAA11CNTRL", action: "test" }, expect.any(Object));
    expect(screen.getByRole("button", { name: "Testar conexão com desk-semed-admin" })).toBeDisabled();
  });

  it("asks for confirmation before restarting Tailscale on this server", () => {
    renderAt();

    fireEvent.click(screen.getByRole("button", { name: /Reiniciar Tailscale/ }));
    expect(mocks.mutate).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Reiniciar" }));
    expect(mocks.mutate).toHaveBeenCalledWith({ node: "self", action: "restart" }, expect.any(Object));
  });

  it("filters by group, state and search text", () => {
    renderAt();

    fireEvent.change(screen.getByPlaceholderText(/Buscar por nome/), { target: { value: "srv-sup" } });
    expect(screen.getByRole("region", { name: "semed-srv" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "gatling-users" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/Buscar por nome/), { target: { value: "" } });
    fireEvent.change(screen.getByDisplayValue("Todos"), { target: { value: "offline" } });
    expect(screen.getByRole("region", { name: "semed-users" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "semed-srv" })).not.toBeInTheDocument();
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
});
