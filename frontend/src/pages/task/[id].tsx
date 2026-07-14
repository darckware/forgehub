import { useState } from "react";
import { Link, useParams } from "react-router-dom";
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
          <Label htmlFor="executor_type">Executor type</Label>
          <Select id="executor_type" {...register("executor_type")}>
            {EXECUTOR_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace("_", " ")}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="exec_status">Initial status</Label>
          <Select id="exec_status" {...register("status")}>
            {EXECUTION_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </Select>
        </div>
      </div>
      <div className="space-y-2">
        <Label htmlFor="outcome_summary">Summary (optional)</Label>
        <Textarea
          id="outcome_summary"
          placeholder="What was attempted or accomplished?"
          {...register("outcome_summary")}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="evidence_ref">Evidence ref (required for completed/verified)</Label>
          <Input
            id="evidence_ref"
            placeholder="PR #123, commit sha, doc URL…"
            {...register("evidence_ref")}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="actual_cost">Actual cost</Label>
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
          Cancel
        </Button>
        <Button type="submit" disabled={createExecution.isPending}>
          {createExecution.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Record execution
        </Button>
      </div>
    </form>
  );
}

export default function TaskDetailPage() {
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
  const taskProjectId = task?.project_id ?? planningItems?.find((item) => item.id === task?.planning_item_id)?.project_id;

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Execution", href: "/tasks" },
          { label: task?.title ?? "…" },
        ]}
      />

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading task…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load task: {(error as Error)?.message}</span>
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
                {task.status.replace("_", " ")}
              </Badge>
              <Badge variant="outline" className="text-sm capitalize">
                {task.priority} priority
              </Badge>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-xl">Project</CardTitle>
                <CardDescription>The owning project for this task.</CardDescription>
              </CardHeader>
              <CardContent>
                {task.project_id ? (
                  <p className="text-sm font-medium">{projectName(task.project_id)}</p>
                ) : (
                  <p className="text-sm italic text-muted-foreground">No project linked.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-xl">Planning item</CardTitle>
                <CardDescription>The source planning item this task was split from.</CardDescription>
              </CardHeader>
              <CardContent>
                {task.planning_item_id ? (
                  <p className="text-sm font-medium">{planningItemTitle(task.planning_item_id)}</p>
                ) : (
                  <p className="text-sm italic text-muted-foreground">No planning item linked.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-xl">Schedule &amp; cost</CardTitle>
                <CardDescription>Due date and estimated cost.</CardDescription>
              </CardHeader>
              <CardContent>
                <dl className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">Due date</dt>
                    <dd>{task.due_date ?? "—"}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">Estimated cost</dt>
                    <dd>{task.estimated_cost != null ? task.estimated_cost : "—"}</dd>
                  </div>
                  {task.parent_task_id && (
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">Parent task</dt>
                      <dd className="text-right">{parentTaskTitle(task.parent_task_id)}</dd>
                    </div>
                  )}
                </dl>
              </CardContent>
            </Card>
          </div>

          <TaskAutomationCard taskId={task.id} projectId={taskProjectId ?? undefined} />

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xl">Kanboard</CardTitle>
                <CardDescription>
                  Sync this task to the real Kanboard project as a card.
                </CardDescription>
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
                      Open card
                    </a>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={pullKanboard.isPending}
                      onClick={() => pullKanboard.mutate()}
                      title="Read current column from Kanboard and update this task's status"
                    >
                      {pullKanboard.isPending ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="mr-2 h-4 w-4" />
                      )}
                      Pull status
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
                  {task.kanboard_task_id != null ? "Re-sync" : "Sync to Kanboard"}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {task.kanboard_task_id != null
                  ? `Linked to Kanboard card #${task.kanboard_task_id}.`
                  : "Not synced yet — this will create a card in the ForgeHub Kanboard project."}
              </p>
              {syncKanboard.isError && (
                <p className="mt-2 text-sm text-destructive">
                  {(syncKanboard.error as Error)?.message}
                </p>
              )}
              {pullKanboard.isError && (
                <p className="mt-2 text-sm text-destructive">
                  Pull failed: {(pullKanboard.error as Error)?.message}
                </p>
              )}
              {pullKanboard.isSuccess && (
                <p className="mt-2 text-sm text-emerald-600">
                  Status updated from Kanboard.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <History className="h-5 w-5" />
                  Task executions
                </CardTitle>
                <CardDescription>
                  Every real execution attempt by an agent, sub-agent, human, or system. A task can
                  have multiple executions (failed, retried, verified, completed).
                </CardDescription>
              </div>
              <Button size="sm" onClick={() => setShowExecForm((v) => !v)}>
                <Play className="mr-2 h-4 w-4" />
                {showExecForm ? "Cancel" : "Record execution"}
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
                      <TableHead>#</TableHead>
                      <TableHead>Executor</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Started</TableHead>
                      <TableHead>Finished</TableHead>
                      <TableHead>Cost</TableHead>
                      <TableHead>Evidence</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {task.executions.map((execution) => (
                      <TableRow key={execution.id}>
                        <TableCell className="text-muted-foreground">
                          #{execution.attempt_number ?? "—"}
                        </TableCell>
                        <TableCell className="text-sm">
                          {execution.executor_type ?? "unknown"}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={EXEC_STATUS_VARIANT[execution.status] ?? "outline"}
                          >
                            {execution.status}
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
                <p className="text-sm text-muted-foreground">
                  No executions recorded yet for this task.
                </p>
              )}
              {task.executions?.some((e) => e.outcome_summary) && (
                <div className="mt-4 space-y-2 border-t pt-4">
                  {task.executions
                    .filter((e) => e.outcome_summary)
                    .map((e) => (
                      <div key={e.id} className="rounded-md bg-muted/50 p-3 text-sm">
                        <span className="font-medium">#{e.attempt_number}: </span>
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
              Back to list
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
