import { afterEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { usePhoneMenuStyle } from "./usePhoneMenuStyle";

function mockViewport(phone: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: phone,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

function anchorAt(bottom: number) {
  const el = document.createElement("div");
  el.getBoundingClientRect = () => ({ bottom } as DOMRect);
  return { current: el };
}

describe("usePhoneMenuStyle", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("places an open menu under its anchor on a phone, not at the viewport's bottom", () => {
    mockViewport(true);
    const { result } = renderHook(() => usePhoneMenuStyle(anchorAt(120), true));
    expect(result.current).toEqual({ top: 124, maxHeight: "calc(100dvh - 132px)", overflowY: "auto" });
  });

  it("leaves the desktop classes alone", () => {
    mockViewport(false);
    const { result } = renderHook(() => usePhoneMenuStyle(anchorAt(120), true));
    expect(result.current).toBeUndefined();
  });

  it("returns nothing while closed", () => {
    mockViewport(true);
    const { result } = renderHook(() => usePhoneMenuStyle(anchorAt(120), false));
    expect(result.current).toBeUndefined();
  });
});
