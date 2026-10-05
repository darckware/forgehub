import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import IrregularitiesPage from "./index";

vi.mock("@/hooks/useIrregularities", () => ({
  useIrregularities: () => ({ data: [], isLoading: false }),
  useUpdateIrregularityStatus: () => ({ isPending: false, mutate: vi.fn() }),
}));
vi.mock("@/hooks/useWorkstations", () => ({ useWorkstations: () => ({ data: [] }) }));
vi.mock("@/hooks/useClients", () => ({ useClients: () => ({ data: [] }) }));

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage("pt-BR");
});

it("shows filters and empty state in Spanish", async () => {
  await i18n.changeLanguage("es");
  render(<IrregularitiesPage />);
  expect(screen.getByRole("heading", { name: "Irregularidades" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Todos los estados" })).toBeInTheDocument();
  expect(screen.getByText("No se encontraron irregularidades.")).toBeInTheDocument();
});
