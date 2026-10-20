import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { apiClient, ApiError } from "@/lib/api";
import { demandKeys, useAgentWork, type Demand, type AgentWorkItem } from "./useDemands";
import { useAgents } from "./useAgent";
import { useProjects } from "./useProject";
import { useTasks, useTaskDependencies } from "./useTask";
import { useGovernedApprovalRequests, useDecideGovernedApproval } from "./useGovernance";
import { useOperationsViewModel } from "./useOperationsViewModel";

export const WORK_VIEWS = ["attention", "approval", "incubation", "failed", "queued", "running", "completed", "archived"] as const;
export type WorkView = typeof WORK_VIEWS[number];
export type WorkAction = "approve" | "reject" | "postpone" | "drop" | "archive" | "restore" | "delete" | "reconcile" | "retry" | "authorize_retry" | "record_investigation" | "confirm_inactive";
type HistoryEvent = { id: string; action: string; actor: string; created_at: string; payload: Record<string, unknown> | null };
type BulkResult = { id: string; status: "success" | "blocked" | "missing" | "stale"; detail: string | null; number?: number; subject?: string };

export function workState(item: Demand & { work_state?: string }): string {
  if (item.work_state) return item.work_state;
  if (item.status === "archived") return "archived";
  if (item.dispatch_status === "failed") return item.agent_run_id && (!item.dispatch_error || item.dispatch_error.toLowerCase().includes("uncertain")) ? "uncertain" : "failed";
  if (["running", "dispatched"].includes(item.dispatch_status ?? "") || (!item.dispatch_status && item.agent_run_id)) return "running";
  if (item.dispatch_status === "completed") return "completed";
  if (item.requires_approval && item.approval_status !== "approved") return item.approval_status === "rejected" ? "rejected" : "approval";
  if (item.origin_type === "incubation") return item.incubation_state === "decision_pending" ? "overdue" : "incubation";
  return "queued";
}

function failureText(error: Error | null): string | null {
  if (error instanceof ApiError && typeof error.body === "object" && error.body && "detail" in error.body && typeof error.body.detail === "string") return error.body.detail;
  return error?.message ?? null;
}

