import { describe, expect, it } from "vitest";
import { ctrlByte } from "./terminalCtrlKey";

describe("ctrlByte", () => {
  it("maps letters in either case to C0", () => {
    expect(ctrlByte("a")).toBe("\x01");
    expect(ctrlByte("r")).toBe("\x12");
    expect(ctrlByte("R")).toBe("\x12");
    expect(ctrlByte("z")).toBe("\x1a");
  });

  it("maps the punctuation a terminal knows", () => {
    expect(ctrlByte("[")).toBe("\x1b");
    expect(ctrlByte("\\")).toBe("\x1c");
    expect(ctrlByte("_")).toBe("\x1f");
    expect(ctrlByte("@")).toBe("\x00");
    expect(ctrlByte(" ")).toBe("\x00");
    expect(ctrlByte("?")).toBe("\x7f");
  });

  it("refuses what Ctrl doesn't change", () => {
    expect(ctrlByte("1")).toBeNull();
    expect(ctrlByte("é")).toBeNull();
    expect(ctrlByte("ab")).toBeNull();
    expect(ctrlByte("")).toBeNull();
  });
});
