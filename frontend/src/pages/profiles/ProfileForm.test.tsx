import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import ProfileForm from "./ProfileForm";

vi.mock("@/hooks/useAuth", () => ({
  useCreateProfile: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateProfile: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("localizes permission labels and sensitive actions", async () => {
  await i18n.changeLanguage("es");
  render(<ProfileForm onClose={() => undefined} />);
  expect(screen.getByText("Permisos para acciones sensibles")).toBeInTheDocument();
  expect(screen.getByText("Crear y revisar conceptos")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Guardar" })).toBeInTheDocument();
});
