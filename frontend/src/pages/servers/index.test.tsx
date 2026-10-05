import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import ServersPage from ".";

vi.mock("@/hooks/useServers", () => ({
  useServers: () => ({ data: [], isLoading: false }),
  useDeleteServer: () => ({ isPending: false, mutate: vi.fn() }),
  useToggleServerAccess: () => ({ isPending: false, mutate: vi.fn() }),
  useServerStatusProbe: () => ({ statuses: {}, checkingIds: new Set(), isChecking: false, checkAll: vi.fn(), checkOne: vi.fn() }),
}));
vi.mock("@/components/AssistantToggleButton", () => ({ AssistantToggleButton: () => null }));

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("shows the server inventory empty state in Spanish", async () => {
  await i18n.changeLanguage("es");
  render(<MemoryRouter><ServersPage /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "Servidores" })).toBeInTheDocument();
  expect(screen.getByText("No se encontraron servidores en este grupo.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Nuevo servidor" })).toBeInTheDocument();
});
