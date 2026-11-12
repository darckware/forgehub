import { StrictMode, useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@/i18n";
import { ConfirmDialog } from "./confirm-dialog";
import { SidePanel } from "./side-panel";

function Harness({ busy = false, onClose }: { busy?: boolean; onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Abrir</button>
      {open && (
        <SidePanel
          title="Conceder acesso"
          description="Escolha agentes e máquinas"
          busy={busy}
          onClose={() => { onClose?.(); setOpen(false); }}
          footer={<button type="button">Gravar</button>}
        >
          <input aria-label="Busca" />
        </SidePanel>
      )}
    </>
  );
}

describe("SidePanel", () => {
  it("renders a labelled modal dialog on the right with header, body and footer", () => {
    render(<SidePanel title="Histórico" description="Tudo que rodou" onClose={() => undefined} footer={<button type="button">Ok</button>}><p>corpo</p></SidePanel>);
    const dialog = screen.getByRole("dialog", { name: "Histórico" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAccessibleDescription("Tudo que rodou");
    expect(dialog.className).toContain("max-w-xl");
    expect(dialog.className).toContain("slide-in-from-right");
    expect(screen.getByText("corpo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ok" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fechar" })).toBeInTheDocument();
  });

  it("honors the size override and renders nothing while closed", () => {
    const { rerender } = render(<SidePanel open={false} title="X" onClose={() => undefined} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    rerender(<SidePanel title="X" size="3xl" onClose={() => undefined} />);
    expect(screen.getByRole("dialog").className).toContain("max-w-3xl");
  });

  it("closes on Escape, on the overlay and on the close button", () => {
    const onClose = vi.fn();
    render(<SidePanel title="X" onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByTestId("side-panel-overlay"));
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).toHaveBeenCalledTimes(3);
  });

  it("ignores Escape, the overlay and the close button while busy", () => {
    const onClose = vi.fn();
    render(<SidePanel title="X" busy onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.click(screen.getByTestId("side-panel-overlay"));
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true");
  });

  it("lets a confirmation inside the panel take the Escape first", () => {
    const onClose = vi.fn();
    const onCancel = vi.fn();
    render(
      <SidePanel title="X" onClose={onClose}>
        <ConfirmDialog open title="Excluir?" onConfirm={() => undefined} onCancel={onCancel} />
      </SidePanel>,
    );
    fireEvent.keyDown(screen.getByRole("dialog", { name: "Excluir?" }), { key: "Escape" });
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("focuses the first field on open and returns focus to the opener on close", () => {
    render(<Harness />);
    const opener = screen.getByRole("button", { name: "Abrir" });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("textbox", { name: "Busca" })).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("renders as a form and submits from the footer", () => {
    const onSubmit = vi.fn((e: React.FormEvent) => e.preventDefault());
    render(
      <SidePanel as="form" title="Novo" onSubmit={onSubmit} onClose={() => undefined} footer={<button type="submit">Gravar</button>}>
        <input aria-label="Nome" />
      </SidePanel>,
    );
    const dialog = screen.getByRole("dialog", { name: "Novo" });
    expect(dialog.tagName).toBe("FORM");
    fireEvent.click(screen.getByRole("button", { name: "Gravar" }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });

  it("keeps a field's own autoFocus and still returns focus to the real opener", () => {
    function AutoHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Abrir</button>
          {open && (
            <SidePanel title="Chave" onClose={() => setOpen(false)}>
              <input aria-label="Usuário" />
              <input aria-label="Senha" autoFocus />
            </SidePanel>
          )}
        </>
      );
    }
    render(<AutoHarness />);
    const opener = screen.getByRole("button", { name: "Abrir" });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("textbox", { name: "Senha" })).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(opener).toHaveFocus();
  });

  it("closes only the topmost panel on Escape", () => {
    const outer = vi.fn();
    const inner = vi.fn();
    render(
      <>
        <SidePanel title="Fora" onClose={outer} />
        <SidePanel title="Dentro" onClose={inner} />
      </>,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(inner).toHaveBeenCalledOnce();
    expect(outer).not.toHaveBeenCalled();
  });

  it("locks body scroll while any panel is open and restores it after the last closes", () => {
    document.body.style.overflow = "auto";
    const { rerender, unmount } = render(
      <>
        <SidePanel title="A" onClose={() => undefined} />
        <SidePanel title="B" onClose={() => undefined} />
      </>,
    );
    expect(document.body.style.overflow).toBe("hidden");
    rerender(<SidePanel title="A" onClose={() => undefined} />);
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe("auto");
    document.body.style.overflow = "";
  });

  it("returns focus to the opener under React StrictMode (Esc and close button), keeping autoFocus", () => {
    function StrictHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Abrir</button>
          {open && (
            <SidePanel title="Estrito" onClose={() => setOpen(false)}>
              <input aria-label="Primeiro" />
              <input aria-label="Senha" autoFocus />
            </SidePanel>
          )}
        </>
      );
    }
    render(<StrictMode><StrictHarness /></StrictMode>);
    const opener = screen.getByRole("button", { name: "Abrir" });

    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("textbox", { name: "Senha" })).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();

    fireEvent.click(opener);
    expect(screen.getByRole("textbox", { name: "Senha" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("under StrictMode focuses the first field when nothing asks for focus", () => {
    render(<StrictMode><Harness /></StrictMode>);
    const opener = screen.getByRole("button", { name: "Abrir" });
    opener.focus();
    fireEvent.click(opener);
    expect(screen.getByRole("textbox", { name: "Busca" })).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(opener).toHaveFocus();
  });
});
