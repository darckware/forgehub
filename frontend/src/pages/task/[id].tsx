import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  AlertCircle,
  Download,
  ExternalLink,
  History,
  Loader2,
  Play,
  RefreshCw,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EXECUTION_STATUSES,
  EXECUTOR_TYPES,
  executionCreateSchema,
  type ExecutionCreateInput,
  useSyncTaskToKanboard,
  usePullKanboard,
  useTask,
  useTasks,
  useCreateExecution,
} from "@/hooks/useTask";
import { useProjects } from "@/hooks/useProject";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { EntityDocsCard } from "@/components/EntityDocsCard";
import { usePlanningItems } from "@/hooks/useBacklog";
import { TaskAutomationCard } from "@/components/TaskAutomationCard";
import { TaskDependenciesCard } from "@/components/TaskDependenciesCard";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  planned: "outline",
  assigned: "secondary",
  in_progress: "default",
  blocked: "destructive",
  done: "success",
  deployed: "success",
  cancelled: "destructive",
};

const KANBOARD_URL =
  (import.meta.env.VITE_KANBOARD_URL as string | undefined) ?? "http://localhost:8081";

const EXEC_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  pending: "outline",
  running: "default",
  completed: "success",
  failed: "destructive",
  retried: "warning",
  verified: "success",
};

