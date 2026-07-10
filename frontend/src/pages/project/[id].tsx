import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import {
  AlertCircle,
  ArrowLeft,
  CalendarRange,
  CheckCircle2,
  ClipboardList,
  FolderTree,
  GitPullRequestArrow,
  Kanban,
  ListTodo,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Trash2,
  Unlock,
  XCircle,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ProjectFileBrowser } from "@/components/ProjectFileBrowser";
import {
  useApproveProjectPlan,
  useChangeRequests,
  useCreateChangeRequest,
  useCreatePlanBaseline,
  useCreateProjectPlan,
  useCreateStructureNode,
  useDeleteChangeRequest,
  useDeleteStructureNode,
  usePlanBaselines,
  useProject,
  useProjectPlans,
  useStructureNodes,
  useUpdateChangeRequest,
  useUpdateProject,
  useUpdateStructureNode,
  type ChangeRequest,
  type ProjectCreateInput,
  type StructureNode,
} from "@/hooks/useProject";
import { useProductVersion } from "@/hooks/useProduct";
import { useTasksByChangeRequest, useKanboardCleanup } from "@/hooks/useTask";
import { useDeletePlanningItem } from "@/hooks/useBacklog";
import { EntityDocsCard } from "@/components/EntityDocsCard";
import { ProjectForm } from "./ProjectForm";
import { StructureNodeForm } from "./StructureNodeForm";
import { ProjectPlanForm } from "./ProjectPlanForm";
import { ChangeRequestForm } from "./ChangeRequestForm";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

const CHANGE_REQUEST_STATUS_VARIANT: Record<string, "outline" | "success" | "destructive" | "secondary"> = {
  pending: "outline",
  approved: "success",
  rejected: "destructive",
  applied: "secondary",
};

const CHANGE_REQUEST_IMPACT_LABELS: Record<string, string> = {
  affects_scope: "Scope",
  affects_schedule: "Schedule",
  affects_cost: "Cost",
  adds_features: "Adds features",
  removes_features: "Removes features",
  introduces_critical_bug_fix: "Critical bug fix",
  changes_agents: "Agents",
  changes_skills: "Skills",
  changes_architecture: "Architecture",
  changes_security: "Security",
};

function changeRequestImpactLabels(cr: ChangeRequest): string[] {
  return Object.entries(CHANGE_REQUEST_IMPACT_LABELS)
    .filter(([key]) => Boolean(cr[key as keyof ChangeRequest]))
    .map(([, label]) => label);
}

// ---------------------------------------------------------------------------
// ChangeRequestCard — single CR row with inline edit, deliberation actions,
// task count, and create-task shortcut.
// ---------------------------------------------------------------------------

interface ChangeRequestCardProps {
  cr: ChangeRequest;
  baselines: import("@/hooks/useProject").PlanBaseline[];
  isEditing: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: (values: import("@/hooks/useProject").ChangeRequestUpdateInput) => void;
  onApprove: () => void;
  onReject: () => void;
  onMarkApplied: () => void;
  onDelete: () => void;
  isMutating: boolean;
}

