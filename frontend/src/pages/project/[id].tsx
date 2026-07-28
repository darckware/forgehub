import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import {
  AlertCircle,
  Archive,
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
  SquareTerminal,
  Trash2,
  Unlock,
  XCircle,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ProjectFileBrowser } from "@/components/ProjectFileBrowser";
import { useBackupListing, useDeleteBackup, useRunBackup } from "@/hooks/useSystemControl";
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
import { ProjectMcpServerManager } from "@/components/mcp/ProjectMcpServerManager";
import { useProjectMcpServers } from "@/hooks/useProjectMcp";
import { ProjectForm } from "./ProjectForm";
import { StructureNodeForm } from "./StructureNodeForm";
import { ProjectPlanForm } from "./ProjectPlanForm";
import { ChangeRequestForm } from "./ChangeRequestForm";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ProjectAutomationCard } from "@/components/ProjectAutomationCard";

const CHANGE_REQUEST_STATUS_VARIANT: Record<string, "outline" | "success" | "destructive" | "secondary"> = {
  pending: "outline",
  approved: "success",
  rejected: "destructive",
  applied: "secondary",
};

const CHANGE_REQUEST_IMPACT_KEYS: Record<string, string> = {
  affects_scope: "detail.changeRequestImpact.scope",
  affects_schedule: "detail.changeRequestImpact.schedule",
  affects_cost: "detail.changeRequestImpact.cost",
  adds_features: "detail.changeRequestImpact.addsFeatures",
  removes_features: "detail.changeRequestImpact.removesFeatures",
  introduces_critical_bug_fix: "detail.changeRequestImpact.criticalBugFix",
  changes_agents: "detail.changeRequestImpact.agents",
  changes_skills: "detail.changeRequestImpact.skills",
  changes_architecture: "detail.changeRequestImpact.architecture",
  changes_security: "detail.changeRequestImpact.security",
};

