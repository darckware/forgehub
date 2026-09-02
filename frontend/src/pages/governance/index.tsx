import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  Bot,
  CheckSquare,
  Clock,
  Loader2,
  PlayCircle,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  usePlanningItems,
  useUpdatePlanningItem,
  type PlanningItem,
} from "@/hooks/useBacklog";
import { useProjects } from "@/hooks/useProject";
import { useTasks } from "@/hooks/useTask";
import { useAgents } from "@/hooks/useAgent";

// ---------------------------------------------------------------------------
// Aba: Liberação de Planejamento (Gate Backlog -> Em Análise -> Execução)
// ---------------------------------------------------------------------------

type PlanningGateCategory = "all" | "in_analysis" | "backlog" | "released" | "rejected";

function PlanningGateTab() {
  const { data: planningItems, isLoading: isLoadingPlanning } = usePlanningItems();
  const { data: projects } = useProjects();
  const { data: tasks } = useTasks();
  const { data: agents } = useAgents();

  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const [categoryFilter, setCategoryFilter] = useState<PlanningGateCategory>("in_analysis");
  const [actingItemId, setActingItemId] = useState<string | null>(null);
  const [assignedAgents, setAssignedAgents] = useState<Record<string, string>>({});

  const updatePlanning = useUpdatePlanningItem(actingItemId ?? "");

  // Map tasks count by planning_item_id
  const tasksCountMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const t of tasks ?? []) {
      if (t.planning_item_id) {
        map.set(t.planning_item_id, (map.get(t.planning_item_id) || 0) + 1);
      }
    }
    return map;
  }, [tasks]);

  // Categorize planning item for governance gate
  const getGateCategory = (item: PlanningItem): PlanningGateCategory => {
    if (item.status === "in_progress") return "released";
    if (item.status === "triaged" || item.status === "scoped") return "in_analysis";
    if (item.status === "rejected" || item.status === "blocked") return "rejected";
    return "backlog"; // new, baselined or others unvalidated
  };

  const projectMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const p of projects ?? []) {
      map.set(p.id, p.name);
    }
    return map;
  }, [projects]);

  const filteredItems = useMemo(() => {
    return (planningItems ?? []).filter((item) => {
      if (selectedProjectId && item.project_id !== selectedProjectId) return false;
      if (categoryFilter !== "all" && getGateCategory(item) !== categoryFilter) return false;
      return true;
    });
  }, [planningItems, selectedProjectId, categoryFilter]);

  const counts = useMemo(() => {
    const items = (planningItems ?? []).filter(
      (i) => !selectedProjectId || i.project_id === selectedProjectId
    );
    const res: Record<PlanningGateCategory, number> = {
      all: items.length,
      in_analysis: 0,
      backlog: 0,
      released: 0,
      rejected: 0,
    };
    for (const item of items) {
      const cat = getGateCategory(item);
      res[cat] = (res[cat] || 0) + 1;
    }
    return res;
  }, [planningItems, selectedProjectId]);

  const handleSetStatus = async (item: PlanningItem, newStatus: "in_progress" | "triaged" | "new" | "rejected") => {
    setActingItemId(item.id);
    try {
      await updatePlanning.mutateAsync({
        status: newStatus,
      });
    } finally {
      setActingItemId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner de Contexto de Governança */}
      <Card className="border-primary/20 bg-muted/20">
        <CardContent className="p-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between text-xs">
          <div>
            <h3 className="font-semibold text-sm flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-primary" />
              Gate de Liberação para Execução
            </h3>
            <p className="text-muted-foreground mt-0.5">
              Itens <strong>não validados permanecem no Backlog</strong>. Ao serem colocados <strong>Em Análise</strong> e <strong>Liberados</strong>, eles transitam diretamente para a esteira de <strong>Execução</strong> dos agentes e desenvolvedores.
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Label className="text-[11px] font-semibold text-muted-foreground whitespace-nowrap">
              Filtrar Projeto:
            </Label>
            <Select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="h-8 text-xs w-48 bg-background"
            >
              <option value="">Todos os Projetos</option>
              {projects?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Pílulas de Filtro de Categoria de Governança */}
      <div className="flex flex-wrap items-center gap-1.5">
        <Button
          size="sm"
          variant={categoryFilter === "in_analysis" ? "default" : "outline"}
          className="h-8 text-xs gap-1.5"
          onClick={() => setCategoryFilter("in_analysis")}
        >
          <span className="h-2 w-2 rounded-full bg-amber-500" />
          Em Análise <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.in_analysis}</Badge>
        </Button>
        <Button
          size="sm"
          variant={categoryFilter === "backlog" ? "default" : "outline"}
          className="h-8 text-xs gap-1.5"
          onClick={() => setCategoryFilter("backlog")}
        >
          <span className="h-2 w-2 rounded-full bg-zinc-400" />
          No Backlog (Não Validados) <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.backlog}</Badge>
        </Button>
        <Button
          size="sm"
          variant={categoryFilter === "released" ? "default" : "outline"}
          className="h-8 text-xs gap-1.5"
          onClick={() => setCategoryFilter("released")}
        >
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          Liberados para Execução <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.released}</Badge>
        </Button>
        <Button
          size="sm"
          variant={categoryFilter === "rejected" ? "default" : "outline"}
          className="h-8 text-xs gap-1.5"
          onClick={() => setCategoryFilter("rejected")}
        >
          <span className="h-2 w-2 rounded-full bg-rose-500" />
          Rejeitados / Bloqueados <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.rejected}</Badge>
        </Button>
        <Button
          size="sm"
          variant={categoryFilter === "all" ? "default" : "outline"}
          className="h-8 text-xs gap-1.5"
          onClick={() => setCategoryFilter("all")}
        >
          Todos <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">{counts.all}</Badge>
        </Button>
      </div>

      {/* Lista de Itens no Gate de Governança */}
      {isLoadingPlanning ? (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground text-xs">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          Carregando itens de governança...
        </div>
      ) : filteredItems.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center text-xs text-muted-foreground space-y-2">
            <ShieldCheck className="mx-auto h-8 w-8 text-muted-foreground/30" />
            <p className="font-semibold text-sm text-foreground">
              Nenhum item encontrado nesta categoria de governança
            </p>
            <p className="text-[11px] text-muted-foreground">
              Alterne os filtros acima para visualizar itens no Backlog, Em Análise ou Liberados.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((item) => {
            const isActing = actingItemId === item.id && updatePlanning.isPending;
            const gateCat = getGateCategory(item);
            const taskCount = tasksCountMap.get(item.id) || 0;
            const projectName = (item.project_id && projectMap.get(item.project_id)) || "Projeto";

            return (
              <Card key={item.id} className="border-border/80 hover:border-primary/30 transition-colors">
                <CardContent className="p-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between text-xs">
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded bg-muted px-2 py-0.5 font-semibold text-[10px] text-muted-foreground">
                        {projectName}
                      </span>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {item.item_type}
                      </Badge>
                      <Badge
                        variant={
                          gateCat === "released"
                            ? "success"
                            : gateCat === "in_analysis"
                            ? "default"
                            : gateCat === "rejected"
                            ? "destructive"
                            : "outline"
                        }
                        className="text-[10px]"
                      >
                        {gateCat === "released"
                          ? "✓ Liberado para Execução"
                          : gateCat === "in_analysis"
                          ? "⏳ Em Análise"
                          : gateCat === "rejected"
                          ? "✗ Rejeitado"
                          : "📋 No Backlog"}
                      </Badge>
                      <h4 className="font-semibold text-sm text-foreground truncate max-w-lg">
                        {item.title}
                      </h4>
                    </div>

                    <div className="flex flex-wrap items-center gap-3 text-muted-foreground text-[11px]">
                      <span>Prioridade: <strong className="text-foreground uppercase">{item.priority}</strong></span>
                      <span>·</span>
                      <span className="flex items-center gap-1">
                        <CheckSquare className="h-3 w-3 text-primary" /> {taskCount} tarefa(s)
                      </span>
                      {assignedAgents[item.id] && (
                        <>
                          <span>·</span>
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-primary/10 text-primary font-semibold">
                            <Bot className="h-3 w-3" />
                            {agents?.find((a) => a.id === assignedAgents[item.id])?.name ?? "Agente Atribuído"}
                          </span>
                        </>
                      )}
                      {item.description && (
                        <>
                          <span>·</span>
                          <span className="truncate max-w-sm">{item.description}</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Seleção de Agente Executor e Ações de Governança */}
                  <div className="flex flex-wrap items-center gap-2 shrink-0 pt-2 md:pt-0">
                    {/* Seleção de Agente Executor (Obrigatório para liberação) */}
                    <div
                      className={`flex items-center gap-1.5 bg-background border rounded-md px-2 py-0.5 shadow-2xs transition-colors ${
                        !assignedAgents[item.id] && gateCat !== "released"
                          ? "border-amber-500/60 ring-1 ring-amber-500/30"
                          : "border-input"
                      }`}
                    >
                      <Bot className="h-3.5 w-3.5 text-primary shrink-0" />
                      <Select
                        value={assignedAgents[item.id] || ""}
                        onChange={(e) =>
                          setAssignedAgents((prev) => ({ ...prev, [item.id]: e.target.value }))
                        }
                        className="h-7 text-xs border-0 bg-transparent p-0 w-40 font-medium focus:ring-0"
                      >
                        <option value="">Selecione o Agente *</option>
                        {agents?.map((agent) => (
                          <option key={agent.id} value={agent.id}>
                            {agent.name} ({agent.agent_type})
                          </option>
                        ))}
                      </Select>
                    </div>

                    {gateCat !== "released" && (
                      <Button
                        size="sm"
                        disabled={isActing || !assignedAgents[item.id]}
                        className="h-8 text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                        onClick={() => handleSetStatus(item, "in_progress")}
                        title={
                          !assignedAgents[item.id]
                            ? "Selecione um Agente Executor antes de liberar para execução"
                            : "Liberar item para execução"
                        }
                      >
                        {isActing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />}
                        Liberar p/ Execução
                      </Button>
                    )}

                    {gateCat !== "in_analysis" && gateCat !== "released" && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isActing}
                        className="h-8 text-xs gap-1.5 text-amber-600 dark:text-amber-400 border-amber-500/30"
                        onClick={() => handleSetStatus(item, "triaged")}
                      >
                        <Clock className="h-3.5 w-3.5" />
                        Colocar Em Análise
                      </Button>
                    )}

                    {gateCat !== "backlog" && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isActing}
                        className="h-8 text-xs gap-1.5"
                        onClick={() => handleSetStatus(item, "new")}
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        Voltar p/ Backlog
                      </Button>
                    )}

                    {gateCat !== "rejected" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={isActing}
                        className="h-8 text-xs gap-1 text-destructive hover:bg-destructive/10"
                        onClick={() => handleSetStatus(item, "rejected")}
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        Rejeitar
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function GovernancePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent">
          <ShieldCheck className="h-6 w-6 text-primary" />
          5. Gate de Governança
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          Validação e controle de liberação do planejamento para a esteira de execução dos agentes. Ver também <Link to="/governance/policies" className="text-primary font-semibold hover:underline">Políticas</Link>.
        </p>
      </div>

      <PlanningGateTab />
    </div>
  );
}
