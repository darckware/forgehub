import { describe, expect, it } from "vitest";
import { MIN_BLOCK_PERCENT, axisTicks, formatDuration, spanInWindow, timeToPercent } from "./swimlaneLayout";

const START = Date.parse("2026-09-28T14:00:00Z");
const END = Date.parse("2026-09-28T15:00:00Z");

describe("swimlaneLayout", () => {
  it("maps times to the window and clamps outside it", () => {
    expect(timeToPercent(START, START, END)).toBe(0);
    expect(timeToPercent(Date.parse("2026-09-28T14:30:00Z"), START, END)).toBe(50);
    expect(timeToPercent(END + 60_000, START, END)).toBe(100);
  });

  it("places a closed span, clips one crossing the edge, drops one outside", () => {
    const span = spanInWindow("2026-09-28T14:15:00Z", "2026-09-28T14:30:00Z", START, END, END);
    expect(span).toMatchObject({ left: 25, width: 25, clippedStart: false, clippedEnd: false });
    const crossing = spanInWindow("2026-09-28T13:50:00Z", "2026-09-28T14:06:00Z", START, END, END);
    expect(crossing).toMatchObject({ left: 0, clippedStart: true });
    expect(crossing!.width).toBeCloseTo(10);
    expect(spanInWindow("2026-09-28T12:00:00Z", "2026-09-28T12:30:00Z", START, END, END)).toBeNull();
  });

  it("runs an open span up to now, and never draws it thinner than clickable", () => {
    const now = Date.parse("2026-09-28T14:45:00Z");
    const open = spanInWindow("2026-09-28T14:30:00Z", null, START, END, now);
    expect(open).toMatchObject({ left: 50, width: 25, clippedEnd: true });
    const blip = spanInWindow("2026-09-28T14:30:00Z", "2026-09-28T14:30:01Z", START, END, END);
    expect(blip!.width).toBe(MIN_BLOCK_PERCENT);
  });

  it("chooses round, readable ticks", () => {
    const hour = axisTicks(START, END);
    expect(hour.length).toBeGreaterThanOrEqual(4);
    expect(hour.length).toBeLessThanOrEqual(8);
    expect(hour.every((tick) => new Date(tick).getMinutes() % 10 === 0)).toBe(true);
    const day = axisTicks(START, START + 24 * 3_600_000);
    expect(day.length).toBeLessThanOrEqual(8);
  });

  it("formats durations", () => {
    expect(formatDuration(450)).toBe("450 ms");
    expect(formatDuration(42_000)).toBe("42 s");
    expect(formatDuration(125_000)).toBe("2 min 5 s");
    expect(formatDuration(3_600_000 + 5 * 60_000)).toBe("1 h 5 min");
  });
});
