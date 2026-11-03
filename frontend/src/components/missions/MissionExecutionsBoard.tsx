import { Loader2 } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePhoneListDetail } from "@/hooks/useIsPhone";
import type { MissionActionKind } from "@/hooks/useMissions";
import type { MissionExecutionsViewModel } from "@/hooks/useMissionExecutionsViewModel";
import { cn } from "@/lib/utils";
import { MissionActionDialog } from "./MissionActionDialog";
import { MissionConflictsBanner } from "./MissionConflictsBanner";
import { MissionEnvironmentsStrip } from "./MissionEnvironmentsStrip";
import { MissionPlanningView } from "./MissionPlanningView";
import { MissionTaskDetail } from "./MissionTaskDetail";
import { MissionTaskCard, MissionTaskTableRow } from "./MissionTaskRow";
import { MissionTimeline } from "./MissionTimeline";
import { formatDuration, secondsUntil } from "./missionFormat";

const MISSION_ACTIONS: MissionActionKind[] = ["pause", "resume", "cancel"];

/** The board (§9): header → conflicts → environments → (planning) → tasks,
 * with the selected task's detail on the right (1440 px) or full-width with
 * a back bar (390 px). Pure render of the ViewModel. */
export function MissionExecutionsBoard({ vm }: { vm: MissionExecutionsViewModel }) {
  const { t, i18n } = useTranslation("missions");
  const board = vm.board!;
  const mission = board.mission;
  const phone = usePhoneListDetail(Boolean(vm.selectedTask));
  const select = (taskId: string) => { vm.selectTask(taskId); phone.openDetail(); };
  const back = () => { phone.backToList(); vm.selectTask(null); };
  const remaining = secondsUntil(mission.deadline_at);
  const showDetail = Boolean(vm.selectedTask) && phone.showDetail;
  const showList = !vm.selectedTask || phone.showList;

  return (
    <div className="space-y-4">
      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <Link to="/missions" className="text-sm font-normal text-muted-foreground hover:underline">{t("board.back")} ›</Link>
            <span className="break-words">{mission.name}</span>
          </span>
        }
        description={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <Badge variant="outline">{t(`state.${mission.state}`, mission.state)}</Badge>
            <span>{t("board.priority", { value: mission.priority })}</span>
            <span>· {mission.orchestrator.name ?? "—"}</span>
            <span>· {mission.deadline_at ? t("board.deadline", { value: formatDuration(remaining) }) : t("board.noDeadline")}</span>
            {mission.baseline && <span>· {t("board.baseline", { name: mission.baseline.name ?? mission.baseline.id.slice(0, 8) })}</span>}
            <span className={cn("rounded-full border px-1.5", vm.live === "paused" ? "border-amber-500 text-amber-700" : "text-muted-foreground")}
              data-testid="live-chip">
              {vm.live === "paused" ? t("board.livePaused") : t("board.live")}
            </span>
            <span className="text-muted-foreground">{t("board.updatedAt", { value: new Date(board.generated_at).toLocaleTimeString(i18n.language) })}</span>
          </span>
        }
        actions={board.viewer.can_act ? (
          <div className="flex flex-wrap gap-2">
            {MISSION_ACTIONS.map((action) => {
              const blocked = vm.missionBlockedReason(action);
              if (blocked === "MISSION_TRANSITION_NOT_ALLOWED") return null;
              const busy = vm.status === "submitting" && vm.pending?.kind === action;
              return (
                <Button key={action} size="sm" variant={action === "cancel" ? "destructive" : "outline"}
                  disabled={Boolean(blocked) || vm.status === "submitting"}
                  title={blocked ? t("actions.blockedTitle", { reason: blocked }) : undefined}
                  className="max-md:h-auto max-md:whitespace-normal"
                  onClick={() => vm.openAction(action)}>
                  {busy && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                  {t(`actions.${action}`)}
                </Button>
              );
            })}
          </div>
        ) : <span className="text-xs text-muted-foreground">{t("board.readOnly")}</span>}
      />

      {vm.lastResult && (
        <p role="status" className="rounded border border-emerald-500/40 bg-emerald-500/5 px-3 py-1.5 text-xs">
          {t("actions.done", { action: t(`actions.${vm.lastResult}`) })}
        </p>
      )}
      {!mission.baseline && mission.state !== "planning" && mission.state !== "draft" && (
        <p className="rounded border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm" data-testid="no-baseline">{t("board.noBaseline")}</p>
      )}
      {!mission.baseline && (mission.state === "planning" || mission.state === "draft") && board.tasks.length > 0 && (
        <p className="rounded border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm" data-testid="no-baseline">{t("board.noBaseline")}</p>
      )}

      <MissionConflictsBanner conflicts={board.conflicts} />
      <MissionEnvironmentsStrip environments={board.environments} />
      {board.planning && <MissionPlanningView planning={board.planning} vm={vm} />}

      {board.tasks.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground" data-testid="no-tasks">
          {t("board.noTasks")}{" "}
          <Link to="/backlog" className="font-semibold text-primary underline">{t("board.openPlanning")}</Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1fr)_22rem]">
          {showList && (
            <div className={cn("min-w-0", !vm.selectedTask && "md:col-span-2")}>
              <div className="mb-3 flex gap-2" role="group" aria-label={t("board.viewLabel")}>
                <Button size="sm" variant={vm.taskView === "list" ? "default" : "outline"}
                  aria-pressed={vm.taskView === "list"} onClick={() => vm.setTaskView("list")}>{t("board.listView")}</Button>
                <Button size="sm" variant={vm.taskView === "graph" ? "default" : "outline"}
                  aria-pressed={vm.taskView === "graph"} onClick={() => vm.setTaskView("graph")}>{t("board.graphView")}</Button>
              </div>
              {vm.taskView === "graph" ? (
                <ol className="space-y-2" data-testid="task-graph" aria-label={t("board.graphView")}>
                  {board.tasks.map((task) => (
                    <li key={task.task_id} data-testid={`graph-task-${task.task_id}`} className="rounded-lg border bg-card p-3 text-sm">
                      <div className="mb-1 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                        <span>{t("board.graphDependsOn")}:</span>
                        {task.depends_on.length ? task.depends_on.map((dep) => (
                          <span key={dep.task_id} className="rounded border px-1">#{dep.number ?? dep.task_id}</span>
                        )) : <span>{t("board.none")}</span>}
                        <span aria-hidden="true">→</span>
                      </div>
                      <button type="button" className="text-left font-medium text-primary underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
                        onClick={() => select(task.task_id)}>#{task.number ?? task.task_id} {task.title}</button>
                    </li>
                  ))}
                </ol>
              ) : <>
              <div className="max-md:hidden" data-testid="task-table">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {(["number", "task", "dependsOn", "executor", "reviewer", "state", "evidence", "actions"] as const).map((col) => (
                        <TableHead key={col}>{t(`board.columns.${col}`)}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {board.tasks.map((task) => (
                      <MissionTaskTableRow key={task.task_id} task={task} selected={vm.selectedTask?.task_id === task.task_id}
                        onSelect={() => select(task.task_id)} />
                    ))}
                  </TableBody>
                </Table>
              </div>
              <div className="space-y-2 md:hidden" data-testid="task-cards">
                {board.tasks.map((task) => (
                  <MissionTaskCard key={task.task_id} task={task} selected={vm.selectedTask?.task_id === task.task_id}
                    onSelect={() => select(task.task_id)} />
                ))}
              </div>
              </>}
            </div>
          )}
          {showDetail && vm.selectedTask && (
            <MissionTaskDetail vm={vm} task={vm.selectedTask} projectId={mission.project_id} onBack={back} />
          )}
        </div>
      )}

      {!vm.selectedTask && <MissionTimeline projectId={mission.project_id} />}
      <MissionActionDialog vm={vm} />
    </div>
  );
}
