/** Shared formatting for the mission executions screen (M0.7). */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "—";
  const sign = seconds < 0 ? "-" : "";
  let rest = Math.abs(Math.round(seconds));
  const days = Math.floor(rest / 86400); rest -= days * 86400;
  const hours = Math.floor(rest / 3600); rest -= hours * 3600;
  const minutes = Math.floor(rest / 60);
  if (days) return `${sign}${days}d ${hours}h`;
  if (hours) return `${sign}${hours}h ${minutes}m`;
  return `${sign}${minutes}m`;
}

export function secondsUntil(iso: string | null | undefined, from: Date = new Date()): number | null {
  if (!iso) return null;
  return Math.round((new Date(iso).getTime() - from.getTime()) / 1000);
}

/** Running timer tone: amber at 80 % of the deadline, red past it (§4). */
export function timerTone(elapsed: number | null, dispatchedAt: string | null, deadlineAt: string | null): "ok" | "warn" | "late" {
  if (elapsed == null || !dispatchedAt || !deadlineAt) return "ok";
  const total = (new Date(deadlineAt).getTime() - new Date(dispatchedAt).getTime()) / 1000;
  if (total <= 0) return "late";
  if (elapsed >= total) return "late";
  return elapsed >= total * 0.8 ? "warn" : "ok";
}

export const STATE_TONE: Record<string, string> = {
  done_proven: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  done_historical: "border-border bg-muted text-muted-foreground",
  uncertain: "border-red-500/50 bg-red-500/10 text-red-700 dark:text-red-300",
  running: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  queued: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  scheduled: "border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300",
  changes_requested: "border-orange-500/40 bg-orange-500/10 text-orange-700 dark:text-orange-300",
  awaiting_review: "border-violet-500/40 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  evidence_failed: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
  reported: "border-sky-500/30 bg-sky-500/5 text-sky-700 dark:text-sky-300",
  failed: "border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-300",
  blocked: "border-orange-500/40 bg-orange-500/5 text-orange-700 dark:text-orange-300",
  ready: "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300",
  not_ready: "border-border text-muted-foreground",
  cancelled: "border-border text-muted-foreground line-through",
};
