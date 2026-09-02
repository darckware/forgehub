import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FolderKanban,
  GitBranch,
  ListTodo,
  Loader2,
  Lock,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ApiError } from "@/lib/api";
import {
  useProducts,
  usePublishProductVersion,
  useUpdateProductVersion,
} from "@/hooks/useProduct";
import { useProjects, useUpdateProject, type Project } from "@/hooks/useProject";
import { usePlanningItems } from "@/hooks/useBacklog";
import { useTasks, type ProjectTask } from "@/hooks/useTask";

const TERMINAL_STATUSES = new Set(["done", "deployed", "cancelled"]);

interface BlockingTask {
  project_id: string;
  project_name: string;
  task_id: string;
  task_number: number;
  title: string;
  status: string;
}

export function deriveVersionReadiness(
  projects: Pick<Project, "id" | "name" | "product_version_id">[],
  tasks: ProjectTask[],
  versionId: string | null,
) {
  const versionProjects = versionId
    ? projects.filter((project) => project.product_version_id === versionId)
    : [];
  const projectIds = new Set(versionProjects.map((project) => project.id));
  const versionTasks = tasks.filter((task) => Boolean(task.project_id && projectIds.has(task.project_id)));
  const completed = versionTasks.filter((task) => TERMINAL_STATUSES.has(task.status));
  const pending = versionTasks.filter((task) => !TERMINAL_STATUSES.has(task.status));
  return {
    projects: versionProjects,
    tasks: versionTasks,
    completed,
    pending,
    eligible: versionTasks.length > 0 && pending.length === 0,
  };
}

function publishBlockingTasks(error: unknown): BlockingTask[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const body = error.body as { detail?: { blocking?: BlockingTask[] } } | undefined;
  return body?.detail?.blocking ?? null;
}

const TASK_STATUS_BADGES: Record<string, { label: string; variant: "success" | "outline" | "destructive" | "default" | "secondary" }> = {
  done: { label: "Concluída", variant: "success" },
  deployed: { label: "Deploy", variant: "success" },
  in_progress: { label: "Em Execução", variant: "default" },
  assigned: { label: "Atribuída", variant: "outline" },
  ready: { label: "Pronta", variant: "outline" },
  planned: { label: "Planejada", variant: "outline" },
  blocked: { label: "Bloqueada", variant: "destructive" },
  cancelled: { label: "Cancelada", variant: "secondary" },
};

