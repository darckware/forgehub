import { Fragment, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("backlog");
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
        planned_end_date: values.planned_end_date || undefined,
      },
      { onSuccess: () => setEditing(false) }
    );
  }

  if (editing) {
    return (
      <li className="rounded-md border bg-card p-4">
        <p className="mb-3 text-sm font-medium">{t("list.taskRow.editingTask")}</p>
        <TaskForm
          defaultValues={{
            title: task.title,
            description: task.description ?? "",
            status: task.status,
            priority: task.priority,
            planning_item_id: planningItemId,
            planned_end_date: task.planned_end_date ?? "",
          }}
          projectId={task.project_id ?? projectId ?? undefined}
          onSubmit={handleUpdate}
          onCancel={() => setEditing(false)}
          isSubmitting={updateTask.isPending}
          submitLabel={t("list.taskRow.saveTask")}
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
          <span className="text-muted-foreground">#{task.number}</span> {task.title}
          {task.parent_task_id && (
            <span className="ml-2 text-xs text-muted-foreground">{t("list.taskRow.subtaskLabel")}</span>
          )}
        </Link>
        <div className="flex shrink-0 items-center gap-1.5">
          {task.health !== "ok" && (
            <span title={t(`list.taskRow.health.${task.health}`, task.health)}>
              <AlertCircle className="h-3.5 w-3.5 text-destructive" />
            </span>
          )}
          <Badge variant={TASK_STATUS_VARIANT[task.status] ?? "outline"}>
            {t(`enums.taskStatuses.${task.status}`, { defaultValue: task.status.replace("_", " ") })}
          </Badge>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setEditing(true)}
            title={t("list.taskRow.editTooltip")}
          >
            <Pencil className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setPendingDelete(true)}
            disabled={deleteTask.isPending}
            title={t("list.taskRow.deleteTooltip")}
          >
            <Trash2 className="h-3 w-3 text-destructive" />
          </Button>
        </div>
      </li>
      {deleteTask.isError && (
        <li className="text-sm text-destructive">
          {(deleteTask.error as Error)?.message}
        </li>
      )}
      <ConfirmDialog
        open={pendingDelete}
        title={t("list.taskRow.deleteDialog.title")}
        description={t("list.taskRow.deleteDialog.description", { title: task.title })}
        confirmLabel={t("list.taskRow.deleteDialog.confirm")}
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
  const { t } = useTranslation("backlog");
  const { data: tasks, isLoading } = useTasks(planningItemId);
  const createTask = useCreateTask();
  const [showTaskForm, setShowTaskForm] = useState(autoOpenForm);

  function handleCreateTask(values: TaskCreateInput) {
    createTask.mutate(
      {
        ...values,
        planning_item_id: planningItemId,
        description: values.description || undefined,
        change_request_id: values.change_request_id || undefined,
        parent_task_id: values.parent_task_id || undefined,
        planned_end_date: values.planned_end_date || undefined,
      },
      { onSuccess: () => setShowTaskForm(false) }
    );
  }

  return (
    <div className="space-y-2 py-2">
      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("list.tasksRow.loading")}
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
        <p className="text-sm text-muted-foreground">{t("list.tasksRow.empty")}</p>
      )}

      {showTaskForm ? (
        <div className="rounded-md border bg-card p-4">
          <p className="mb-3 text-sm font-medium">{t("list.tasksRow.newTaskHeading")}</p>
          <TaskForm
            onSubmit={handleCreateTask}
            onCancel={() => setShowTaskForm(false)}
            isSubmitting={createTask.isPending}
            submitLabel={t("list.tasksRow.addTaskSubmit")}
            defaultValues={{
              planning_item_id: planningItemId,
            }}
            projectId={projectId ?? undefined}
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
          {t("list.tasksRow.addTaskButton")}
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
  const { t } = useTranslation("backlog");
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
        <p className="mb-3 text-sm font-medium">{t("list.editRow.editing", { title: item.title })}</p>
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
          submitLabel={t("list.editRow.saveButton")}
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
    planned_end_date: string | null | undefined;
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
  const { t } = useTranslation("backlog");
  const { data: planningItems, isLoading, isError, error } = usePlanningItems();
  const { data: projects } = useProjects();
  const createPlanningItem = useCreatePlanningItem();
  const deletePlanningItem = useDeletePlanningItem();
  const queryClient = useQueryClient();

  const [showForm, setShowForm] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
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
          const t = await apiClient.get<Array<{ title: string; description?: string | null; status: string; priority: string; planned_end_date?: string | null; estimated_cost?: number | null }>>(`/api/v1/tasks?planning_item_id=${item.id}`);
          tasks = t.map((task) => ({
            title: task.title,
            description: task.description,
            status: task.status,
            priority: task.priority,
            planned_end_date: task.planned_end_date,
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
            planned_end_date: task.planned_end_date || undefined,
            estimated_cost: task.estimated_cost ?? undefined,
            planning_item_id: created.id,
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
          <h1 className="text-3xl font-bold tracking-tight">{t("list.title")}</h1>
          <p className="text-muted-foreground">{t("list.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <select
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={filterProjectId}
            onChange={(e) => setFilterProjectId(e.target.value)}
          >
            <option value="">{t("list.filterAllProjects")}</option>
            {projects?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>

          {/* Expand / Collapse All Tasks */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const allExpanded = visibleItems.length > 0 && expandedIds.size === visibleItems.length;
              if (allExpanded) {
                setExpandedIds(new Set());
              } else {
                setExpandedIds(new Set(visibleItems.map((i) => i.id)));
              }
            }}
            title={
              visibleItems.length > 0 && expandedIds.size === visibleItems.length
                ? t("list.collapseAllTooltip")
                : t("list.expandAllTooltip")
            }
          >
            <ChevronDown className={`mr-1 h-4 w-4 transition-transform ${visibleItems.length > 0 && expandedIds.size === visibleItems.length ? "rotate-180" : ""}`} />
            {visibleItems.length > 0 && expandedIds.size === visibleItems.length
              ? t("list.collapseAllButton")
              : t("list.expandAllButton")}
          </Button>

          {/* Export */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={visibleItems.length === 0}
            title={t("list.exportTooltip")}
          >
            <Download className="mr-2 h-4 w-4" />
            {t("list.exportButton")}
          </Button>

          {/* Import */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={importing}
            title={t("list.importTooltip")}
          >
            {importing ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-2 h-4 w-4" />
            )}
            {t("list.importButton")}
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
            {t("list.newButton")}
          </Button>
        </div>
      </div>

      {importError && (
        <div className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {t("list.importFailed", { error: importError })}
        </div>
      )}

      {showForm && (
        <Card>
          <CardHeader>
            <CardTitle>{t("list.createCard.title")}</CardTitle>
            <CardDescription>{t("list.createCard.description")}</CardDescription>
          </CardHeader>
          <CardContent>
            <PlanningItemForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isSubmitting={createPlanningItem.isPending}
            />
            {createPlanningItem.isError && (
              <p className="mt-3 text-sm text-destructive">
                {t("list.createError", { error: (createPlanningItem.error as Error)?.message })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("list.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("list.loadError", { error: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && visibleItems.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <ClipboardList className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("list.emptyState.title")}</p>
              <p className="text-sm text-muted-foreground">{t("list.emptyState.description")}</p>
            </div>
            <Button onClick={() => setShowForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t("list.newButton")}
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
                  <TableHead>{t("list.columns.title")}</TableHead>
                  <TableHead>{t("list.columns.type")}</TableHead>
                  <TableHead>{t("list.columns.status")}</TableHead>
                  <TableHead>{t("list.columns.priority")}</TableHead>
                  <TableHead>{t("list.columns.versionScope")}</TableHead>
                  <TableHead className="text-right">{t("list.columns.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visibleItems.map((item) => {
                  const isExpanded = expandedIds.has(item.id);
                  const isEditing = editingId === item.id;
                  return (
                    <Fragment key={item.id}>
                      <TableRow className={isEditing ? "bg-muted/10" : undefined}>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0"
                            aria-label={isExpanded ? t("list.collapseTasks") : t("list.expandTasks")}
                            onClick={() => {
                              setExpandedIds((prev) => {
                                const next = new Set(prev);
                                if (next.has(item.id)) {
                                  next.delete(item.id);
                                } else {
                                  next.add(item.id);
                                }
                                return next;
                              });
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
                          {t(`enums.itemTypes.${item.item_type}`, {
                            defaultValue: item.item_type.replace("_", " "),
                          })}
                        </TableCell>
                        <TableCell>
                          <Badge variant={STATUS_VARIANT[item.status] ?? "outline"}>
                            {t(`enums.statuses.${item.status}`, {
                              defaultValue: item.status.replace("_", " "),
                            })}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={PRIORITY_VARIANT[item.priority] ?? "outline"}>
                            {t(`enums.priorities.${item.priority}`, { defaultValue: item.priority })}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {item.version_scope_items && item.version_scope_items.length > 0
                            ? t("list.columns.versionCount", { count: item.version_scope_items.length })
                            : t("list.columns.unscoped")}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0"
                              aria-label={t("list.editAria", { title: item.title })}
                              onClick={() => {
                                setEditingId(isEditing ? null : item.id);
                                setEditingId(isEditing ? null : item.id);
                                setAddingTaskForId(null);
                              }}
                              title={t("list.editTooltip")}
                            >
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0"
                              aria-label={t("list.addTaskAria", { title: item.title })}
                              onClick={() => {
                                setExpandedIds((prev) => new Set(prev).add(item.id));
                                setEditingId(null);
                                setAddingTaskForId(item.id);
                              }}
                              title={t("list.addTaskTooltip")}
                            >
                              <ListPlus className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0"
                              onClick={() => setPendingDeleteId(item.id)}
                              disabled={deletePlanningItem.isPending}
                              aria-label={t("list.deleteAria", { title: item.title })}
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
        title={t("list.deleteDialog.title")}
        description={t("list.deleteDialog.description")}
        confirmLabel={t("list.deleteDialog.confirm")}
        onConfirm={() => {
          if (pendingDeleteId) deletePlanningItem.mutate({ id: pendingDeleteId });
          setPendingDeleteId(null);
        }}
        onCancel={() => setPendingDeleteId(null)}
      />
    </div>
  );
}
