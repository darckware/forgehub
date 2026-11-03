import { ArrowLeft, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { MissionActionKind, MissionTask } from "@/hooks/useMissions";
import type { MissionExecutionsViewModel } from "@/hooks/useMissionExecutionsViewModel";
import { EvidenceList, ReviewerIsExecutorBadge } from "./MissionTaskRow";
import { MissionStateChip } from "./MissionStateChip";
import { MissionTimeline } from "./MissionTimeline";

export const TASK_ACTIONS: MissionActionKind[] = ["dispatch", "schedule", "assign", "request_review", "return"];

/** Right-hand panel (1440 px) / full-width detail with a back bar (390 px). */
export function MissionTaskDetail({ vm, task, projectId, onBack }: {
  vm: MissionExecutionsViewModel; task: MissionTask; projectId: string; onBack: () => void;
}) {
  const { t } = useTranslation("missions");
  const canAct = vm.board?.viewer.can_act ?? false;
  return (
    <aside data-testid="task-detail" className="space-y-4 rounded-lg border bg-card p-4 text-sm">
      <div className="md:hidden">
        <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2">
          <ArrowLeft className="mr-1 h-4 w-4" /> {t("board.backToList")}
        </Button>
      </div>
      <header className="space-y-1">
        <h2 className="break-words text-base font-semibold">#{task.number} {task.title}</h2>
        <MissionStateChip task={task} />
        <p className="text-xs text-muted-foreground">
          {task.executor?.name ?? t("board.none")} → {task.reviewer?.name ?? t("board.none")}{" "}
          {task.reviewer_is_executor && <ReviewerIsExecutorBadge />}
        </p>
        {task.returned_reason && <p className="text-xs text-orange-700 dark:text-orange-300">{task.returned_reason}</p>}
      </header>

      {canAct && (
        <div className="flex flex-wrap gap-2">
          {TASK_ACTIONS.map((action) => {
            const blocked = vm.blockedReason(task, action);
            const busy = vm.status === "submitting" && vm.pending?.kind === action && vm.pending.taskId === task.task_id;
            return (
              <Button
                key={action}
                size="sm"
                variant={action === "return" ? "destructive" : action === "dispatch" ? "default" : "outline"}
                disabled={Boolean(blocked) || vm.status === "submitting"}
                title={blocked ? t("actions.blockedTitle", { reason: blocked }) : undefined}
                className="max-md:h-auto max-md:whitespace-normal"
                onClick={() => vm.openAction(action, { taskId: task.task_id })}
              >
                {busy && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                {t(`actions.${action}`)}
              </Button>
            );
          })}
        </div>
      )}
      {task.blocked_actions.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted-foreground">{t("board.detail.blockedActions")}</summary>
          <ul className="mt-1 space-y-0.5">
            {task.blocked_actions.map((b) => (
              <li key={b.action} className="break-words"><b>{t(`actions.${b.action}`, b.action)}</b>: {b.reason}{b.message ? ` — ${b.message}` : ""}</li>
            ))}
          </ul>
        </details>
      )}
      {task.execution_state === "uncertain" && (
        <p className="rounded border border-red-500/40 bg-red-500/5 p-2 text-xs">
          {t("board.detail.uncertainHint")}{" "}
          <Link className="font-semibold text-primary underline" to="/personal?tab=agent-work">{t("board.detail.openAgentWork")}</Link>
        </p>
      )}

      <section className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("board.detail.attempts")}</h3>
        {task.attempts.length === 0 ? <p className="text-xs text-muted-foreground">{t("board.noContext")}</p> : (
          <ul className="space-y-0.5 text-xs">
            {task.attempts.map((a) => <li key={a.execution_id}>#{a.attempt} · {a.status}</li>)}
          </ul>
        )}
        {task.execution?.demand_number != null && (
          <p className="text-xs">
            <Link className="text-primary underline" to="/demands">{t("board.detail.messages", { number: task.execution.demand_number })}</Link>
          </p>
        )}
      </section>

      <section className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("board.detail.review")}</h3>
        {task.review ? (
          <p className="text-xs">
            {task.reviewer?.name}: <b>{task.review.status}</b>
            {task.review.feedback ? ` — ${task.review.feedback}` : ""}
            {task.review.decided && <span className="block text-muted-foreground">{t("board.detail.reviewDecided")}</span>}
          </p>
        ) : <p className="text-xs text-muted-foreground">{t("board.none")}</p>}
      </section>

      <section className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("board.detail.evidence")}</h3>
        <EvidenceList task={task} />
        {task.evidence.filter((e) => e.verified && e.verified_by).map((e) => (
          <p key={e.ref} className="text-[11px] text-muted-foreground">{t("board.verifiedBy", { name: e.verified_by })}</p>
        ))}
      </section>

      <section className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("board.skills")}</h3>
        {task.skills.length === 0 ? <p className="text-xs text-muted-foreground">{t("board.noSkills")}</p> : (
          <ul className="space-y-0.5 text-xs">
            {task.skills.map((s) => (
              <li key={s.skill_id}>{s.name}: {t("board.skillExecutor")} {s.executor_has ? "✓" : "✗"} · {t("board.skillReviewer")} {s.reviewer_has ? "✓" : "✗"}</li>
            ))}
          </ul>
        )}
        <p className="text-xs text-muted-foreground">
          {task.context ? t("board.context", { version: task.context.version ?? "?" }) : t("board.noContext")}
          {task.context?.stale && ` · ${t("board.contextStale")} (${task.context.stale_reasons.join(", ")})`}
        </p>
      </section>

      <section className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("board.detail.targets")}</h3>
        <ul className="space-y-0.5 text-xs">
          {task.targets.map((target) => <li key={`${target.kind}:${target.key}`} className="break-all">{target.kind}: {target.key}</li>)}
        </ul>
      </section>

      <MissionTimeline projectId={projectId} taskId={task.task_id} />
    </aside>
  );
}
