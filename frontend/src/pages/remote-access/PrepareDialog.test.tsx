import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { PrepareDialog } from "./PrepareDialog";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

const machine = (id: string, name: string, os: string, admin: string | null = null, kind = "workstation") => ({
  id, name, os_family: os, kind, admin_user: admin, darckware_client_name: "Gatling", group_ids: [],
});

function renderDialog() {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") {
      return [machine("w1", "gat-adm-pc01", "windows", "administrador"), machine("w2", "desk", "windows"),
        { ...machine("s1", "gat-srv-01", "windows", null, "server"), ssh_port: 2222 }] as never;
    }
    if (url.startsWith("/api/v1/servers/readiness")) {
      return { entries: [{ server_id: "w1", readiness: "not_prepared", status: "not_prepared" }, { server_id: "w2", readiness: "ready" },
        { server_id: "s1", readiness: "not_prepared", status: "not_prepared" }] } as never;
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
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(22);
    fireEvent.change(screen.getByLabelText("Porta SSH"), { target: { value: "2200" } });
    fireEvent.change(screen.getByLabelText("Senha do administrador"), { target: { value: "S3nha!" } });
    fireEvent.click(screen.getByRole("button", { name: "Preparar agora" }));
    await vi.waitFor(() => expect(onExecution).toHaveBeenCalledWith("e1"));
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/servers/w1", { ssh_port: 2200 });
    expect(vi.mocked(apiClient.put).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(apiClient.post).mock.invocationCallOrder[0]);
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/w1/preparation", {
      mode: "ssh", admin_user: "administrador", admin_password: "S3nha!", disable_admin: true,
    });
  });

  it("asks login and password for another account, and keeps a server's administrator by default", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ execution_id: "e2", script: null } as never);
    const onExecution = renderDialog();
    await screen.findByRole("option", { name: /gat-srv-01/ });
    fireEvent.change(screen.getByLabelText("Máquina"), { target: { value: "w1" } });
    expect(screen.getByRole("radio", { name: "Conta cadastrada: administrador" })).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByLabelText("Login do administrador")).not.toBeInTheDocument(); // only the password is asked
    fireEvent.click(screen.getByRole("radio", { name: "Outra conta" }));
    expect(screen.getByLabelText("Login do administrador")).toBeInTheDocument();

    // A machine with no account on record opens both fields straight away.
    fireEvent.change(screen.getByLabelText("Máquina"), { target: { value: "s1" } });
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(2222);
    expect(screen.queryByRole("radio", { name: "Outra conta" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Login do administrador"), { target: { value: "suporte" } });
    fireEvent.change(screen.getByLabelText("Senha do administrador"), { target: { value: "X1!" } });
    expect(screen.getByRole("checkbox")).not.toBeChecked(); // a server keeps its administrator
    fireEvent.click(screen.getByRole("button", { name: "Preparar agora" }));
    await vi.waitFor(() => expect(onExecution).toHaveBeenCalledWith("e2"));
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/s1/preparation", {
      mode: "ssh", admin_user: "suporte", admin_password: "X1!", disable_admin: false,
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
    expect(apiClient.put).not.toHaveBeenCalled();
  });

  it("rejects invalid ports and stops preparation if saving the port fails", async () => {
    vi.mocked(apiClient.put).mockRejectedValueOnce(new Error("Port save failed"));
    renderDialog();
    await screen.findByRole("option", { name: /gat-adm-pc01/ });
    fireEvent.change(screen.getByLabelText("Máquina"), { target: { value: "w1" } });
    fireEvent.change(screen.getByLabelText("Senha do administrador"), { target: { value: "secret" } });
    for (const value of ["", "0", "65536", "22.5"]) {
      fireEvent.change(screen.getByLabelText("Porta SSH"), { target: { value } });
      expect(screen.getByRole("button", { name: "Preparar agora" })).toBeDisabled();
      expect(screen.getByLabelText("Porta SSH")).toHaveAttribute("aria-invalid", "true");
    }
    fireEvent.change(screen.getByLabelText("Porta SSH"), { target: { value: "2222" } });
    fireEvent.click(screen.getByRole("button", { name: "Preparar agora" }));
    expect(await screen.findByText("Port save failed")).toBeInTheDocument();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(2222);
  });
});
