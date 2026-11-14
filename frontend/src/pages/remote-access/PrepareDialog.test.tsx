import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { PrepareDialog } from "./PrepareDialog";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

const machine = (id: string, name: string, os: string, admin: string | null = null, kind = "workstation") => ({
  id, name, os_family: os, kind, admin_user: admin, remote_user: admin, darckware_client_name: "Gatling", group_ids: [],
});

function renderDialog(customMachines?: unknown[], initialServerId?: string) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/servers") {
      return customMachines ?? [machine("w1", "gat-adm-pc01", "windows", "administrador"), machine("w2", "desk", "windows"),
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
  render(<QueryClientProvider client={qc}><PrepareDialog onClose={vi.fn()} onExecution={onExecution} initialServerId={initialServerId} /></QueryClientProvider>);
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
    expect(screen.getByRole("option", { name: /desk/ })).toBeInTheDocument(); // Ready machines can be reconfigured
    fireEvent.change(screen.getByLabelText("Máquina"), { target: { value: "w1" } });
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(22);
    fireEvent.change(screen.getByLabelText("Porta SSH"), { target: { value: "2200" } });
    fireEvent.change(screen.getByLabelText("Senha do administrador"), { target: { value: "S3nha!" } });
    fireEvent.click(screen.getByRole("button", { name: "Preparar agora" }));
    await vi.waitFor(() => expect(onExecution).toHaveBeenCalledWith("e1"));
    expect(apiClient.put).not.toHaveBeenCalled(); // port is staged with the credentials
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/w1/preparation", {
      mode: "ssh", admin_user: "administrador", admin_password: "S3nha!", disable_admin: true, ssh_port: 2200,
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
      mode: "ssh", admin_user: "suporte", admin_password: "X1!", disable_admin: false, ssh_port: 2222,
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

  it("rejects invalid ports and preserves input when preparation fails", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error("Preparation failed"));
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
    expect(await screen.findByText("Preparation failed")).toBeInTheDocument();
    expect(apiClient.put).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Porta SSH")).toHaveValue(2222);
  });

  it("reconfigures existing darckware with only this machine's vaulted password and never locks itself", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ execution_id: "reconfigured", script: null } as never);
    const existing = { ...machine("own", "server-own", "linux", "aegis", "server"), remote_user: "darckware", login_password_stored: true, login_password_in_vault: true, access_verified_at: "2026-11-13T18:00:00Z" };
    const onExecution = renderDialog([existing], "own");
    await screen.findByRole("option", { name: /server-own/ });
    expect(screen.getByRole("radio", { name: "Conta cadastrada: darckware" })).toHaveAttribute("aria-checked", "true");
    const lock = screen.getByRole("checkbox", { name: /Bloquear a conta/ });
    expect(lock).toBeDisabled();
    expect(lock).not.toBeChecked();
    fireEvent.click(screen.getByRole("checkbox", { name: /Usar a senha darckware desta máquina/ }));
    expect(screen.queryByLabelText("Senha do administrador")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preparar agora" }));
    await vi.waitFor(() => expect(onExecution).toHaveBeenCalledWith("reconfigured"));
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/servers/own/preparation", {
      mode: "ssh", admin_user: "darckware", admin_password: null, disable_admin: false, use_stored_password: true, ssh_port: 22,
    });
    expect(apiClient.get).not.toHaveBeenCalledWith(expect.stringContaining("login-password"));
  });

  it("does not offer the stored password for a legacy login", async () => {
    renderDialog([{ ...machine("old", "server-old", "linux", "aegis", "server"), login_password_stored: true }], "old");
    await screen.findByRole("option", { name: /server-old/ });
    expect(screen.queryByRole("checkbox", { name: /Usar a senha darckware/ })).not.toBeInTheDocument();
  });

  it("retains pending validation after failure and validates staged access after a reload", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ ok: false, detail: "Login verification failed" } as never)
      .mockResolvedValueOnce({ ok: true } as never);
    renderDialog([{ ...machine("pending", "server-pending", "linux", "aegis", "server"), preparation_pending: true }], "pending");
    await screen.findByRole("option", { name: /server-pending/ });
    fireEvent.click(screen.getByRole("button", { name: "Validar acesso" }));
    expect(await screen.findByText("Login verification failed")).toBeInTheDocument();
    expect(screen.getByText(/Há uma configuração pendente/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Validar acesso" }));
    expect(await screen.findByText(/Acesso darckware validado/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Validar acesso" })).not.toBeInTheDocument();
    expect(apiClient.post).toHaveBeenLastCalledWith("/api/v1/servers/pending/preparation/validate");
  });


  it("recovers the existing pending script without generating another preparation", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ script: "staged-existing-script", language: "sh" } as never);
    renderDialog([{ ...machine("pending", "server-pending", "linux", "aegis", "server"), preparation_pending: true }], "pending");
    await screen.findByRole("option", { name: /server-pending/ });
    expect(screen.queryByRole("button", { name: "Preparar agora" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Recuperar instruções pendentes" }));
    expect(await screen.findByText("staged-existing-script")).toBeInTheDocument();
    expect(apiClient.post).toHaveBeenCalledExactlyOnceWith("/api/v1/servers/pending/preparation/pending");
    expect(screen.getByRole("button", { name: "Validar acesso" })).toBeInTheDocument();
  });

});
