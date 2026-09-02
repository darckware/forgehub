import { useMemo, useState } from "react";
import {
  Clock,
  Kanban,
  Loader2,
  Search,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useTasks } from "@/hooks/useTask";
import { usePlanningItems } from "@/hooks/useBacklog";

const COLUMNS: {
  key: "planned" | "in_progress" | "blocked" | "failed" | "done";
  label: string;
  color: string;
  badgeVariant: "outline" | "secondary" | "default" | "destructive";
}[] = [
  { key: "planned", label: "A Fazer / Planejado", color: "border-amber-500/40 bg-amber-500/5", badgeVariant: "outline" },
  { key: "in_progress", label: "Em Execução", color: "border-sky-500/40 bg-sky-500/5", badgeVariant: "default" },
  { key: "blocked", label: "Bloqueado", color: "border-amber-600/40 bg-amber-600/5", badgeVariant: "secondary" },
  { key: "failed", label: "Com Erro / Falha", color: "border-rose-500/40 bg-rose-500/5", badgeVariant: "destructive" },
  { key: "done", label: "Concluído", color: "border-emerald-500/40 bg-emerald-500/5", badgeVariant: "default" },
];

export function ExecutionWaveBoard({ projectId }: { projectId?: string }) {
  const { data: allTasks = [], isLoading } = useTasks();
  const { data: planningItems = [] } = usePlanningItems();

  const [searchTerm, setSearchTerm] = useState("");

  // Filter tasks for the active project
  const projectTasks = useMemo(() => {
    if (!projectId) return allTasks;
    return allTasks.filter((task) => task.project_id === projectId);
  }, [allTasks, projectId]);

  const planningMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of planningItems) {
      map.set(item.id, item.title);
    }
    return map;
  }, [planningItems]);

  const filteredTasks = useMemo(() => {
    if (!searchTerm.trim()) return projectTasks;
    const term = searchTerm.toLowerCase();
    return projectTasks.filter(
      (t) =>
        t.title.toLowerCase().includes(term) ||
        t.description?.toLowerCase().includes(term) ||
        (t.planning_item_id && planningMap.get(t.planning_item_id)?.toLowerCase().includes(term))
    );
  }, [projectTasks, searchTerm, planningMap]);

  return (
    <div className="space-y-4">
      {/* Controles do Quadro */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Kanban className="h-5 w-5 text-primary" />
          <div>
            <h4 className="text-sm font-semibold text-foreground">Fluxo de Execução de Tarefas</h4>
            <p className="text-xs text-muted-foreground">
              Acompanhe o estado das tarefas deliberadas e governadas pelo Governance Gate.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="relative w-64">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Buscar tarefas no quadro..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="h-8 pl-8 text-xs"
            />
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground text-xs gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-primary" /> Carregando quadro de execução...
        </div>
      ) : projectTasks.length === 0 ? (
        <Card className="border-dashed">
          <CardContent className="py-12 text-center space-y-2">
            <Clock className="h-8 w-8 mx-auto text-muted-foreground/50" />
            <p className="text-sm font-medium">Nenhuma tarefa encontrada para este projeto</p>
            <p className="text-xs text-muted-foreground">
              Cadastre itens de planejamento e adicione tarefas na aba "Planejamento & Tarefas".
            </p>
          </CardContent>
        </Card>
      ) : (
        /* Colunas do Kanban de Execução */
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {COLUMNS.map((col) => {
            const columnTasks = filteredTasks.filter((t) => {
              if (col.key === "planned") {
                return (t.status === "planned" || t.status === "ready" || t.status === "assigned") && t.health !== "failed";
              }
              if (col.key === "in_progress") {
                return t.status === "in_progress" && t.health !== "failed";
              }
              if (col.key === "blocked") {
                return t.status === "blocked" && t.health !== "failed";
              }
              if (col.key === "failed") {
                return (
                  t.health === "failed" ||
                  t.executions?.some((ex) => ex.status === "failed")
                );
              }
              if (col.key === "done") {
                return (t.status === "done" || t.status === "deployed") && t.health !== "failed";
              }
              return false;
            });

            return (
              <div
                key={col.key}
                className={`flex flex-col rounded-lg border p-3 min-h-[380px] ${col.color}`}
              >
                {/* Header da Coluna */}
                <div className="flex items-center justify-between pb-2 border-b mb-3">
                  <span className="text-xs font-bold tracking-tight text-foreground flex items-center gap-1.5">
                    {col.label}
                  </span>
                  <Badge variant={col.badgeVariant} className="text-[10px] px-1.5 py-0 h-4">
                    {columnTasks.length}
                  </Badge>
                </div>

                {/* Lista de Cards da Coluna */}
                <div className="space-y-2.5 flex-1 overflow-y-auto max-h-[580px] pr-0.5">
                  {columnTasks.length === 0 ? (
                    <div className="h-24 flex items-center justify-center text-[11px] text-muted-foreground/60 italic border border-dashed rounded-md">
                      Vazio
                    </div>
                  ) : (
                    columnTasks.map((task) => {
                      const planningTitle = task.planning_item_id ? planningMap.get(task.planning_item_id) : null;

                      return (
                        <Card key={task.id} className="bg-card shadow-sm hover:shadow transition-shadow border">
                          <CardContent className="p-3 space-y-2">
                            {/* Planejamento de Origem */}
                            {planningTitle && (
                              <div className="text-[10px] text-primary font-medium truncate flex items-center gap-1">
                                <span className="h-1.5 w-1.5 rounded-full bg-primary shrink-0" />
                                {planningTitle}
                              </div>
                            )}

                            {/* Título da Tarefa */}
                            <div>
                              <div className="flex items-start justify-between gap-1">
                                <span className="font-semibold text-xs text-foreground leading-tight">
                                  #{task.number} {task.title}
                                </span>
                              </div>
                              {task.description && (
                                <p className="text-[11px] text-muted-foreground line-clamp-2 mt-1">
                                  {task.description}
                                </p>
                              )}
                            </div>

                            {/* Detalhes & Prioridade */}
                            <div className="flex items-center justify-between pt-1 border-t text-[10px] text-muted-foreground">
                              <Badge variant="outline" className="capitalize text-[9px] px-1 py-0 h-4">
                                {task.priority}
                              </Badge>
                              {task.planned_end_date && (
                                <span>{task.planned_end_date}</span>
                              )}
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