function changeRequestImpactKeys(cr: ChangeRequest): string[] {
  return Object.entries(CHANGE_REQUEST_IMPACT_KEYS)
    .filter(([key]) => Boolean(cr[key as keyof ChangeRequest]))
    .map(([, key]) => key);
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
  const { t } = useTranslation("project");
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
          submitLabel={t("detail.saveChanges")}
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
                {t(`enums.changeRequestStatus.${cr.status}`, cr.status)}
              </Badge>
              {taskCount > 0 && (
                <Badge variant="secondary" className="gap-1 text-[10px]">
                  <ListTodo className="h-3 w-3" />
                  {t("detail.changeRequestCard.taskCount", { count: taskCount })}
                </Badge>
              )}
            </div>
            {cr.justification && (
              <p className="text-muted-foreground">{cr.justification}</p>
            )}
            <div className="flex flex-wrap gap-1">
              {changeRequestImpactKeys(cr).map((key) => (
                <Badge key={key} variant="secondary" className="text-[10px]">
                  {t(key)}
                </Badge>
              ))}
            </div>
            <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
              {cr.schedule_delta_days != null && (
                <span>{t("detail.changeRequestCard.scheduleDelta", { days: cr.schedule_delta_days })}</span>
              )}
              {cr.cost_delta != null && (
                <span>{t("detail.changeRequestCard.costDelta", { cost: cr.cost_delta })}</span>
              )}
              {cr.requested_by && (
                <span>{t("detail.changeRequestCard.requestedBy", { name: cr.requested_by })}</span>
              )}
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
                  aria-label={t("detail.changeRequestCard.approveAria", { title: cr.title })}
                  onClick={onApprove}
                >
                  <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={isMutating}
                  aria-label={t("detail.changeRequestCard.rejectAria", { title: cr.title })}
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
                {t("detail.changeRequestCard.markApplied")}
              </Button>
            )}

            {/* Edit */}
            {cr.status !== "applied" && (
              <Button
                variant="ghost"
                size="icon"
                disabled={isMutating}
                aria-label={t("detail.changeRequestCard.editAria", { title: cr.title })}
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
                aria-label={t("detail.changeRequestCard.deleteAria", { title: cr.title })}
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

function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(1)} MB`;
  return `${(mb / 1024).toFixed(1)} GB`;
}

/** This project's own backup archives -- kept in their own directory,
 * separate from Hermes's and every other project's (see System Control's
 * Backups card / backend/app/api/routes/system_control.py). Only rendered
 * when the project has backup_enabled. */
function ProjectBackups({
  projectId,
  projectName,
  workingDirectoryPath,
}: {
  projectId: string;
  projectName: string;
  workingDirectoryPath: string | null | undefined;
}) {
  const { t } = useTranslation("project");
  const target = `project:${projectId}`;
  const { data: listing, isLoading } = useBackupListing(target);
  const runBackup = useRunBackup();
  const deleteBackup = useDeleteBackup();
  const [deletingBackup, setDeletingBackup] = useState<string | null>(null);

  return (
    <div className="space-y-2 border-t border-border pt-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{t("detail.backups.title", { name: projectName })}</span>
        <Button
          size="sm"
          variant="outline"
          className="gap-2"
          onClick={() => runBackup.mutate({ target })}
          disabled={runBackup.isPending}
        >
          {runBackup.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Archive className="h-3.5 w-3.5" />}
          {t("detail.backups.backupNow")}
        </Button>
      </div>
      {listing?.path && (
        <p className="font-mono text-xs text-muted-foreground">
          {workingDirectoryPath ?? t("detail.backups.noWorkingDirectorySet")} → {listing.path}
        </p>
      )}
      {runBackup.isError && (
        <p className="text-xs text-destructive">
          {(runBackup.error as Error)?.message ?? t("detail.backups.backupFailed")}
        </p>
      )}
      {deleteBackup.isError && (
        <p className="text-xs text-destructive">
          {(deleteBackup.error as Error)?.message ?? t("detail.backups.deleteBackupFailed")}
        </p>
      )}
      <ConfirmDialog
        open={deletingBackup !== null}
        title={t("detail.backups.deleteDialogTitle", { name: deletingBackup ?? "" })}
        description={t("detail.backups.deleteDialogDescription")}
        loading={deleteBackup.isPending}
        onConfirm={() => {
          if (deletingBackup) {
            deleteBackup.mutate({ target, filename: deletingBackup }, { onSuccess: () => setDeletingBackup(null) });
          }
        }}
        onCancel={() => setDeletingBackup(null)}
      />
      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> {t("detail.backups.loadingArchives")}
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("detail.backups.archiveColumn")}</TableHead>
              <TableHead>{t("detail.backups.sizeColumn")}</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {(listing?.entries ?? []).map((entry) => (
              <TableRow key={entry.path}>
                <TableCell className="font-mono text-xs">{entry.name}</TableCell>
                <TableCell>{formatBytes(entry.size)}</TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive"
                    aria-label={t("detail.backups.deleteArchiveAria", { name: entry.name })}
                    onClick={() => setDeletingBackup(entry.name)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {(listing?.entries ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-xs text-muted-foreground">
                  {t("detail.backups.noBackupArchives")}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

export default function ProjectDetailPage() {
  const { t } = useTranslation("project");
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: project, isLoading, isError, error } = useProject(id);
  const { data: productVersion } = useProductVersion(project?.product_version_id ?? undefined);
  const { data: structureNodes } = useStructureNodes(id);
  const { data: projectMcpServers, isLoading: projectMcpLoading } = useProjectMcpServers(id);
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
      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("detail.loadingProject")}
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
                {t(`enums.projectStatus.${project.status}`, project.status)}
              </Badge>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowEditForm((v) => !v)}
              >
                <Pencil className="mr-2 h-4 w-4" />
                {t("shared.edit")}
              </Button>
            </div>
          </div>

          {showEditForm && (
            <Card>
              <CardHeader>
                <CardTitle>{t("detail.editProjectCardTitle")}</CardTitle>
                <CardDescription>{t("detail.editProjectCardDescription")}</CardDescription>
              </CardHeader>
              <CardContent>
                <ProjectForm
                  defaultValues={{
                    name: project.name,
                    description: project.description ?? "",
                    product_version_id: project.product_version_id ?? "",
                    status: project.status as ProjectCreateInput["status"],
                    working_directory_path: project.working_directory_path ?? "",
                    github_repo_url: project.github_repo_url ?? "",
                    backup_enabled: project.backup_enabled,
                    backup_location: project.backup_location ?? "",
                  }}
                  onSubmit={handleUpdate}
                  onCancel={() => setShowEditForm(false)}
                  isSubmitting={updateProject.isPending}
                  submitLabel={t("detail.saveChanges")}
                />
                {updateProject.isError && (
                  <p className="mt-3 text-sm text-destructive">
                    {t("detail.updateProjectError", { message: (updateProject.error as Error)?.message })}
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
                    {t("detail.projectPlanTitle")}
                  </CardTitle>
                  <CardDescription>{t("detail.projectPlanDescription")}</CardDescription>
                </div>
                {!latestPlan && (
                  <Button variant="outline" size="sm" onClick={() => setShowPlanForm((v) => !v)}>
                    <Plus className="mr-2 h-4 w-4" />
                    {t("detail.createPlanButton")}
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
                        {t(`enums.projectPlanStatus.${latestPlan.status}`, latestPlan.status)}
                      </Badge>
                    </div>
                    {latestPlan.scope_summary && (
                      <div>
                        <dt className="font-medium text-muted-foreground">{t("detail.scopeLabel")}</dt>
                        <dd>{latestPlan.scope_summary}</dd>
                      </div>
                    )}
                    <div className="flex items-center gap-2 text-muted-foreground">
                      <CalendarRange className="h-4 w-4" />
                      <span>
                        {latestPlan.estimated_start_date ?? t("detail.noStartDate")} →{" "}
                        {latestPlan.estimated_end_date ?? t("detail.noTargetDate")}
                      </span>
                    </div>
                    {latestPlan.estimated_cost != null && (
                      <div>
                        <dt className="font-medium text-muted-foreground">{t("detail.estimatedCostLabel")}</dt>
                        <dd>{latestPlan.estimated_cost}</dd>
                      </div>
                    )}

                    {latestPlan.status === "draft" && (
                      <Button
                        size="sm"
                        disabled={approveProjectPlan.isPending}
                        onClick={() => approveProjectPlan.mutate(latestPlan.id)}
                      >
                        {t("detail.approvePlanButton")}
                      </Button>
                    )}

                    {latestPlan.status === "approved" && !showBaselineForm && (
                      <Button size="sm" onClick={() => setShowBaselineForm(true)}>
                        {t("detail.freezeBaselineButton")}
                      </Button>
                    )}

                    {showBaselineForm && (
                      <div className="flex items-center gap-2">
                        <Input
                          value={baselineNameDraft}
                          onChange={(e) => setBaselineNameDraft(e.target.value)}
                          placeholder={t("detail.baselineNamePlaceholder")}
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
                          {t("shared.save")}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setShowBaselineForm(false)}>
                          {t("shared.cancel")}
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
                        <dt className="font-medium text-muted-foreground">{t("detail.baselineHistoryLabel")}</dt>
                        <ul className="space-y-1">
                          {baselines.map((baseline) => (
                            <li
                              key={baseline.id}
                              className="rounded-md border border-border p-2 text-xs"
                            >
                              <span className="font-medium">{baseline.name}</span>{" "}
                              <span className="text-muted-foreground">
                                {t("detail.frozenAt", { date: new Date(baseline.frozen_at).toLocaleString() })}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </dl>
                ) : (
                  !showPlanForm && (
                    <p className="text-sm text-muted-foreground">{t("detail.noPlanYet")}</p>
                  )
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-xl">{t("detail.productVersionTitle")}</CardTitle>
                <CardDescription>{t("detail.productVersionDescription")}</CardDescription>
              </CardHeader>
              <CardContent>
                {project.product_version_id ? (
                  productVersion ? (
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-medium">{productVersion.version}</span>
                      <Badge variant="outline" className="capitalize">
                        {t(`enums.productVersionStatus.${productVersion.status}`, productVersion.status)}
                      </Badge>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">{t("detail.loadingVersion")}</p>
                  )
                ) : (
                  <p className="text-sm italic text-muted-foreground">{t("detail.noProductVersionLinked")}</p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-xl">{t("detail.workingDirectoryTitle")}</CardTitle>
                <CardDescription>{t("detail.workingDirectoryDescription")}</CardDescription>
              </div>
              {!editingPath && (
                <div className="flex items-center gap-2">
                  {project.working_directory_path && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        navigate("/workspace", {
                          state: {
                            openTerminal: { label: project.name, cwd: project.working_directory_path },
                          },
                        })
                      }
                    >
                      <SquareTerminal className="mr-2 h-4 w-4" />
                      {t("detail.openTerminalHere")}
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setPathDraft(project.working_directory_path ?? "");
                      setEditingPath(true);
                    }}
                  >
                    <Pencil className="mr-2 h-4 w-4" />
                    {t("shared.edit")}
                  </Button>
                </div>
              )}
            </CardHeader>
            <CardContent>
              {editingPath ? (
                <div className="flex items-center gap-2">
                  <Input
                    value={pathDraft}
                    onChange={(e) => setPathDraft(e.target.value)}
                    placeholder={t("detail.workingDirectoryPlaceholder")}
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
                    {t("shared.save")}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setEditingPath(false)}>
                    {t("shared.cancel")}
                  </Button>
                </div>
              ) : (
                <p className="text-sm">
                  {project.working_directory_path ?? (
                    <span className="italic text-muted-foreground">{t("detail.notSet")}</span>
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

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">{t("detail.mcpServersTitle")}</CardTitle>
              <CardDescription>{t("detail.mcpServersDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <ProjectMcpServerManager
                projectId={project.id}
                servers={projectMcpServers}
                isLoading={projectMcpLoading}
                workingDirectoryPath={project.working_directory_path ?? null}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">{t("detail.githubBackupsTitle")}</CardTitle>
              <CardDescription>{t("detail.githubBackupsDescription")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{t("detail.githubRepoLabel")}</span>
                {project.github_repo_url ? (
                  <a
                    href={project.github_repo_url}
                    target="_blank"
                    rel="noreferrer"
                    className="truncate font-mono text-xs text-primary hover:underline"
                  >
                    {project.github_repo_url}
                  </a>
                ) : (
                  <span className="italic text-muted-foreground">{t("detail.notSet")}</span>
                )}
              </div>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{t("detail.backupLabel")}</span>
                <Badge variant={project.backup_enabled ? "success" : "outline"}>
                  {project.backup_enabled ? t("detail.backupEnabledBadge") : t("detail.backupDisabledBadge")}
                </Badge>
              </div>
              {project.backup_enabled && (
                <ProjectBackups
                  projectId={project.id}
                  projectName={project.name}
                  workingDirectoryPath={project.working_directory_path}
                />
              )}
            </CardContent>
          </Card>

          {project.working_directory_path && (
            <Card>
              <CardHeader>
                <CardTitle className="text-xl">{t("detail.filesTitle")}</CardTitle>
                <CardDescription>{t("detail.filesDescription")}</CardDescription>
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
                  {t("detail.structureTitle")}
                </CardTitle>
                <CardDescription>{t("detail.structureDescription")}</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={() => setShowNodeForm((v) => !v)}>
                <Plus className="mr-2 h-4 w-4" />
                {t("detail.addNodeButton")}
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
                    submitLabel={t("detail.createNodeLabel")}
                  />
                  {createStructureNode.isError && (
                    <p className="mt-3 text-sm text-destructive">
                      {(createStructureNode.error as Error)?.message}
                    </p>
                  )}
                </div>
              )}

              {!structureNodes || structureNodes.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("detail.noStructureNodes")}</p>
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
                          {t(`enums.structureNodeType.${node.node_type}`, node.node_type)}
                        </Badge>
                        {node.path && (
                          <p className="font-mono text-xs text-muted-foreground">{node.path}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-1">
                        {node.is_locked && (
                          <Badge variant="outline" className="gap-1">
                            <Lock className="h-3 w-3" />
                            {t("detail.lockedBadge")}
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
                          aria-label={
                            node.is_locked
                              ? t("detail.unlockAria", { name: node.name })
                              : t("detail.lockAria", { name: node.name })
                          }
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
                          aria-label={t("detail.deleteNodeAria", { name: node.name })}
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
                  {t("detail.changeRequestsTitle")}
                </CardTitle>
                <CardDescription>{t("detail.changeRequestsDescription")}</CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={() => setShowCrForm((v) => !v)}>
                <Plus className="mr-2 h-4 w-4" />
                {t("detail.newChangeRequestButton")}
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
                <p className="text-sm text-muted-foreground">{t("detail.noChangeRequests")}</p>
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
                {t("detail.kanboardCleanupTitle")}
              </CardTitle>
              <CardDescription>{t("detail.kanboardCleanupDescription")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {cleanupResult && (
                <div className="rounded-md border bg-card p-3 text-sm">
                  <p>
                    <Trans
                      t={t}
                      i18nKey="detail.kanboardCleanupResult"
                      count={cleanupResult.closed}
                      values={{ closed: cleanupResult.closed, skipped: cleanupResult.skipped }}
                      components={{ b: <span className="font-semibold" /> }}
                    />
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
                {t("detail.closeKanboardCardsButton")}
              </Button>
            </CardContent>
          </Card>

          <ProjectAutomationCard projectId={project.id} />

          <EntityDocsCard entityType="project" entityId={project.id} />

          <div>
            <Link to="/projects" className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              {t("detail.backToList")}
            </Link>
          </div>
        </>
      )}

      <ConfirmDialog
        open={pendingDeletePlanningId !== null}
        title={t("detail.deletePlanningItemTitle")}
        description={t("detail.deletePlanningItemDescription")}
        confirmLabel={t("shared.delete")}
        onConfirm={() => {
          if (pendingDeletePlanningId)
            deletePlanningItem.mutate({ id: pendingDeletePlanningId, cascadeTasks: true });
          setPendingDeletePlanningId(null);
        }}
        onCancel={() => setPendingDeletePlanningId(null)}
      />

      <ConfirmDialog
        open={pendingDeleteCrId !== null}
        title={t("detail.deleteChangeRequestTitle")}
        description={t("detail.deleteChangeRequestDescription")}
        confirmLabel={t("shared.delete")}
        onConfirm={() => {
          if (pendingDeleteCrId) deleteChangeRequest.mutate(pendingDeleteCrId);
          setPendingDeleteCrId(null);
        }}
        onCancel={() => setPendingDeleteCrId(null)}
      />
    </div>
  );
}
