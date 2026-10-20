/** Pure geometry for the Agent Activity lanes (phase 4). Percentages of the window width. */

export interface Span {
  left: number;
  width: number;
  /** The span continues past the window's left/right edge. */
  clippedStart: boolean;
  clippedEnd: boolean;
}

/** Narrowest a block is drawn, so a 2-second turn in a 24 h window can still be clicked. */
export const MIN_BLOCK_PERCENT = 0.35;

export function timeToPercent(ms: number, startMs: number, endMs: number): number {
  if (endMs <= startMs) return 0;
  return Math.min(100, Math.max(0, ((ms - startMs) / (endMs - startMs)) * 100));
}

/**
 * Where a [start, end] span sits in the window. An open span (`end` null) runs to `nowMs`
 * (or the window's end, whichever comes first). Null when it lies entirely outside.
 */
export function spanInWindow(
  startIso: string,
  endIso: string | null,
  startMs: number,
  endMs: number,
  nowMs: number,
): Span | null {
  const from = Date.parse(startIso);
  const to = endIso ? Date.parse(endIso) : Math.min(nowMs, endMs);
  if (Number.isNaN(from) || to < startMs || from > endMs) return null;
  const left = timeToPercent(from, startMs, endMs);
  const right = timeToPercent(Math.max(to, from), startMs, endMs);
  const width = Math.max(MIN_BLOCK_PERCENT, right - left);
  return {
    left: Math.min(left, 100 - MIN_BLOCK_PERCENT),
    width,
    clippedStart: from < startMs,
    clippedEnd: !endIso || to > endMs,
  };
}

const TICK_STEPS_MIN = [5, 10, 15, 30, 60, 120, 180, 360];

/** Axis ticks on round clock times, aiming at 4-8 labels whatever the window length. */
export function axisTicks(startMs: number, endMs: number): number[] {
  const minutes = (endMs - startMs) / 60_000;
  if (!(minutes > 0)) return [];
  const step = TICK_STEPS_MIN.find((candidate) => minutes / candidate <= 8) ?? TICK_STEPS_MIN[TICK_STEPS_MIN.length - 1];
  const stepMs = step * 60_000;
  // Align on local clock time (a 30-minute step lands on :00 and :30 in the viewer's zone).
  const offsetMs = new Date(startMs).getTimezoneOffset() * 60_000;
  const first = Math.ceil((startMs - offsetMs) / stepMs) * stepMs + offsetMs;
  const ticks: number[] = [];
  for (let tick = first; tick <= endMs; tick += stepMs) ticks.push(tick);
  return ticks;
}

export function formatDuration(ms: number): string {
  if (ms < 1_000) return `${Math.max(0, Math.round(ms))} ms`;
  const seconds = Math.round(ms / 1_000);
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return seconds % 60 ? `${minutes} min ${seconds % 60} s` : `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
}
