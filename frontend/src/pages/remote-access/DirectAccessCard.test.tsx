import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient, ApiError } from "@/lib/api";
import { DirectAccessCard } from "./DirectAccessCard";

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

const agent = (id: string, name: string, runtime_type: string, allowed = true, unsupported_reason: string | null = null) => ({ id, name, runtime_type, allowed, unsupported_reason });
const ACTIVE = { paused: false, paused_at: null, paused_by: null, reason: null };
const PAUSED = { paused: true, paused_at: "2026-11-06T12:00:00Z", paused_by: "marcelo", reason: "Incidente" };
const open = {
  id: "d1", agent_id: "a1", agent_name: "Porthus", purpose: "support", allow_elevation: true, reason: "Fix the deploy",
  machines: [{ id: "m1", name: "lab-1", sensitive: false }], granted_by: "marcelo",
  opened_at: new Date().toISOString(), expires_at: new Date(Date.now() + 90 * 60_000).toISOString(),
};

function setup(active: unknown[] = [], control: unknown = ACTIVE) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url === "/api/v1/remote-access/direct") return active as never;
    if (url === "/api/v1/remote-access/direct/control") return control as never;
    if (url === "/api/v1/remote-access/direct/agents") return [
      agent("a1", "Porthus", "claude"), agent("a2", "Aramis", "codex"), agent("a3", "Dartan", "agy"),
      agent("a4", "Athos", "hermes", false), agent("a5", "Lara", "hermes", false, "PROFILE_MCP_WITHOUT_MAINTENANCE_TOOLS"),
    ] as never;
    if (url === "/api/v1/servers") return [{ id: "m1", name: "lab-1" }, { id: "m2", name: "srv-app02" }] as never;
    return [] as never;
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><DirectAccessCard /></QueryClientProvider>);
}

/** Opening stays disabled until the pause switch has answered. */
async function openForm() {
  const button = await screen.findByRole("button", { name: "Abrir acesso" });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
}

async function fillForm() {
  await openForm();
  await within(await screen.findByRole("dialog")).findByRole("option", { name: "Porthus" });
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

  it("offers only the listed agents, with sudo/docker off", async () => {
    setup();
    await openForm();
    const form = within(await screen.findByRole("dialog"));
    expect(await form.findByRole("option", { name: "Aramis" })).toBeInTheDocument();
    expect(form.getByRole("option", { name: "Dartan" })).toBeInTheDocument();
    expect(form.queryByRole("option", { name: "Athos" })).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Permitir sudo/docker" })).not.toBeChecked();
    expect(screen.getByRole("option", { name: "1 hora" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "4 horas" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "24 horas" })).toBeInTheDocument();
  });

  it("needs agent, machine and reason before opening", async () => {
    setup();
    await openForm();
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
    expect((await screen.findAllByText("Porthus")).length).toBeGreaterThan(0);
    expect(await screen.findByText("resta 1 h 30 min")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Encerrar" }));
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(await screen.findByText(/não é interrompido/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Encerrar" }).at(-1)!);
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/d1:close", {}));
    expect(await screen.findByText(/1 comando continua em execução/)).toBeInTheDocument();
  });

  it("adds an agent from the active ones, and an unsupported one can't be picked", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({} as never);
    setup();
    const picker = await screen.findByLabelText("Agente para adicionar");
    await within(picker).findByRole("option", { name: "Athos" });
    expect(within(picker).queryByRole("option", { name: "Lara" })).not.toBeInTheDocument();
    expect(screen.getByText("Ainda não suportado")).toBeInTheDocument();
    expect(screen.getByText(/não expõe as ferramentas de manutenção/)).toBeInTheDocument();
    fireEvent.change(picker, { target: { value: "a4" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/agents/a4", {}));
  });

  it("removes an agent only after confirming, and says what was closed", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue({ agent_id: "a2", closed_accesses: 2, running_commands: 1, notice: "" } as never);
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Excluir Aramis da lista" }));
    expect(apiClient.delete).not.toHaveBeenCalled();
    expect(await screen.findByText(/encerrados agora/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    await waitFor(() => expect(apiClient.delete).toHaveBeenCalledWith("/api/v1/remote-access/direct/agents/a2"));
    expect(await screen.findByText(/2 acessos encerrados/)).toBeInTheDocument();
    expect(screen.getByText(/1 comando continua em execução/)).toBeInTheDocument();
  });

  it("pauses only after confirming, with an optional reason", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(PAUSED as never);
    setup();
    expect(await screen.findByText(/Pausa bloqueia o acesso de todos os agentes pelo ForgeHub\./)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Pausar" }));
    expect(apiClient.post).not.toHaveBeenCalled();
    fireEvent.change(await screen.findByLabelText("Motivo (opcional)"), { target: { value: "Incidente" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Pausar" }).at(-1)!);
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/control:pause", { reason: "Incidente" }));
  });

  it("shows the pause, blocks opening and reactivates in one click", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(ACTIVE as never);
    setup([open], PAUSED);
    expect(await screen.findByText(/pausado por marcelo/)).toBeInTheDocument();
    expect(screen.getByText("Incidente")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Abrir acesso" })).toBeDisabled());
    expect(await screen.findByText("resta 1 h 30 min")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Ativar" }));
    await waitFor(() => expect(apiClient.post).toHaveBeenCalledWith("/api/v1/remote-access/direct/control:resume", {}));
  });
});
