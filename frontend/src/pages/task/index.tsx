import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AlertCircle, CheckCircle2, ClipboardList, Copy, Filter, Loader2, Plus, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import {
  useCreateTask,
  useDeleteTask,
  useTasks,
  type TaskCreateInput,
} from "@/hooks/useTask";
import { useProjects } from "@/hooks/useProject";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { TaskForm } from "./TaskForm";
import { ExecutionWaveBoard } from "@/components/ExecutionWaveBoard";

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  planned: "outline",
  ready: "warning",
  assigned: "secondary",
  in_progress: "default",
  blocked: "destructive",
  done: "success",
  deployed: "success",
  cancelled: "destructive",
};

const PRIORITY_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  low: "outline",
  medium: "secondary",
  high: "warning",
  critical: "destructive",
};

const FORGEROUTER_ANTHROPIC_PROMPT = `Implement a ForgeRouter Anthropic-compatible adapter while preserving the existing OpenAI-compatible API.

Context:
- The existing ForgeRouter endpoint is OpenAI-compatible at http://localhost:2100/v1 and must keep working for Codex, Antigravity, and other OpenAI-compatible clients.
- Claude Code does not use OpenAI /v1/chat/completions. It sends Anthropic Messages API requests to /v1/messages.
- Claude Code should be configured with ANTHROPIC_BASE_URL=http://localhost:2100, ANTHROPIC_AUTH_TOKEN=<agent token>, and model forgerouter/auto.
- Do not remove or rename the existing OpenAI-compatible /v1/chat/completions route.

Required implementation:
1. Add an Anthropic-compatible HTTP surface on the same ForgeRouter service:
   - POST /v1/messages
   - GET /v1/models if model discovery does not already return forgerouter/auto and the virtual models Claude Code should see
2. Accept Authorization: Bearer <agent token> using the same agent-key attribution already used by /v1/chat/completions.
3. Support at least model="forgerouter/auto" and route it through the existing ForgeRouter demand/router chain.
4. Translate Anthropic Messages payloads into the internal OpenAI-compatible ChatCompletionRequest format used by the current router:
   - system string or system content blocks
   - messages[] role/content blocks
   - max_tokens, temperature, stop_sequences
   - stream true/false
5. Translate the router response back to Anthropic Messages format:
   - non-streaming: { id, type: "message", role: "assistant", model, content, stop_reason, stop_sequence, usage }
   - streaming: Anthropic SSE event sequence with message_start, content_block_start, content_block_delta, content_block_stop, message_delta, message_stop
6. Keep OpenAI-compatible behavior unchanged:
   - http://localhost:2100/v1/chat/completions continues to accept model forgerouter/auto
   - http://localhost:2100/v1 remains the base URL for OpenAI-compatible clients
7. Add tests for:
   - non-streaming /v1/messages with model forgerouter/auto
   - streaming /v1/messages
   - auth failure
   - OpenAI-compatible /v1/chat/completions still works

Acceptance checks:
curl -X POST http://localhost:2100/v1/messages \\
  -H "Authorization: Bearer <agent token>" \\
  -H "anthropic-version: 2023-06-01" \\
  -H "content-type: application/json" \\
  -d '{"model":"forgerouter/auto","max_tokens":32,"messages":[{"role":"user","content":"Reply only OK"}]}'

The curl response must be valid Anthropic Messages JSON. After that, Claude Code can use:
{
  "model": "forgerouter/auto",
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:2100",
    "ANTHROPIC_AUTH_TOKEN": "<agent token>",
    "ANTHROPIC_MODEL": "forgerouter/auto",
    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1"
  }
}
`;

