import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@/i18n";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import MissionsPage from "./index";

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><MissionsPage /></MemoryRouter></QueryClientProvider>);
}

const summary = {
  project_id: "m07-a", name: "m07 Missão A", state: "active", priority: 10, orchestrator: { id: "o", name: "Athos" },
  deadline_at: null, remaining_seconds: null, progress: { done_proven: 1, total: 4 }, running: 1, queued: 2,
  awaiting_review: 0, uncertain: 1, conflicts: 1, warnings: 0, last_decision: null,
};

beforeEach(async () => { await i18n.changeLanguage("pt-BR"); });
afterEach(() => vi.restoreAllMocks());

describe("missions list (M0.7)", () => {
  it("loading", () => {
    vi.spyOn(apiClient, "get").mockReturnValue(new Promise(() => {}));
    open();
    expect(screen.getByTestId("missions-loading")).toBeInTheDocument();
  });

  it("empty", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25, contested_agents: [] });
    open();
    expect(await screen.findByTestId("missions-empty")).toBeInTheDocument();
  });

  it("error with retry", async () => {
    vi.spyOn(apiClient, "get").mockRejectedValue(new Error("down"));
    open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível carregar as missões.");
  });

  it("lists missions with counts and the contested agents panel", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      items: [summary, { ...summary, project_id: "m07-b", name: "m07 Missão B", priority: 50 }], total: 2, page: 1, page_size: 25,
      contested_agents: [{ agent_id: "x", name: "Porthus", winner_project_id: "m07-a",
        missions: [{ project_id: "m07-a", name: "m07 Missão A", priority: 10 }, { project_id: "m07-b", name: "m07 Missão B", priority: 50 }] }],
    });
    open();
    expect((await screen.findAllByText("m07 Missão A")).length).toBeGreaterThan(0);
    expect(screen.getByTestId("contested-agents")).toHaveTextContent("vence por prioridade: m07 Missão A");
  });
});
