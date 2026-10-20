import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { Server } from "@/hooks/useServers";
import { MaintenanceDialog } from "./MaintenanceDialog";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn() } }));

describe("MaintenanceDialog", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("shows who did what on the machine: agent runs with reason and ticket, terminal sessions", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([
      { at: "2026-10-19T12:00:00Z", kind: "execution", actor: "Vector", agent_name: "Vector", trigger: "agent",
        title: "Reiniciar spooler", status: "succeeded", reason: "Fila travada", darckware_item_kind: "ticket",
        darckware_item_id: "T-7", execution_id: "e1" },
      { at: "2026-10-19T11:00:00Z", kind: "terminal", actor: "marcelodarck", agent_name: null, trigger: null,
        title: "Terminal SSH aberto", status: null, reason: null, darckware_item_kind: null, darckware_item_id: null, execution_id: null },
    ] as never);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter><MaintenanceDialog machine={{ id: "m1", name: "PC-01" } as Server} onClose={vi.fn()} /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("link", { name: "Reiniciar spooler" })).toHaveAttribute("href", "/remote-access/executions/e1");
    expect(screen.getByText(/agente Vector · chamado T-7/)).toBeInTheDocument();
    expect(screen.getByText("Fila travada")).toBeInTheDocument();
    expect(screen.getByText(/marcelodarck/)).toBeInTheDocument();
    expect(apiClient.get).toHaveBeenCalledWith("/api/v1/servers/m1/maintenance");
  });
});
