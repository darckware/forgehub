import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import PromptCommandsPage from "./index";

vi.mock("@/hooks/usePromptCommands", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/usePromptCommands")>();
  return {
    ...actual,
    usePromptCommands: () => ({ data: [], isLoading: false, isError: false }),
    useCreatePromptCommand: () => ({ isPending: false, mutate: vi.fn() }),
    useUpdatePromptCommand: () => ({ isPending: false, mutate: vi.fn() }),
    useDeletePromptCommand: () => ({ isPending: false, mutate: vi.fn() }),
  };
});
vi.mock("@/components/AssistantToggleButton", () => ({ AssistantToggleButton: () => null }));

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("shows the command catalog in Spanish", async () => {
  await i18n.changeLanguage("es");
  render(<PromptCommandsPage />);
  expect(screen.getByRole("heading", { name: "Comandos del chat" })).toBeInTheDocument();
  expect(screen.getByText("No hay comandos registrados todavía.")).toBeInTheDocument();
});
