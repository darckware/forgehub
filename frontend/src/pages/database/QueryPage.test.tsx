import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import QueryPage from "./QueryPage";

vi.mock("./SchemaContext", () => ({ useSchema: () => ({ instance: "company", db: "forgehub", schema: "company" }) }));
vi.mock("@/hooks/useDatabase", () => ({ useExecuteQuery: () => ({ isPending: false, mutateAsync: vi.fn() }) }));

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("shows query actions in Spanish", async () => {
  await i18n.changeLanguage("es");
  render(<QueryPage />);
  expect(screen.getByRole("button", { name: "Ejecutar" })).toBeInTheDocument();
  expect(screen.getByText("Ejecuta una consulta para ver los resultados")).toBeInTheDocument();
});
