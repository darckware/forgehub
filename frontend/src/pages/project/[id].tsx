import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowLeft,
  CheckSquare,
  ListTodo,
  Loader2,
  Hash,
  Pencil,
  Plus,
  Settings,
  SquareTerminal,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ProjectFileBrowser } from "@/components/ProjectFileBrowser";
import {
  useProject,
  useUpdateProject,
  type ProjectCreateInput,
} from "@/hooks/useProject";
import { useProductVersion } from "@/hooks/useProduct";
import { usePlanningItems } from "@/hooks/useBacklog";
import { useTasks, type ProjectTask } from "@/hooks/useTask";
import { EntityDocsCard } from "@/components/EntityDocsCard";
import { ProjectForm } from "./ProjectForm";

export default function ProjectDetailPage() {
  const { t } = useTranslation("project");
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: project, isLoading, isError, error } = useProject(id);
  const { data: productVersion } = useProductVersion(project?.product_version_id ?? undefined);
  const updateProject = useUpdateProject(id ?? "");
  const { data: allPlanningItems, isLoading: isLoadingPlanning } = usePlanningItems();
  const { data: allTasks } = useTasks();

  const [editingPath, setEditingPath] = useState(false);
  const [pathDraft, setPathDraft] = useState("");
  const [showEditForm, setShowEditForm] = useState(false);

  // Filter planning items and tasks for this specific project
  const projectPlanningItems = useMemo(() => {
    if (!id || !allPlanningItems) return [];
    return allPlanningItems.filter((item) => item.project_id === id);
  }, [id, allPlanningItems]);

  const tasksByPlanningItem = useMemo(() => {
    const map = new Map<string, ProjectTask[]>();
    for (const task of allTasks ?? []) {
      if (task.planning_item_id) {
        const existing = map.get(task.planning_item_id) || [];
        existing.push(task);
        map.set(task.planning_item_id, existing);
      }
    }
    return map;
  }, [allTasks]);

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
          <div className="flex flex-col gap-3 border-b pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <Settings className="h-5 w-5 text-primary" />
                <h1 className="text-2xl font-bold tracking-tight">Configurações do Projeto: {project.name}</h1>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {project.description || "Gerencie configurações de repositório, diretório de trabalho e especificações do projeto."}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs capitalize">
                {t(`enums.projectStatus.${project.status}`, project.status)}
              </Badge>
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => setShowEditForm((v) => !v)}
              >
                <Pencil className="mr-1.5 h-3.5 w-3.5" />
                {showEditForm ? t("shared.cancel") : t("shared.edit")}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => navigate("/workspace", { state: { openChannel: { projectId: project.id } } })}
              >
                <Hash className="mr-1.5 h-3.5 w-3.5" />
                {t("detail.openChannel")}
              </Button>
              <Link
                to={`/projects?view=project_detail&project_id=${project.id}`}
                className={buttonVariants({ variant: "default", size: "sm" }) + " text-xs gap-1.5"}
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Voltar à Central de Backlog
              </Link>
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
            {/* Card de Planejamentos e Tarefas do Projeto */}
            <Card className="flex flex-col">
              <CardHeader className="flex flex-row items-center justify-between pb-3">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base font-semibold">
                    <ListTodo className="h-4 w-4 text-primary" />
                    Itens de Planejamento & Backlog
                    {projectPlanningItems && (
                      <span className="text-xs font-normal text-muted-foreground">
                        ({projectPlanningItems.length})
                      </span>
                    )}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Planejamentos e features vinculados a este projeto.
                  </CardDescription>
                </div>
                <Link
                  to={`/projects?view=project_detail&project_id=${project.id}`}
                  className={buttonVariants({ variant: "outline", size: "sm" }) + " text-xs gap-1.5 h-8"}
                >
                  <ListTodo className="h-3.5 w-3.5" />
                  Gerenciar Backlog
                </Link>
              </CardHeader>
              <CardContent className="flex-1 space-y-3">
                {isLoadingPlanning ? (
                  <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> Carregando planejamentos...
                  </div>
                ) : !projectPlanningItems || projectPlanningItems.length === 0 ? (
                  <div className="rounded-md border border-dashed p-4 text-center">
                    <p className="text-xs italic text-muted-foreground">
                      Nenhum item de planejamento cadastrado para este projeto.
                    </p>
                    <Link
                      to={`/projects?view=project_detail&project_id=${project.id}`}
                      className="mt-2 inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium"
                    >
                      <Plus className="h-3 w-3" /> Criar planejamento na Central de Backlog
                    </Link>
                  </div>
                ) : (
                  <div className="max-h-72 space-y-2 overflow-y-auto pr-1">
                    {projectPlanningItems.map((item) => {
                      const tasks = tasksByPlanningItem.get(item.id) ?? [];
                      const doneTasks = tasks.filter((t) => t.status === "done" || t.status === "deployed").length;
                      return (
                        <div
                          key={item.id}
                          className="flex flex-col gap-1 rounded-md border p-2.5 text-xs hover:bg-accent/40 transition-colors"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <Badge variant="outline" className="text-[10px] capitalize shrink-0 font-normal">
                                {item.item_type}
                              </Badge>
                              <span className="font-semibold truncate text-foreground">{item.title}</span>
                            </div>
                            <Badge variant="secondary" className="text-[10px] capitalize shrink-0">
                              {item.status}
                            </Badge>
                          </div>
                          {item.description && (
                            <p className="text-muted-foreground line-clamp-1 text-[11px]">{item.description}</p>
                          )}
                          <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground border-t mt-1">
                            <span className="flex items-center gap-1">
                              <CheckSquare className="h-3 w-3 text-emerald-500" />
                              {tasks.length === 0
                                ? "Sem tarefas vinculadas"
                                : `${doneTasks}/${tasks.length} tarefas concluídas`}
                            </span>
                            {item.output_path && (
                              <span className="font-mono text-[10px] truncate max-w-[140px]" title={item.output_path}>
                                {item.output_path}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Card da Versão do Produto */}
            <Card className="flex flex-col">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base font-semibold">
                  <Badge variant="outline" className="h-5 w-5 rounded-full p-0 flex items-center justify-center text-[10px]">v</Badge>
                  {t("detail.productVersionTitle")}
                </CardTitle>
                <CardDescription className="text-xs">{t("detail.productVersionDescription")}</CardDescription>
              </CardHeader>
              <CardContent className="flex-1 space-y-3">
                {project.product_version_id ? (
                  productVersion ? (
                    <div className="rounded-md border p-3 bg-muted/20 space-y-2 text-xs">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-sm text-foreground">Versão {productVersion.version}</span>
                        <Badge variant="outline" className="capitalize text-[10px]">
                          {t(`enums.productVersionStatus.${productVersion.status}`, productVersion.status)}
                        </Badge>
                      </div>
                      {productVersion.release_notes && (
                        <div className="text-muted-foreground pt-1 border-t text-[11px]">
                          <p className="font-medium text-foreground mb-0.5">Notas da versão:</p>
                          <p className="line-clamp-3">{productVersion.release_notes}</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {t("detail.loadingVersion")}
                    </div>
                  )
                ) : (
                  <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground italic">
                    {t("detail.noProductVersionLinked")}
                  </div>
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

          <EntityDocsCard entityType="project" entityId={project.id} />

          <div>
            <Link to="/projects" className={buttonVariants({ variant: "outline" })}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              {t("detail.backToList")}
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
