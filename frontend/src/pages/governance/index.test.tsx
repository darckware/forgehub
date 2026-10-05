import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import GovernancePage from "./index";

vi.mock("@/hooks/useBacklog", () => ({
  usePlanningItems: () => ({ data: [], isLoading: false }),
  useUpdatePlanningItem: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));
vi.mock("@/hooks/useProject", () => ({ useProjects: () => ({ data: [] }) }));
vi.mock("@/hooks/useTask", () => ({ useTasks: () => ({ data: [] }) }));
vi.mock("@/hooks/useAgent", () => ({ useAgents: () => ({ data: [] }) }));

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("renders the governance gate in English", async () => {
  await i18n.changeLanguage("en");
  render(<MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><GovernancePage /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "5. Governance gate" })).toBeInTheDocument();
  expect(screen.getByText("No items found in this governance category")).toBeInTheDocument();
});
