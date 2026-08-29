import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
});
