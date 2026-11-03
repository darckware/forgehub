/** Pure helpers for routine occurrences on the Agent Activity lanes (A.2). */
import type { RoutineOutcome, TimelineRoutine } from "@/hooks/useAgentActivityTimeline";

/** Outcome style: a glyph (so it never depends on colour alone) and a tone. */
export const ROUTINE_MARK: Record<RoutineOutcome, { glyph: string; tone: string }> = {
  done: { glyph: "✓", tone: "border-emerald-600 bg-emerald-500 text-white" },
  failed: { glyph: "✕", tone: "border-destructive bg-destructive text-destructive-foreground" },
  missed: { glyph: "!", tone: "border-amber-700 bg-amber-400 text-amber-950" },
  skipped: { glyph: "–", tone: "border-slate-500 bg-slate-300 text-slate-900" },
  running: { glyph: "…", tone: "border-sky-600 bg-sky-500 text-white" },
  pending: { glyph: "…", tone: "border-sky-600 bg-background text-sky-700 dark:text-sky-300" },
  scheduled: { glyph: "○", tone: "border-border bg-background text-muted-foreground" },
};

export interface UpcomingRoutine {
  next: TimelineRoutine;
  /** Further occurrences of the same routine within the next 24 h. */
  later: number;
}

export interface RoutineGroups {
  /** Occurrences inside the window (anything but `scheduled`). */
  past: TimelineRoutine[];
  /** Missed or failed inside the window, newest first. */
  attention: TimelineRoutine[];
  /** Per routine, its next `scheduled` occurrence and how many more follow; soonest first. */
  upcoming: UpcomingRoutine[];
  counts: Record<"done" | "failed" | "missed", number>;
}

export function groupRoutines(
  routines: TimelineRoutine[] | undefined,
  startMs: number,
  endMs: number,
  agentId: string | null,
): RoutineGroups {
  const mine = (routines ?? []).filter((item) => !agentId || item.agent_id === agentId);
  const past = mine.filter((item) => {
    const at = Date.parse(item.occurrence_at);
    return item.outcome !== "scheduled" && at >= startMs && at <= endMs;
  });
  const attention = past
    .filter((item) => item.outcome === "missed" || item.outcome === "failed")
    .sort((a, b) => Date.parse(b.occurrence_at) - Date.parse(a.occurrence_at));
  // One row per routine -- its next occurrence, plus how many more fall in the 24 h -- so an
  // hourly routine doesn't push a daily one off the list.
  const nextByRoutine = new Map<string, UpcomingRoutine>();
  for (const item of mine
    .filter((entry) => entry.outcome === "scheduled")
    .sort((a, b) => Date.parse(a.occurrence_at) - Date.parse(b.occurrence_at))) {
    const seen = nextByRoutine.get(item.routine_id);
    if (seen) seen.later += 1;
    else nextByRoutine.set(item.routine_id, { next: item, later: 0 });
  }
  const upcoming = [...nextByRoutine.values()];
  const counts = { done: 0, failed: 0, missed: 0 };
  for (const item of past) {
    if (item.outcome === "done" || item.outcome === "failed" || item.outcome === "missed") counts[item.outcome] += 1;
  }
  return { past, attention, upcoming, counts };
}

/** "08:00 (America/Sao_Paulo)": the instant in the routine's own timezone. */
export function formatInRoutineZone(iso: string, timeZone: string, language: string, withDate = false): string {
  const options: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", timeZone };
  if (withDate) Object.assign(options, { day: "2-digit", month: "2-digit" });
  try {
    return `${new Intl.DateTimeFormat(language, options).format(Date.parse(iso))} (${timeZone})`;
  } catch {
    // An unknown zone name: fall back to the viewer's clock rather than hide the time.
    delete options.timeZone;
    return new Intl.DateTimeFormat(language, options).format(Date.parse(iso));
  }
}
