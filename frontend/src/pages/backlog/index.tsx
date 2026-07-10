import { Fragment, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Download,
  Filter,
  ListPlus,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  planningItemKeys,
  useCreatePlanningItem,
  useDeletePlanningItem,
  useUpdatePlanningItem,
  usePlanningItems,
  type PlanningItem,
  type PlanningItemCreateInput,
  type PlanningItemUpdateInput,
} from "@/hooks/useBacklog";
import {
  taskKeys,
  useCreateTask,
  useDeleteTask,
  useUpdateTask,
  useTasks,
  type ProjectTask,
  type TaskCreateInput,
  type TaskUpdateInput,
} from "@/hooks/useTask";
import { useProjects } from "@/hooks/useProject";
import { apiClient } from "@/lib/api";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { PlanningItemForm } from "./PlanningItemForm";
import { TaskForm } from "../task/TaskForm";

const PRIORITY_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  low: "secondary",
  medium: "outline",
  high: "warning",
  critical: "destructive",
};

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  new: "outline",
  triaged: "secondary",
  scoped: "default",
  in_progress: "warning",
  blocked: "destructive",
  done: "success",
  rejected: "destructive",
};

const TASK_STATUS_VARIANT: Record<
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

// ---------------------------------------------------------------------------
// Sub-row: expanded tasks + inline add/edit/delete
// ---------------------------------------------------------------------------

function TaskRow({
  task,
  planningItemId,
  projectId,
}: {
  task: ProjectTask;
  planningItemId: string;
  projectId: string | null | undefined;
}) {
  const updateTask = useUpdateTask(task.id);
  const deleteTask = useDeleteTask();
  const [editing, setEditing] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);

  function handleUpdate(values: TaskUpdateInput) {
    updateTask.mutate(
      {
        ...values,
        description: values.description || undefined,
        change_request_id: values.change_request_id || undefined,
        parent_task_id: values.parent_task_id || undefined,
        due_date: values.due_date || undefined,
      },
      { onSuccess: () => setEditing(false) }
    );
  }

  if (editing) {
    return (
      <li className="rounded-md border bg-card p-4">
        <p className="mb-3 text-sm font-medium">Editing task</p>
        <TaskForm
          defaultValues={{
            title: task.title,
            description: task.description ?? "",
            status: task.status,
            priority: task.priority,
            project_id: task.project_id ?? projectId ?? "",
            planning_item_id: planningItemId,
            due_date: task.due_date ?? "",
          }}
          onSubmit={handleUpdate}
          onCancel={() => setEditing(false)}
          isSubmitting={updateTask.isPending}
          submitLabel="Save task"
        />
        {updateTask.isError && (
          <p className="mt-2 text-sm text-destructive">
            {(updateTask.error as Error)?.message}
          </p>
        )}
      </li>
    );
  }

  return (
    <>
      <li className="flex items-center justify-between gap-3 text-sm">
        <Link to={`/tasks/${task.id}`} className="min-w-0 flex-1 hover:underline truncate">
          {task.title}
          {task.parent_task_id && (
            <span className="ml-2 text-xs text-muted-foreground">(subtask)</span>
          )}
        </Link>
        <div className="flex shrink-0 items-center gap-1.5">
          <Badge variant={TASK_STATUS_VARIANT[task.status] ?? "outline"}>
            {task.status.replace("_", " ")}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setEditing(true)}
            title="Edit task"
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setPendingDelete(true)}
            disabled={deleteTask.isPending}
            title="Delete task"
          >
            <Trash2 className="h-3 w-3 text-destructive" />
          </Button>
        </div>
      </li>
      <ConfirmDialog
        open={pendingDelete}
        title="Delete task?"
        description={`"${task.title}" will be permanently deleted.`}
        confirmLabel="Delete"
        onConfirm={() => {
          deleteTask.mutate(task.id);
          setPendingDelete(false);
        }}
        onCancel={() => setPendingDelete(false)}
      />
    </>
  );
}

