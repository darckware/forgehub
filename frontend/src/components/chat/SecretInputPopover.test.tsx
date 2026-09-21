import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SecretInputPopover } from "./SecretInputPopover";

describe("SecretInputPopover", () => {
  it("opens popover, fills secret info, and submits formatted prompt for ForgeVault", () => {
    const onInsertSecret = vi.fn();
    render(<SecretInputPopover onInsertSecret={onInsertSecret} />);

    // Trigger button
    const trigger = screen.getByLabelText("Inserir Senha ou Token Secreto (ForgeVault)");
    expect(trigger).toBeInTheDocument();

    // Open popover
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Gravar Segredo no ForgeVault")).toBeInTheDocument();

    // Fill secret name
    const nameInput = screen.getByPlaceholderText("Ex: TYPESAFE_API_KEY");
    fireEvent.change(nameInput, { target: { value: "typesafe_api_key" } });

    // Fill secret value
    const valInput = screen.getByPlaceholderText("Cole o valor da chave secreta...");
    fireEvent.change(valInput, { target: { value: "ts_live_key_secret_9988" } });

    // Submit
    const submitBtn = screen.getByRole("button", { name: /Inserir para o ForgeVault/i });
    fireEvent.click(submitBtn);

    expect(onInsertSecret).toHaveBeenCalledWith(
      'Por favor, grave com segurança esta credencial no ForgeVault:\n<secret name="TYPESAFE_API_KEY" env="production">ts_live_key_secret_9988</secret>'
    );

    // Popover should close
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows error if secret name or value is missing", () => {
    const onInsertSecret = vi.fn();
    render(<SecretInputPopover onInsertSecret={onInsertSecret} />);

    const trigger = screen.getByLabelText("Inserir Senha ou Token Secreto (ForgeVault)");
    fireEvent.click(trigger);

    const submitBtn = screen.getByRole("button", { name: /Inserir para o ForgeVault/i });
    fireEvent.click(submitBtn);

    expect(screen.getByText(/Informe o nome do segredo/i)).toBeInTheDocument();
    expect(onInsertSecret).not.toHaveBeenCalled();
  });
});
