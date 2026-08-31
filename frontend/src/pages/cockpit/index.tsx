import { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Gauge,
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
  ExternalLink,
  Clock,
  ArrowRight,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { AgentTelemetryPanel } from "@/components/AgentTelemetryPanel";
import { useProducts } from "@/hooks/useProduct";
import { useProjects, PROJECT_SOLUTION_TYPE_LABELS, type Project } from "@/hooks/useProject";
import { usePlanningItems } from "@/hooks/useBacklog";
import { useTasks, type ProjectTask } from "@/hooks/useTask";
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

function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

interface FactoryPhaseItem {
  id: number;
  key: string;
  name: string;
  shortName: string;
  description: string;
  route: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  activeBorder: string;
  badgeBg: string;
}

const FACTORY_PHASES: FactoryPhaseItem[] = [
  {
    id: 1,
    key: "conception",
    name: "1. Concepção & Contexto",
    shortName: "1. Concepção",
    description: "Abertura de escopo vinculado ao Produto, Stack e Assets.",
    route: "/conception",
    icon: Lightbulb,
    color: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/60",
    activeBorder: "border-emerald-500 bg-emerald-500/15 ring-2 ring-emerald-500/40",
    badgeBg: "bg-emerald-500 text-white",
  },
  {
    id: 2,
    key: "screens",
    name: "2. Telas & Regras de Negócio",
    shortName: "2. Telas & Regras",
    description: "Protótipos visuais e regras de negócio de tela.",
    route: "/screen-inspector",
    icon: Layout,
    color: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/60",
    activeBorder: "border-emerald-500 bg-emerald-500/15 ring-2 ring-emerald-500/40",
    badgeBg: "bg-emerald-500 text-white",
  },
  {
    id: 3,
    key: "database",
    name: "3. Banco de Dados & ERD",
    shortName: "3. Banco & ERD",
    description: "Modelagem relacional e schemas de dados.",
    route: "/concept-erd",
    icon: Database,
    color: "text-emerald-600 border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/60",
    activeBorder: "border-emerald-500 bg-emerald-500/15 ring-2 ring-emerald-500/40",
    badgeBg: "bg-emerald-500 text-white",
  },
  {
    id: 4,
    key: "projects",
    name: "4. Central de Projetos & Backlog",
    shortName: "4. Projetos",
    description: "1 Projeto → N Planejamentos → N Tarefas.",
    route: "/projects",
    icon: FolderKanban,
    color: "text-sky-600 border-sky-500/30 bg-sky-500/5 hover:border-sky-500/60",
    activeBorder: "border-sky-500 bg-sky-500/15 ring-2 ring-sky-500/40",
    badgeBg: "bg-sky-500 text-white",
  },
  {
    id: 5,
    key: "governance",
    name: "5. Gate de Governança",
    shortName: "5. Governança",
    description: "Homologação e seleção do Agente Executor.",
    route: "/governance",
    icon: ShieldCheck,
    color: "text-amber-600 border-amber-500/30 bg-amber-500/5 hover:border-amber-500/60",
    activeBorder: "border-amber-500 bg-amber-500/15 ring-2 ring-amber-500/40",
    badgeBg: "bg-amber-500 text-white",
  },
  {
    id: 6,
    key: "version_closure",
    name: "6. Fechamento de Versão",
    shortName: "6. Fechamento",
    description: "Auditoria 100% e trava definitiva de produção.",
    route: "/version-closure",
    icon: CheckCircle2,
    color: "text-purple-600 border-purple-500/30 bg-purple-500/5 hover:border-purple-500/60",
    activeBorder: "border-purple-500 bg-purple-500/15 ring-2 ring-purple-500/40",
    badgeBg: "bg-purple-500 text-white",
  },
];

interface ProjectPhaseEvolution {
  currentPhaseId: number;
  currentPhaseName: string;
  lifecycleStatus: {
    key: "conception" | "planning" | "execution" | "completed";
    label: string;
    variant: "outline" | "default" | "secondary" | "destructive";
    className: string;
  };
  phaseStartedAt: string;
}

function computeProjectPhaseEvolution(
  project: Project,
  allTasks: ProjectTask[] = [],
  allPlanningItems: any[] = []
): ProjectPhaseEvolution {
  const projectTasks = allTasks.filter((t) => t.project_id === project.id);
  const projectPlannings = allPlanningItems.filter((p) => p.project_id === project.id);
  const inProgressTasks = projectTasks.filter((t) => t.status === "in_progress");
  const doneTasks = projectTasks.filter((t) => t.status === "done" || t.status === "deployed");
  const totalTasks = projectTasks.length;

  // 1. Finalizado (Version Closure)
  if (project.status === "completed" || (totalTasks > 0 && doneTasks.length === totalTasks && inProgressTasks.length === 0)) {
    return {
      currentPhaseId: 6,
      currentPhaseName: "6. Fechamento de Versão",
      lifecycleStatus: {
        key: "completed",
        label: "Finalizado",
        variant: "outline",
        className: "border-purple-500/40 text-purple-600 bg-purple-500/10 font-bold",
      },
      phaseStartedAt: project.updated_at || project.created_at || "",
    };
  }

  // 2. Em Execução (Liberado no Governance com tarefas ativas)
  if (inProgressTasks.length > 0 || project.status === "active") {
    return {
      currentPhaseId: 5,
      currentPhaseName: "5. Gate de Governança",
      lifecycleStatus: {
        key: "execution",
        label: "Em Execução",
        variant: "outline",
        className: "border-amber-500/40 text-amber-600 bg-amber-500/10 font-bold animate-pulse",
      },
      phaseStartedAt: project.updated_at || project.created_at || "",
    };
  }

  // 3. Planejamento (Central de Projetos, Tarefas & Backlog)
  if (totalTasks > 0 || projectPlannings.length > 0 || project.status === "planned") {
    return {
      currentPhaseId: 4,
      currentPhaseName: "4. Central de Projetos",
      lifecycleStatus: {
        key: "planning",
        label: "Planejamento",
        variant: "outline",
        className: "border-sky-500/40 text-sky-600 bg-sky-500/10 font-bold",
      },
      phaseStartedAt: project.created_at || "",
    };
  }

  // 4. Concepção inicial
  return {
    currentPhaseId: 1,
    currentPhaseName: "1. Concepção & Contexto",
    lifecycleStatus: {
      key: "conception",
      label: "Concepção",
      variant: "outline",
      className: "border-emerald-500/40 text-emerald-600 bg-emerald-500/10 font-bold",
    },
    phaseStartedAt: project.created_at || "",
  };
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
  const [selectedPhaseId, setSelectedPhaseId] = useState<number | null>(null); // null = All phases

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

  // Project phase count mapping (automatically computes each project's phase)
  const projectEvolutionMap = useMemo(() => {
    const map = new Map<string, ProjectPhaseEvolution>();
    productProjects.forEach((proj) => {
      map.set(proj.id, computeProjectPhaseEvolution(proj, tasks ?? [], planningItems ?? []));
    });
    return map;
  }, [productProjects, tasks, planningItems]);

  const phaseProjectCounts = useMemo(() => {
    const counts: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0 };
    productProjects.forEach((proj) => {
      const evo = projectEvolutionMap.get(proj.id);
      if (evo && evo.currentPhaseId in counts) {
        counts[evo.currentPhaseId]++;
      }
    });
    return counts;
  }, [productProjects, projectEvolutionMap]);

  // Filter projects by active phase
  const selectedPhase = FACTORY_PHASES.find((p) => p.id === selectedPhaseId);

  const displayedProjects = useMemo(() => {
    if (!selectedPhaseId) return productProjects;
    return productProjects.filter((proj) => {
      const evo = projectEvolutionMap.get(proj.id);
      return evo?.currentPhaseId === selectedPhaseId;
    });
  }, [productProjects, selectedPhaseId, projectEvolutionMap]);

  return (
    <div className="space-y-6 p-6">
      {/* Header com Filtros de Contexto */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b pb-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            <Gauge className="h-6 w-6 text-primary" />
            Cockpit de Execução
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Acompanhamento em tempo real da esteira de desenvolvimento, ondas de tarefas e transição automática de fases.
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
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline & Esteira (6 Fases)</TabsTrigger>
          <TabsTrigger value="tarefas">Execução de Tarefas ({relevantTasks.length})</TabsTrigger>
          <TabsTrigger value="telemetria">Telemetria & Agentes</TabsTrigger>
        </TabsList>

        {/* ABA 1: PIPELINE COMPLETO 6 FASES */}
        <TabsContent value="pipeline" className="mt-4 space-y-6">
          <Card className="border-primary/20 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-sm font-semibold flex items-center gap-2">
                    <Layers className="h-4 w-4 text-primary" />
                    Fluxo Sequencial da Software Factory (1 a 6)
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Clique em qualquer fase para filtrar os projetos correspondentes. A esteira evolui automaticamente.
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

            <CardContent className="space-y-4">
              {/* Grid das 6 Fases Sequenciais */}
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
                {FACTORY_PHASES.map((phase) => {
                  const Icon = phase.icon;
                  const isSelected = selectedPhaseId === phase.id;
                  const count = phaseProjectCounts[phase.id] ?? 0;

                  return (
                    <div
                      key={phase.id}
                      onClick={() => setSelectedPhaseId(isSelected ? null : phase.id)}
                      className={`group rounded-xl border p-3.5 flex flex-col justify-between cursor-pointer transition-all duration-200 ${
                        isSelected ? phase.activeBorder : phase.color
                      }`}
                    >
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-xs font-bold">
                          <span className="flex items-center gap-1.5">
                            <Icon className="h-3.5 w-3.5" />
                            {phase.shortName}
                          </span>
                          <Badge
                            className={`text-[9px] px-1.5 py-0 font-bold ${
                              isSelected
                                ? "bg-primary text-primary-foreground"
                                : count > 0
                                ? "bg-primary/20 text-primary border border-primary/30"
                                : "bg-muted text-muted-foreground"
                            }`}
                          >
                            {count} {count === 1 ? "proj" : "projs"}
                          </Badge>
                        </div>
                        <p className="text-[11px] text-muted-foreground line-clamp-2">
                          {phase.description}
                        </p>
                      </div>

                      <div className="pt-3 flex items-center justify-between text-[10px] font-semibold">
                        <span className="text-muted-foreground group-hover:text-foreground">
                          {isSelected ? "Ativa (Clique p/ limpar)" : "Filtrar fase"}
                        </span>
                        <Link
                          to={phase.route}
                          onClick={(e) => e.stopPropagation()}
                          className="hover:underline flex items-center gap-0.5 text-primary font-bold"
                          title={`Ir para tela ${phase.name}`}
                        >
                          <span>Acessar</span>
                          <ExternalLink className="h-3 w-3" />
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Painel Interativo de Acompanhamento de Projetos com Transição de Fase */}
              <div className="rounded-xl border bg-muted/20 p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-2.5">
                  <div className="flex items-center gap-2">
                    {selectedPhase ? (
                      <selectedPhase.icon className={`h-4 w-4 ${selectedPhase.color.split(" ")[0]}`} />
                    ) : (
                      <Layers className="h-4 w-4 text-primary" />
                    )}
                    <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                      {selectedPhase
                        ? `Acompanhamento: ${selectedPhase.name}`
                        : "Acompanhamento: Todos os Projetos na Esteira"}
                    </h3>
                    <Badge variant="secondary" className="text-[10px]">
                      {displayedProjects.length} {displayedProjects.length === 1 ? "projeto" : "projetos"}
                    </Badge>
                  </div>

                  {selectedPhase && (
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => setSelectedPhaseId(null)}
                        className="text-xs text-muted-foreground hover:text-foreground underline"
                      >
                        Ver todas as fases
                      </button>
                      <Link
                        to={selectedPhase.route}
                        className="text-xs font-semibold text-primary hover:underline flex items-center gap-1"
                      >
                        Acessar Módulo Completo <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  )}
                </div>

                {displayedProjects.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground">
                    Nenhum projeto associado a esta fase no momento.
                  </div>
                ) : (
                  <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                    {displayedProjects.map((proj) => {
                      const evo = projectEvolutionMap.get(proj.id) || computeProjectPhaseEvolution(proj, tasks ?? [], planningItems ?? []);
                      const projTasks = (tasks ?? []).filter((t) => t.project_id === proj.id);
                      const projDoneTasks = projTasks.filter((t) => t.status === "done" || t.status === "deployed");
                      const projProgress = projTasks.length > 0 ? Math.round((projDoneTasks.length / projTasks.length) * 100) : 0;
                      const isFocused = activeProject?.id === proj.id;
                      const phaseConfig = FACTORY_PHASES.find((f) => f.id === evo.currentPhaseId) || FACTORY_PHASES[0];

                      return (
                        <div
                          key={proj.id}
                          onClick={() => setSelectedProjectId(proj.id)}
                          className={`rounded-lg border p-3 text-xs space-y-2 cursor-pointer transition-colors bg-background ${
                            isFocused ? "border-primary ring-1 ring-primary shadow-sm" : "hover:border-primary/50"
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <div className="min-w-0">
                              <p className="font-bold truncate text-foreground text-sm" title={proj.name}>
                                {proj.name}
                              </p>
                              <p className="text-[11px] text-muted-foreground">
                                {proj.solution_type ? PROJECT_SOLUTION_TYPE_LABELS[proj.solution_type] : "Aplicação"}
                              </p>
                            </div>
                            {/* Status do Ciclo de Vida: Conception | Planejamento | Em Execução | Finalizado */}
                            <Badge variant={evo.lifecycleStatus.variant} className={`text-[10px] px-1.5 py-0.5 shrink-0 ${evo.lifecycleStatus.className}`}>
                              {evo.lifecycleStatus.label}
                            </Badge>
                          </div>

                          {/* Fase Atual Automática da Esteira */}
                          <div className="flex items-center justify-between text-[11px] bg-muted/40 px-2 py-1 rounded">
                            <span className="text-muted-foreground">Fase Atual:</span>
                            <span className="font-semibold text-primary">
                              {evo.currentPhaseName}
                            </span>
                          </div>

                          {/* Data/Hora de Inicialização */}
                          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground pt-1 border-t">
                            <Clock className="h-3 w-3 shrink-0 text-primary/70" />
                            <span>Inicializado em:</span>
                            <span className="font-medium text-foreground">
                              {formatDateTime(evo.phaseStartedAt || proj.created_at)}
                            </span>
                          </div>

                          {/* Progresso de Tarefas do Projeto */}
                          <div className="space-y-1 pt-0.5">
                            <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                              <span>Tarefas: {projDoneTasks.length}/{projTasks.length}</span>
                              <span className="font-bold text-foreground">{projProgress}%</span>
                            </div>
                            <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                              <div
                                className="h-full bg-primary transition-all duration-300"
                                style={{ width: `${projProgress}%` }}
                              />
                            </div>
                          </div>

                          {/* Botão de Ação Direta */}
                          <div className="pt-1 flex items-center justify-between border-t">
                            <span className="text-[10px] text-muted-foreground">
                              {isFocused ? "Em foco" : "Clique p/ focar"}
                            </span>
                            <Link
                              to={phaseConfig.route}
                              onClick={(e) => e.stopPropagation()}
                              className="text-[11px] font-semibold text-primary hover:underline flex items-center gap-0.5"
                            >
                              Acessar Fase Atual →
                            </Link>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
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
