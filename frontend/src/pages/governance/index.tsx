import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  CheckSquare,
  Clock,
  Loader2,
  PlayCircle,
  Plus,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import {
  useApprovals,
  useApproveApproval,
  useCreateApproval,
  useDecideGovernedApproval,
  useGovernedApprovalRequests,
  useRejectApproval,
  type Approval,
  type ApprovalCreateInput,
  type GovernedApprovalRequest,
} from "@/hooks/useGovernance";
import {
  usePlanningItems,
  useUpdatePlanningItem,
  type PlanningItem,
} from "@/hooks/useBacklog";
import { useProjects } from "@/hooks/useProject";
import { useTasks } from "@/hooks/useTask";
import { useAgents } from "@/hooks/useAgent";
import { ApprovalForm } from "./ApprovalForm";

const STATUS_VARIANT: Record<string, "outline" | "success" | "destructive" | "secondary"> = {
  pending: "outline",
  approved: "success",
  rejected: "destructive",
  decided: "secondary",
  expired: "destructive",
  stale: "destructive",
};

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
                    {/* Seletor de Agente Executor */}
                    <div className="flex items-center gap-1.5 bg-background border rounded-md px-2 py-0.5 shadow-2xs">
                      <Bot className="h-3.5 w-3.5 text-primary shrink-0" />
                      <Select
                        value={assignedAgents[item.id] || ""}
                        onChange={(e) =>
                          setAssignedAgents((prev) => ({ ...prev, [item.id]: e.target.value }))
                        }
                        className="h-7 text-xs border-0 bg-transparent p-0 w-36 font-medium focus:ring-0"
                      >
                        <option value="">Agente Executor...</option>
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
                        disabled={isActing}
                        className="h-8 text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
                        onClick={() => handleSetStatus(item, "in_progress")}
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

// ---------------------------------------------------------------------------
// Aprovações de Sistema e Trilha Existente
// ---------------------------------------------------------------------------

function ApprovalRow({ approval }: { approval: Approval }) {
  const approve = useApproveApproval();
  const reject = useRejectApproval();
  const isPending = approval.status === "pending";
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <Link to={`/governance/${approval.id}`} className="font-medium hover:underline">
            {approval.approval_type}
          </Link>
          <Badge variant="outline" className="text-xs">{approval.entity_type}</Badge>
          <Badge variant={STATUS_VARIANT[approval.status] ?? "outline"}>{approval.status}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {approval.requested_by} · entidade {approval.entity_id.slice(0, 8)}…
          {approval.comments && <> · {approval.comments}</>}
        </p>
      </div>
      {isPending && (
        <div className="flex shrink-0 gap-2">
          <Button
            size="sm" variant="outline" disabled={approve.isPending || reject.isPending}
            onClick={() => approve.mutate({ id: approval.id, decided_by: "operator" })}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />Aprovar
          </Button>
          <Button
            size="sm" variant="ghost" disabled={approve.isPending || reject.isPending}
            onClick={() => reject.mutate({ id: approval.id, decided_by: "operator" })}
          >
            <XCircle className="mr-1.5 h-3.5 w-3.5 text-destructive" />Rejeitar
          </Button>
        </div>
      )}
    </div>
  );
}

