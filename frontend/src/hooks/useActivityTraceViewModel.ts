import { useCallback, useEffect, useMemo, useState } from "react";
import type { AgentLiveSnapshot } from "./useAgentActivity";
import {
  useActivitySnapshotAt,
  useActivityTimeline,
  type ActivityTimeline,
  type TimelineBlock,
  type TimelineWindow,
} from "./useAgentActivityTimeline";

export type TracePreset = "1h" | "2h" | "6h" | "24h" | "custom";
export type TraceRangeError = "order" | "tooWide" | "invalid" | null;

const PRESET_MS: Record<Exclude<TracePreset, "custom">, number> = {
  "1h": 60 * 60_000,
  "2h": 2 * 60 * 60_000,
  "6h": 6 * 60 * 60_000,
  "24h": 24 * 60 * 60_000,
};
const MAX_WINDOW_MS = 24 * 60 * 60_000;
/** Replay speed: one real second covers one minute of the window. */
export const PLAY_SPEED = 60;
const PLAY_TICK_MS = 250;
/** Replay frames are requested at this resolution, so dragging doesn't fire a request per pixel. */
const SNAPSHOT_STEP_MS = 5_000;
const SNAPSHOT_DEBOUNCE_MS = 250;
const LIVE_REFRESH_MS = 30_000;

export interface CustomRange {
  /** `datetime-local` values (the viewer's local time). */
  start: string;
  end: string;
}

export interface ActivityTraceViewModel {
  status: "loading" | "ready" | "replaying" | "error";
  preset: TracePreset;
  customRange: CustomRange;
  rangeError: TraceRangeError;
  window: TimelineWindow | null;
  windowStartMs: number | null;
  windowEndMs: number | null;
  timeline: ActivityTimeline | null;
  isFetching: boolean;
  /** Replay cursor (epoch ms); null = live. */
  cursor: number | null;
  playing: boolean;
  replaySnapshot: AgentLiveSnapshot | null;
  replayLoading: boolean;
  selectedBlock: { agentId: string; block: TimelineBlock } | null;
  setPreset: (preset: TracePreset) => void;
  setCustomRange: (range: CustomRange) => void;
  setCursor: (ms: number | null) => void;
  backToLive: () => void;
  togglePlay: () => void;
  selectBlock: (agentId: string, block: TimelineBlock | null) => void;
}

