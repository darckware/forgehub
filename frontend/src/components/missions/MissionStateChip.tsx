import { useTranslation } from "react-i18next";
import type { MissionTask } from "@/hooks/useMissions";
import { cn } from "@/lib/utils";
import { STATE_TONE, formatDuration, secondsUntil, timerTone } from "./missionFormat";

/** State of one task's execution, with the running timer or the reason it waits (§4). */
export function MissionStateChip({ task }: { task: MissionTask }) {
  const { t } = useTranslation("missions");
  const state = task.execution_state;
  const execution = task.execution;
  let detail: string | null = null;
  let tone: "ok" | "warn" | "late" = "ok";
  if (state === "running" && execution) {
    const deadline = execution.deadline_at && execution.dispatched_at
      ? (new Date(execution.deadline_at).getTime() - new Date(execution.dispatched_at).getTime()) / 1000 : null;
    detail = t("board.elapsed", { elapsed: formatDuration(execution.elapsed_seconds), deadline: formatDuration(deadline) });
    tone = timerTone(execution.elapsed_seconds, execution.dispatched_at, execution.deadline_at);
  } else if (state === "queued" && task.queued_reason) {
    detail = task.queued_reason;
  } else if (state === "scheduled" && execution?.scheduled_at) {
    detail = formatDuration(secondsUntil(execution.scheduled_at));
  } else if (state === "failed" && execution?.attempts != null) {
    detail = t("board.attempts", { n: execution.attempts, limit: execution.retry_limit ?? "?" });
  } else if (state === "blocked" && task.blocking.length) {
    detail = task.blocking.map((n) => `#${n}`).join(", ");
  } else if (state === "not_ready" && task.missing.length) {
    detail = task.missing.join(", ");
  }
  return (
    <span
      data-testid={`state-${task.task_id}`}
      className={cn(
        "inline-flex max-w-full flex-wrap items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
        STATE_TONE[state] ?? "border-border",
        tone === "warn" && "ring-1 ring-amber-500",
        tone === "late" && "ring-1 ring-red-500",
      )}
    >
      <span>{t(`exec.${state}`, state)}</span>
      {detail && <span className="font-normal opacity-80 break-all">· {detail}</span>}
    </span>
  );
}
