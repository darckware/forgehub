import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import { MissionAcceptance } from "./MissionAcceptance";

function open(canAct = true) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MissionAcceptance projectId="mission-1" canAct={canAct} />
  </QueryClientProvider>);
}
beforeEach(async () => { vi.restoreAllMocks(); await i18n.changeLanguage("pt-BR"); });
describe("mission acceptance", () => {
  const request = { id: "request-1", target_type: "mission_dossier", target_id: "mission-1", target_hash: "abc123", requested_by_name: "Athos", target_revision_id: "version-1" };
  it("requires a reason and confirms the exact dossier before deciding", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue([request]);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({});
    open();
    expect(await screen.findByText("abc123")).toBeInTheDocument();
    const accept = screen.getByRole("button", { name: "Aceitar missão" });
    expect(accept).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Motivo do aceite ou da devolução"), { target: { value: "Entregas conferidas" } });
    fireEvent.click(accept);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("abc123");
    expect(within(dialog).queryByRole("textbox")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Aceitar missão" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/governed/approval-requests/request-1:decide",
      expect.objectContaining({ decision: "approved", comments: "Entregas conferidas" })));
  });
  it("keeps a viewer read only", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue([request]);
    open(false);
    expect(await screen.findByText("abc123")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Aceitar missão" })).toBeNull();
  });
  it("distinguishes a missing request from failed loading", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("network failed"));
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar o pedido de aceite.");
    expect(screen.queryByText("O orquestrador ainda não solicitou o aceite.")).toBeNull();
  });
});
