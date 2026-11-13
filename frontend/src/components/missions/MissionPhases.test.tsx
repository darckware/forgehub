import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { MissionPhase } from "@/hooks/useMissions";
import { missionBoardSchema } from "@/hooks/useMissions";
import { missionBoard, missionPhase } from "@/test/fixtures/missionBoard";
import { MissionPhases } from "./MissionPhases";

function open(phases: MissionPhase[], { canEdit = false, canDecide = true } = {}) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: {
    queries: { retry: false }, mutations: { retry: false },
  } })}>
    <MissionPhases projectId="mission-1" phases={phases} canEdit={canEdit} canDecide={canDecide} />
  </QueryClientProvider>);
}

beforeEach(async () => { vi.restoreAllMocks(); await i18n.changeLanguage("pt-BR"); });

describe("mission phases", () => {
  it("renders numbered phases with their status and expands to planning items and tasks", () => {
    open([missionPhase(), missionPhase({ phase_id: "ph-2", position: 2, name: "Telas", planning_items: [] })]);
    const first = screen.getByTestId("phase-1");
    expect(within(first).getByText("Estrutura")).toBeInTheDocument();
    expect(within(first).getByText("Planejada")).toBeInTheDocument();
    expect(screen.queryByText("Menu e rotas")).toBeNull();
    fireEvent.click(within(first).getByRole("button", { name: /Estrutura/ }));
    expect(screen.getByText("Menu e rotas")).toBeInTheDocument();
    expect(screen.getByText("#9102 Rotas")).toBeInTheDocument();
    // Read-only for a viewer who cannot edit.
    expect(screen.queryByRole("button", { name: "Adicionar fase" })).toBeNull();
  });

  it("adds a phase with name and objective", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ phases: [] });
    open([], { canEdit: true });
    expect(screen.getByText("Nenhuma fase cadastrada.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Nome da fase"), { target: { value: "Estrutura" } });
    fireEvent.change(screen.getByLabelText("Objetivo"), { target: { value: "Navegação, sem regras" } });
    fireEvent.click(screen.getByRole("button", { name: "Adicionar fase" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/mission-1/phases",
      { name: "Estrutura", objective: "Navegação, sem regras" }));
  });

  it("approves a homologated phase", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ phases: [] });
    open([missionPhase({ phase_status: "awaiting_approval", homologation_verdict: "approved",
      homologation_summary: "Navegação testada", homologation_evidence: "git:abc123",
      homologator: { agent_id: "a-dartan", name: "Dartan" } })]);
    fireEvent.click(screen.getByRole("button", { name: /Estrutura/ }));
    expect(screen.getByText("Homologação por Dartan: aprovada")).toBeInTheDocument();
    expect(screen.getByText("Evidências: git:abc123")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Aprovar fase" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/mission-1/phases/ph-1:approve",
      { expected_phase_status: "awaiting_approval" }));
  });

  it("returns a phase only with a reason", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ phases: [] });
    open([missionPhase({ phase_status: "awaiting_approval", homologation_summary: "ok" })]);
    fireEvent.click(screen.getByRole("button", { name: /Estrutura/ }));
    fireEvent.click(screen.getByRole("button", { name: "Devolver" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Devolver" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Motivo"), { target: { value: "Faltou o menu" } });
    fireEvent.click(confirm);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/mission-1/phases/ph-1:return",
      { reason: "Faltou o menu", expected_phase_status: "awaiting_approval" }));
  });

  it("hides the decision from a viewer who is not Marcelo", () => {
    open([missionPhase({ phase_status: "awaiting_approval" })], { canDecide: false });
    fireEvent.click(screen.getByRole("button", { name: /Estrutura/ }));
    expect(screen.queryByRole("button", { name: "Aprovar fase" })).toBeNull();
  });

  it("parses a board without phases (older backend) as an empty list", () => {
    const { phases: _omit, ...withoutPhases } = missionBoard();
    expect(missionBoardSchema.parse(withoutPhases).phases).toEqual([]);
  });
});
