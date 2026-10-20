import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { TailscaleApiKeyCard } from "./TailscaleApiKeyCard";

vi.mock("@/lib/api", () => ({ apiClient: { get: vi.fn(), put: vi.fn(), delete: vi.fn() } }));

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><TailscaleApiKeyCard /></QueryClientProvider>);
}

describe("TailscaleApiKeyCard", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("pt-BR");
  });

  it("saves only a tskey-api credential and never shows it back", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ configured: false, hint: null, updated_by: null, updated_at: null } as never);
    vi.mocked(apiClient.put).mockResolvedValue({ configured: true, hint: "ab12", updated_by: "m", updated_at: "2026-10-20T10:00:00Z" } as never);
    renderCard();
    expect(await screen.findByText(/Não configurada/)).toBeInTheDocument();
    const input = screen.getByLabelText("Nova credencial da API");
    fireEvent.change(input, { target: { value: "tskey-auth-wrongkind" } });
    expect(screen.getByRole("button", { name: "Salvar" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "tskey-api-kXYZ-ab12" } });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText("Configurada (termina em ab12)")).toBeInTheDocument();
    expect(apiClient.put).toHaveBeenCalledWith("/api/v1/vpn/tailscale-api-key", { api_key: "tskey-api-kXYZ-ab12" });
    expect(input).toHaveValue("");
  });
});
