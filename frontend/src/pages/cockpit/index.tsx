import { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Gauge,
  Sparkles,
  Layers,
  CheckCircle2,
  Filter,
  Lightbulb,
  Layout,
  FolderKanban,
  CheckSquare,
  ShieldCheck,
  TrendingUp,
  Users,
  Database,
  PlayCircle,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AgentTelemetryPanel } from "@/components/AgentTelemetryPanel";
import { useProducts } from "@/hooks/useProduct";
import { useProjects } from "@/hooks/useProject";
import { usePlanningItems } from "@/hooks/useBacklog";
import { useTasks } from "@/hooks/useTask";
import { useAgentTelemetry, useCockpit, type Cockpit, type PhaseKey } from "@/hooks/useFactory";

const PHASE_LABEL: Record<PhaseKey, string> = {
  conception: "Concepção",
  designer: "UI & ERD",
  procedures: "Planejamento",
  execution: "Tarefas",
  quality: "Qualidade",
};

const PHASE_BADGE_VARIANT: Record<string, "success" | "warning" | "outline" | "destructive"> = {
  approved: "success",
  in_progress: "warning",
  pending: "outline",
  blocked: "destructive",
};

function formatCost(cost: number): string {
  return cost.toLocaleString("pt-BR", { style: "currency", currency: "USD" });
}

function TeamBadge({ projectId, teamSize }: { projectId: string; teamSize: number }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      className="shrink-0"
      onClick={() => navigate("/workspace", { state: { openChannel: { projectId } } })}
      title="Abrir o canal deste projeto"
    >
      <Badge variant={teamSize > 0 ? "secondary" : "outline"} className="gap-1 text-[10px]">
        <Users className="h-3 w-3" />
        {teamSize} {teamSize === 1 ? "agente" : "agentes"}
      </Badge>
    </button>
  );
}