export function useAgentTasksViewModel() {
  const [params, setParams] = useSearchParams();
  const rawView = params.get("workView");
  const view: WorkView = WORK_VIEWS.includes(rawView as WorkView) ? rawView as WorkView : "attention";
  const search = params.get("workSearch") ?? "", context = params.get("workContext") ?? "all";
  const agent = params.get("workAgent") ?? "all", from = params.get("workFrom") ?? "", to = params.get("workTo") ?? "";
  const requestedPage = Math.max(1, Number(params.get("workPage")) || 1);
  const [composing, setComposing] = useState(false), [debouncedSearch, setDebouncedSearch] = useState(search);
  useEffect(() => { if (composing) return; const timer = setTimeout(() => setDebouncedSearch(search), search ? 300 : 0); return () => clearTimeout(timer); }, [search, composing]);
  const day = (value: string, end: boolean) => { const date = new Date(`${value}T${end ? "23:59:59.999" : "00:00:00"}`); return value && Number.isFinite(date.getTime()) ? date.toISOString() : undefined; };
  const query = useAgentWork({ view, search: debouncedSearch, context, agent_id: agent === "all" ? undefined : agent,
    created_from: day(from, false), created_to: day(to, true), page: requestedPage, page_size: 25 });
  const agents = useAgents(), projects = useProjects(), tasks = useTasks();
  const approvals = useGovernedApprovalRequests("pending"), decideApproval = useDecideGovernedApproval();
  const operations = useOperationsViewModel("questions");
  const questions = (operations.questions.data ?? []).filter(question => question.status === "pending" && question.blocking);
  const [selectedId, setSelectedId] = useState<string | null>(null), [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<{ item: AgentWorkItem; action: WorkAction } | null>(null);
  const [bulkConfirmation, setBulkConfirmation] = useState<{ action: "archive" | "restore"; items: AgentWorkItem[] } | null>(null);
  const [bulkResults, setBulkResults] = useState<BulkResult[]>([]);
  const [reason, setReason] = useState(""), [evidence, setEvidence] = useState(""), [postponeAt, setPostponeAt] = useState("");
  const [runConfirmation, setRunConfirmation] = useState("");
  const [notice, setNotice] = useState(false);
  const client = useQueryClient(), items = query.data?.items ?? [], page = query.data?.page ?? requestedPage;
  const selected = items.find(row => row.id === selectedId) ?? null;
  const filterKey = `${view}:${context}:${agent}:${from}:${to}:${debouncedSearch}:${requestedPage}`;
  useEffect(() => { setSelectedId(null); setSelectedIds([]); }, [filterKey]);
  const resultFilterKey = `${view}:${context}:${agent}:${from}:${to}:${debouncedSearch}`;
  useEffect(() => { setBulkResults([]); }, [resultFilterKey]);
  useEffect(() => { if (query.data && query.data.page !== requestedPage) setParams(prev => { const next = new URLSearchParams(prev); next.set("workPage", String(query.data.page)); return next; }, { replace: true }); }, [query.data?.page, requestedPage, setParams]);
  const history = useQuery({ queryKey: [...demandKeys.all, "history", selectedId], queryFn: ({ signal }) => apiClient.get<HistoryEvent[]>(`/api/v1/demands/${selectedId}/history`, { signal }), enabled: Boolean(selectedId) });
  const sources = useQuery({ queryKey: [...demandKeys.all, "sources", selectedId], queryFn: ({ signal }) => apiClient.get<Demand[]>(`/api/v1/demands/${selectedId}/sources`, { signal }), enabled: Boolean(selectedId) });
  const dependencies = useTaskDependencies(selected?.origin_id ?? "");
  const invalidate = () => Promise.all([demandKeys.all, ["operations"], ["agent-activity"], ["tasks"], ["notifications"]].map(queryKey => client.invalidateQueries({ queryKey })));
  const mutation = useMutation({
    mutationFn: async ({ item, action }: { item: AgentWorkItem; action: WorkAction }) => {
      const url = `/api/v1/demands/${item.id}`;
      if (action === "delete") return apiClient.delete(url);
      if (action === "retry") return apiClient.post(`${url}:reprocess`, {});
      if (action === "reconcile") return apiClient.post(`${url}/reconcile`, {});
      return apiClient.post(`${url}/decision`, { action, reason: reason.trim() || null, evidence_ref: evidence.trim() || null,
        expected_updated_at: item.updated_at, confirmation: action === "confirm_inactive" ? runConfirmation.trim() : null, matures_at: action === "postpone" ? new Date(postponeAt).toISOString() : null });
    }, onSuccess: async () => { setConfirmation(null); setNotice(true); await invalidate(); },
  });
  const bulk = useMutation({
    mutationFn: ({ action, items: selectedItems }: { action: "archive" | "restore"; items: AgentWorkItem[] }) => apiClient.post<{ results: BulkResult[] }>("/api/v1/demands/agent-work/bulk", { action, items: selectedItems.map(item => ({ id: item.id, updated_at: item.updated_at })) }),
    onSuccess: async (result, variables) => {
      const byId = new Map(variables.items.map(item => [item.id, item]));
      setBulkResults(result.results.map(row => ({ ...row, number: byId.get(row.id)?.number, subject: byId.get(row.id)?.subject })));
      setBulkConfirmation(null); setSelectedIds([]); await invalidate();
    },
  });
  const setFilter = (key: string, value: string) => setParams(prev => { const next = new URLSearchParams(prev); next.set("tab", "agent-work"); if (value && value !== "all") next.set(key, value); else next.delete(key); if (key !== "workPage") next.delete("workPage"); return next; }, { replace: true });
  const agentName = (item: Demand) => agents.data?.find(row => row.id === (item.incubation_owner_id ?? item.target_agent_id))?.name ?? item.from_agent;
  const contextName = (item: Demand) => projects.data?.find(row => row.id === item.project_id)?.name ?? item.context_area;
  return {
    query, items, filtered: items, view, search, context, agent, from, to, page, total: query.data?.total ?? 0, counts: query.data?.counts ?? {},
    agents: agents.data ?? [], selected, setSelectedId, contextName, agentName, state: workState, setComposing, notice,
    questions, questionsError: operations.questions.isError, answerQuestion: operations.answerQuestion,
    setView: (value: string) => setFilter("workView", value), setSearch: (value: string) => setFilter("workSearch", value), setContext: (value: string) => setFilter("workContext", value),
    setAgent: (value: string) => setFilter("workAgent", value), setFrom: (value: string) => setFilter("workFrom", value), setTo: (value: string) => setFilter("workTo", value), setPage: (value: number) => setFilter("workPage", String(value)),
    contexts: (query.data?.contexts ?? []).map(row => ({ key: row.project_id ? `project:${row.project_id}` : row.area ? `area:${row.area}` : "unclassified", label: projects.data?.find(project => project.id === row.project_id)?.name ?? row.area })),
    history, sources: sources.data ?? [], sourcesError: sources.isError,
    dependencies: (dependencies.data ?? []).map(dep => tasks.data?.find(task => task.id === dep.depends_on_task_id)).filter(Boolean),
    dependenciesError: dependencies.isError || tasks.isError || (dependencies.data ?? []).some(dep => !tasks.data?.some(task => task.id === dep.depends_on_task_id)),
    approvals, decideApproval, taskName: (id: string) => tasks.data?.find(task => task.id === id)?.title ?? id,
    confirmation, reason, setReason, evidence, setEvidence, runConfirmation, setRunConfirmation,
    /** What confirm_inactive must be typed back: the run id, or #number when no run was recorded. */
    runIdentifier: (item: AgentWorkItem) => item.agent_run_id ?? `#${item.number}`, postponeAt, setPostponeAt, mutation, mutationError: failureText(mutation.error),
    ask: (item: AgentWorkItem, action: WorkAction) => { setConfirmation({ item, action }); setReason(""); setEvidence(""); setPostponeAt(""); setRunConfirmation(""); mutation.reset(); setNotice(false); },
    cancel: () => { if (!mutation.isPending) setConfirmation(null); }, confirm: () => { if (confirmation) mutation.mutate(confirmation); },
    allowed: (item: AgentWorkItem, action: string) => (item.allowed_actions ?? []).includes(action),
    selectedIds, toggle: (id: string) => setSelectedIds(ids => ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id]),
    togglePage: () => setSelectedIds(selectedIds.length === items.length ? [] : items.map(item => item.id)),
    bulk, bulkConfirmation, bulkResults, bulkError: failureText(bulk.error),
    askBulk: (action: "archive" | "restore") => { setBulkConfirmation({ action, items: items.filter(item => selectedIds.includes(item.id)) }); bulk.reset(); },
    cancelBulk: () => { if (!bulk.isPending) setBulkConfirmation(null); }, confirmBulk: () => { if (bulkConfirmation) bulk.mutate(bulkConfirmation); },
  };
}
