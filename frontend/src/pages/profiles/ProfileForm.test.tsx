import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import ProfileForm from "./ProfileForm";

const { updateProfile } = vi.hoisted(() => ({ updateProfile: vi.fn() }));

vi.mock("@/hooks/useAuth", () => ({
  useCreateProfile: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateProfile: () => ({ isPending: false, mutateAsync: updateProfile }),
}));

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("localizes permission labels and sensitive actions", async () => {
  await i18n.changeLanguage("es");
  render(<ProfileForm onClose={() => undefined} />);
  expect(screen.getByText("Permisos para acciones sensibles")).toBeInTheDocument();
  expect(screen.getByText("Crear y revisar conceptos")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Guardar" })).toBeInTheDocument();
});

it("keeps existing permissions outside the displayed catalog when saving", async () => {
  const { fireEvent, waitFor } = await import("@testing-library/react");
  render(<ProfileForm onClose={() => undefined} profile={{
    id: "p", name: "Existing", description: null,
    permissions: [{ module: "legacy_module", can_view: true, can_query: true, can_write: true, can_delete: true }],
    action_permissions: [{ action_key: "channel.manage", allowed: true }],
    created_at: "", updated_at: "",
  }} />);
  fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(updateProfile).toHaveBeenCalledWith(expect.objectContaining({
    body: expect.objectContaining({
      permissions: expect.arrayContaining([expect.objectContaining({ module: "legacy_module", can_delete: true })]),
      action_permissions: expect.arrayContaining([expect.objectContaining({ action_key: "channel.manage", allowed: true })]),
    }),
  })));
});