function ProjectProgressList({ cockpit }: { cockpit: Cockpit | undefined }) {
  if (!cockpit || cockpit.products.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          Nenhum produto cadastrado ainda.
        </CardContent>
      </Card>
    );
  }
  return (
    <div className="space-y-4">
      {cockpit.products.map((product) => (
        <Card key={product.product_id}>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">{product.product_name}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {product.projects.length === 0 ? (
              <p className="text-xs text-muted-foreground">Nenhum projeto ainda.</p>
            ) : (
              product.projects.map((project) => (
                <div key={project.project_id} className="space-y-2 rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <p className="truncate text-sm font-medium">{project.project_name}</p>
                        <Badge
                          variant="outline"
                          className={`shrink-0 text-[10px] ${project.project_type === "maintenance" ? "border-amber-500/40 text-amber-600" : "border-sky-500/40 text-sky-600"}`}
                        >
                          {project.project_type === "maintenance" ? "Manutenção" : "Nova Implementação"}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        v{project.version_number} · {project.version_status}
                        {project.pipeline_name && (
                          <> · pipeline: {project.pipeline_name}{project.pipeline_template_name && ` (${project.pipeline_template_name})`}</>
                        )}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <TeamBadge projectId={project.project_id} teamSize={project.team_size} />
                      <span className="text-xs font-medium tabular-nums text-muted-foreground">
                        {formatCost(project.total_cost)}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {project.phases.map((phase) => (
                      <Badge
                        key={phase.key}
                        variant={PHASE_BADGE_VARIANT[phase.state] ?? "outline"}
                        className="text-[10px]"
                      >
                        {PHASE_LABEL[phase.key as PhaseKey] ?? phase.key}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function CockpitPage() {
  const [tab, setTab] = useState("pipeline");
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");

  const { data: products } = useProducts();
  const { data: projects } = useProjects();
  const { data: planningItems } = usePlanningItems();
  const { data: tasks } = useTasks();
  const { data: agentTelemetry } = useAgentTelemetry();
  const { data: cockpit } = useCockpit();

  const activeProduct = products?.find((p) => p.id === selectedProductId);

  // Filter projects by selected product
  const productProjects = useMemo(() => {
    if (!selectedProductId) return projects ?? [];
    return (projects ?? []).filter((p) =>
      activeProduct?.versions?.some((v) => v.id === p.product_version_id)
    );
  }, [projects, selectedProductId, activeProduct]);

  // Active focused project
  const activeProject = useMemo(() => {
    if (selectedProjectId) {
      return productProjects.find((p) => p.id === selectedProjectId);
    }
    return productProjects[0];
  }, [productProjects, selectedProjectId]);

  // Metrics filtered by project or product
  const relevantPlanningItems = useMemo(() => {
    return (planningItems ?? []).filter((item) => {
      if (activeProject) return item.project_id === activeProject.id;
      if (selectedProductId) {
        return productProjects.some((p) => p.id === item.project_id);
      }
      return true;
    });
  }, [planningItems, activeProject, selectedProductId, productProjects]);

  const relevantTasks = useMemo(() => {
    return (tasks ?? []).filter((t) => {
      if (activeProject) return t.project_id === activeProject.id;
      if (selectedProductId) {
        return productProjects.some((p) => p.id === t.project_id);
      }
      return true;
    });
  }, [tasks, activeProject, selectedProductId, productProjects]);

  // Task counters
  const inProgressTasks = relevantTasks.filter((t) => t.status === "in_progress");
  const blockedTasks = relevantTasks.filter((t) => t.status === "blocked");
  const doneTasks = relevantTasks.filter((t) => t.status === "done" || t.status === "deployed");
  const progressPercent =
    relevantTasks.length > 0 ? Math.round((doneTasks.length / relevantTasks.length) * 100) : 0;

  return (
    <div className="space-y-6 p-6">
      {/* Header com Filtros de Contexto */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b pb-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            <Gauge className="h-6 w-6 text-primary" />
            6. Cockpit de Execução
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Acompanhamento em tempo real da esteira de desenvolvimento, ondas de tarefas e agentes em execução.
          </p>
        </div>

        {/* Seletores de Contexto: Produto e Projeto */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 bg-muted/30 p-1.5 rounded-lg border">
            <Filter className="h-4 w-4 text-muted-foreground" />

            {/* Seletor de Produto */}
            <select
              className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-medium focus-visible:ring-1 focus-visible:ring-primary"
              value={selectedProductId}
              onChange={(e) => {
                setSelectedProductId(e.target.value);
                setSelectedProjectId("");
              }}
            >
              <option value="">Todos os Produtos</option>
              {products?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>

            {/* Seletor de Projeto */}
            <select
              className="h-8 rounded-md border border-input bg-background px-2.5 text-xs font-semibold focus-visible:ring-1 focus-visible:ring-primary"
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
            >
              <option value="">Todos os Projetos</option>
              {productProjects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.status})
                </option>
              ))}
            </select>
          </div>

          <Badge variant="outline" className="flex items-center gap-1 border-primary/30 text-primary py-1 px-2.5 font-semibold text-xs">
            <Sparkles className="h-3.5 w-3.5" />
            AI-SDLC 7 Fases
          </Badge>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline & Esteira (7 Fases)</TabsTrigger>
          <TabsTrigger value="tarefas">Execução de Tarefas ({relevantTasks.length})</TabsTrigger>
          <TabsTrigger value="telemetria">Telemetria & Agentes</TabsTrigger>
        </TabsList>

        {/* ABA 1: PIPELINE COMPLETO 7 FASES */}
        <TabsContent value="pipeline" className="mt-4 space-y-6">
          <Card className="border-primary/20 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Layers className="h-4 w-4 text-primary" />
                    Fluxo Sequencial da Software Factory
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Navegue diretamente por cada fase do ciclo de vida de desenvolvimento governado.
                  </CardDescription>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground font-medium">Progresso Geral:</span>
                  <span className="font-bold text-primary">{progressPercent}%</span>
                  <div className="w-24 h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all duration-300"
                      style={{ width: `${progressPercent}%` }}
                    />
                  </div>
                </div>
              </div>
            </CardHeader>

            <CardContent>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
                {/* 1. Concepção & Contexto */}
                <Link
                  to="/conception"
                  className="group rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3.5 flex flex-col justify-between hover:border-emerald-500/60 hover:shadow-md transition-all"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-bold text-emerald-600">
                      <span className="flex items-center gap-1.5">
                        <Lightbulb className="h-3.5 w-3.5" />
                        1. Concepção
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      Abertura de escopo vinculado ao Produto e Stack.
                    </p>
                  </div>
                  <div className="pt-3 flex items-center justify-between text-[10px] font-semibold text-emerald-600 group-hover:translate-x-0.5 transition-transform">
                    <span>Acessar</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </div>
                </Link>

                {/* 2. Telas & Regras */}
                <Link
                  to="/screen-inspector"
                  className="group rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3.5 flex flex-col justify-between hover:border-emerald-500/60 hover:shadow-md transition-all"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-bold text-emerald-600">
                      <span className="flex items-center gap-1.5">
                        <Layout className="h-3.5 w-3.5" />
                        2. Telas & Regras
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      Protótipos visuais e regras de negócio de tela.
                    </p>
                  </div>
                  <div className="pt-3 flex items-center justify-between text-[10px] font-semibold text-emerald-600 group-hover:translate-x-0.5 transition-transform">
                    <span>Acessar</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </div>
                </Link>

                {/* 3. Banco de Dados & ERD */}
                <Link
                  to="/concept-erd"
                  className="group rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3.5 flex flex-col justify-between hover:border-emerald-500/60 hover:shadow-md transition-all"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-bold text-emerald-600">
                      <span className="flex items-center gap-1.5">
                        <Database className="h-3.5 w-3.5" />
                        3. Banco & ERD
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      Modelagem relacional e schemas de dados.
                    </p>
                  </div>
                  <div className="pt-3 flex items-center justify-between text-[10px] font-semibold text-emerald-600 group-hover:translate-x-0.5 transition-transform">
                    <span>Acessar</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </div>
                </Link>

                {/* 4. Central de Projetos & Backlog */}
                <Link
                  to="/projects"
                  className="group rounded-xl border border-sky-500/30 bg-sky-500/5 p-3.5 flex flex-col justify-between hover:border-sky-500/60 hover:shadow-md transition-all"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-bold text-sky-600">
                      <span className="flex items-center gap-1.5">
                        <FolderKanban className="h-3.5 w-3.5" />
                        4. Projetos
                      </span>
                      <Badge className="bg-sky-500 text-white text-[9px] px-1 py-0">
                        {productProjects.length}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      1 Projeto → N Planejamentos → N Tarefas.
                    </p>
                  </div>
                  <div className="pt-3 flex items-center justify-between text-[10px] font-semibold text-sky-600 group-hover:translate-x-0.5 transition-transform">
                    <span>Acessar</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </div>
                </Link>

                {/* 5. Gate de Governança */}
                <Link
                  to="/governance"
                  className="group rounded-xl border border-amber-500/30 bg-amber-500/5 p-3.5 flex flex-col justify-between hover:border-amber-500/60 hover:shadow-md transition-all"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-bold text-amber-600">
                      <span className="flex items-center gap-1.5">
                        <ShieldCheck className="h-3.5 w-3.5" />
                        5. Governança
                      </span>
                      <Badge variant="outline" className="text-[9px] border-amber-500/40 text-amber-600 px-1 py-0">
                        {relevantPlanningItems.length}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      Homologação e seleção do Agente Executor.
                    </p>
                  </div>
                  <div className="pt-3 flex items-center justify-between text-[10px] font-semibold text-amber-600 group-hover:translate-x-0.5 transition-transform">
                    <span>Acessar</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </div>
                </Link>

                {/* 6. Cockpit de Execução */}
                <div
                  className="rounded-xl border-2 border-primary bg-primary/10 p-3.5 flex flex-col justify-between shadow-sm"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-bold text-primary">
                      <span className="flex items-center gap-1.5">
                        <Gauge className="h-3.5 w-3.5" />
                        6. Cockpit
                      </span>
                      <Badge className="bg-primary text-primary-foreground text-[9px] px-1 py-0">
                        Atual
                      </Badge>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      Visão em tempo real das ondas de tarefas.
                    </p>
                  </div>
                  <div className="pt-3 flex items-center justify-between text-[10px] font-semibold text-primary">
                    <span>Monitorando</span>
                    <PlayCircle className="h-3.5 w-3.5" />
                  </div>
                </div>

                {/* 7. Fechamento de Versão */}
                <Link
                  to="/version-closure"
                  className="group rounded-xl border border-purple-500/30 bg-purple-500/5 p-3.5 flex flex-col justify-between hover:border-purple-500/60 hover:shadow-md transition-all"
                >
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs font-bold text-purple-600">
                      <span className="flex items-center gap-1.5">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        7. Fechamento
                      </span>
                    </div>
                    <p className="text-[11px] text-muted-foreground line-clamp-2">
                      Auditoria 100% e trava definitiva de produção.
                    </p>
                  </div>
                  <div className="pt-3 flex items-center justify-between text-[10px] font-semibold text-purple-600 group-hover:translate-x-0.5 transition-transform">
                    <span>Acessar</span>
                    <ChevronRight className="h-3.5 w-3.5" />
                  </div>
                </Link>
              </div>
            </CardContent>
          </Card>

          {/* Resumo do Projeto Selecionado */}
          {activeProject && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FolderKanban className="h-4 w-4 text-primary" />
                    <CardTitle className="text-sm font-semibold">
                      Projeto em Destaque: {activeProject.name}
                    </CardTitle>
                    <Badge variant="outline" className="text-[10px]">
                      {activeProject.status}
                    </Badge>
                  </div>
                  <Link
                    to={`/projects`}
                    className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
                  >
                    Abrir na Central de Projetos <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
              </CardHeader>
              <CardContent className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                <div className="p-3 rounded-lg bg-muted/30 border">
                  <span className="text-xs text-muted-foreground">Planejamentos</span>
                  <p className="text-xl font-bold text-foreground mt-0.5">{relevantPlanningItems.length}</p>
                </div>
                <div className="p-3 rounded-lg bg-sky-500/10 border border-sky-500/20">
                  <span className="text-xs text-sky-600 font-semibold">Em Execução</span>
                  <p className="text-xl font-bold text-sky-600 mt-0.5">{inProgressTasks.length}</p>
                </div>
                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
                  <span className="text-xs text-amber-600 font-semibold">Bloqueadas</span>
                  <p className="text-xl font-bold text-amber-600 mt-0.5">{blockedTasks.length}</p>
                </div>
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                  <span className="text-xs text-emerald-600 font-semibold">Concluídas</span>
                  <p className="text-xl font-bold text-emerald-600 mt-0.5">{doneTasks.length}</p>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* ABA 2: QUADRO DE EXECUÇÃO DAS TAREFAS */}
        <TabsContent value="tarefas" className="mt-4 space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <CheckSquare className="h-4 w-4 text-primary" />
                Tarefas do Projeto em Andamento ({relevantTasks.length})
              </CardTitle>
              <CardDescription className="text-xs">
                Acompanhe o estado de execução de cada tarefa com o agente responsável e status em tempo real.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {relevantTasks.length === 0 ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  Nenhuma tarefa registrada para o projeto selecionado.
                </div>
              ) : (
                <div className="divide-y divide-border">
                  {relevantTasks.map((t) => (
                    <div key={t.id} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                      <div className="space-y-1 flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={
                              t.status === "done" || t.status === "deployed"
                                ? "success"
                                : t.status === "in_progress"
                                ? "default"
                                : t.status === "blocked"
                                ? "destructive"
                                : "outline"
                            }
                            className="text-[10px]"
                          >
                            {t.status}
                          </Badge>
                          <span className="font-semibold text-foreground truncate">
                            {t.title}
                          </span>
                        </div>
                        {t.description && (
                          <p className="text-[11px] text-muted-foreground truncate max-w-xl">
                            {t.description}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-3 shrink-0">
                        <Badge variant="outline" className="text-[10px] capitalize">
                          Prioridade: {t.priority}
                        </Badge>
                        <Link
                          to="/projects"
                          className="text-[11px] font-semibold text-primary hover:underline"
                        >
                          Ver no Projeto →
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ABA 3: TELEMETRIA */}
        <TabsContent value="telemetria" className="mt-4 space-y-6">
          <AgentTelemetryPanel agents={agentTelemetry?.agents ?? []} />

          <div>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <TrendingUp className="h-4 w-4 text-primary" />
              Andamento Consolidado por Produto
            </h2>
            <ProjectProgressList cockpit={cockpit} />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
