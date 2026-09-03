import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "@/i18n";
import type { VpnStatus } from "@/hooks/useVpn";
import VpnPage from ".";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
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
    useVpnAction: () => ({ mutate: mocks.mutate, isPending: false, error: null }),
  };
});

const STATUS: VpnStatus = {
  independent_from_cloudflare: true,
  backend_state: "Running",
  checked_at: "2026-09-03T15:00:00Z",
  source_error: null,
  sources: [],
  connection: { kind: "derp", relay: "fra", latency_ms: 46 },
  nodes: [
    {
      role: "local",
      hostname: "NotebookSTI-wsl",
      tailscale_ipv4: "100.119.242.42",
      state: "online",
      online: true,
      active: true,
      last_seen: null,
      rx_bytes: 120,
      tx_bytes: 80,
      daemon_state: "active",
      posture: {
        accept_dns: false,
        accept_routes: false,
        advertise_exit_node: false,
        tailscale_ssh: false,
        exit_node: false,
        restricted: true,
      },
    },
    {
      role: "remote",
      hostname: "vmi3547248",
      tailscale_ipv4: "100.105.235.114",
      state: "online",
      online: true,
      active: true,
      last_seen: "2026-09-03T14:59:00Z",
      rx_bytes: 500,
      tx_bytes: 300,
      daemon_state: "observed",
      posture: null,
    },
  ],
};

describe("VPN control page", () => {
  beforeEach(() => {
    mocks.mutate.mockReset();
    mocks.refetch.mockReset();
    mocks.status.mockReturnValue({
      data: STATUS,
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: mocks.refetch,
    });
    mocks.operations.mockReturnValue({ data: { operations: [], limit: 25 }, isLoading: false });
  });

  it("shows the private topology and explains that Tailscale is independent", () => {
    render(<VpnPage />);

    expect(screen.getByRole("heading", { name: "Controle VPN" })).toBeInTheDocument();
    expect(screen.getAllByText("NotebookSTI-wsl")).not.toHaveLength(0);
    expect(screen.getAllByText("vmi3547248")).not.toHaveLength(0);
    expect(screen.getByText(/Cloudflare e Tailscale são camadas independentes/i)).toBeInTheDocument();
    expect(screen.getByText(/não altera firewall, portas públicas, rotas, DNS ou exit node/i)).toBeInTheDocument();
  });

  it("never offers a remote disconnect action", () => {
    render(<VpnPage />);

    expect(screen.getByRole("button", { name: "Desconectar NotebookSTI-wsl" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Desconectar vmi3547248" })).not.toBeInTheDocument();
  });

  it("runs the non-disruptive connection test immediately", () => {
    render(<VpnPage />);

    fireEvent.click(screen.getByRole("button", { name: "Testar conexão com vmi3547248" }));
    expect(mocks.mutate).toHaveBeenCalledWith(
      { node: "local", action: "test" },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("keeps remote restart unavailable when the private peer is offline", () => {
    mocks.status.mockReturnValue({
      data: {
        ...STATUS,
        nodes: STATUS.nodes.map((node) =>
          node.role === "remote" ? { ...node, state: "offline", online: false, active: false } : node,
        ),
      },
      isLoading: false,
      isFetching: false,
      isError: false,
      error: null,
      refetch: mocks.refetch,
    });

    render(<VpnPage />);

    expect(screen.queryByRole("button", { name: "Reiniciar Tailscale em vmi3547248" })).not.toBeInTheDocument();
    expect(screen.getByText(/console do provedor/i)).toBeInTheDocument();
  });
});
