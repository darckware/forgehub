import { CheckCircle2, CircleDashed, MoreHorizontal, ShieldAlert, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import { TableCell, TableRow } from "@/components/ui/table";
import type { MissionTask } from "@/hooks/useMissions";
import { cn } from "@/lib/utils";
import { MissionStateChip } from "./MissionStateChip";

function EvidenceIcon({ verified }: { verified: boolean | null }) {
  if (verified === true) return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-label="verified" />;
  if (verified === false) return <XCircle className="h-3.5 w-3.5 text-red-600" aria-label="refused" />;
  return <CircleDashed className="h-3.5 w-3.5 text-muted-foreground" aria-label="unchecked" />;
}

export function EvidenceList({ task, compact = false }: { task: MissionTask; compact?: boolean }) {
  const { t } = useTranslation("missions");
  if (task.evidence.length === 0) return <span className="text-muted-foreground">{t("board.noEvidence")}</span>;
  if (compact) return <span>{t("board.evidenceCount", { count: task.evidence.length })}</span>;
  return (
    <ul className="space-y-0.5">
      {task.evidence.map((item) => (
        <li key={item.ref} className="flex items-center gap-1 text-xs">
          <EvidenceIcon verified={item.verified} />
          <code className="break-all font-mono">{item.ref.length > 24 ? `${item.ref.slice(0, 24)}…` : item.ref}</code>
          {item.reviewed_by && item.verified && (
            <span className="text-muted-foreground">· {item.reviewed_by.name}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

function People({ task }: { task: MissionTask }) {
  const { t } = useTranslation("missions");
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span>{task.executor?.name ?? t("board.none")}</span>
      <span aria-hidden>→</span>
      <span>{task.reviewer?.name ?? t("board.none")}</span>
      {task.reviewer_is_executor && <ReviewerIsExecutorBadge />}
    </span>
  );
}

export function ReviewerIsExecutorBadge() {
  const { t } = useTranslation("missions");
  return (
    <span className="inline-flex items-center gap-0.5 rounded border border-red-500/50 bg-red-500/10 px-1 text-[10px] font-semibold text-red-700 dark:text-red-300">
      <ShieldAlert className="h-3 w-3" /> {t("board.reviewerIsExecutor")}
    </span>
  );
}

function Context({ task }: { task: MissionTask }) {
  const { t } = useTranslation("missions");
  if (!task.context) return null;
  return (
    <span className={cn("text-[10px]", task.context.stale ? "font-semibold text-amber-700 dark:text-amber-300" : "text-muted-foreground")}>
      {t("board.context", { version: task.context.version ?? "?" })}
      {task.context.stale && ` · ${t("board.contextStale")}`}
    </span>
  );
}

interface RowProps {
  task: MissionTask;
  selected: boolean;
  onSelect: () => void;
}

/** One task on the 1440 px table (§9). */
export function MissionTaskTableRow({ task, selected, onSelect }: RowProps) {
  const { t } = useTranslation("missions");
  return (
    <TableRow
      data-testid={`task-row-${task.task_id}`}
      className={cn("cursor-pointer align-top", selected && "bg-muted/60")}
      onClick={onSelect}
    >
      <TableCell className="font-mono text-xs">{task.number}</TableCell>
      <TableCell className="min-w-[12rem]">
        <div className="font-medium">{task.title}</div>
        <Context task={task} />
        {task.skills.length > 0 && (
          <div className="mt-0.5 flex flex-wrap gap-1">
            {task.skills.map((skill) => (
              <span key={skill.skill_id} className={cn("rounded border px-1 text-[10px]",
                skill.executor_has && skill.reviewer_has ? "border-emerald-500/40" : "border-amber-500/60")}
                title={`${t("board.skillExecutor")}: ${skill.executor_has ? "✓" : "✗"} · ${t("board.skillReviewer")}: ${skill.reviewer_has ? "✓" : "✗"}`}>
                {skill.name} {skill.executor_has ? "✓" : "✗"}/{skill.reviewer_has ? "✓" : "✗"}
              </span>
            ))}
          </div>
        )}
      </TableCell>
      <TableCell className="text-xs">
        {task.depends_on.length === 0 ? t("board.none") : task.depends_on.map((dep) => (
          <span key={dep.task_id} className="mr-1 whitespace-nowrap">
            #{dep.number} {dep.status === "done" || dep.status === "deployed" ? "✓" : "…"}
          </span>
        ))}
      </TableCell>
      <TableCell className="text-xs">{task.executor?.name ?? t("board.none")}</TableCell>
      <TableCell className="text-xs">
        <div className="flex flex-col gap-0.5">
          <span>{task.reviewer?.name ?? t("board.none")}</span>
          {task.reviewer_is_executor && <ReviewerIsExecutorBadge />}
        </div>
      </TableCell>
      <TableCell><MissionStateChip task={task} /></TableCell>
      <TableCell><EvidenceList task={task} /></TableCell>
      <TableCell>
        <button
          type="button"
          className="rounded p-1 hover:bg-muted"
          aria-label={t("actions.menu", { number: task.number })}
          onClick={(event) => { event.stopPropagation(); onSelect(); }}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
      </TableCell>
    </TableRow>
  );
}

/** One task on the 390 px card list (§9). */
export function MissionTaskCard({ task, selected, onSelect }: RowProps) {
  const { t } = useTranslation("missions");
  return (
    <button
      type="button"
      data-testid={`task-card-${task.task_id}`}
      onClick={onSelect}
      className={cn("w-full space-y-1.5 rounded-lg border bg-card p-3 text-left text-sm", selected && "border-primary")}
    >
      <div className="flex items-start gap-2">
        <span className="font-mono text-xs text-muted-foreground">#{task.number}</span>
        <span className="min-w-0 flex-1 break-words font-medium">{task.title}</span>
        <MoreHorizontal className="h-4 w-4 shrink-0 text-muted-foreground" aria-label={t("actions.menu", { number: task.number })} />
      </div>
      <MissionStateChip task={task} />
      <div className="flex flex-wrap items-center justify-between gap-1 text-xs text-muted-foreground">
        <People task={task} />
        <EvidenceList task={task} compact />
      </div>
      <Context task={task} />
    </button>
  );
}
