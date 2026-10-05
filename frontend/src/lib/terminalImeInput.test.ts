import { describe, expect, it, vi } from "vitest";
import { attachTerminalImeInput, imeEditToPtyInput } from "./terminalImeInput";

const DEL = "\x7f";

describe("imeEditToPtyInput", () => {
  it("sends only the appended text", () => {
    expect(imeEditToPtyInput("ola", "ola.")).toBe(".");
  });

  it("erases and retypes an autocorrected word instead of resending the line", () => {
    // The 2026-10-04 report: "." made Gboard rewrite the sentence.
    const before = "ele esta duplicand o texto digitado";
    const after = "ele está duplicado o texto digitado. ";
    const data = imeEditToPtyInput(before, after);
    expect(data).toBe(DEL.repeat("a duplicand o texto digitado".length) + "á duplicado o texto digitado. ");
    expect(data).not.toContain("ele esta");
  });

  it("turns a deletion into DEL and a line break into Enter", () => {
    expect(imeEditToPtyInput("abc", "ab")).toBe(DEL);
    expect(imeEditToPtyInput("ls", "ls\n")).toBe("\r");
  });
});

describe("attachTerminalImeInput", () => {
  function setup() {
    const container = document.createElement("div");
    const textarea = document.createElement("textarea");
    container.appendChild(textarea);
    document.body.appendChild(container);
    const xtermInput = vi.fn();
    textarea.addEventListener("input", xtermInput, true);
    textarea.addEventListener("keydown", xtermInput, true);
    const send = vi.fn();
    const detach = attachTerminalImeInput(container, () => textarea, send);
    const type = (value: string) => {
      textarea.dispatchEvent(new KeyboardEvent("keydown", { keyCode: 229, bubbles: true } as KeyboardEventInit));
      textarea.value = value;
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
    };
    return { textarea, send, xtermInput, detach, type };
  }

  it("keeps IME edits away from xterm and sends each change once", () => {
    const { send, xtermInput, type, detach } = setup();
    type("ola");
    type("olá.");
    expect(send.mock.calls.map(([d]) => d)).toEqual(["ola", `${DEL}á.`]);
    expect(xtermInput).not.toHaveBeenCalled();
    detach();
  });
});
