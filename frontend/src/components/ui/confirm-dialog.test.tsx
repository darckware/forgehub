import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { ConfirmDialog } from "./confirm-dialog";


describe("ConfirmDialog", () => {
  it("keeps a failed destructive action visible with an actionable error", () => {
    render(
      <ConfirmDialog
        open
        title="Excluir agente"
        error="Este agente possui histórico operacional. Arquive-o em vez de excluir."
        onConfirm={() => undefined}
        onCancel={() => undefined}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("histórico operacional");
  });

  it("renders operation context and prevents an unavailable confirmation", () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Solicitar monitoramento"
        confirmLabel="Confirmar solicitação"
        confirmDisabled
        onConfirm={onConfirm}
        onCancel={() => undefined}
      >
        <dl>
          <dt>Execução</dt>
          <dd>EXEC-284</dd>
        </dl>
      </ConfirmDialog>,
    );

    expect(screen.getByRole("dialog")).toHaveTextContent("EXEC-284");
    const confirm = screen.getByRole("button", { name: "Confirmar solicitação" });
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("contains modal focus, makes the background inert, and restores the opener", () => {
    const onCancel = vi.fn();
    const { container, rerender } = render(
      <>
        <button type="button" onClick={() => undefined}>Open operation</button>
        <ConfirmDialog
          open={false}
          closeLabel="Close operation"
          confirmLabel="Confirm operation"
          onConfirm={() => undefined}
          onCancel={onCancel}
        />
      </>,
    );
    const opener = screen.getByRole("button", { name: "Open operation" });
    opener.focus();

    rerender(
      <>
        <button type="button" onClick={() => undefined}>Open operation</button>
        <ConfirmDialog
          open
          closeLabel="Close operation"
          confirmLabel="Confirm operation"
          onConfirm={() => undefined}
          onCancel={onCancel}
        />
      </>,
    );

    const dialog = screen.getByRole("dialog");
    const close = screen.getByRole("button", { name: "Close operation" });
    const confirm = screen.getByRole("button", { name: "Confirm operation" });
    expect(screen.getByRole("button", { name: /cancelar/i })).toHaveFocus();
    expect(container).toHaveAttribute("inert");

    close.focus();
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(confirm).toHaveFocus();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(onCancel).toHaveBeenCalledOnce();

    rerender(
      <>
        <button type="button" onClick={() => undefined}>Open operation</button>
        <ConfirmDialog
          open={false}
          closeLabel="Close operation"
          confirmLabel="Confirm operation"
          onConfirm={() => undefined}
          onCancel={onCancel}
        />
      </>,
    );
    expect(screen.getByRole("button", { name: "Open operation" })).toHaveFocus();
    expect(container).not.toHaveAttribute("inert");
  });
});
