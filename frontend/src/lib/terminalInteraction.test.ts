import { describe, expect, it, vi } from "vitest";
import {
  copyTerminalText,
  findLastHttpUrl,
  terminalBufferToText,
  type TerminalBufferLike,
} from "./terminalInteraction";

describe("terminal interaction helpers", () => {
  it("finds the last URL even when ANSI/OSC sequences surround it", () => {
    const output = [
      "first https://example.test/old",
      "\u001b]8;;https://accounts.google.com/o/oauth2/auth?client_id=123&scope=email\u0007",
      "Click here\u001b]8;;\u0007",
    ].join("\n");

    expect(findLastHttpUrl(output)).toBe(
      "https://accounts.google.com/o/oauth2/auth?client_id=123&scope=email",
    );
  });

  it("reconstructs wrapped terminal rows without inserting line breaks", () => {
    const rows = [
      { isWrapped: false, text: "https://accounts.google.com/oauth?client=" },
      { isWrapped: true, text: "abc" },
      { isWrapped: false, text: "next line" },
    ];
    const buffer: TerminalBufferLike = {
      length: rows.length,
      getLine: (index) => {
        const row = rows[index];
        return row
          ? { isWrapped: row.isWrapped, translateToString: () => row.text }
          : undefined;
      },
    };

    expect(terminalBufferToText(buffer)).toBe(
      "https://accounts.google.com/oauth?client=abc\nnext line",
    );
  });

  it("falls back to execCommand when navigator.clipboard is unavailable", async () => {
    Object.defineProperty(document, "execCommand", {
      configurable: true,
      value: vi.fn(() => true),
    });
    const execCommand = vi.spyOn(document, "execCommand").mockReturnValue(true);

    await expect(copyTerminalText("authorization code")).resolves.toBe(true);
    expect(execCommand).toHaveBeenCalledWith("copy");
  });
});