function toLocalInput(ms: number): string {
  const date = new Date(ms);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function validateCustomRange(range: CustomRange): TraceRangeError {
  const start = Date.parse(range.start);
  const end = Date.parse(range.end);
  if (Number.isNaN(start) || Number.isNaN(end)) return "invalid";
  if (start >= end) return "order";
  if (end - start > MAX_WINDOW_MS) return "tooWide";
  return null;
}

/** Rounds down to the minute so a "last 2 h" window only changes key once a minute. */
function minuteFloor(ms: number): number {
  return Math.floor(ms / 60_000) * 60_000;
}

/**
 * Traceability state for the Agent Activity screen (phase 4): which window the lanes and
 * the event table show, and the replay cursor that re-positions the constellation, cards
 * and pulse at a past instant (GET /agent-activity/snapshot?at=).
 *
 * A preset window follows "now" (refreshed every 30 s); a custom one is fixed. Moving the
 * cursor puts the page in replay; `backToLive` leaves it.
 */
export function useActivityTraceViewModel(): ActivityTraceViewModel {
  const [preset, setPresetState] = useState<TracePreset>("2h");
  const [customRange, setCustomRangeState] = useState<CustomRange>(() => {
    const end = minuteFloor(Date.now());
    return { start: toLocalInput(end - PRESET_MS["1h"]), end: toLocalInput(end) };
  });
  const [anchor, setAnchor] = useState(() => minuteFloor(Date.now()));
  const [cursor, setCursorState] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [debouncedAt, setDebouncedAt] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ agentId: string; block: TimelineBlock } | null>(null);

  // A preset window slides with the clock -- but not while replaying, which would move
  // the ground under the cursor.
  useEffect(() => {
    if (preset === "custom" || cursor !== null) return;
    const timer = setInterval(() => setAnchor(minuteFloor(Date.now())), LIVE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [preset, cursor]);

  const rangeError = preset === "custom" ? validateCustomRange(customRange) : null;
  const window = useMemo<TimelineWindow | null>(() => {
    if (preset === "custom") {
      if (rangeError) return null;
      return {
        start: new Date(Date.parse(customRange.start)).toISOString(),
        end: new Date(Date.parse(customRange.end)).toISOString(),
      };
    }
    // The end is "now" rounded up so the newest minute is inside the window.
    const end = anchor + 60_000;
    return { start: new Date(end - PRESET_MS[preset]).toISOString(), end: new Date(end).toISOString() };
  }, [preset, customRange, rangeError, anchor]);
  const windowStartMs = window ? Date.parse(window.start) : null;
  const windowEndMs = window ? Date.parse(window.end) : null;

  const timelineQuery = useActivityTimeline(window, {
    refetchInterval: preset !== "custom" && cursor === null ? LIVE_REFRESH_MS : false,
  });

  useEffect(() => {
    if (cursor === null) {
      setDebouncedAt(null);
      return;
    }
    const timer = setTimeout(() => {
      const stepped = Math.min(Math.floor(cursor / SNAPSHOT_STEP_MS) * SNAPSHOT_STEP_MS, Date.now());
      setDebouncedAt(new Date(stepped).toISOString());
    }, playing ? 0 : SNAPSHOT_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [cursor, playing]);
  const snapshotQuery = useActivitySnapshotAt(debouncedAt);

  useEffect(() => {
    if (!playing || windowEndMs === null) return;
    const timer = setInterval(() => {
      setCursorState((current) =>
        Math.min((current ?? windowStartMs ?? Date.now()) + PLAY_TICK_MS * PLAY_SPEED, windowEndMs, Date.now()),
      );
    }, PLAY_TICK_MS);
    return () => clearInterval(timer);
  }, [playing, windowStartMs, windowEndMs]);

  // Playback stops by itself at the end of the window (or at "now").
  useEffect(() => {
    if (playing && cursor !== null && windowEndMs !== null && cursor >= Math.min(windowEndMs, Date.now()) - 1) {
      setPlaying(false);
    }
  }, [playing, cursor, windowEndMs]);

  const setCursor = useCallback(
    (ms: number | null) => {
      if (ms === null) {
        setCursorState(null);
        setPlaying(false);
        return;
      }
      const clamped = Math.min(Math.max(ms, windowStartMs ?? ms), Math.min(windowEndMs ?? ms, Date.now()));
      setCursorState(clamped);
    },
    [windowStartMs, windowEndMs],
  );

  const backToLive = useCallback(() => {
    setCursorState(null);
    setPlaying(false);
    setAnchor(minuteFloor(Date.now()));
  }, []);

  const togglePlay = useCallback(() => {
    if (playing) {
      setPlaying(false);
      return;
    }
    // Starting from live (or from the very end) replays the window from its start.
    const atEnd = cursor === null || (windowEndMs !== null && cursor >= Math.min(windowEndMs, Date.now()) - 1_000);
    if (atEnd) setCursorState(windowStartMs);
    setPlaying(true);
  }, [playing, cursor, windowStartMs, windowEndMs]);

  const setPreset = useCallback((next: TracePreset) => {
    setPresetState(next);
    setCursorState(null);
    setPlaying(false);
    setSelected(null);
    setAnchor(minuteFloor(Date.now()));
  }, []);

  const setCustomRange = useCallback((range: CustomRange) => {
    setCustomRangeState(range);
    setPresetState("custom");
    setCursorState(null);
    setPlaying(false);
    setSelected(null);
  }, []);

  const selectBlock = useCallback((agentId: string, block: TimelineBlock | null) => {
    setSelected(block ? { agentId, block } : null);
  }, []);

  const timeline = timelineQuery.data ?? null;
  const status: ActivityTraceViewModel["status"] =
    timelineQuery.isError && !timeline
      ? "error"
      : !timeline && window !== null
        ? "loading"
        : cursor !== null
          ? "replaying"
          : "ready";

  return {
    status,
    preset,
    customRange,
    rangeError,
    window,
    windowStartMs,
    windowEndMs,
    timeline,
    isFetching: timelineQuery.isFetching,
    cursor,
    playing,
    replaySnapshot: cursor !== null ? snapshotQuery.data ?? null : null,
    replayLoading: cursor !== null && (snapshotQuery.isFetching || debouncedAt === null),
    selectedBlock: selected,
    setPreset,
    setCustomRange,
    setCursor,
    backToLive,
    togglePlay,
    selectBlock,
  };
}
