import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { ScriptLibrary } from "./ScriptLibrary";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

describe("ScriptLibrary", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (url.startsWith("/api/v1/host-scripts/categories")) return [{ id: "cat", slug: "diag", label: "Diagnóstico", description: null }] as never;
      return [{
        id: "sys", name: "Instalar RustDesk", category_id: "cat", description: "Instala", platform: "windows", risk: "change",
        timeout_seconds: 900, parameters: [], content: "x", current_version: 1, is_system: true, system_key: "rustdesk_install:windows",
        archived: false, created_by: "forgehub", updated_by: "forgehub", created_at: "", updated_at: "",
      }] as never;
    });
  });

  it("lists by classification, locks system scripts and creates a script with parameters", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ id: "new" } as never);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={qc}><ScriptLibrary /></QueryClientProvider>);
    expect(await screen.findByRole("region", { name: "Diagnóstico" })).toBeInTheDocument();
    expect(screen.getByText("Sistema")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Editar Instalar RustDesk" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Novo script" }));
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Limpar temp" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar parâmetro" }));
    fireEvent.change(screen.getByLabelText("Nome (MAIÚSCULAS)"), { target: { value: "dias" } });
    fireEvent.change(screen.getByLabelText("Script"), { target: { value: "Get-ChildItem $env:TEMP" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    await vi.waitFor(() => expect(apiClient.post).toHaveBeenCalled());
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/host-scripts", expect.objectContaining({
      name: "Limpar temp", category_id: "cat", platform: "windows", content: "Get-ChildItem $env:TEMP",
      parameters: [{ name: "DIAS", label: null, required: false, default: null, secret: false }],
    }));
  });
});
