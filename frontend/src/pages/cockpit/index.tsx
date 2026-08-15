import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Gauge,
  Sparkles,
  Layers,
  Play,
  CheckCircle2,
  ArrowRight,
  Filter,
  Lightbulb,
  Layout,
  FolderKanban,
  ListTodo,
  CheckSquare,
  TrendingUp,
  Users,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
                          {project.project_type === "maintenance" ? "Manutenção" : "Criação"}
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

interface WaveBatch {
  id: string;
  name: string;
  plansCount: number;
  tasksCount: number;
  status: "active" | "queued" | "completed";
}

const MOCK_WAVES: WaveBatch[] = [
  { id: "wave_1", name: "Lote 1: Core API Backend & Schemas DB", plansCount: 2, tasksCount: 7, status: "completed" },
  { id: "wave_2", name: "Lote 2: Frontend Auth & Telas de Usuários", plansCount: 2, tasksCount: 6, status: "active" },
  { id: "wave_3", name: "Lote 3: Dashboard Financeiro & Relatórios", plansCount: 1, tasksCount: 4, status: "queued" },
];

export default function CockpitPage() {
  const [tab, setTab] = useState("pipeline");
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const { data: products } = useProducts();
  const { data: projects } = useProjects();
  const { data: planningItems } = usePlanningItems();
  const { data: tasks } = useTasks();
  const { data: agentTelemetry } = useAgentTelemetry();
  const { data: cockpit } = useCockpit();

  const activeProduct = products?.find((p) => p.id === selectedProductId);

  // Filter metrics based on selected product
  const relevantProjects = projects?.filter((p) => {
    if (!selectedProductId) return true;
    return activeProduct?.versions?.some((v) => v.id === p.product_version_id);
  });

  const relevantPlanningItems = planningItems?.filter((item) => {
    if (!selectedProductId) return true;
    return relevantProjects?.some((p) => p.id === item.project_id);
  });

  const relevantTasks = tasks?.filter((t) => {
    if (!selectedProductId) return true;
    return relevantProjects?.some((p) => p.id === t.project_id);
  });

  // Calculate phase counts
  const conceptionCount = activeProduct ? (activeProduct.versions?.length ?? 1) : (products?.length ?? 0);
  const projectsCount = relevantProjects?.length ?? 0;
  const planningCount = relevantPlanningItems?.length ?? 0;
  const tasksDoneCount = relevantTasks?.filter((t) => t.status === "done" || t.status === "deployed").length ?? 0;
  const tasksTotalCount = relevantTasks?.length ?? 0;
  const progressPercent = tasksTotalCount > 0 ? Math.round((tasksDoneCount / tasksTotalCount) * 100) : 0;

  return (
    <div className="space-y-6 p-6">
      {/* Header com Filtro de Produto */}
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b pb-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            <Gauge className="h-6 w-6 text-primary" />
            Cockpit Multiprojetos & Fluxo de Desenvolvimento IA
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Visão ponta a ponta do pipeline AI-SDLC: da Concepção à Liberação por Lotes de Execução (Waves).
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs font-semibold text-muted-foreground">Produto:</span>
            <select
              className="h-9 rounded-md border border-input bg-background px-3 text-xs font-medium focus-visible:ring-1 focus-visible:ring-primary"
              value={selectedProductId}
              onChange={(e) => setSelectedProductId(e.target.value)}
            >
              <option value="">Todos os Produtos</option>
              {products?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <Badge variant="outline" className="flex items-center gap-1 border-primary/30 text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            AI-SDLC Pipeline
          </Badge>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="telemetria">Telemetria</TabsTrigger>
        </TabsList>

        <TabsContent value="pipeline" className="mt-4 space-y-6">
      {/* Visão Sequencial do Fluxo de Desenvolvimento (5 Fases) */}
      <Card className="border-primary/20 shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" />
              Pipeline de Desenvolvimento de Software (AI-SDLC)
            </CardTitle>
            <span className="text-xs font-medium text-muted-foreground">
              {selectedProductId ? `Foco: ${activeProduct?.name}` : "Visão Global Multiprojetos"}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-5 relative">
            {/* Fase 1: Concepção */}
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3.5 space-y-2 relative">
              <div className="flex items-center justify-between font-bold text-emerald-600 text-xs">
                <span className="flex items-center gap-1.5">
                  <Lightbulb className="h-3.5 w-3.5" />
                  1. Concepção
                </span>
                <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-600">
                  {conceptionCount} Versão(ões)
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">PRD, Visão do Produto e Módulos definidos.</p>
              <div className="flex justify-end pt-1">
                <Link to="/conception" className="text-[10px] text-primary hover:underline flex items-center gap-0.5">
                  Ver Concepção <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>

            {/* Fase 2: UI & ERD */}
            <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3.5 space-y-2">
              <div className="flex items-center justify-between font-bold text-emerald-600 text-xs">
                <span className="flex items-center gap-1.5">
                  <Layout className="h-3.5 w-3.5" />
                  2. UI & Diagrama ERD
                </span>
                <Badge variant="outline" className="text-[10px] border-emerald-500/40 text-emerald-600">
                  Aprovado
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">Inspeção de Telas & Modelo Relacional de Dados.</p>
              <div className="flex justify-end gap-2 pt-1">
                <Link to="/screen-inspector" className="text-[10px] text-primary hover:underline">
                  Telas
                </Link>
                <span className="text-[10px] text-muted-foreground">•</span>
                <Link to="/concept-erd" className="text-[10px] text-primary hover:underline flex items-center gap-0.5">
                  Diagrama <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>

            {/* Fase 3: Projetos & Criar Projeto */}
            <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3.5 space-y-2">
              <div className="flex items-center justify-between font-bold text-sky-600 text-xs">
                <span className="flex items-center gap-1.5">
                  <FolderKanban className="h-3.5 w-3.5" />
                  3. Projetos
                </span>
                <Badge className="bg-sky-500 text-white text-[10px]">
                  {projectsCount} Ativos
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">Projetos técnicos criados e vinculados à versão.</p>
              <div className="flex justify-end pt-1">
                <Link to="/projects?tab=projects" className="text-[10px] text-primary hover:underline flex items-center gap-0.5">
                  Ver Projetos <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>

            {/* Fase 4: Planejamento & Escopo */}
            <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3.5 space-y-2">
              <div className="flex items-center justify-between font-bold text-sky-600 text-xs">
                <span className="flex items-center gap-1.5">
                  <ListTodo className="h-3.5 w-3.5" />
                  4. Planejamento
                </span>
                <Badge className="bg-sky-500 text-white text-[10px]">
                  {planningCount} Itens
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">Features, bugs e melhorias triados no escopo.</p>
              <div className="flex justify-end pt-1">
                <Link to="/projects?tab=planning" className="text-[10px] text-primary hover:underline flex items-center gap-0.5">
                  Ver Planejamento <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>

            {/* Fase 5: Tarefas & Liberação */}
            <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/5 p-3.5 space-y-2">
              <div className="flex items-center justify-between font-bold text-indigo-600 text-xs">
                <span className="flex items-center gap-1.5">
                  <CheckSquare className="h-3.5 w-3.5" />
                  5. Liberação Tarefas
                </span>
                <Badge variant="outline" className="text-[10px] border-indigo-500/40 text-indigo-600">
                  {progressPercent}% Pronto
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">Ondas de tarefas em execução e prontas para release.</p>
              <div className="flex justify-end pt-1">
                <Link to="/projects?tab=tasks" className="text-[10px] text-primary hover:underline flex items-center gap-0.5">
                  Ver Tarefas <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Painel de Lotes de Liberação (Execution Waves) */}
      <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Play className="h-4 w-4 text-primary" />
              Lotes de Liberação da Execução (Execution Waves)
            </CardTitle>
            <CardDescription className="text-xs">
              Liberação em lotes controlados para os agentes programadores do Módulo Messages.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {MOCK_WAVES.map((wave) => (
              <div
                key={wave.id}
                className={`flex items-center justify-between rounded-lg border p-3.5 text-xs transition-colors ${
                  wave.status === "active"
                    ? "border-sky-500/50 bg-sky-500/5"
                    : wave.status === "completed"
                    ? "border-emerald-500/30 bg-emerald-500/5 opacity-80"
                    : "bg-muted/20"
                }`}
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold">{wave.name}</span>
                    {wave.status === "active" && (
                      <Badge className="bg-sky-500 text-white text-[10px]">Em Execução</Badge>
                    )}
                    {wave.status === "completed" && (
                      <Badge className="bg-emerald-500 text-white text-[10px]">Concluído</Badge>
                    )}
                    {wave.status === "queued" && (
                      <Badge variant="outline" className="text-[10px]">Na Fila</Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                    <span>{wave.plansCount} Planejamentos</span>
                    <span>•</span>
                    <span>{wave.tasksCount} Tarefas</span>
                  </div>
                </div>

                {wave.status === "queued" && (
                  <Button size="sm" variant="outline" className="text-xs">
                    Liberar Lote
                  </Button>
                )}
                {wave.status === "completed" && (
                  <CheckCircle2 className="h-5 w-5 text-emerald-500" />
                )}
              </div>
            ))}
          </CardContent>
        </Card>
        </TabsContent>

        <TabsContent value="telemetria" className="mt-4 space-y-6">
          <AgentTelemetryPanel agents={agentTelemetry?.agents ?? []} />

          <div>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <TrendingUp className="h-4 w-4 text-primary" />
              Andamento do Projeto
            </h2>
            <ProjectProgressList cockpit={cockpit} />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
