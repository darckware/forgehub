import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PLAY_SPEED, useActivityTraceViewModel, validateCustomRange } from "./useActivityTraceViewModel";

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(() => new Promise(() => {})) },
}));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("validateCustomRange", () => {
  it("accepts up to 24 h and refuses reversed, too wide or empty ranges", () => {
    expect(validateCustomRange({ start: "2026-09-28T14:00", end: "2026-09-28T15:00" })).toBeNull();
    expect(validateCustomRange({ start: "2026-09-28T15:00", end: "2026-09-28T14:00" })).toBe("order");
    expect(validateCustomRange({ start: "2026-09-27T14:00", end: "2026-09-28T15:00" })).toBe("tooWide");
    expect(validateCustomRange({ start: "", end: "2026-09-28T15:00" })).toBe("invalid");
  });
});

describe("useActivityTraceViewModel", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-09-28T15:00:30Z"));
  });
  afterEach(() => vi.useRealTimers());

  it("starts live, enters replay on a cursor and returns to live", () => {
    const { result } = renderHook(() => useActivityTraceViewModel(), { wrapper });
    expect(result.current.cursor).toBeNull();
    expect(result.current.window).toEqual({ start: "2026-09-28T13:01:00.000Z", end: "2026-09-28T15:01:00.000Z" });
    act(() => result.current.setCursor(Date.parse("2026-09-28T14:00:00Z")));
    expect(result.current.cursor).toBe(Date.parse("2026-09-28T14:00:00Z"));
    // clamped to the window and never past now
    act(() => result.current.setCursor(Date.parse("2026-09-29T00:00:00Z")));
    expect(result.current.cursor).toBe(Date.parse("2026-09-28T15:00:30Z"));
    act(() => result.current.backToLive());
    expect(result.current.cursor).toBeNull();
  });

  it("plays from the window's start and stops by itself at now", () => {
    const { result } = renderHook(() => useActivityTraceViewModel(), { wrapper });
    act(() => result.current.setPreset("1h"));
    const start = result.current.windowStartMs!;
    act(() => result.current.togglePlay());
    expect(result.current.playing).toBe(true);
    expect(result.current.cursor).toBe(start);
    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(result.current.cursor).toBe(start + 1_000 * PLAY_SPEED);
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(result.current.playing).toBe(false);
    expect(result.current.cursor).toBeLessThanOrEqual(Date.now());
  });
});
