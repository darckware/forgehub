import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { RunCommandDialog } from "./RunCommandDialog";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const machine = (id: string, name: string, os: string) => ({
  id, name, os_family: os, darckware_client_name: "Gatling", kind: "workstation", group_ids: [],
});

describe("RunCommandDialog", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url === "/api/v1/servers") return [machine("m1", "PC01", "windows"), machine("m2", "PC02", "windows"), machine("s1", "srv", "linux")] as never;
      if (url === "/api/v1/host-groups") return [{ id: "g1", name: "Secretaria", darckware_client_name: "Gatling", server_ids: ["m1", "m2"] }] as never;
      return [] as never;
    });
  });

  it("expands groups, suggests PowerShell for Windows, reviews and sends", async () => {
    const onStarted = vi.fn();
    vi.mocked(apiClient.post).mockResolvedValue({ id: "e1" } as never);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><RunCommandDialog onClose={vi.fn()} onStarted={onStarted} /></QueryClientProvider>);

    fireEvent.click(await screen.findByLabelText(/Grupo Secretaria \(2\)/));
    expect(screen.getByText("2 máquinas selecionadas")).toBeInTheDocument();
    expect((screen.getByLabelText("Tipo de comando") as HTMLSelectElement).value).toBe("powershell");

    fireEvent.change(screen.getByLabelText("Comando"), { target: { value: "Get-Date" } });
    fireEvent.click(screen.getByRole("button", { name: "Revisar" }));
    expect(screen.getByText(/Será executado em 2 máquinas/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Executar em 2 máquinas" }));

    await vi.waitFor(() => expect(onStarted).toHaveBeenCalled());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-executions", {
      command: "Get-Date", shell: "powershell", server_ids: [], group_ids: ["g1"], timeout_seconds: 300,
    });
  });

  it("warns when the selection mixes Windows and Linux", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><RunCommandDialog onClose={vi.fn()} onStarted={vi.fn()} initialServerIds={["m1", "s1"]} /></QueryClientProvider>);
    expect(await screen.findByText(/A seleção mistura Windows com Linux\/macOS/)).toBeInTheDocument();
  });
});