export default function VersionClosurePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedProjectId = searchParams.get("project_id");

  const { data: projects, isLoading: isLoadingProjects } = useProjects();
  const { data: products } = useProducts();
  const { data: allPlanningItems, isLoading: isLoadingPlanning } = usePlanningItems();
  const { data: allTasks, isLoading: isLoadingTasks } = useTasks();

  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [releaseNotes, setReleaseNotes] = useState("");
  const [showConfirmCloseDialog, setShowConfirmCloseDialog] = useState(false);

  // Sync selected project
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
    return products.find((prod) =>
      prod.versions?.some((v) => v.id === activeProject.product_version_id)
    ) ?? null;
  }, [activeProject, products]);

  const activeVersion = useMemo(() => {
    if (!activeProject?.product_version_id || !activeProduct) return null;
    return activeProduct.versions?.find((v) => v.id === activeProject.product_version_id) ?? null;
  }, [activeProject, activeProduct]);

  useEffect(() => {
    if (activeVersion?.release_notes) {
      setReleaseNotes(activeVersion.release_notes);
    } else {
      setReleaseNotes("");
    }
  }, [activeVersion]);

  // Project planning items & tasks
  const projectPlanningItems = useMemo(() => {
    if (!selectedProjectId || !allPlanningItems) return [];
    return allPlanningItems.filter((item) => item.project_id === selectedProjectId);
  }, [selectedProjectId, allPlanningItems]);

  const tasksByPlanningItem = useMemo(() => {
    const map = new Map<string, ProjectTask[]>();
    for (const t of allTasks ?? []) {
      if (t.planning_item_id) {
        const list = map.get(t.planning_item_id) || [];
        list.push(t);
        map.set(t.planning_item_id, list);
      }
    }
    return map;
  }, [allTasks]);

  const projectTasks = useMemo(() => {
    if (!selectedProjectId || !allTasks) return [];
    return allTasks.filter((t) => t.project_id === selectedProjectId);
  }, [selectedProjectId, allTasks]);

  const versionReadiness = useMemo(
    () => deriveVersionReadiness(projects ?? [], allTasks ?? [], activeVersion?.id ?? null),
    [projects, allTasks, activeVersion?.id],
  );

  // Calculations
  const completedTasks = useMemo(() => {
    return projectTasks.filter((t) => TERMINAL_STATUSES.has(t.status));
  }, [projectTasks]);

  const pendingTasks = useMemo(() => {
    return projectTasks.filter((t) => !TERMINAL_STATUSES.has(t.status));
  }, [projectTasks]);

  // Planejamentos finalizados: cada item deve possuir tarefas e todas devem estar concluídas ou status 'done'
  const completedPlanningCount = useMemo(() => {
    return projectPlanningItems.filter((item) => {
      const tasks = tasksByPlanningItem.get(item.id) || [];
      const itemPending = tasks.filter((t) => !TERMINAL_STATUSES.has(t.status));
      return (tasks.length > 0 && itemPending.length === 0) || item.status === "done";
    }).length;
  }, [projectPlanningItems, tasksByPlanningItem]);

  const isAllPlanningComplete = projectPlanningItems.length > 0 && completedPlanningCount === projectPlanningItems.length;
  const isAllTasksComplete = projectTasks.length > 0 && pendingTasks.length === 0;
  const canExecuteClosure = activeVersion
    ? versionReadiness.eligible && isAllPlanningComplete
    : isAllTasksComplete && isAllPlanningComplete;
  const closureTasks = activeVersion ? versionReadiness.tasks : projectTasks;
  const closureCompletedTasks = activeVersion ? versionReadiness.completed : completedTasks;
  const closurePendingTasks = activeVersion ? versionReadiness.pending : pendingTasks;
  const progressPercent = projectTasks.length > 0
    ? Math.round((completedTasks.length / projectTasks.length) * 100)
    : 0;

  const isProjectClosed = activeVersion
    ? activeVersion.status === "published"
    : activeProject?.status === "completed";

  const publish = usePublishProductVersion();
  const updateVersion = useUpdateProductVersion();
  const updateProject = useUpdateProject(selectedProjectId);

  const blocking = publishBlockingTasks(publish.error);

  const handleExecuteClosure = async () => {
    if (!activeProject) return;

    // 1. If version exists, update release notes and publish version
    if (activeVersion) {
      if (releaseNotes !== (activeVersion.release_notes ?? "")) {
        await updateVersion.mutateAsync({
          id: activeVersion.id,
          release_notes: releaseNotes,
        });
      }
      await publish.mutateAsync(activeVersion.id);
    } else {
      // Direct project close if no version is attached
      await updateProject.mutateAsync({
        status: "completed",
      });
    }
    setShowConfirmCloseDialog(false);
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-4 border-b pb-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent flex items-center gap-2">
            <Lock className="h-6 w-6 text-primary" />
            7. Fechamento de Versão
          </h1>
          <p className="text-xs text-muted-foreground mt-1">
            Valide a conclusão de todo o planejamento e tarefas para selar e gerar a versão oficial da produção.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link
            to="/projects"
            className="inline-flex items-center gap-1.5 text-xs rounded-md border border-input bg-background px-3 py-1.5 font-medium hover:bg-accent"
          >
            <FolderKanban className="h-4 w-4 text-primary" />
            Central de Projetos
          </Link>
        </div>
      </div>

      {/* Seletor de Contexto do Projeto */}
      <Card className="border-primary/20 bg-muted/20">
        <CardContent className="p-4 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-col sm:flex-row sm:items-center gap-4 flex-1">
            <div className="min-w-[240px]">
              <Label className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                Projeto a Fechar
              </Label>
              <Select
                value={selectedProjectId}
                onChange={(e) => {
                  setSelectedProjectId(e.target.value);
                  setSearchParams({ project_id: e.target.value });
                }}
                className="h-9 text-xs font-semibold bg-background"
              >
                {projects?.map((proj) => (
                  <option key={proj.id} value={proj.id}>
                    {proj.name} {proj.status === "completed" ? "(Fechado)" : ""}
                  </option>
                ))}
              </Select>
            </div>

            {activeProject && (
              <div className="flex flex-wrap items-center gap-2 pt-1 sm:pt-4 text-xs">
                <Badge
                  variant={activeProject.status === "completed" ? "secondary" : "outline"}
                  className="text-xs"
                >
                  Status: {activeProject.status === "completed" ? "Fechado / Concluído" : activeProject.status}
                </Badge>

                {activeProduct && activeVersion && (
                  <span className="rounded-md border bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground">
                    Produto: <strong className="text-foreground">{activeProduct.name}</strong> · Versão Alvo:{" "}
                    <strong className="text-primary font-mono">v{activeVersion.version}</strong>
                  </span>
                )}

                <span className="rounded-md border bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground">
                  Planejamentos: <strong className="text-foreground">{completedPlanningCount}/{projectPlanningItems.length} finalizados</strong>
                </span>

                <span className="rounded-md border bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground">
                  Tarefas: <strong className="text-foreground">{completedTasks.length}/{projectTasks.length}</strong> ({progressPercent}%)
                </span>
                {activeVersion && (
                  <span className="rounded-md border bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground">
                    Versão completa: <strong className="text-foreground">{versionReadiness.projects.length} projetos · {closureCompletedTasks.length}/{closureTasks.length} tarefas</strong>
                  </span>
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {isLoadingProjects || isLoadingPlanning || isLoadingTasks ? (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground text-xs">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          Carregando dados do fechamento do projeto...
        </div>
      ) : !activeProject ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center text-xs text-muted-foreground">
            Selecione um projeto para auditar o fechamento.
          </CardContent>
        </Card>
      ) : isProjectClosed ? (
        /* ================= PROJETO JÁ FECHADO / PUBLICADO ================= */
        <div className="space-y-6">
          <Card className="border-emerald-500/40 bg-emerald-500/5 shadow-sm">
            <CardContent className="flex flex-col sm:flex-row items-center gap-4 py-6">
              <div className="p-3 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <Lock className="h-8 w-8" />
              </div>
              <div className="space-y-1 text-center sm:text-left flex-1">
                <h3 className="text-base font-bold text-emerald-700 dark:text-emerald-300 flex items-center gap-2 justify-center sm:justify-start">
                  Projeto Fechado & Versão de Produção Publicada
                </h3>
                <p className="text-xs text-muted-foreground">
                  Este projeto foi concluído com sucesso e selado para a versão de produção{" "}
                  <strong className="font-mono text-foreground">v{activeVersion?.version ?? "1.0.0"}</strong>.
                  Novas alterações de escopo, planejamento e tarefas estão <strong>permanentemente bloqueadas</strong>.
                </p>
                {activeVersion?.release_notes && (
                  <div className="mt-3 p-3 rounded bg-background/80 border text-xs text-foreground font-mono">
                    <p className="text-[10px] font-bold uppercase text-muted-foreground mb-1">Notas de Lançamento Registradas:</p>
                    {activeVersion.release_notes}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Checklist Histórico em Somente-Leitura */}
          <Card>
            <CardHeader className="p-4 border-b">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                Histórico Selado de Planejamento & Tarefas Entregues ({projectPlanningItems.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
              {projectPlanningItems.map((item) => {
                const tasks = tasksByPlanningItem.get(item.id) || [];
                return (
                  <div key={item.id} className="p-3 rounded-md border bg-muted/10 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-foreground flex items-center gap-2">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                        {item.title}
                      </span>
                      <Badge variant="secondary" className="text-[10px]">
                        {tasks.length} tarefa(s) concluída(s)
                      </Badge>
                    </div>
                    <div className="pl-5 space-y-1">
                      {tasks.map((task) => (
                        <div key={task.id} className="text-[11px] text-muted-foreground flex items-center gap-2">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          <span className="font-mono">#{task.number}</span>
                          <span>{task.title}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>
      ) : (
        /* ================= PROJETO EM ABERTO / AUDITORIA DE FECHAMENTO ================= */
        <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
          {/* Coluna Principal: Checklist de Planejamentos e Tarefas */}
          <div className="space-y-6">
            <Card>
              <CardHeader className="p-4 border-b">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <div>
                    <CardTitle className="text-sm font-semibold flex items-center gap-2">
                      <ListTodo className="h-4 w-4 text-primary" />
                      Auditoria do Planejamento & Tarefas para Produção
                    </CardTitle>
                    <CardDescription className="text-xs mt-0.5">
                      Todas as tarefas devem estar concluídas para autorizar o fechamento do projeto.
                    </CardDescription>
                  </div>
                  <Badge variant={canExecuteClosure ? "success" : "outline"} className="text-xs">
                    {activeVersion ? `${closureCompletedTasks.length}/${closureTasks.length} na versão` : `${completedTasks.length}/${projectTasks.length} concluídas (${progressPercent}%)`}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="p-4 space-y-4">
                {projectPlanningItems.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground">
                    Nenhum item de planejamento cadastrado para este projeto.
                  </div>
                ) : (
                  projectPlanningItems.map((item) => {
                    const tasks = tasksByPlanningItem.get(item.id) || [];
                    const itemPending = tasks.filter((t) => !TERMINAL_STATUSES.has(t.status));
                    const itemComplete = tasks.length > 0 && itemPending.length === 0;

                    return (
                      <div
                        key={item.id}
                        className={`rounded-lg border p-3.5 space-y-3 transition-colors ${
                          itemComplete
                            ? "bg-emerald-500/5 border-emerald-500/30"
                            : "bg-card border-border"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            {itemComplete ? (
                              <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                            ) : (
                              <Clock className="h-4 w-4 text-amber-500 shrink-0" />
                            )}
                            <span className="font-semibold text-xs text-foreground truncate">
                              {item.title}
                            </span>
                            <Badge variant="outline" className="text-[10px] uppercase font-mono">
                              {item.item_type}
                            </Badge>
                          </div>

                          <span className="text-[11px] font-semibold text-muted-foreground">
                            {tasks.filter((t) => TERMINAL_STATUSES.has(t.status)).length}/{tasks.length} tasks
                          </span>
                        </div>

                        {/* Lista de Tarefas do Item */}
                        {tasks.length === 0 ? (
                          <p className="text-[11px] text-muted-foreground italic pl-6">
                            Sem tarefas associadas a este planejamento.
                          </p>
                        ) : (
                          <div className="space-y-1.5 pl-6">
                            {tasks.map((task) => {
                              const isTaskDone = TERMINAL_STATUSES.has(task.status);
                              const badgeInfo = TASK_STATUS_BADGES[task.status] ?? {
                                label: task.status,
                                variant: "outline",
                              };
                              return (
                                <div
                                  key={task.id}
                                  className="flex items-center justify-between gap-2 text-xs p-1.5 rounded bg-background/70 border text-muted-foreground"
                                >
                                  <div className="flex items-center gap-2 truncate">
                                    <span className="font-mono text-[10px] text-muted-foreground">
                                      #{task.number}
                                    </span>
                                    <span className={isTaskDone ? "line-through text-muted-foreground" : "text-foreground font-medium"}>
                                      {task.title}
                                    </span>
                                  </div>
                                  <Badge variant={badgeInfo.variant} className="text-[10px] shrink-0">
                                    {badgeInfo.label}
                                  </Badge>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </CardContent>
            </Card>

            {/* Notas de Lançamento */}
            <Card>
              <CardHeader className="p-4 border-b">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <GitBranch className="h-4 w-4 text-primary" />
                  Notas de Lançamento da Produção (Changelog)
                </CardTitle>
                <CardDescription className="text-xs">
                  Descreva as entregas, correções e novidades contempladas no fechamento deste projeto.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-4">
                <Textarea
                  rows={4}
                  value={releaseNotes}
                  onChange={(e) => setReleaseNotes(e.target.value)}
                  placeholder="Ex: Lançamento da versão 1.0.0 contendo módulo de autenticação, relatórios gerenciais e correção de lentidão no carregamento..."
                  className="resize-none text-xs font-mono"
                />
              </CardContent>
            </Card>
          </div>

          {/* Coluna Lateral: Resumo de Fechamento & Trava de Produção */}
          <div className="space-y-6">
            <Card className="border-primary/40 shadow-md">
              <CardHeader className="p-4 border-b">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-primary" />
                  Selo de Produção & Fechamento
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 space-y-4 text-xs">
                <div className="rounded-md bg-muted/60 p-3 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Projeto:</span>
                    <strong className="text-foreground">{activeProject.name}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Versão de Produção:</span>
                    <strong className="font-mono text-primary">v{activeVersion?.version ?? "1.0.0"}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Planejamentos Concluídos:</span>
                    <strong className={completedPlanningCount === projectPlanningItems.length && projectPlanningItems.length > 0 ? "text-emerald-600" : "text-amber-500"}>
                      {completedPlanningCount} de {projectPlanningItems.length}
                    </strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Tarefas Concluídas:</span>
                    <strong>{closureCompletedTasks.length} de {closureTasks.length}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Tarefas Pendentes:</span>
                    <strong className={closurePendingTasks.length > 0 ? "text-destructive" : "text-emerald-600"}>
                      {closurePendingTasks.length}
                    </strong>
                  </div>
                </div>

                {/* Status de Bloqueio ou Prontidão */}
                {!canExecuteClosure ? (
                  <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 space-y-2 text-destructive text-xs">
                    <div className="flex items-center gap-2 font-bold">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      Fechamento Bloqueado
                    </div>
                    <p className="text-[11px] leading-relaxed">
                      {closureTasks.length === 0
                        ? "A versão precisa possuir ao menos uma tarefa antes da publicação."
                        : <>Existem <strong>{closurePendingTasks.length} tarefa(s) pendente(s)</strong> {activeVersion ? "em projetos desta versão" : "no projeto"}. O fechamento só é autorizado quando 100% das tarefas forem finalizadas.</>}
                    </p>
                    <ul className="list-disc pl-4 text-[10px] space-y-0.5 max-h-32 overflow-y-auto">
                      {closurePendingTasks.map((t) => (
                        <li key={t.id}>
                          {activeVersion && `${versionReadiness.projects.find((project) => project.id === t.project_id)?.name ?? "Projeto"} — `}#{t.number} {t.title} ({t.status})
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 space-y-1.5 text-emerald-700 dark:text-emerald-300 text-xs">
                    <div className="flex items-center gap-2 font-bold">
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
                      Pronto para Fechamento
                    </div>
                    <p className="text-[11px] leading-relaxed">
                      Todas as tarefas foram concluídas. Você pode selar o projeto e gerar a versão oficial da produção.
                    </p>
                  </div>
                )}

                <div className="p-2.5 rounded bg-muted/40 text-[11px] text-muted-foreground border flex items-start gap-2">
                  <ShieldAlert className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                  <span>
                    <strong>Atenção:</strong> O fechamento é permanente. Uma vez fechado, o projeto é travado e não poderá mais ser reaberto ou editado.
                  </span>
                </div>

                <Button
                  className="w-full h-10 gap-2 font-bold text-xs bg-emerald-600 hover:bg-emerald-700 text-white"
                  disabled={!canExecuteClosure || publish.isPending || updateVersion.isPending || updateProject.isPending}
                  onClick={() => setShowConfirmCloseDialog(true)}
                >
                  {(publish.isPending || updateVersion.isPending || updateProject.isPending) ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Lock className="h-4 w-4" />
                  )}
                  Fechar Projeto & Publicar Produção
                </Button>

                {blocking && (
                  <div className="space-y-1 rounded-md border border-destructive/40 bg-destructive/5 p-2.5 text-xs text-destructive">
                    <p className="font-medium">Tarefas bloqueando a publicação:</p>
                    <ul className="list-disc pl-4">
                      {blocking.map((b) => (
                        <li key={b.task_id}>
                          {b.project_name} — #{b.task_number} {b.title} ({b.status})
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {publish.isError && !blocking && (
                  <p className="text-xs text-destructive">
                    {(publish.error as Error)?.message}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Diálogo de Confirmação Irrevogável de Fechamento */}
      <ConfirmDialog
        open={showConfirmCloseDialog}
        title="Confirmar Fechamento do Projeto e Geração de Produção"
        description={activeVersion
          ? `Tem certeza que deseja publicar a versão de produção "${activeVersion.version}"? Esta operação é definitiva e concluirá os ${versionReadiness.projects.length} projetos vinculados.`
          : `Tem certeza que deseja fechar o projeto "${activeProject?.name}"? Esta operação é definitiva e travará o projeto contra qualquer alteração futura.`}
        confirmLabel="Sim, Fechar Projeto Definitivamente"
        onConfirm={handleExecuteClosure}
        onCancel={() => setShowConfirmCloseDialog(false)}
      />
    </div>
  );
}
