import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it } from "vitest";
import i18n from "@/i18n";
import LoginPage from "./LoginPage";

afterEach(async () => {
  cleanup();
  await i18n.changeLanguage("pt-BR");
});

it("renders login controls in the selected language", async () => {
  await i18n.changeLanguage("pt-BR");
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><LoginPage /></MemoryRouter>
    </QueryClientProvider>,
  );
  expect(screen.getByRole("heading", { name: "Bem-vindo de volta" })).toBeInTheDocument();
  expect(screen.getByLabelText("Usuário")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Entrar" })).toBeInTheDocument();
});
