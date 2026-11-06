import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient, ApiError } from "@/lib/api";
import { DirectAccessCard } from "./DirectAccessCard";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const agent = (id: string, name: string, runtime_type: string) => ({ id, name, is_active: true, status: "active", agent_type: "executor", runtime_type });
const open = {
  id: "d1", agent_id: "a1", agent_name: "Porthus", purpose: "support", allow_elevation: true, reason: "Fix the deploy",
  machines: [{ id: "m1", name: "lab-1", sensitive: false }], granted_by: "marcelo",
  opened_at: new Date().toISOString(), expires_at: new Date(Date.now() + 90 * 60_000).toISOString(),
};

function setup(active: unknown[] = []) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/remote-access/direct") return active as never;
    if (url.startsWith("/api/v1/agents")) return [agent("a1", "Porthus", "claude"), agent("a2", "Aramis", "codex"), agent("a3", "Dartan", "agy"), agent("a4", "Athos", "hermes")] as never;
    if (url === "/api/v1/servers") return [{ id: "m1", name: "lab-1" }, { id: "m2", name: "srv-app02" }] as never;
    return [] as never;
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><DirectAccessCard /></QueryClientProvider>);
}

async function fillForm() {
  fireEvent.click(await screen.findByRole("button", { name: "Abrir acesso" }));
  await screen.findByRole("option", { name: "Porthus" });
  fireEvent.change(screen.getByLabelText("Agente"), { target: { value: "a1" } });
  fireEvent.click(await screen.findByRole("checkbox", { name: "srv-app02" }));
  fireEvent.change(screen.getByLabelText("Motivo"), { target: { value: "Corrigir o deploy" } });
}

const submitButton = () => screen.getAllByRole("button", { name: "Abrir acesso" }).at(-1)!;

describe("DirectAccessCard", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("offers only Claude, Codex and agy, with sudo/docker off", async () => {
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Abrir acesso" }));
    expect(await screen.findByRole("option", { name: "Aramis" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Dartan" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Athos" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Permitir sudo/docker" })).not.toBeChecked();
    expect(screen.getByRole("option", { name: "1 hora" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "4 horas" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "24 horas" })).toBeInTheDocument();
  });

  it("needs agent, machine and reason before opening", async () => {
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Abrir acesso" }));
    expect(submitButton()).toBeDisabled();
  });

  it("asks once on the same screen for a sensitive machine, then confirms", async () => {
    vi.mocked(apiClient.post)
      .mockRejectedValueOnce(new ApiError("conflict", 409, { detail: { code: "SENSITIVE_CONFIRMATION_REQUIRED", machines: ["srv-app02"] } }))
      .mockResolvedValueOnce({} as never);
    setup();
    await fillForm();
    fireEvent.click(submitButton());
    expect(await screen.findByText("Inclui srv-app02. Abrir acesso mesmo assim?")).toBeInTheDocument();
    expect(vi.mocked(apiClient.post).mock.calls[0][1]).toMatchObject({ confirm_sensitive: false, allow_elevation: false });
    fireEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledTimes(2));
    expect(vi.mocked(apiClient.post).mock.calls[1][1]).toMatchObject({ confirm_sensitive: true, duration_hours: 1, purpose: "support" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("drops the confirmation when the selection changes", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(
      new ApiError("conflict", 409, { detail: { code: "SENSITIVE_CONFIRMATION_REQUIRED", machines: ["srv-app02"] } }));
    setup();
    await fillForm();
    fireEvent.click(submitButton());
    await screen.findByText("Inclui srv-app02. Abrir acesso mesmo assim?");
    fireEvent.click(screen.getByRole("checkbox", { name: "lab-1" }));
    expect(screen.queryByText("Inclui srv-app02. Abrir acesso mesmo assim?")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirmar" })).not.toBeInTheDocument();
  });

  it("lists an open access with its time left and closes it after confirming", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: "d1", closed_at: "", running_commands: 1, notice: "" } as never);
    setup([open]);
    expect(await screen.findByText("Porthus")).toBeInTheDocument();
    expect(screen.getByText("resta 1 h 30 min")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Encerrar" }));
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(await screen.findByText(/não é interrompido/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Encerrar" }).at(-1)!);
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/d1:close", {}));
    expect(await screen.findByText(/1 comando continua em execução/)).toBeInTheDocument();
  });
});
