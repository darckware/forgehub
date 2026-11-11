import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import type { MissionTask } from "@/hooks/useMissions";
import { missionTask } from "@/test/fixtures/missionBoard";
import { MissionCriteria } from "./MissionCriteria";

const task: MissionTask = missionTask({ task_id: "task-1", number: 1, title: "API response" });

function open(canManage = true) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: {
    queries: { retry: false }, mutations: { retry: false },
  } })}>
    <MissionCriteria projectId="mission-1" tasks={[task]} reviewers={[]} canManage={canManage} />
  </QueryClientProvider>);
}

beforeEach(async () => { vi.restoreAllMocks(); await i18n.changeLanguage("pt-BR"); });

describe("mission acceptance criteria", () => {
  it("links an objective criterion to selected work and assigns a verifier", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue([]);
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({ id: "criterion-1" });
    open();
    fireEvent.change(await screen.findByLabelText("Código"), { target: { value: "AC-1" } });
    fireEvent.change(screen.getByLabelText("Resultado esperado"), { target: { value: "A resposta segue o contrato" } });
    fireEvent.change(screen.getByLabelText("Como verificar"), { target: { value: "Executar o teste de contrato" } });
    fireEvent.click(screen.getByLabelText(/API response/));
    fireEvent.click(screen.getByRole("button", { name: "Salvar critério" }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/v1/missions/mission-1/criteria",
      expect.objectContaining({ code: "AC-1", task_ids: ["task-1"], verifier_is_marcelo: true })));
  });

  it("keeps the criteria read-only after the baseline", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue([]);
    open(false);
    expect(await screen.findByText("Nenhum critério de aceite cadastrado.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Salvar critério" })).toBeNull();
  });

  it("shows a load failure instead of treating it as an empty list", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("offline"));
    open(false);
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar os critérios.");
  });
});