function ChangeRequestCard({
  cr,
  baselines,
  isEditing,
  onEdit,
  onCancelEdit,
  onSaveEdit,
  onApprove,
  onReject,
  onMarkApplied,
  onDelete,
  isMutating,
}: ChangeRequestCardProps) {
  const { data: derivedTasks } = useTasksByChangeRequest(cr.id);
  const taskCount = derivedTasks?.length ?? 0;

  return (
    <li className="rounded-md border border-border p-3 text-sm">
      {isEditing ? (
        <ChangeRequestForm
          baselines={baselines}
          initialValues={{
            title: cr.title,
            justification: cr.justification ?? "",
            plan_baseline_id: cr.plan_baseline_id ?? "",
            requested_by: cr.requested_by ?? "",
            affects_scope: cr.affects_scope,
            affects_schedule: cr.affects_schedule,
            affects_cost: cr.affects_cost,
            adds_features: cr.adds_features,
            removes_features: cr.removes_features,
            introduces_critical_bug_fix: cr.introduces_critical_bug_fix,
            changes_agents: cr.changes_agents,
            changes_skills: cr.changes_skills,
            changes_architecture: cr.changes_architecture,
            changes_security: cr.changes_security,
          }}
          onSubmit={(values) => onSaveEdit(values)}
          onCancel={onCancelEdit}
          isSubmitting={isMutating}
          submitLabel="Save changes"
        />
      ) : (
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{cr.title}</span>
              <Badge
                variant={CHANGE_REQUEST_STATUS_VARIANT[cr.status] ?? "outline"}
                className="capitalize"
              >
                {cr.status}
              </Badge>
              {taskCount > 0 && (
                <Badge variant="secondary" className="gap-1 text-[10px]">
                  <ListTodo className="h-3 w-3" />
                  {taskCount} task{taskCount !== 1 ? "s" : ""}
                </Badge>
              )}
            </div>
            {cr.justification && (
              <p className="text-muted-foreground">{cr.justification}</p>
            )}
            <div className="flex flex-wrap gap-1">
              {changeRequestImpactLabels(cr).map((label) => (
                <Badge key={label} variant="secondary" className="text-[10px]">
                  {label}
                </Badge>
              ))}
            </div>
            <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
              {cr.schedule_delta_days != null && (
                <span>Schedule delta: {cr.schedule_delta_days}d</span>
              )}
              {cr.cost_delta != null && <span>Cost delta: {cr.cost_delta}</span>}
              {cr.requested_by && <span>Requested by {cr.requested_by}</span>}
            </div>
          </div>

          <div className="flex shrink-0 flex-wrap items-center gap-1">
            {/* Deliberation actions */}
            {cr.status === "pending" && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={isMutating}
                  aria-label={`Approve ${cr.title}`}
                  onClick={onApprove}
                >
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={isMutating}
                  aria-label={`Reject ${cr.title}`}
                  onClick={onReject}
                >
                  <XCircle className="h-4 w-4 text-destructive" />
                </Button>
              </>
            )}
            {cr.status === "approved" && (
              <Button
                variant="outline"
                size="sm"
                disabled={isMutating}
                onClick={onMarkApplied}
              >
                Mark applied
              </Button>
            )}

            {/* Edit */}
            {cr.status !== "applied" && (
              <Button
                variant="ghost"
                size="icon"
                disabled={isMutating}
                aria-label={`Edit ${cr.title}`}
                onClick={onEdit}
              >
                <Pencil className="h-4 w-4" />
              </Button>
            )}

            {/* Delete */}
            {cr.status !== "applied" && (
              <Button
                variant="ghost"
                size="icon"
                disabled={isMutating}
                aria-label={`Delete ${cr.title}`}
                onClick={onDelete}
              >
                <Trash2 className="h-4 w-4 text-destructive" />
              </Button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: project, isLoading, isError, error } = useProject(id);
  const { data: productVersion } = useProductVersion(project?.product_version_id ?? undefined);
  const { data: structureNodes } = useStructureNodes(id);
  const updateProject = useUpdateProject(id ?? "");
  const createStructureNode = useCreateStructureNode(id ?? "");
  const updateStructureNode = useUpdateStructureNode(id ?? "");
  const deleteStructureNode = useDeleteStructureNode(id ?? "");
  const { data: plans } = useProjectPlans(id);
  const { data: baselines } = usePlanBaselines(id);
  const { data: changeRequests } = useChangeRequests(id);
  const createProjectPlan = useCreateProjectPlan(id ?? "");
  const approveProjectPlan = useApproveProjectPlan(id ?? "");
  const createPlanBaseline = useCreatePlanBaseline(id ?? "");
  const createChangeRequest = useCreateChangeRequest(id ?? "");
  const updateChangeRequest = useUpdateChangeRequest(id ?? "");
  const deleteChangeRequest = useDeleteChangeRequest(id ?? "");
  const deletePlanningItem = useDeletePlanningItem();
  const [editingPath, setEditingPath] = useState(false);
  const [pathDraft, setPathDraft] = useState("");
  const [showEditForm, setShowEditForm] = useState(false);
  const [showNodeForm, setShowNodeForm] = useState(false);
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [showBaselineForm, setShowBaselineForm] = useState(false);
  const [baselineNameDraft, setBaselineNameDraft] = useState("");
  const [showCrForm, setShowCrForm] = useState(false);
  const [editingCrId, setEditingCrId] = useState<string | null>(null);
  const [pendingDeletePlanningId, setPendingDeletePlanningId] = useState<string | null>(null);
  const [pendingDeleteCrId, setPendingDeleteCrId] = useState<string | null>(null);
  const kanboardCleanup = useKanboardCleanup();
  const [cleanupResult, setCleanupResult] = useState<{
    closed: number;
    skipped: number;
    errors: string[];
  } | null>(null);

  const latestPlan = plans?.[0];

  function handleUpdate(values: ProjectCreateInput) {
    updateProject.mutate(
      {
        ...values,
        description: values.description || undefined,
        product_version_id: values.product_version_id || undefined,
        working_directory_path: values.working_directory_path || undefined,
      },
      { onSuccess: () => setShowEditForm(false) }
    );
  }

  return (
    <div className="space-y-6">
      <Breadcrumb
        items={[
          { label: "Projects", href: "/projects" },
          { label: project?.name ?? "…" },
        ]}
      />

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading project…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load project: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && project && (
        <>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">{project.name}</h1>
              {project.description && (
                <p className="mt-1 max-w-2xl text-muted-foreground">{project.description}</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-sm capitalize">
                {project.status.replace("_", " ")}
              </Badge>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowEditForm((v) => !v)}
              >
                <Pencil className="mr-2 h-4 w-4" />
                Edit
              </Button>
            </div>
          </div>

          {showEditForm && (
            <Card>
              <CardHeader>
                <CardTitle>Edit project</CardTitle>
                <CardDescription>Update name, description, version, status, or working directory.</CardDescription>
              </CardHeader>
              <CardContent>
                <ProjectForm
                  defaultValues={{
                    name: project.name,
                    description: project.description ?? "",
                    product_version_id: project.product_version_id ?? "",
                    status: project.status as ProjectCreateInput["status"],
                    working_directory_path: project.working_directory_path ?? "",
                  }}
                  onSubmit={handleUpdate}
                  onCancel={() => setShowEditForm(false)}
                  isSubmitting={updateProject.isPending}
                  submitLabel="Save changes"
                />
                {updateProject.isError && (
                  <p className="mt-3 text-sm text-destructive">
                    Failed to update project: {(updateProject.error as Error)?.message}
                  </p>
                )}
              </CardContent>
            </Card>
          )}

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-xl">
                    <ClipboardList className="h-5 w-5" />
                    Project plan
                  </CardTitle>
                  <CardDescription>Scope, schedule, and baseline state.</CardDescription>
                </div>
                {!latestPlan && (
                  <Button variant="outline" size="sm" onClick={() => setShowPlanForm((v) => !v)}>
                    <Plus className="mr-2 h-4 w-4" />
                    Create plan
                  </Button>
                )}
              </CardHeader>
              <CardContent className="space-y-4">
                {showPlanForm && (
                  <div className="rounded-md border border-border p-4">
                    <ProjectPlanForm
                      onSubmit={(values) =>
                        createProjectPlan.mutate(values, { onSuccess: () => setShowPlanForm(false) })
                      }
                      onCancel={() => setShowPlanForm(false)}
                      isSubmitting={createProjectPlan.isPending}
                    />
                    {createProjectPlan.isError && (
                      <p className="mt-3 text-sm text-destructive">
                        {(createProjectPlan.error as Error)?.message}
                      </p>
                    )}
                  </div>
                )}

                {latestPlan ? (
                  <dl className="space-y-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{latestPlan.name}</span>
                      <Badge
                        variant={latestPlan.status === "baselined" ? "success" : "outline"}
                        className="capitalize"
                      >
                        {latestPlan.status}
                      </Badge>
                    </div>
                    {latestPlan.scope_summary && (
                      <div>
                        <dt className="font-medium text-muted-foreground">Scope</dt>
                        <dd>{latestPlan.scope_summary}</dd>
                      </div>
                    )}
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <CalendarRange className="h-4 w-4" />
                      <span>
                        {latestPlan.estimated_start_date ?? "No start date"} →{" "}
                        {latestPlan.estimated_end_date ?? "No target date"}
                      </span>
                    </div>
                    {latestPlan.estimated_cost != null && (
                      <div>
                        <dt className="font-medium text-muted-foreground">Estimated cost</dt>
                        <dd>{latestPlan.estimated_cost}</dd>
                      </div>
                    )}

                    {latestPlan.status === "draft" && (
                      <Button
                        size="sm"
                        disabled={approveProjectPlan.isPending}
                        onClick={() => approveProjectPlan.mutate(latestPlan.id)}
                      >
                        Approve plan
                      </Button>
                    )}

                    {latestPlan.status === "approved" && !showBaselineForm && (
                      <Button size="sm" onClick={() => setShowBaselineForm(true)}>
                        Freeze baseline
                      </Button>
                    )}

                    {showBaselineForm && (
                      <div className="flex items-center gap-2">
                        <Input
                          value={baselineNameDraft}
                          onChange={(e) => setBaselineNameDraft(e.target.value)}
                          placeholder="Baseline v1"
                        />
                        <Button
                          size="sm"
                          disabled={!baselineNameDraft || createPlanBaseline.isPending}
                          onClick={() =>
                            createPlanBaseline.mutate(
                              { project_plan_id: latestPlan.id, name: baselineNameDraft },
                              {
                                onSuccess: () => {
                                  setShowBaselineForm(false);
                                  setBaselineNameDraft("");
                                },
                              }
                            )
                          }
                        >
                          Save
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setShowBaselineForm(false)}>
                          Cancel
                        </Button>
                      </div>
                    )}

                    {(approveProjectPlan.isError || createPlanBaseline.isError) && (
                      <p className="text-sm text-destructive">
                        {((approveProjectPlan.error ?? createPlanBaseline.error) as Error)?.message}
                      </p>
                    )}

                    {baselines && baselines.length > 0 && (
                      <div className="space-y-2 pt-2">
                        <dt className="font-medium text-muted-foreground">Baseline history</dt>
                        <ul className="space-y-1">
                          {baselines.map((baseline) => (
                            <li
                              key={baseline.id}
                              className="rounded-md border border-border p-2 text-xs"
                            >
                              <span className="font-medium">{baseline.name}</span>{" "}
                              <span className="text-muted-foreground">
                                frozen {new Date(baseline.frozen_at).toLocaleString()}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </dl>
                ) : (
                  !showPlanForm && (
                    <p className="text-sm text-muted-foreground">
                      No plan has been created for this project yet.
                    </p>
                  )
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-xl">Product version</CardTitle>
                <CardDescription>The target version this project delivers against.</CardDescription>
              </CardHeader>
              <CardContent>
                {project.product_version_id ? (
                  productVersion ? (
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-medium">{productVersion.version}</span>
                      <Badge variant="outline" className="capitalize">
                        {productVersion.status.replace(/_/g, " ")}
                      </Badge>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">Loading version…</p>
                  )
                ) : (
                  <p className="text-sm italic text-muted-foreground">No product version linked.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xl">Working directory</CardTitle>
                <CardDescription>
                  On-disk path of this project's real code/repo.
                </CardDescription>
              </div>
              {!editingPath && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setPathDraft(project.working_directory_path ?? "");
                    setEditingPath(true);
                  }}
                >
                  <Pencil className="mr-2 h-4 w-4" />
                  Edit
                </Button>
              )}
            </CardHeader>
            <CardContent>
              {editingPath ? (
                <div className="flex items-center gap-2">
                  <Input
                    value={pathDraft}
                    onChange={(e) => setPathDraft(e.target.value)}
                    placeholder="/root/project/forgehub"
                  />
                  <Button
                    size="sm"
                    disabled={updateProject.isPending}
                    onClick={() =>
                      updateProject.mutate(
                        { working_directory_path: pathDraft },
                        { onSuccess: () => setEditingPath(false) }
                      )
                    }
                  >
                    Save
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setEditingPath(false)}>
                    Cancel
                  </Button>
                </div>
              ) : (
                <p className="text-sm">
                  {project.working_directory_path ?? (
                    <span className="italic text-muted-foreground">Not set</span>
                  )}
                </p>
              )}
              {updateProject.isError && (
                <p className="mt-2 text-sm text-destructive">
                  {(updateProject.error as Error)?.message}
                </p>
              )}
            </CardContent>
          </Card>

          {project.working_directory_path && (
            <Card>
              <CardHeader>
                <CardTitle className="text-xl">Files</CardTitle>
                <CardDescription>
                  Browse, view, and edit the working directory's real files and folders.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="max-h-96 overflow-y-auto pr-1">
                  <ProjectFileBrowser projectId={project.id} />
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <FolderTree className="h-5 w-5" />
                  Project structure
                </CardTitle>
                <CardDescription>
                  Folders, modules, screens, and DB objects registered against this project.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={() => setShowNodeForm((v) => !v)}>
                <Plus className="mr-2 h-4 w-4" />
                Add node
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {showNodeForm && (
                <div className="rounded-md border border-border p-4">
                  <StructureNodeForm
                    siblingNodes={structureNodes ?? []}
                    onSubmit={(values) =>
                      createStructureNode.mutate(
                        {
                          ...values,
                          parent_node_id: values.parent_node_id || undefined,
                          path: values.path || undefined,
                          description: values.description || undefined,
                        },
                        { onSuccess: () => setShowNodeForm(false) }
                      )
                    }
                    onCancel={() => setShowNodeForm(false)}
                    isSubmitting={createStructureNode.isPending}
                    submitLabel="Create node"
                  />
                  {createStructureNode.isError && (
                    <p className="mt-3 text-sm text-destructive">
                      {(createStructureNode.error as Error)?.message}
                    </p>
                  )}
                </div>
              )}

              {!structureNodes || structureNodes.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No structure nodes registered for this project yet.
                </p>
              ) : (
                <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
                  {structureNodes.map((node: StructureNode) => (
                    <li
                      key={node.id}
                      className="flex items-center justify-between rounded-md border border-border p-2 text-sm"
                    >
                      <div>
                        <span className="font-medium">{node.name}</span>{" "}
                        <Badge variant="outline" className="ml-1 capitalize">
                          {node.node_type.replace(/_/g, " ")}
                        </Badge>
                        {node.path && (
                          <p className="font-mono text-xs text-muted-foreground">{node.path}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        {node.is_locked && (
                          <Badge variant="outline" className="gap-1">
                            <Lock className="h-3 w-3" />
                            locked
                          </Badge>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={updateStructureNode.isPending}
                          onClick={() =>
                            updateStructureNode.mutate({
                              nodeId: node.id,
                              payload: { is_locked: !node.is_locked },
                            })
                          }
                          aria-label={node.is_locked ? `Unlock ${node.name}` : `Lock ${node.name}`}
                        >
                          {node.is_locked ? (
                            <Unlock className="h-4 w-4" />
                          ) : (
                            <Lock className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={node.is_locked || deleteStructureNode.isPending}
                          onClick={() => deleteStructureNode.mutate(node.id)}
                          aria-label={`Delete ${node.name}`}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
              {(updateStructureNode.isError || deleteStructureNode.isError) && (
                <p className="text-sm text-destructive">
                  {((updateStructureNode.error ?? deleteStructureNode.error) as Error)?.message}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <GitPullRequestArrow className="h-5 w-5" />
                  Change requests
                </CardTitle>
                <CardDescription>
                  Post-baseline deviations tracked against scope, time, and cost.
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={() => setShowCrForm((v) => !v)}>
                <Plus className="mr-2 h-4 w-4" />
                New change request
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {showCrForm && (
                <div className="rounded-md border border-border p-4">
                  <ChangeRequestForm
                    baselines={baselines ?? []}
                    onSubmit={(values) =>
                      createChangeRequest.mutate(values, { onSuccess: () => setShowCrForm(false) })
                    }
                    onCancel={() => setShowCrForm(false)}
                    isSubmitting={createChangeRequest.isPending}
                  />
                  {createChangeRequest.isError && (
                    <p className="mt-3 text-sm text-destructive">
                      {(createChangeRequest.error as Error)?.message}
                    </p>
                  )}
                </div>
              )}

              {!changeRequests || changeRequests.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No change requests have been registered for this project yet.
                </p>
              ) : (
                <ul className="max-h-96 space-y-3 overflow-y-auto pr-1">
                  {changeRequests.map((cr) => (
                    <ChangeRequestCard
                      key={cr.id}
                      cr={cr}
                      baselines={baselines ?? []}
                      isEditing={editingCrId === cr.id}
                      onEdit={() => setEditingCrId(cr.id)}
                      onCancelEdit={() => setEditingCrId(null)}
                      onSaveEdit={(values) =>
                        updateChangeRequest.mutate(
                          { id: cr.id, payload: values },
                          { onSuccess: () => setEditingCrId(null) }
                        )
                      }
                      onApprove={() =>
                        updateChangeRequest.mutate({ id: cr.id, payload: { status: "approved" } })
                      }
                      onReject={() =>
                        updateChangeRequest.mutate({ id: cr.id, payload: { status: "rejected" } })
                      }
                      onMarkApplied={() =>
                        updateChangeRequest.mutate({ id: cr.id, payload: { status: "applied" } })
                      }
                      onDelete={() => setPendingDeleteCrId(cr.id)}
                      isMutating={updateChangeRequest.isPending || deleteChangeRequest.isPending}
                    />
                  ))}
                </ul>
              )}
              {(updateChangeRequest.isError || deleteChangeRequest.isError) && (
                <p className="text-sm text-destructive">
                  {((updateChangeRequest.error ?? deleteChangeRequest.error) as Error)?.message}
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="border-amber-200 bg-amber-50/50 dark:border-amber-800 dark:bg-amber-950/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Kanban className="h-5 w-5" />
                Kanboard cleanup
              </CardTitle>
              <CardDescription>
                Close all Kanboard cards linked to this project's tasks and clear their links.
                Use this at the end of a delivery phase so the next phase starts with a clean board.
                Tasks can be re-synced to Kanboard individually after cleanup.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {cleanupResult && (
                <div className="rounded-md border bg-card p-3 text-sm">
                  <p>
                    Closed <span className="font-semibold">{cleanupResult.closed}</span> card
                    {cleanupResult.closed !== 1 ? "s" : ""}, skipped{" "}
                    <span className="font-semibold">{cleanupResult.skipped}</span>.
                  </p>
                  {cleanupResult.errors.length > 0 && (
                    <ul className="mt-2 space-y-1 text-destructive">
                      {cleanupResult.errors.map((e, i) => (
                        <li key={i}>{e}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {kanboardCleanup.isError && (
                <p className="text-sm text-destructive">
                  {(kanboardCleanup.error as Error)?.message}
                </p>
              )}
              <Button
                variant="outline"
                className="border-amber-400 text-amber-700 hover:bg-amber-100 dark:border-amber-600 dark:text-amber-400"
                disabled={kanboardCleanup.isPending}
                onClick={() =>
                  kanboardCleanup.mutate(project!.id, {
                    onSuccess: (data) => setCleanupResult(data),
                  })
                }
              >
                {kanboardCleanup.isPending && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Close all Kanboard cards for this project
              </Button>
            </CardContent>
          </Card>

          <EntityDocsCard entityType="project" entityId={project.id} />

          <div>
            <Link to="/projects" className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to list
            </Link>
          </div>
        </>
      )}

      <ConfirmDialog
        open={pendingDeletePlanningId !== null}
        title="Delete planning item?"
        description="This will permanently delete the planning item and all of its tasks. This action cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDeletePlanningId)
            deletePlanningItem.mutate({ id: pendingDeletePlanningId, cascadeTasks: true });
          setPendingDeletePlanningId(null);
        }}
        onCancel={() => setPendingDeletePlanningId(null)}
      />

      <ConfirmDialog
        open={pendingDeleteCrId !== null}
        title="Delete change request?"
        description="This change request will be permanently deleted. This action cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {
          if (pendingDeleteCrId) deleteChangeRequest.mutate(pendingDeleteCrId);
          setPendingDeleteCrId(null);
        }}
        onCancel={() => setPendingDeleteCrId(null)}
      />
    </div>
  );
}
