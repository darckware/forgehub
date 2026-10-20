import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/i18n";
import { SecretInputPopover } from "./SecretInputPopover";

afterEach(async () => { cleanup(); await i18n.changeLanguage("pt-BR"); });

it("uses the active interface language for the secret dialog and agent instruction", async () => {
  await i18n.changeLanguage("es");
  const onInsertSecret = vi.fn();
  render(<SecretInputPopover onInsertSecret={onInsertSecret} />);

  fireEvent.click(screen.getByRole("button", { name: "Insertar contraseña o token secreto (ForgeVault)" }));
  expect(screen.getByRole("dialog", { name: "Insertar contraseña o token en ForgeVault" })).toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText("Ej.: TYPESAFE_API_KEY"), { target: { value: "MI_CLAVE" } });
  fireEvent.change(screen.getByPlaceholderText("Pega el valor secreto…"), { target: { value: "valor-privado" } });
  fireEvent.click(screen.getByRole("button", { name: "Insertar en ForgeVault" }));

  expect(onInsertSecret).toHaveBeenCalledWith(
    'Por favor, guarda esta credencial de forma segura en ForgeVault:\n<secret name="MI_CLAVE" env="production">valor-privado</secret>',
  );
});
