import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { Server } from "@/hooks/useServers";
import { InstallKeyModal } from "./ServerDialogs";

vi.mock("@/lib/api", () => ({ apiClient: { post: vi.fn(), put: vi.fn() } }));

function renderDialog(sshPort?: number) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const server = { id: "s1", name: "srv", remote_user: "darckware", ip_address: "10.0.0.1", ssh_port: sshPort } as Server;
  render(<QueryClientProvider client={qc}><InstallKeyModal server={server} onClose={vi.fn()} onInstalled={vi.fn()} /></QueryClientProvider>);
}

describe("InstallKeyModal SSH port", () => {
  beforeEach(async () => {
    vi.resetAllMocks();
    await i18n.changeLanguage("pt-BR");
    vi.mocked(apiClient.put).mockResolvedValue({} as never);
    vi.mocked(apiClient.post).mockResolvedValue({ ok: true, steps: [] } as never);
  });

  it("defaults to 22 and saves a custom port before installing the key", async () => {
    renderDialog();
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(22);
    fireEvent.change(screen.getByLabelText("Porta SSH"), { target: { value: "2222" } });
    fireEvent.change(screen.getByDisplayValue(""), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Instalar chave" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/servers/s1", { ssh_port: 2222 });
    expect(vi.mocked(apiClient.put).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(apiClient.post).mock.invocationCallOrder[0]);
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/s1/install-key", { password: "secret", remote_user: null, admin_user: "root" });
  });

  it("opens with the saved port and blocks invalid input", () => {
    renderDialog(2022);
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(2022);
    fireEvent.change(screen.getByDisplayValue(""), { target: { value: "secret" } });
    for (const value of ["", "0", "65536", "22.5"]) {
      fireEvent.change(screen.getByLabelText("Porta SSH"), { target: { value } });
      expect(screen.getByRole("button", { name: "Instalar chave" })).toBeDisabled();
      expect(screen.getByLabelText("Porta SSH")).toHaveAttribute("aria-invalid", "true");
    }
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("preserves input and does not connect when saving the port fails", async () => {
    vi.mocked(apiClient.put).mockRejectedValueOnce(new Error("Port save failed"));
    renderDialog(2022);
    fireEvent.change(screen.getByDisplayValue(""), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Instalar chave" }));
    expect(await screen.findByText("Port save failed")).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(2022);
  });
});
