import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Gauge,
  Sparkles,
  Layers,
  Play,
  CheckCircle2,
  Cpu,
  ArrowRight,
  Filter,
  Lightbulb,
  Layout,
  FolderKanban,
  ListTodo,
  CheckSquare,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useProducts } from "@/hooks/useProduct";
import { useProjects } from "@/hooks/useProject";
import { usePlanningItems } from "@/hooks/useBacklog";
import { useTasks } from "@/hooks/useTask";

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
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const { data: products } = useProducts();
  const { data: projects } = useProjects();
  const { data: planningItems } = usePlanningItems();
  const { data: tasks } = useTasks();

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

      {/* Painel de Lotes de Liberação (Execution Waves) & Agentes IA */}
      <div className="grid gap-6 md:grid-cols-[1fr_340px]">
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

        {/* Status dos Agentes Programadores em Tempo Real */}
        <Card className="border-primary/20">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Cpu className="h-4 w-4 text-primary" />
              Telemetria de Execução dos Agentes
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="rounded-md border p-3 bg-card text-xs space-y-1.5">
              <div className="flex justify-between font-bold">
                <span className="text-primary">#Hephaestus (Backend Agent)</span>
                <span className="text-emerald-500">Ativo</span>
              </div>
              <p className="text-[11px] text-muted-foreground">Sessão Hermes: <code className="text-xs">20260727_auth</code></p>
              <div className="flex justify-between text-[11px] text-muted-foreground pt-1 border-t">
                <span>Tempo Médio: 45s</span>
                <span>Sucesso: 100%</span>
              </div>
            </div>

            <div className="rounded-md border p-3 bg-card text-xs space-y-1.5">
              <div className="flex justify-between font-bold">
                <span className="text-primary">#Scriba (Frontend UI Agent)</span>
                <span className="text-amber-500">Trabalhando</span>
              </div>
              <p className="text-[11px] text-muted-foreground">Construindo Tela Login (Open Design)</p>
              <div className="flex justify-between text-[11px] text-muted-foreground pt-1 border-t">
                <span>Tempo Médio: 1m 20s</span>
                <span>Sucesso: 98%</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
