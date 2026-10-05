import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import SchemaPage from "./SchemaPage";

vi.mock("./SchemaContext", () => ({ useSchema: () => ({ schema: "company", instance: "company", db: "forgehub" }) }));
vi.mock("@/hooks/useDatabase", () => ({
  useDatabaseTables: () => ({ data: [], isLoading: false, refetch: vi.fn(), isFetching: false }),
  useDatabaseTable: () => ({ data: null, isLoading: false }),
  useExecuteQuery: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDatabaseFunctions: () => ({ data: [], isLoading: false, refetch: vi.fn(), isFetching: false }),
  useDatabaseFunction: () => ({ data: null, isLoading: false }),
  useCreateFunction: () => ({ mutateAsync: vi.fn() }),
  useDropFunction: () => ({ mutateAsync: vi.fn() }),
  useDatabaseIndexes: () => ({ data: [], isLoading: false, refetch: vi.fn(), isFetching: false }),
  useDropIndex: () => ({ mutateAsync: vi.fn() }),
}));

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("shows database schema navigation and empty states in Spanish", async () => {
  await i18n.changeLanguage("es");
  render(<SchemaPage />);
  expect(screen.getByText("Selecciona una tabla")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Funciones" }));
  expect(screen.getByText("Selecciona una función")).toBeInTheDocument();
});
