import { useMemo, useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowRight,
  CheckSquare,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  FolderKanban,
  FolderOpen,
  Layout,
  ListTodo,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useCreateProject,
  useDeleteProject,
  useProjects,
  type Project,
  type ProjectCreateInput,
} from "@/hooks/useProject";
import { useProducts } from "@/hooks/useProduct";
import {
  useCreatePlanningItem,
  useDeletePlanningItem,
  usePlanningItems,
  useUpdatePlanningItem,
  type PlanningItem,
  type PlanningItemCreateInput,
} from "@/hooks/useBacklog";
import {
  useCreateTask,
  useDeleteTask,
  useTasks,
  useUpdateTask,
  type ProjectTask,
  type TaskCreateInput,
} from "@/hooks/useTask";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ProjectForm } from "./ProjectForm";
import { PlanningItemForm } from "../backlog/PlanningItemForm";
import { TaskForm } from "../task/TaskForm";
import { ExecutionWaveBoard } from "@/components/ExecutionWaveBoard";

const PROJECT_STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  planned: "outline",
  active: "success",
  on_hold: "warning",
  completed: "secondary",
  cancelled: "destructive",
};

const PLANNING_ITEM_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  feature: { label: "Feature", color: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30" },
  bug: { label: "Bug", color: "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30" },
  hotfix: { label: "Hotfix", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  improvement: { label: "Melhoria", color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30" },
  technical_debt: { label: "Débito Técnico", color: "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30" },
  refactoring: { label: "Refatoração", color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/30" },
  security_fix: { label: "Segurança", color: "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30" },
  research: { label: "Pesquisa", color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/30" },
  documentation: { label: "Documentação", color: "bg-zinc-500/10 text-zinc-600 dark:text-zinc-400 border-zinc-500/30" },
};

const STATUS_CATEGORIES = {
  all: "Todos",
  open: "Abertos",
  in_progress: "Em Execução",
  done: "Finalizados",
  blocked_error: "Com Bloqueio / Erro",
} as const;

type StatusCategoryKey = keyof typeof STATUS_CATEGORIES;

function getStatusCategory(status: string): StatusCategoryKey {
  if (status === "done") return "done";
  if (status === "in_progress") return "in_progress";
  if (status === "blocked" || status === "rejected") return "blocked_error";
  return "open";
}

const TASK_STATUS_COLORS: Record<string, string> = {
  planned: "bg-muted text-muted-foreground border-border",
  ready: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30",
  assigned: "bg-blue-500/10 text-blue-700 dark:text-blue-300 border-blue-500/30",
  in_progress: "bg-sky-500/15 text-sky-700 dark:text-sky-300 border-sky-500/40 font-semibold",
  blocked: "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/40",
  done: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40",
  deployed: "bg-teal-500/15 text-teal-700 dark:text-teal-300 border-teal-500/40 font-bold",
  cancelled: "bg-zinc-500/10 text-zinc-500 border-zinc-500/30 line-through",
};

export default function ProjectCentralPage() {
  const { t } = useTranslation("project");
  const [searchParams, setSearchParams] = useSearchParams();

  const activeViewTab = searchParams.get("view") || "project_detail";
  const requestedProjectId = searchParams.get("project_id");

  const { data: projects, isLoading: isLoadingProjects } = useProjects();
  const { data: products } = useProducts();
  const { data: allPlanningItems, isLoading: isLoadingPlanning } = usePlanningItems();
  const { data: allTasks, isLoading: isLoadingTasks } = useTasks();

  const createProject = useCreateProject();
  const deleteProject = useDeleteProject();

  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [showCreateProjectModal, setShowCreateProjectModal] = useState(false);
  const [pendingDeleteProjectId, setPendingDeleteProjectId] = useState<string | null>(null);

  // Sync selected project with list or search params
  useEffect(() => {
    if (projects && projects.length > 0) {
      if (requestedProjectId && projects.some((p) => p.id === requestedProjectId)) {
        setSelectedProjectId(requestedProjectId);
      } else if (!selectedProjectId || !projects.some((p) => p.id === selectedProjectId)) {
        setSelectedProjectId(projects[0].id);
      }
    }
  }, [projects, requestedProjectId, selectedProjectId]);

  const activeProject = useMemo(
    () => projects?.find((p) => p.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );

  const activeProduct = useMemo(() => {
    if (!activeProject?.product_version_id || !products) return null;
    return products.find((prod) => prod.versions?.some((v) => v.id === activeProject.product_version_id)) ?? null;
  }, [activeProject, products]);

  const activeVersion = useMemo(() => {
    if (!activeProject?.product_version_id || !activeProduct) return null;
    return activeProduct.versions?.find((v) => v.id === activeProject.product_version_id) ?? null;
  }, [activeProject, activeProduct]);

  // Tasks map keyed by planning_item_id
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

  // Filter planning items for active project
  const projectPlanningItems = useMemo(() => {
    if (!selectedProjectId || !allPlanningItems) return [];
    return allPlanningItems.filter((item) => item.project_id === selectedProjectId);
  }, [selectedProjectId, allPlanningItems]);

  // Filter tasks belonging directly or indirectly to active project
  const projectTasks = useMemo(() => {
    if (!selectedProjectId || !allTasks) return [];
    return allTasks.filter((task) => task.project_id === selectedProjectId);
  }, [selectedProjectId, allTasks]);

  function handleCreateProject(values: ProjectCreateInput) {
    createProject.mutate(
      {
        ...values,
        description: values.description || undefined,
        working_directory_path: values.working_directory_path || undefined,
      },
      {
        onSuccess: (newProj) => {
          setShowCreateProjectModal(false);
          setSelectedProjectId(newProj.id);
          setSearchParams({ view: "project_detail", project_id: newProj.id });
        },
      }
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-4 border-b pb-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent flex items-center gap-2">
            <FolderKanban className="h-6 w-6 text-primary" />
            4. Central de Projetos & Backlog
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Selecione o projeto para estruturar itens de planejamento e acompanhar suas tarefas associadas.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {activeProject && (
            <Link
              to={`/projects/${activeProject.id}`}
              className="inline-flex items-center gap-1.5 text-xs rounded-md border border-input bg-background px-3 py-1.5 font-medium hover:bg-accent"
            >
              <Pencil className="h-4 w-4 text-primary" />
              Configurações do Projeto
            </Link>
          )}
          <Link
            to="/screen-inspector"
            className="inline-flex items-center gap-1.5 text-xs rounded-md border border-input bg-background px-3 py-1.5 font-medium hover:bg-accent"
          >
            <Layout className="h-4 w-4 text-primary" />
            Telas & Protótipos
          </Link>
        </div>
      </div>

      {/* Modal de Criação de Projeto */}
      {showCreateProjectModal && (
        <Card className="border-primary/40 bg-card shadow-lg">
          <CardHeader className="p-4 border-b">
            <CardTitle className="text-base font-semibold">{t("list.createCardTitle")}</CardTitle>
            <CardDescription className="text-xs">{t("list.createCardDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="p-4">
            <ProjectForm
              onSubmit={handleCreateProject}
              onCancel={() => setShowCreateProjectModal(false)}
              isSubmitting={createProject.isPending}
            />
            {createProject.isError && (
              <p className="mt-3 text-xs text-destructive">
                {t("list.createError", { message: (createProject.error as Error)?.message })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Navegação entre Abas Principais */}
      <Tabs
        value={activeViewTab}
        onValueChange={(val) => {
          setSearchParams({ view: val, ...(selectedProjectId ? { project_id: selectedProjectId } : {}) });
        }}
        className="space-y-6"
      >
        <TabsList className="grid grid-cols-3 max-w-xl bg-muted/60 p-1">
          <TabsTrigger value="project_detail" className="gap-2 text-xs">
            <ListTodo className="h-4 w-4 text-primary" />
            Planejamento & Tarefas
          </TabsTrigger>
          <TabsTrigger value="execution_board" className="gap-2 text-xs">
            <CheckSquare className="h-4 w-4 text-primary" />
            Quadro de Execução
          </TabsTrigger>
          <TabsTrigger value="all_projects" className="gap-2 text-xs">
            <FolderOpen className="h-4 w-4 text-primary" />
            Todos os Projetos ({projects?.length ?? 0})
          </TabsTrigger>
        </TabsList>

        {/* ================= ABA 1: PLANEJAMENTO & TAREFAS (MASTER-DETAIL) ================= */}
        <TabsContent value="project_detail" className="space-y-6">
          {isLoadingProjects ? (
            <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground text-sm">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              Carregando projetos...
            </div>
          ) : !projects || projects.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
                <FolderKanban className="h-10 w-10 text-muted-foreground/40" />
                <div>
                  <p className="font-semibold text-sm">Nenhum projeto cadastrado</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Projetos são gerados a partir da Fase 1 (Conception & Context) ao aprovar a ideia e criar o projeto.
                  </p>
                </div>
                <Link
                  to="/conception"
                  className={buttonVariants({ variant: "default", size: "sm" }) + " gap-1.5 text-xs"}
                >
                  <FolderKanban className="h-4 w-4" />
                  Ir para 1. Conception & Context
                </Link>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* Barra de Contexto do Projeto Ativo */}
              <Card className="border-primary/20 bg-muted/20">
                <CardContent className="p-4 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-3 flex-1">
                    <div className="min-w-[220px]">
                      <Label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                        Projeto Ativo
                      </Label>
                      <Select
                        value={selectedProjectId}
                        onChange={(e) => {
                          setSelectedProjectId(e.target.value);
                          setSearchParams({ view: "project_detail", project_id: e.target.value });
                        }}
                        className="h-9 text-xs font-semibold bg-background"
                      >
                        {projects.map((proj) => (
                          <option key={proj.id} value={proj.id}>
                            {proj.name}
                          </option>
                        ))}
                      </Select>
                    </div>

                    {activeProject && (
                      <div className="flex flex-wrap items-center gap-2 pt-1 sm:pt-4 text-xs">
                        <Badge variant={PROJECT_STATUS_VARIANT[activeProject.status] ?? "outline"} className="text-xs">
                          {t(`enums.projectStatus.${activeProject.status}`, activeProject.status)}
                        </Badge>
                        {activeProduct && activeVersion && (
                          <span className="rounded-md border bg-background/80 px-2 py-1 text-[11px] text-muted-foreground">
                            Produto: <strong className="text-foreground">{activeProduct.name}</strong> (v{activeVersion.version})
                          </span>
                        )}
                        <span className="rounded-md border bg-background/80 px-2 py-1 text-[11px] text-muted-foreground">
                          Planejamentos: <strong className="text-primary">{projectPlanningItems.length}</strong>
                        </span>
                        <span className="rounded-md border bg-background/80 px-2 py-1 text-[11px] text-muted-foreground">
                          Tarefas: <strong className="text-primary">{projectTasks.length}</strong>
                        </span>
                      </div>
                    )}
                  </div>

                  {activeProject && (
                    <div className="flex items-center gap-2 shrink-0 pt-2 lg:pt-0">
                      <Link
                        to={`/projects/${activeProject.id}`}
                        className={buttonVariants({ variant: "outline", size: "sm" }) + " text-xs gap-1.5"}
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        Detalhes do Projeto
                      </Link>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Painel Central de Planejamentos e Tarefas */}
              {activeProject && (
                <ProjectPlanningAndTasksManager
                  project={activeProject}
                  planningItems={projectPlanningItems}
                  tasksByPlanningItem={tasksByPlanningItem}
                  isLoading={isLoadingPlanning || isLoadingTasks}
                />
              )}
            </>
          )}
        </TabsContent>

        {/* ================= ABA 2: QUADRO DE EXECUÇÃO / TAREFAS ================= */}
        <TabsContent value="execution_board" className="space-y-6">
          {activeProject ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold flex items-center gap-2">
                    <CheckSquare className="h-4 w-4 text-primary" />
                    Quadro de Tarefas e Ondas de Execução ({activeProject.name})
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Acompanhe o estado de execução das tarefas do projeto.
                  </p>
                </div>
              </div>
              <ExecutionWaveBoard />
            </div>
          ) : (
            <Card>
              <CardContent className="py-12 text-center text-xs text-muted-foreground">
                Selecione um projeto para visualizar o quadro de execução.
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ================= ABA 3: CATÁLOGO DE TODOS OS PROJETOS ================= */}
        <TabsContent value="all_projects" className="space-y-6">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Lista consolidada de todos os projetos cadastrados no ambiente. A criação de novos projetos ocorre na Fase 1 (Conception & Context).
            </p>
            <Link
              to="/conception"
              className={buttonVariants({ variant: "outline", size: "sm" }) + " gap-1.5 text-xs font-semibold"}
            >
              <FolderKanban className="h-4 w-4 text-primary" />
              1. Conception & Context
            </Link>
          </div>

          {projects && projects.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {projects.map((proj) => {
                const projItems = allPlanningItems?.filter((i) => i.project_id === proj.id) ?? [];
                const projTasksList = allTasks?.filter((t) => t.project_id === proj.id) ?? [];
                return (
                  <Card key={proj.id} className="flex flex-col hover:border-primary/40 transition-colors">
                    <CardHeader className="p-4 pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-base leading-tight font-bold">{proj.name}</CardTitle>
                        <Badge variant={PROJECT_STATUS_VARIANT[proj.status] ?? "outline"} className="text-[10px]">
                          {t(`enums.projectStatus.${proj.status}`, proj.status)}
                        </Badge>
                      </div>
                      {proj.description && (
                        <CardDescription className="line-clamp-2 text-xs mt-1">{proj.description}</CardDescription>
                      )}
                    </CardHeader>
                    <CardContent className="p-4 pt-2 flex-1 space-y-2 text-xs text-muted-foreground">
                      <div className="flex items-center gap-3 pt-1">
                        <span className="inline-flex items-center gap-1 font-medium text-foreground">
                          <ListTodo className="h-3.5 w-3.5 text-primary" /> {projItems.length} planejamentos
                        </span>
                        <span className="inline-flex items-center gap-1 font-medium text-foreground">
                          <CheckSquare className="h-3.5 w-3.5 text-emerald-500" /> {projTasksList.length} tarefas
                        </span>
                      </div>
                    </CardContent>
                    <CardFooter className="p-4 pt-0 flex items-center justify-between border-t gap-2 bg-muted/10">
                      <Button
                        variant="default"
                        size="sm"
                        className="text-xs h-7 gap-1"
                        onClick={() => {
                          setSelectedProjectId(proj.id);
                          setSearchParams({ view: "project_detail", project_id: proj.id });
                        }}
                      >
                        Abrir Planejamento <ArrowRight className="h-3 w-3" />
                      </Button>
                      <div className="flex items-center gap-1">
                        <Link
                          to={`/projects/${proj.id}`}
                          className={buttonVariants({ variant: "ghost", size: "sm" }) + " text-xs h-7"}
                        >
                          Detalhes
                        </Link>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive"
                          onClick={() => setPendingDeleteProjectId(proj.id)}
                          title="Excluir projeto"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </CardFooter>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Diálogo de confirmação de exclusão */}
      <ConfirmDialog
        open={pendingDeleteProjectId !== null}
        title={t("list.deleteDialogTitle")}
        description={t("list.deleteDialogDescription")}
        confirmLabel={t("shared.delete")}
        onConfirm={() => {
          if (pendingDeleteProjectId) {
            deleteProject.mutate(pendingDeleteProjectId);
            if (selectedProjectId === pendingDeleteProjectId) {
              const remaining = projects?.filter((p) => p.id !== pendingDeleteProjectId);
              setSelectedProjectId(remaining?.[0]?.id ?? "");
            }
          }
          setPendingDeleteProjectId(null);
        }}
        onCancel={() => setPendingDeleteProjectId(null)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Gerenciador Unificado de Planejamentos e Tarefas do Projeto (Master-Detail)
// ---------------------------------------------------------------------------

interface ProjectPlanningAndTasksManagerProps {
  project: Project;
  planningItems: PlanningItem[];
  tasksByPlanningItem: Map<string, ProjectTask[]>;
  isLoading: boolean;
}

function ProjectPlanningAndTasksManager({
  project,
  planningItems,
  tasksByPlanningItem,
  isLoading,
}: ProjectPlanningAndTasksManagerProps) {
  const [statusFilter, setStatusFilter] = useState<StatusCategoryKey>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set());

  const [showNewPlanningForm, setShowNewPlanningForm] = useState(false);
  const [editingPlanningItem, setEditingPlanningItem] = useState<PlanningItem | null>(null);
  const [addingTaskForPlanningItemId, setAddingTaskForPlanningItemId] = useState<string | null>(null);
  const [editingTask, setEditingTask] = useState<ProjectTask | null>(null);

  const createPlanningItem = useCreatePlanningItem();
  const updatePlanningItem = useUpdatePlanningItem(editingPlanningItem?.id ?? "");
  const deletePlanningItem = useDeletePlanningItem();

  const createTask = useCreateTask();
  const updateTask = useUpdateTask(editingTask?.id ?? "");
  const deleteTask = useDeleteTask();

  // Filter planning items by status category and search term
  const filteredPlanningItems = useMemo(() => {
    return planningItems.filter((item) => {
      if (statusFilter !== "all" && getStatusCategory(item.status) !== statusFilter) {
        return false;
      }
      if (searchTerm.trim()) {
        const term = searchTerm.toLowerCase();
        const matchesTitle = item.title.toLowerCase().includes(term);
        const matchesDesc = item.description?.toLowerCase().includes(term);
        if (!matchesTitle && !matchesDesc) return false;
      }
      return true;
    });
  }, [planningItems, statusFilter, searchTerm]);

  // Status counts
  const counts = useMemo(() => {
    const res: Record<StatusCategoryKey, number> = {
      all: planningItems.length,
      open: 0,
      in_progress: 0,
      done: 0,
      blocked_error: 0,
    };
    for (const item of planningItems) {
      const cat = getStatusCategory(item.status);
      res[cat] = (res[cat] || 0) + 1;
    }
    return res;
  }, [planningItems]);

  const toggleExpand = (id: string) => {
    setExpandedItemIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => {
    setExpandedItemIds(new Set(filteredPlanningItems.map((i) => i.id)));
  };

  const collapseAll = () => {
    setExpandedItemIds(new Set());
  };

  function handleCreatePlanningItem(values: PlanningItemCreateInput) {
    createPlanningItem.mutate(
      {
        ...values,
        project_id: project.id,
        description: values.description || undefined,
        output_path: values.output_path || undefined,
      },
      {
        onSuccess: (created) => {
          setShowNewPlanningForm(false);
          setExpandedItemIds((prev) => new Set(prev).add(created.id));
        },
      }
    );
  }

  function handleUpdatePlanningItem(values: Partial<PlanningItemCreateInput>) {
    if (!editingPlanningItem) return;
    updatePlanningItem.mutate(
      {
        ...values,
        description: values.description || undefined,
      },
      {
        onSuccess: () => setEditingPlanningItem(null),
      }
    );
  }

  function handleCreateTask(values: TaskCreateInput) {
    createTask.mutate(
      {
        ...values,
        description: values.description || undefined,
        planned_end_date: values.planned_end_date || undefined,
      },
      {
        onSuccess: () => {
          setAddingTaskForPlanningItemId(null);
        },
      }
    );
  }

  function handleUpdateTask(values: Partial<TaskCreateInput>) {
    if (!editingTask) return;
    updateTask.mutate(
      {
        ...values,
        description: values.description || undefined,
        planned_end_date: values.planned_end_date || undefined,
      },
      {
        onSuccess: () => setEditingTask(null),
      }
    );
  }

  return (
    <div className="space-y-4">
      {/* Barra de Controles e Filtros de Status */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        {/* Pílulas de Status */}
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            size="sm"
            variant={statusFilter === "all" ? "default" : "outline"}
            className="h-8 text-xs gap-1.5"
            onClick={() => setStatusFilter("all")}
          >
            Todos <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.all}</Badge>
          </Button>
          <Button
            size="sm"
            variant={statusFilter === "open" ? "default" : "outline"}
            className="h-8 text-xs gap-1.5"
            onClick={() => setStatusFilter("open")}
          >
            <span className="h-2 w-2 rounded-full bg-amber-500" />
            Abertos <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.open}</Badge>
          </Button>
          <Button
            size="sm"
            variant={statusFilter === "in_progress" ? "default" : "outline"}
            className="h-8 text-xs gap-1.5"
            onClick={() => setStatusFilter("in_progress")}
          >
            <span className="h-2 w-2 rounded-full bg-sky-500" />
            Em Execução <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.in_progress}</Badge>
          </Button>
          <Button
            size="sm"
            variant={statusFilter === "done" ? "default" : "outline"}
            className="h-8 text-xs gap-1.5"
            onClick={() => setStatusFilter("done")}
          >
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Finalizados <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.done}</Badge>
          </Button>
          <Button
            size="sm"
            variant={statusFilter === "blocked_error" ? "default" : "outline"}
            className="h-8 text-xs gap-1.5"
            onClick={() => setStatusFilter("blocked_error")}
          >
            <span className="h-2 w-2 rounded-full bg-rose-500" />
            Com Bloqueio / Erro <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.blocked_error}</Badge>
          </Button>
        </div>

        {/* Busca e Ações Rápidas */}
        <div className="flex items-center gap-2">
          <div className="relative w-48 sm:w-60">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Buscar planejamentos..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-8 pl-8 text-xs"
            />
          </div>

          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs gap-1"
            onClick={() => {
              if (expandedItemIds.size > 0) collapseAll();
              else expandAll();
            }}
            title={expandedItemIds.size > 0 ? "Recolher todas as tarefas" : "Expandir todas as tarefas"}
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expandedItemIds.size > 0 ? "rotate-180" : ""}`} />
            {expandedItemIds.size > 0 ? "Recolher" : "Expandir Tarefas"}
          </Button>

          <Button
            size="sm"
            onClick={() => {
              setShowNewPlanningForm((v) => !v);
              setEditingPlanningItem(null);
            }}
            className="h-8 text-xs gap-1.5 font-semibold"
          >
            <Plus className="h-3.5 w-3.5" />
            Novo Planejamento
          </Button>
        </div>
      </div>

      {/* Formulário de Novo Item de Planejamento */}
      {showNewPlanningForm && (
        <Card className="border-primary/40 bg-card shadow-md">
          <CardHeader className="p-4 border-b">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Plus className="h-4 w-4 text-primary" />
              Novo Item de Planejamento para: <span className="text-primary">{project.name}</span>
            </CardTitle>
            <CardDescription className="text-xs">
              Cadastre uma feature, bug, refatoração ou melhoria para este projeto.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4">
            <PlanningItemForm
              defaultValues={{ project_id: project.id }}
              onSubmit={handleCreatePlanningItem}
              onCancel={() => setShowNewPlanningForm(false)}
              isSubmitting={createPlanningItem.isPending}
            />
          </CardContent>
        </Card>
      )}

      {/* Modal / Card de Edição de Item de Planejamento */}
      {editingPlanningItem && (
        <Card className="border-primary/40 bg-card shadow-md">
          <CardHeader className="p-4 border-b">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Pencil className="h-4 w-4 text-primary" />
              Editar Planejamento: {editingPlanningItem.title}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <PlanningItemForm
              defaultValues={{
                title: editingPlanningItem.title,
                description: editingPlanningItem.description ?? "",
                item_type: editingPlanningItem.item_type,
                status: editingPlanningItem.status,
                priority: editingPlanningItem.priority,
                project_id: project.id,
              }}
              onSubmit={handleUpdatePlanningItem}
              onCancel={() => setEditingPlanningItem(null)}
              isSubmitting={updatePlanningItem.isPending}
              submitLabel="Salvar Alterações"
            />
          </CardContent>
        </Card>
      )}

      {/* Modal / Card de Criação de Tarefa */}
      {addingTaskForPlanningItemId && (
        <Card className="border-emerald-500/40 bg-card shadow-md">
          <CardHeader className="p-4 border-b">
            <CardTitle className="text-sm font-semibold flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
              <Plus className="h-4 w-4" />
              Nova Tarefa de Execução
            </CardTitle>
            <CardDescription className="text-xs">
              Vinculada ao planejamento:{" "}
              <strong>{planningItems.find((i) => i.id === addingTaskForPlanningItemId)?.title}</strong>
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4">
            <TaskForm
              defaultValues={{
                planning_item_id: addingTaskForPlanningItemId,
              }}
              projectId={project.id}
              onSubmit={handleCreateTask}
              onCancel={() => setAddingTaskForPlanningItemId(null)}
              isSubmitting={createTask.isPending}
              submitLabel="Criar Tarefa"
            />
          </CardContent>
        </Card>
      )}

      {/* Modal / Card de Edição de Tarefa */}
      {editingTask && (
        <Card className="border-primary/40 bg-card shadow-md">
          <CardHeader className="p-4 border-b">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Pencil className="h-4 w-4 text-primary" />
              Editar Tarefa: {editingTask.title}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4">
            <TaskForm
              defaultValues={{
                title: editingTask.title,
                description: editingTask.description ?? "",
                plan_brief: editingTask.plan_brief ?? "",
                status: editingTask.status,
                priority: editingTask.priority,
                planning_item_id: editingTask.planning_item_id ?? "",
                planned_end_date: editingTask.planned_end_date ?? "",
              }}
              projectId={project.id}
              onSubmit={handleUpdateTask}
              onCancel={() => setEditingTask(null)}
              isSubmitting={updateTask.isPending}
              submitLabel="Salvar Tarefa"
            />
          </CardContent>
        </Card>
      )}

      {/* Lista de Itens de Planejamento */}
      {isLoading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground text-xs">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          Carregando planejamentos e tarefas do projeto...
        </div>
      ) : filteredPlanningItems.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center text-xs text-muted-foreground space-y-3">
            <ListTodo className="mx-auto h-8 w-8 text-muted-foreground/30" />
            <div>
              <p className="font-semibold text-sm text-foreground">
                {statusFilter === "all"
                  ? "Nenhum item de planejamento cadastrado para este projeto"
                  : `Nenhum planejamento no status "${STATUS_CATEGORIES[statusFilter]}"`}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Cadastre as features, correções e requisitos do projeto para gerar tarefas executáveis.
              </p>
            </div>
            <Button
              size="sm"
              onClick={() => setShowNewPlanningForm(true)}
              className="gap-1.5 text-xs"
            >
              <Plus className="h-3.5 w-3.5" />
              Adicionar Primeiro Planejamento
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredPlanningItems.map((item) => {
            const tasks = tasksByPlanningItem.get(item.id) || [];
            const isExpanded = expandedItemIds.has(item.id);
            const doneTasks = tasks.filter((t) => t.status === "done" || t.status === "deployed").length;
            const progressPercent = tasks.length > 0 ? Math.round((doneTasks / tasks.length) * 100) : 0;
            const typeInfo = PLANNING_ITEM_TYPE_LABELS[item.item_type] ?? {
              label: item.item_type,
              color: "bg-muted text-foreground border-border",
            };

            return (
              <Card
                key={item.id}
                className={`transition-all border-border/80 ${
                  isExpanded ? "ring-1 ring-primary/20 shadow-xs" : "hover:border-border"
                }`}
              >
                {/* Cabeçalho do Planejamento (Clicável para expandir) */}
                <div
                  className="p-4 cursor-pointer flex flex-col gap-3 md:flex-row md:items-center md:justify-between select-none"
                  onClick={() => toggleExpand(item.id)}
                >
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <button
                      type="button"
                      className="mt-0.5 p-1 rounded hover:bg-muted text-muted-foreground"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleExpand(item.id);
                      }}
                    >
                      <ChevronRight className={`h-4 w-4 transition-transform ${isExpanded ? "rotate-90 text-primary" : ""}`} />
                    </button>

                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${typeInfo.color}`}>
                          {typeInfo.label}
                        </span>

                        <Badge
                          variant={
                            item.status === "done"
                              ? "success"
                              : item.status === "in_progress"
                              ? "default"
                              : item.status === "blocked" || item.status === "rejected"
                              ? "destructive"
                              : "outline"
                          }
                          className="text-[10px]"
                        >
                          {item.status === "in_progress"
                            ? "Em Execução"
                            : item.status === "done"
                            ? "Concluído"
                            : item.status === "blocked"
                            ? "Bloqueado"
                            : item.status === "triaged"
                            ? "Triado"
                            : item.status === "scoped"
                            ? "Escopado"
                            : "Aberto"}
                        </Badge>

                        <Badge variant="outline" className="text-[10px] uppercase font-mono">
                          {item.priority}
                        </Badge>

                        <h4 className="text-sm font-semibold text-foreground truncate max-w-xl">
                          {item.title}
                        </h4>
                      </div>

                      {item.description && (
                        <p className="text-xs text-muted-foreground line-clamp-1">
                          {item.description}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Resumo de Progresso das Tarefas e Ações */}
                  <div
                    className="flex items-center justify-between md:justify-end gap-3 shrink-0 pt-2 md:pt-0"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {/* Barra de Progresso */}
                    <div className="flex items-center gap-2 min-w-[140px]">
                      <div className="w-24 bg-muted h-2 rounded-full overflow-hidden border">
                        <div
                          className="bg-emerald-500 h-full transition-all duration-300"
                          style={{ width: `${progressPercent}%` }}
                        />
                      </div>
                      <span className="text-[11px] font-semibold text-muted-foreground whitespace-nowrap">
                        {doneTasks}/{tasks.length} ({progressPercent}%)
                      </span>
                    </div>

                    {/* Botões de Ação do Planejamento */}
                    <div className="flex items-center gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        className="h-7 px-2 text-xs gap-1 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-500/10"
                        onClick={() => setAddingTaskForPlanningItemId(item.id)}
                        title="Adicionar tarefa a este planejamento"
                      >
                        <Plus className="h-3.5 w-3.5" />
                        <span className="hidden sm:inline">Nova Tarefa</span>
                      </Button>

                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-muted-foreground hover:text-foreground"
                        onClick={() => setEditingPlanningItem(item)}
                        title="Editar planejamento"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>

                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-7 w-7 text-destructive hover:text-destructive hover:bg-destructive/10"
                        onClick={() => deletePlanningItem.mutate({ id: item.id, cascadeTasks: true })}
                        title="Excluir planejamento e suas tarefas"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Área Expandida: Lista de Tarefas do Planejamento */}
                {isExpanded && (
                  <div className="border-t bg-muted/10 p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <h5 className="text-xs font-bold text-muted-foreground flex items-center gap-1.5 uppercase tracking-wider">
                        <CheckSquare className="h-3.5 w-3.5 text-primary" />
                        Tarefas de Execução deste Planejamento ({tasks.length})
                      </h5>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-6 text-[11px] gap-1 bg-background"
                        onClick={() => setAddingTaskForPlanningItemId(item.id)}
                      >
                        <Plus className="h-3 w-3" /> Adicionar Tarefa
                      </Button>
                    </div>

                    {tasks.length === 0 ? (
                      <div className="py-6 text-center rounded-md border border-dashed text-xs text-muted-foreground bg-background/50">
                        <p>Nenhuma tarefa vinculada a este planejamento ainda.</p>
                        <Button
                          size="sm"
                          variant="secondary"
                          className="mt-2 text-xs h-7 gap-1"
                          onClick={() => setAddingTaskForPlanningItemId(item.id)}
                        >
                          <Plus className="h-3.5 w-3.5" /> Criar Primeira Tarefa
                        </Button>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {tasks.map((task) => {
                          const isDone = task.status === "done" || task.status === "deployed";
                          return (
                            <div
                              key={task.id}
                              className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2.5 rounded-md border bg-card text-xs hover:border-primary/30 transition-colors"
                            >
                              <div className="flex items-center gap-2.5 flex-1 min-w-0">
                                <span
                                  className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                    TASK_STATUS_COLORS[task.status] ?? "bg-muted"
                                  }`}
                                >
                                  {task.status === "in_progress"
                                    ? "Em Andamento"
                                    : task.status === "done"
                                    ? "Concluída"
                                    : task.status === "deployed"
                                    ? "Deploy"
                                    : task.status === "blocked"
                                    ? "Bloqueada"
                                    : "Planejada"}
                                </span>

                                <span className={`font-medium flex-1 truncate ${isDone ? "line-through text-muted-foreground" : "text-foreground"}`}>
                                  {task.title}
                                </span>
                              </div>

                              <div className="flex items-center gap-2 shrink-0 justify-end">
                                {task.planned_end_date && (
                                  <span className="text-[10px] text-muted-foreground flex items-center gap-1 font-mono">
                                    <Clock className="h-3 w-3" /> {task.planned_end_date}
                                  </span>
                                )}

                                <Badge variant="outline" className="text-[10px] font-mono">
                                  {task.priority}
                                </Badge>

                                <div className="flex items-center gap-1">
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    className="h-6 w-6 text-muted-foreground hover:text-foreground"
                                    onClick={() => setEditingTask(task)}
                                    title="Editar tarefa"
                                  >
                                    <Pencil className="h-3 w-3" />
                                  </Button>
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    className="h-6 w-6 text-destructive hover:bg-destructive/10"
                                    onClick={() => deleteTask.mutate(task.id)}
                                    title="Excluir tarefa"
                                  >
                                    <Trash2 className="h-3 w-3" />
                                  </Button>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
