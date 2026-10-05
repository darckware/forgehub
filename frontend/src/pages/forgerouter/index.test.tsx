import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { apiClient } from "@/lib/api";
import ForgeRouterPage from "./index";

afterEach(async () => {
  cleanup();
  vi.restoreAllMocks();
  await i18n.changeLanguage("pt-BR");
});

it("announces the loading state in the active language", async () => {
  await i18n.changeLanguage("es");
  vi.spyOn(apiClient, "post").mockReturnValue(new Promise(() => undefined));
  render(<ForgeRouterPage />);
  expect(screen.getByRole("status")).toHaveTextContent("Preparando la sesión...");
});