function PlanningItemTasksRow({
  planningItemId,
  projectId,
  autoOpenForm = false,
}: {
  planningItemId: string;
  projectId: string | null | undefined;
  autoOpenForm?: boolean;
}) {
  const { data: tasks, isLoading } = useTasks(planningItemId);
  const createTask = useCreateTask();
  const [showTaskForm, setShowTaskForm] = useState(autoOpenForm);

  function handleCreateTask(values: TaskCreateInput) {
    createTask.mutate(
      {
        ...values,
        planning_item_id: planningItemId,
        project_id: values.project_id || projectId || undefined,
        description: values.description || undefined,
        change_request_id: values.change_request_id || undefined,
        parent_task_id: values.parent_task_id || undefined,
        due_date: values.due_date || undefined,
      },
      { onSuccess: () => setShowTaskForm(false) }
    );
  }

  return (
    <div className="space-y-2 py-2">
      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading tasks…
        </div>
      )}

      {!isLoading && tasks && tasks.length > 0 && (
        <ul className="space-y-1.5">
          {tasks.map((task) => (
            <TaskRow
              key={task.id}
              task={task}
              planningItemId={planningItemId}
              projectId={projectId}
            />
          ))}
        </ul>
      )}

      {!isLoading && (!tasks || tasks.length === 0) && !showTaskForm && (
        <p className="text-sm text-muted-foreground">No tasks yet for this planning item.</p>
      )}

      {showTaskForm ? (
        <div className="rounded-md border bg-card p-4">
          <p className="mb-3 text-sm font-medium">New task</p>
          <TaskForm
            onSubmit={handleCreateTask}
            onCancel={() => setShowTaskForm(false)}
            isSubmitting={createTask.isPending}
            submitLabel="Add task"
            defaultValues={{
              planning_item_id: planningItemId,
              project_id: projectId ?? "",
            }}
          />
          {createTask.isError && (
            <p className="mt-2 text-sm text-destructive">
              {(createTask.error as Error)?.message}
            </p>
          )}
        </div>
      ) : (
        <Button
          variant="outline"
          size="sm"
          className="mt-1 h-7 text-xs"
          onClick={() => setShowTaskForm(true)}
        >
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          Add task
        </Button>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline edit row
// ---------------------------------------------------------------------------

function EditItemRow({
  item,
  onClose,
}: {
  item: PlanningItem;
  onClose: () => void;
}) {
  const updateItem = useUpdatePlanningItem(item.id);

  function handleSubmit(values: PlanningItemUpdateInput) {
    updateItem.mutate(
      {
        ...values,
        description: values.description || undefined,
        product_version_id: values.product_version_id || undefined,
        severity: values.severity || undefined,
        environment: values.environment || undefined,
        detected_in_version: values.detected_in_version || undefined,
      },
      { onSuccess: onClose }
    );
  }

  return (
    <TableRow>
      <TableCell />
      <TableCell colSpan={6} className="bg-muted/20 py-4">
        <p className="mb-3 text-sm font-medium">Editing: {item.title}</p>
        <PlanningItemForm
          defaultValues={{
            title: item.title,
            description: item.description ?? "",
            item_type: item.item_type,
            status: item.status,
            priority: item.priority,
            product_version_id: item.product_version_id ?? "",
            project_id: item.project_id ?? "",
            output_path: "",
          }}
          onSubmit={handleSubmit}
          onCancel={onClose}
          isSubmitting={updateItem.isPending}
          submitLabel="Save changes"
        />
        {updateItem.isError && (
          <p className="mt-2 text-sm text-destructive">
            {(updateItem.error as Error)?.message}
          </p>
        )}
      </TableCell>
    </TableRow>
  );
}

// ---------------------------------------------------------------------------
// JSON import/export helpers
// ---------------------------------------------------------------------------

type ExportItem = {
  title: string;
  description: string | null | undefined;
  item_type: string;
  status: string;
  priority: string;
  project_id: string | null | undefined;
  product_version_id: string | null | undefined;
  output_path: string | null | undefined;
  tasks: Array<{
    title: string;
    description: string | null | undefined;
    status: string;
    priority: string;
    due_date: string | null | undefined;
    estimated_cost: number | null | undefined;
  }>;
};

function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function BacklogPage() {
  const { data: planningItems, isLoading, isError, error } = usePlanningItems();
  const { data: projects } = useProjects();
  const createPlanningItem = useCreatePlanningItem();
  const deletePlanningItem = useDeletePlanningItem();
  const queryClient = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [addingTaskForId, setAddingTaskForId] = useState<string | null>(null);
  const [filterProjectId, setFilterProjectId] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const visibleItems = filterProjectId
    ? (planningItems ?? []).filter((i) => i.project_id === filterProjectId)
    : (planningItems ?? []);

  function handleCreate(values: PlanningItemCreateInput) {
    createPlanningItem.mutate(
      {
        ...values,
        description: values.description || undefined,
        product_version_id: values.product_version_id || undefined,
        severity: values.severity || undefined,
        environment: values.environment || undefined,
        detected_in_version: values.detected_in_version || undefined,
      },
      { onSuccess: () => setShowForm(false) }
    );
  }

  // --- Export ---
  async function handleExport() {
    const items = visibleItems;
    const exported: ExportItem[] = await Promise.all(
      items.map(async (item) => {
        let tasks: ExportItem["tasks"] = [];
        try {
          const t = await apiClient.get<Array<{ title: string; description?: string | null; status: string; priority: string; due_date?: string | null; estimated_cost?: number | null }>>(`/api/v1/tasks?planning_item_id=${item.id}`);
          tasks = t.map((task) => ({
            title: task.title,
            description: task.description,
            status: task.status,
            priority: task.priority,
            due_date: task.due_date,
            estimated_cost: task.estimated_cost,
          }));
        } catch {
          // tasks stay empty if fetch fails
        }
        return {
          title: item.title,
          description: item.description,
          item_type: item.item_type,
          status: item.status,
          priority: item.priority,
          project_id: item.project_id,
          product_version_id: item.product_version_id,
          output_path: item.output_path,
          tasks,
        };
      })
    );
    const label = filterProjectId
      ? (projects?.find((p) => p.id === filterProjectId)?.name ?? "filtered")
      : "all";
    downloadJson(exported, `planning-${label}-${new Date().toISOString().slice(0, 10)}.json`);
  }

  // --- Import ---
  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setImportError(null);
    try {
      const text = await file.text();
      const data = JSON.parse(text) as ExportItem[];
      if (!Array.isArray(data)) throw new Error("JSON must be an array of planning items.");

      for (const item of data) {
        if (!item.title) throw new Error(`Item missing "title" field.`);

        // Create planning item
        const created = await apiClient.post<{ id: string }>("/api/v1/planning-items", {
          title: item.title,
          description: item.description || undefined,
          item_type: item.item_type || "feature",
          status: item.status || "new",
          priority: item.priority || "medium",
          project_id: item.project_id || undefined,
          product_version_id: item.product_version_id || undefined,
          output_path: item.output_path || undefined,
        });

        // Create tasks linked to this item
        for (const task of item.tasks ?? []) {
          if (!task.title) continue;
          await apiClient.post("/api/v1/tasks", {
            title: task.title,
            description: task.description || undefined,
            status: task.status || "planned",
            priority: task.priority || "medium",
            due_date: task.due_date || undefined,
            estimated_cost: task.estimated_cost ?? undefined,
            planning_item_id: created.id,
            project_id: item.project_id || undefined,
          });
        }
      }

      // Refresh both lists
      queryClient.invalidateQueries({ queryKey: planningItemKeys.all });
      queryClient.invalidateQueries({ queryKey: taskKeys.all });
    } catch (err) {
      setImportError((err as Error).message);
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Planning</h1>
          <p className="text-muted-foreground">
            Planning items entering version scope: features, bugs, hotfixes, improvements,
            technical debt, and more.
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

          {/* Export */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={visibleItems.length === 0}
            title="Export visible items + their tasks as JSON"
          >
            <Download className="mr-2 h-4 w-4" />
            Export JSON
          </Button>

          {/* Import */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            title="Import planning items from a previously exported JSON file"
          >
            {importing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            Import JSON
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={handleImportFile}
          />

          <Button onClick={() => { setShowForm((v) => !v); setEditingId(null); }}>
            <Plus className="mr-2 h-4 w-4" />
            New planning item
          </Button>
        </div>
      </div>

      {importError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          Import failed: {importError}
        </div>
      )}

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>Create planning item</CardTitle>
            <CardDescription>
              Capture a feature, bug, or other planning item before it enters triage and version
              scope.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PlanningItemForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createPlanningItem.isPending}
            />
            {createPlanningItem.isError && (
              <p className="mt-3 text-sm text-destructive">
                Failed to create planning item: {(createPlanningItem.error as Error)?.message}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading planning items…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load planning items: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && visibleItems.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ClipboardList className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No planning items yet</p>
              <p className="text-sm text-muted-foreground">
                Create your first feature request or bug report to start building the backlog.
              </p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New planning item
            </Button>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && visibleItems.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Title</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Priority</TableHead>
                  <TableHead>Version scope</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleItems.map((item) => {
                  const isExpanded = expandedId === item.id;
                  const isEditing = editingId === item.id;
                  return (
                    <Fragment key={item.id}>
                      <TableRow className={isEditing ? "bg-muted/10" : undefined}>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            aria-label={isExpanded ? "Collapse tasks" : "Expand tasks"}
                            onClick={() => {
                              setExpandedId(isExpanded ? null : item.id);
                              if (isEditing) setEditingId(null);
                            }}
                          >
                            {isExpanded ? (
                              <ChevronDown className="h-4 w-4" />
                            ) : (
                              <ChevronRight className="h-4 w-4" />
                            )}
                          </Button>
                        </TableCell>
                        <TableCell>
                          <Link
                            to={`/backlog/${item.id}`}
                            className="font-medium hover:underline"
                          >
                            {item.title}
                          </Link>
                          {item.description && (
                            <p className="line-clamp-1 text-sm text-muted-foreground">
                              {item.description}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="capitalize">
                          {item.item_type.replace("_", " ")}
                        </TableCell>
                        <TableCell>
                          <Badge variant={STATUS_VARIANT[item.status] ?? "outline"}>
                            {item.status.replace("_", " ")}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={PRIORITY_VARIANT[item.priority] ?? "outline"}>
                            {item.priority}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {item.version_scope_items && item.version_scope_items.length > 0
                            ? `${item.version_scope_items.length} version(s)`
                            : "Unscoped"}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0"
                              aria-label={`Edit ${item.title}`}
                              onClick={() => {
                                setEditingId(isEditing ? null : item.id);
                                setExpandedId(null);
                                setAddingTaskForId(null);
                              }}
                              title="Edit planning item"
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0"
                              aria-label={`Add task to ${item.title}`}
                              onClick={() => {
                                setExpandedId(item.id);
                                setEditingId(null);
                                setAddingTaskForId(item.id);
                              }}
                              title="Add task"
                            >
                              <ListPlus className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0"
                              onClick={() => setPendingDeleteId(item.id)}
                              disabled={deletePlanningItem.isPending}
                              aria-label={`Delete ${item.title}`}
                            >
                              <Trash2 className="h-3.5 w-3.5 text-destructive" />
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>

                      {/* Inline edit form */}
                      {isEditing && (
                        <EditItemRow item={item} onClose={() => setEditingId(null)} />
                      )}

                      {/* Expanded tasks sub-row */}
                      {isExpanded && !isEditing && (
                        <TableRow>
                          <TableCell />
                          <TableCell colSpan={6} className="bg-muted/30 py-3">
                            <PlanningItemTasksRow
                              planningItemId={item.id}
                              projectId={item.project_id}
                              autoOpenForm={addingTaskForId === item.id}
                            />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete planning item?"
        description="This will permanently delete the planning item and all related tasks. This cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDeleteId) deletePlanningItem.mutate({ id: pendingDeleteId });
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