export default function TaskPage() {
  const [searchParams] = useSearchParams();
  const prefilledCrId = searchParams.get("change_request_id") ?? undefined;
  const prefilledPlanningItemId = searchParams.get("planning_item_id") ?? undefined;
  const prefilledProjectId = searchParams.get("project_id") ?? undefined;

  const { data: tasks, isLoading, isError, error } = useTasks();
  const { data: projects } = useProjects();
  const createTask = useCreateTask();
  const deleteTask = useDeleteTask();
  const [showForm, setShowForm] = useState(false);
  const [filterProjectId, setFilterProjectId] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [copiedPrompt, setCopiedPrompt] = useState(false);

  const visibleTasks = filterProjectId
    ? (tasks ?? []).filter((t) => t.project_id === filterProjectId)
    : (tasks ?? []);

  // Auto-open form when arriving with pre-filled params from a planning item or CR button.
  useEffect(() => {
    if (prefilledCrId || prefilledPlanningItemId) setShowForm(true);
  }, [prefilledCrId, prefilledPlanningItemId]);

  function handleCreate(values: TaskCreateInput) {
    createTask.mutate(
      {
        ...values,
        description: values.description || undefined,
        project_id: values.project_id || undefined,
        planning_item_id: values.planning_item_id || undefined,
        change_request_id: values.change_request_id || undefined,
        parent_task_id: values.parent_task_id || undefined,
        due_date: values.due_date || undefined,
      },
      {
        onSuccess: () => setShowForm(false),
      }
    );
  }

  async function handleCopyForgeRouterPrompt() {
    await navigator.clipboard.writeText(FORGEROUTER_ANTHROPIC_PROMPT);
    setCopiedPrompt(true);
    window.setTimeout(() => setCopiedPrompt(false), 1800);
  }

  return (
    <div className="space-y-6">
      <ExecutionWaveBoard />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Execution</h1>
          <p className="text-muted-foreground">
            Planned tasks and subtasks split out from planning items, assigned to agents and tracked
            through execution.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={filterProjectId}
            onChange={(e) => setFilterProjectId(e.target.value)}
          >
            <option value="">All projects</option>
            {projects?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <Button onClick={() => setShowForm((v) => !v)}>
            <Plus className="mr-2 h-4 w-4" />
            New task
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
          <div>
            <CardTitle>ForgeRouter Anthropic adapter task</CardTitle>
            <CardDescription>
              Viable only if ForgeRouter adds an Anthropic Messages API surface while keeping the
              current OpenAI-compatible surface for Codex.
            </CardDescription>
          </div>
          <Button variant="outline" size="sm" onClick={() => void handleCopyForgeRouterPrompt()}>
            {copiedPrompt ? (
              <CheckCircle2 className="mr-2 h-4 w-4 text-emerald-500" />
            ) : (
              <Copy className="mr-2 h-4 w-4" />
            )}
            {copiedPrompt ? "Copied" : "Copy prompt"}
          </Button>
        </CardHeader>
        <CardContent>
          <pre className="max-h-56 overflow-auto rounded-md border bg-muted/30 p-3 text-xs leading-relaxed text-muted-foreground whitespace-pre-wrap">
            {FORGEROUTER_ANTHROPIC_PROMPT}
          </pre>
        </CardContent>
      </Card>

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Create task</CardTitle>
            <CardDescription>
              Register a new task. Assignments and executions are tracked once work begins.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <TaskForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createTask.isPending}
              projectId={prefilledProjectId}
              defaultValues={{
                change_request_id: prefilledCrId ?? "",
                planning_item_id: prefilledPlanningItemId ?? "",
                project_id: prefilledProjectId ?? "",
              }}
            />
            {createTask.isError && (
              <p className="mt-3 text-sm text-destructive">
                Failed to create task: {(createTask.error as Error)?.message}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading tasks…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load tasks: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && visibleTasks.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ClipboardList className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No tasks yet</p>
              <p className="text-sm text-muted-foreground">
                Create your first task to start tracking assignment and execution.
              </p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New task
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && visibleTasks.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Due date</TableHead>
                  <TableHead>Executions</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleTasks.map((task) => (
                  <TableRow key={task.id}>
                    <TableCell>
                      <Link to={`/tasks/${task.id}`} className="font-medium hover:underline">
                        {task.title}
                      </Link>
                      {task.parent_task_id && (
                        <p className="text-xs text-muted-foreground">Subtask</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[task.status] ?? "outline"}>
                        {task.status.replace("_", " ")}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={PRIORITY_VARIANT[task.priority] ?? "outline"}>
                        {task.priority}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {task.due_date ?? "—"}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {task.executions?.length ?? 0}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Link
                          to={`/tasks/${task.id}`}
                          className={buttonVariants({ variant: "outline", size: "sm" })}
                        >
                          View
                        </Link>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPendingDeleteId(task.id)}
                          disabled={deleteTask.isPending}
                          aria-label={`Delete ${task.title}`}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete task?"
        description="This will permanently delete the task and all its executions. This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDeleteId) deleteTask.mutate(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