function StartExecutionForm({
  taskId,
  onClose,
}: {
  taskId: string;
  onClose: () => void;
}) {
  const { t } = useTranslation("task");
  const createExecution = useCreateExecution(taskId);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ExecutionCreateInput>({
    resolver: zodResolver(executionCreateSchema),
    defaultValues: { executor_type: "agent", status: "running" },
  });

  function onSubmit(values: ExecutionCreateInput) {
    createExecution.mutate(values, { onSuccess: onClose });
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 pt-2">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="executor_type">{t("startExecutionForm.executorTypeLabel")}</Label>
          <Select id="executor_type" {...register("executor_type")}>
            {EXECUTOR_TYPES.map((execType) => (
              <option key={execType} value={execType}>
                {t(`enums.executorType.${execType}`, execType.replace("_", " "))}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="exec_status">{t("startExecutionForm.initialStatusLabel")}</Label>
          <Select id="exec_status" {...register("status")}>
            {EXECUTION_STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`enums.executionStatus.${s}`, s)}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="outcome_summary">{t("startExecutionForm.summaryLabel")}</Label>
        <Textarea
          id="outcome_summary"
          placeholder={t("startExecutionForm.summaryPlaceholder")}
          {...register("outcome_summary")}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="evidence_ref">{t("startExecutionForm.evidenceRefLabel")}</Label>
          <Input
            id="evidence_ref"
            placeholder={t("startExecutionForm.evidenceRefPlaceholder")}
            {...register("evidence_ref")}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="actual_cost">{t("startExecutionForm.actualCostLabel")}</Label>
          <Input id="actual_cost" type="number" step="0.01" placeholder="0.00" {...register("actual_cost")} />
        </div>
      </div>
      {createExecution.isError && (
        <p className="text-sm text-destructive">
          {(createExecution.error as Error)?.message}
        </p>
      )}
      {errors.root && (
        <p className="text-sm text-destructive">{errors.root.message}</p>
      )}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onClose} disabled={createExecution.isPending}>
          {t("startExecutionForm.cancel")}
        </Button>
        <Button type="submit" disabled={createExecution.isPending}>
          {createExecution.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t("startExecutionForm.submit")}
        </Button>
      </div>
    </form>
  );
}

export default function TaskDetailPage() {
  const { t } = useTranslation("task");
  const { id } = useParams<{ id: string }>();
  const { data: task, isLoading, isError, error } = useTask(id);
  const syncKanboard = useSyncTaskToKanboard(id ?? "");
  const pullKanboard = usePullKanboard(id ?? "");
  const { data: projects } = useProjects();
  const { data: planningItems } = usePlanningItems();
  const { data: allTasks } = useTasks();
  const [showExecForm, setShowExecForm] = useState(false);

  const projectName = (pid: string) =>
    projects?.find((p) => p.id === pid)?.name ?? pid.slice(0, 8) + "…";
  const planningItemTitle = (iid: string) =>
    planningItems?.find((i) => i.id === iid)?.title ?? iid.slice(0, 8) + "…";
  const parentTaskTitle = (tid: string) =>
    allTasks?.find((t) => t.id === tid)?.title ?? tid.slice(0, 8) + "…";

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: t("detail.breadcrumbExecution"), href: "/tasks" },
          { label: task?.title ?? "…" },
        ]}
      />

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("detail.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("detail.loadError", { message: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && task && (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{task.title}</h1>
              {task.description && (
                <p className="mt-1 max-w-2xl text-muted-foreground">{task.description}</p>
              )}
            </div>
            <div className="flex flex-col items-end gap-2">
              <Badge
                variant={STATUS_VARIANT[task.status] ?? "outline"}
                className="text-sm capitalize"
              >
                {t(`enums.taskStatus.${task.status}`, task.status.replace("_", " "))}
              </Badge>
              <Badge variant="outline" className="text-sm capitalize">
                {t("detail.priorityLabel", {
                  priority: t(`enums.taskPriority.${task.priority}`, task.priority),
                })}
              </Badge>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-xl">{t("detail.projectCard.title")}</CardTitle>
                <CardDescription>{t("detail.projectCard.description")}</CardDescription>
              </CardHeader>
              <CardContent>
                {task.project_id ? (
                  <p className="text-sm font-medium">{projectName(task.project_id)}</p>
                ) : (
                  <p className="text-sm italic text-muted-foreground">{t("detail.projectCard.none")}</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-xl">{t("detail.planningItemCard.title")}</CardTitle>
                <CardDescription>{t("detail.planningItemCard.description")}</CardDescription>
              </CardHeader>
              <CardContent>
                {task.planning_item_id ? (
                  <p className="text-sm font-medium">{planningItemTitle(task.planning_item_id)}</p>
                ) : (
                  <p className="text-sm italic text-muted-foreground">{t("detail.planningItemCard.none")}</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-xl">{t("detail.scheduleCard.title")}</CardTitle>
                <CardDescription>{t("detail.scheduleCard.description")}</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">{t("detail.scheduleCard.dueDate")}</dt>
                    <dd>{task.planned_end_date ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">{t("detail.scheduleCard.estimatedCost")}</dt>
                    <dd>{task.estimated_cost != null ? task.estimated_cost : "—"}</dd>
                  </div>
                  {task.parent_task_id && (
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">{t("detail.scheduleCard.parentTask")}</dt>
                      <dd className="text-right">{parentTaskTitle(task.parent_task_id)}</dd>
                    </div>
                  )}
                </dl>
              </CardContent>
            </Card>
          </div>

          <TaskDependenciesCard taskId={task.id} />

          <TaskAutomationCard taskId={task.id} projectId={task.project_id ?? undefined} />

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xl">{t("detail.kanboard.title")}</CardTitle>
                <CardDescription>{t("detail.kanboard.description")}</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {task.kanboard_task_id != null && (
                  <>
                    <a
                      href={`${KANBOARD_URL}/task/${task.kanboard_task_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className={buttonVariants({ variant: "outline", size: "sm" })}
                    >
                      <ExternalLink className="mr-2 h-4 w-4" />
                      {t("detail.kanboard.openCard")}
                    </a>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={pullKanboard.isPending}
                      onClick={() => pullKanboard.mutate()}
                      title={t("detail.kanboard.pullTooltip")}
                    >
                      {pullKanboard.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="mr-2 h-4 w-4" />
                      )}
                      {t("detail.kanboard.pullStatus")}
                    </Button>
                  </>
                )}
                <Button
                  size="sm"
                  disabled={syncKanboard.isPending}
                  onClick={() => syncKanboard.mutate()}
                >
                  {syncKanboard.isPending ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="mr-2 h-4 w-4" />
                  )}
                  {task.kanboard_task_id != null
                    ? t("detail.kanboard.resync")
                    : t("detail.kanboard.sync")}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {task.kanboard_task_id != null
                  ? t("detail.kanboard.linked", { id: task.kanboard_task_id })
                  : t("detail.kanboard.notSynced")}
              </p>
              {syncKanboard.isError && (
                <p className="mt-2 text-sm text-destructive">
                  {(syncKanboard.error as Error)?.message}
                </p>
              )}
              {pullKanboard.isError && (
                <p className="mt-2 text-sm text-destructive">
                  {t("detail.kanboard.pullFailed", { message: (pullKanboard.error as Error)?.message })}
                </p>
              )}
              {pullKanboard.isSuccess && (
                <p className="mt-2 text-sm text-emerald-600">
                  {t("detail.kanboard.pullSuccess")}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <History className="h-5 w-5" />
                  {t("detail.executions.title")}
                </CardTitle>
                <CardDescription>{t("detail.executions.description")}</CardDescription>
              </div>
              <Button size="sm" onClick={() => setShowExecForm((v) => !v)}>
                <Play className="mr-2 h-4 w-4" />
                {showExecForm ? t("detail.executions.cancel") : t("detail.executions.record")}
              </Button>
            </CardHeader>

            {showExecForm && (
              <CardContent className="border-t pt-4">
                <StartExecutionForm taskId={id!} onClose={() => setShowExecForm(false)} />
              </CardContent>
            )}

            <CardContent
              className={task.executions && task.executions.length > 0 ? "p-0" : undefined}
            >
              {task.executions && task.executions.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("detail.executions.columns.number")}</TableHead>
                      <TableHead>{t("detail.executions.columns.executor")}</TableHead>
                      <TableHead>{t("detail.executions.columns.status")}</TableHead>
                      <TableHead>{t("detail.executions.columns.started")}</TableHead>
                      <TableHead>{t("detail.executions.columns.finished")}</TableHead>
                      <TableHead>{t("detail.executions.columns.cost")}</TableHead>
                      <TableHead>{t("detail.executions.columns.evidence")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {task.executions.map((execution) => (
                      <TableRow key={execution.id}>
                        <TableCell className="text-muted-foreground">
                          #{execution.attempt_number ?? "—"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {execution.executor_type
                            ? t(`enums.executorType.${execution.executor_type}`, execution.executor_type)
                            : t("detail.executions.unknownExecutor")}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={EXEC_STATUS_VARIANT[execution.status] ?? "outline"}
                          >
                            {t(`enums.executionStatus.${execution.status}`, execution.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {execution.started_at
                            ? new Date(execution.started_at).toLocaleString()
                            : "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {execution.finished_at
                            ? new Date(execution.finished_at).toLocaleString()
                            : "—"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {execution.actual_cost != null ? execution.actual_cost : "—"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {execution.evidence_ref ? (
                            <span className="font-mono text-xs">{execution.evidence_ref}</span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <p className="text-sm text-muted-foreground">{t("detail.executions.empty")}</p>
              )}
              {task.executions?.some((e) => e.outcome_summary) && (
                <div className="mt-4 space-y-2 border-t pt-4">
                  {task.executions
                    .filter((e) => e.outcome_summary)
                    .map((e) => (
                      <div key={e.id} className="rounded-md bg-muted/50 p-3 text-sm">
                        <span className="font-medium">
                          {t("detail.executions.attempt", { number: e.attempt_number })}:{" "}
                        </span>
                        {e.outcome_summary}
                      </div>
                    ))}
                </div>
              )}
            </CardContent>
          </Card>

          <EntityDocsCard entityType="task" entityId={task.id} />

          <div>
            <Link to="/tasks" className={buttonVariants({ variant: "outline" })}>
              {t("detail.backToList")}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
