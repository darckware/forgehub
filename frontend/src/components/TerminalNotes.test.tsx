import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const save = vi.fn(async ({ notes }: { id: string; notes: string }) => ({ label: null, notes }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/hooks/useTerminalBrowse", () => ({ useUpdateTerminalMetadata: () => ({ mutateAsync: save, isPending: false, isError: false }) }));

import { TerminalNotes } from "./TerminalNotes";

describe("TerminalNotes", () => {
  it("saves notes against the active session and keeps an unsaved draft when hidden", async () => {
    const { rerender } = render(<TerminalNotes sessionId="session-1" label="Codex - ForgeHub" notes="antes" open onClose={() => {}} />);
    expect(screen.getByText("Codex - ForgeHub")).toBeInTheDocument();
    const input = screen.getByLabelText("terminalNotes.description");
    fireEvent.change(input, { target: { value: "Retomar após o limite" } });
    rerender(<TerminalNotes sessionId="session-1" label="Codex - ForgeHub" notes="antes" open={false} onClose={() => {}} />);
    rerender(<TerminalNotes sessionId="session-1" label="Codex - ForgeHub" notes="antes" open onClose={() => {}} />);
    expect(input).toHaveValue("Retomar após o limite");
    fireEvent.click(screen.getByText("terminalNotes.save"));
    await waitFor(() => expect(save).toHaveBeenCalledWith({ id: "session-1", notes: "Retomar após o limite", expected_notes: "antes" }));
  });
});
