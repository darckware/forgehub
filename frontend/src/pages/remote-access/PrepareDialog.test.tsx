import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { PrepareDialog } from "./PrepareDialog";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn() } }));

const machine = (id: string, name: string, os: string, admin: string | null = null) => ({
  id, name, os_family: os, kind: "workstation", admin_user: admin, darckware_client_name: "Gatling", group_ids: [],
});

function renderDialog() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") return [machine("w1", "gat-adm-pc01", "windows", "administrador"), machine("w2", "desk", "windows")] as never;
    if (url.startsWith("/api/v1/servers/readiness")) {
      return { entries: [{ server_id: "w1", readiness: "online_no_access" }, { server_id: "w2", readiness: "ready" }] } as never;
    }
    return [] as never;
  });
  const onExecution = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><PrepareDialog onClose={vi.fn()} onExecution={onExecution} /></QueryClientProvider>);
  return onExecution;
}

describe("PrepareDialog", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("prepares over SSH with the administrator and opens the execution", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ execution_id: "e1", script: null } as never);
    const onExecution = renderDialog();
    await screen.findByRole("option", { name: /gat-adm-pc01/ });
    expect(screen.queryByRole("option", { name: /desk/ })).not.toBeInTheDocument(); // already Ready
    fireEvent.change(screen.getByLabelText("Máquina"), { target: { value: "w1" } });
    fireEvent.change(screen.getByLabelText("Senha do administrador"), { target: { value: "S3nha!" } });
    fireEvent.click(screen.getByRole("button", { name: "Preparar agora" }));
    await vi.waitFor(() => expect(onExecution).toHaveBeenCalledWith("e1"));
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/w1/preparation", {
      mode: "ssh", admin_user: "administrador", admin_password: "S3nha!", disable_admin: true,
    });
  });

  it("copies the script without sending any password", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ execution_id: null, script: "New-LocalUser darckware", language: "powershell" } as never);
    renderDialog();
    await screen.findByRole("option", { name: /gat-adm-pc01/ });
    fireEvent.change(screen.getByLabelText("Máquina"), { target: { value: "w1" } });
    fireEvent.click(screen.getByRole("radio", { name: "Copiar script (RustDesk)" }));
    fireEvent.click(screen.getByRole("button", { name: "Gerar script" }));
    expect(await screen.findByText("New-LocalUser darckware")).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/w1/preparation", expect.objectContaining({ mode: "copy", admin_password: null }));
  });
});
