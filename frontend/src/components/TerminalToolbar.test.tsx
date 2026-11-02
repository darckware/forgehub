import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/hooks/usePhoneMenuStyle", () => ({ usePhoneMenuStyle: () => undefined }));
import { TerminalToolbar } from "./TerminalToolbar";

describe("TerminalToolbar", () => {
  it("exposes terminal actions directly and disables a missing link", () => {
    const copy = vi.fn();
    const zoomIn = vi.fn();
    render(<TerminalToolbar copied={false} onCopy={copy} latestLink={null} onOpenLatestLink={vi.fn()} fontSize={14} onZoomOut={vi.fn()} onZoomReset={vi.fn()} onZoomIn={zoomIn} touchDevice={false} touchInput={false} onToggleTouchInput={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "terminal.copy" }));
    fireEvent.click(screen.getByRole("button", { name: "terminal.zoomIn" }));
    expect(copy).toHaveBeenCalledOnce();
    expect(zoomIn).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "terminal.noLinkDetected" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "terminal.help.title" }));
    expect(screen.getByText("terminal.help.select")).toBeInTheDocument();
  });
});