function ApprovalsTab() {
  const approvals = useApprovals();
  const create = useCreateApproval();
  const [showForm, setShowForm] = useState(false);

  const pending = approvals.data?.filter((a) => a.status === "pending") ?? [];
  const decided = approvals.data?.filter((a) => a.status !== "pending") ?? [];

  const submit = async (values: ApprovalCreateInput) => {
    await create.mutateAsync({
      ...values,
      comments: values.comments || undefined,
      policy_id: values.policy_id || undefined,
    });
    setShowForm(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          <Plus className="mr-1.5 h-3.5 w-3.5" />
          {showForm ? "Cancelar" : "Nova Aprovação Genérica"}
        </Button>
      </div>

      {showForm && (
        <Card>
          <CardHeader><CardTitle className="text-base">Nova Aprovação Genérica</CardTitle></CardHeader>
          <CardContent>
            <ApprovalForm onSubmit={submit} onCancel={() => setShowForm(false)} isSubmitting={create.isPending} />
            {create.isError && <p className="mt-2 text-sm text-destructive">{(create.error as Error)?.message}</p>}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base"><Clock className="h-4 w-4" />Pendentes</CardTitle>
          <CardDescription>{pending.length} aguardando decisão</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          {approvals.isLoading && <p className="text-sm text-muted-foreground">Carregando...</p>}
          {!approvals.isLoading && pending.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma aprovação pendente.</p>}
          {pending.map((a) => <ApprovalRow key={a.id} approval={a} />)}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Histórico</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {decided.length === 0 && <p className="text-sm text-muted-foreground">Sem decisões ainda.</p>}
          {decided.map((a) => <ApprovalRow key={a.id} approval={a} />)}
        </CardContent>
      </Card>
    </div>
  );
}

function ConceptApprovalRow({ request }: { request: GovernedApprovalRequest }) {
  const decide = useDecideGovernedApproval();
  const [comments, setComments] = useState("");
  const isPending = request.status === "pending";
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium">{request.approval_type} — {request.target_type}</p>
          <p className="text-xs text-muted-foreground">
            Solicitado por {request.requested_by_name} ({request.requested_by_type}) · alvo {request.target_id.slice(0, 8)}…
          </p>
        </div>
        <Badge variant={STATUS_VARIANT[request.status] ?? "outline"}>{request.status}</Badge>
      </div>
      {isPending && (
        <div className="flex items-end gap-2">
          <Textarea rows={1} placeholder="Comentário (opcional)" value={comments} onChange={(e) => setComments(e.target.value)} className="flex-1" />
          <Button
            size="sm" variant="outline" disabled={decide.isPending}
            onClick={() => decide.mutate({ requestId: request.id, decision: "approved", comments: comments || undefined })}
          >
            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />Aprovar
          </Button>
          <Button
            size="sm" variant="ghost" disabled={decide.isPending}
            onClick={() => decide.mutate({ requestId: request.id, decision: "rejected", comments: comments || undefined })}
          >
            <XCircle className="mr-1.5 h-3.5 w-3.5 text-destructive" />Rejeitar
          </Button>
        </div>
      )}
      {decide.isError && <p className="text-xs text-destructive">{(decide.error as Error)?.message}</p>}
    </div>
  );
}

function ConceptApprovalsTab() {
  const requests = useGovernedApprovalRequests();
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base"><AlertTriangle className="h-4 w-4" />Aprovações de Concepção</CardTitle>
        <CardDescription>
          Fluxo governado (policy + separação de deveres) usado para aprovar Concepções antes da autorização de entrega.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {requests.isLoading && <p className="text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />Carregando...</p>}
        {!requests.isLoading && (requests.data?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">Nenhuma solicitação de aprovação de concepção.</p>}
        {requests.data?.map((r) => <ConceptApprovalRow key={r.id} request={r} />)}
      </CardContent>
    </Card>
  );
}

export default function GovernancePage() {
  const [tab, setTab] = useState("planning_gate");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/70 bg-clip-text text-transparent">
          <ShieldCheck className="h-6 w-6 text-primary" />
          5. Gate de Governança
        </h1>
        <p className="text-xs text-muted-foreground mt-1">
          Validação e controle de liberação do planejamento para a esteira de execução. Ver também <Link to="/governance/policies" className="text-primary font-semibold hover:underline">Políticas</Link>.
        </p>
      </div>
      <Tabs value={tab} onValueChange={setTab} className="space-y-6">
        <TabsList className="grid grid-cols-3 max-w-xl bg-muted/60 p-1">
          <TabsTrigger value="planning_gate" className="gap-2 text-xs font-semibold">
            <PlayCircle className="h-4 w-4 text-primary" />
            Gate de Planejamento
          </TabsTrigger>
          <TabsTrigger value="approvals" className="gap-2 text-xs">
            <CheckCircle2 className="h-4 w-4 text-primary" />
            Aprovações Gerais
          </TabsTrigger>
          <TabsTrigger value="concept" className="gap-2 text-xs">
            <AlertTriangle className="h-4 w-4 text-primary" />
            Aprovações de Concepção
          </TabsTrigger>
        </TabsList>
        <TabsContent value="planning_gate" className="mt-4">
          <PlanningGateTab />
        </TabsContent>
        <TabsContent value="approvals" className="mt-4">
          <ApprovalsTab />
        </TabsContent>
        <TabsContent value="concept" className="mt-4">
          <ConceptApprovalsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
