import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import { apiClient, ApiError } from "@/lib/api";
import { demandKeys, useAgentWork, useAgentWorkAnalysis, type Demand, type AgentWorkItem } from "./useDemands";
import { useAgents } from "./useAgent";
import { useProjects } from "./useProject";
import { useTasks, useTaskDependencies } from "./useTask";
import { useGovernedApprovalRequests, useDecideGovernedApproval } from "./useGovernance";
import { QUESTION_BULK_MAX, useBulkCancelQuestions, useOperationsViewModel, usePendingQuestions, useQuestionAnalysis, type QuestionAnalysisItem, type QuestionBulkResult } from "./useOperationsViewModel";
import { missionDecisionsKey } from "./useMissions";
import { useAuthStore } from "@/store/authStore";

export const WORK_VIEWS = ["decision", "approvals_queue", "processing", "waiting", "resolved", "attention", "approval", "incubation", "failed", "queued", "running", "completed", "archived"] as const;
export type WorkView = typeof WORK_VIEWS[number];
/** Server-side group of the agent-work list a tab reads. */
export type WorkGroup = "tasks" | "incubation";
/** One tab strip beside "Analisar e encaminhar" (Marcelo, 2026-11-13). */
export const WORK_TABS = ["tasks", "incubation", "approvals", "answers"] as const;
export type WorkTab = typeof WORK_TABS[number];
type MoodleApprovalsSummary = { items: unknown[] };

/** `workTab` wins; older links still land: a question id opens Respostas,
 * `workGroup=moodle` Aprovações and `workGroup=incubation` Incubações. */
export function resolveWorkTab(params: URLSearchParams): WorkTab {
  const explicit = params.get("workTab");
  if (WORK_TABS.includes(explicit as WorkTab)) return explicit as WorkTab;
  if (params.get("questionId")) return "answers";
  const legacy = params.get("workGroup");
  if (legacy === "moodle") return "approvals";
  if (legacy === "incubation" || (!legacy && params.get("workView") === "incubation")) return "incubation";
  return "tasks";
}
/** Same key and request as MoodleApprovalPanel, so both read one cached response. */
export const MOODLE_APPROVALS_KEY = ["personal", "moodle-approvals"] as const;
export type WorkAction = "approve" | "reject" | "postpone" | "drop" | "archive" | "restore" | "delete" | "reconcile" | "retry" | "authorize_retry" | "record_investigation" | "confirm_inactive";
type HistoryEvent = { id: string; action: string; actor: string; created_at: string; payload: Record<string, unknown> | null };
/** Respostas filter over the question analysis (Marcelo, 2026-11-14). */
export const QUESTION_FILTERS = ["all", "archive", "answer"] as const;
export type QuestionFilter = typeof QUESTION_FILTERS[number];
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
  const { t } = useTranslation("personal");
  const readableContext = (value: string | null | undefined) => value?.startsWith("instructor:") ? t("agentTasks.instructorContext") : value;
  const [params, setParams] = useSearchParams();
  const tab = resolveWorkTab(params);
  const group: WorkGroup = tab === "incubation" ? "incubation" : "tasks";
  // Each list tab keeps its own filters/page in the URL.
  const paramKey = (key: string) => tab === "incubation" ? key.replace(/^work/, "incubation") : tab === "approvals" ? key.replace(/^work/, "approvals") : key;
  const value = (key: string) => params.get(paramKey(key));
  const rawView = value("workView");
  const views = WORK_VIEWS.filter(view => ["decision", "processing", "waiting", "resolved", "archived", rawView].includes(view));
  const view: WorkView = tab === "approvals" ? "approvals_queue" : WORK_VIEWS.includes(rawView as WorkView) ? rawView as WorkView : "decision";
  const search = value("workSearch") ?? "", context = value("workContext") ?? "all";
  const agent = value("workAgent") ?? "all", from = value("workFrom") ?? "", to = value("workTo") ?? "";
  const requestedPage = Math.max(1, Number(value("workPage")) || 1);
  const [composing, setComposing] = useState(false), [searchTerm, setSearchTerm] = useState({ group, search });
  const debouncedSearch = searchTerm.group === group ? searchTerm.search : search;
  useEffect(() => { if (composing) return; const timer = setTimeout(() => setSearchTerm({ group, search }), search ? 300 : 0); return () => clearTimeout(timer); }, [group, search, composing]);
  const day = (value: string, end: boolean) => { const date = new Date(`${value}T${end ? "23:59:59.999" : "00:00:00"}`); return value && Number.isFinite(date.getTime()) ? date.toISOString() : undefined; };
  // Aprovações badge: always the unfiltered queue, whichever tab is open.
  const approvalsQueue = useAgentWork({ group: "tasks", view: "approvals_queue", page: 1, page_size: 1 }, true);
  const listed = tab !== "answers";
  const query = useAgentWork(tab === "approvals" ? { group, view, page: requestedPage, page_size: 25 } : { group, view, search: debouncedSearch, context, agent_id: agent === "all" ? undefined : agent,
    created_from: day(from, false), created_to: day(to, true), page: requestedPage, page_size: 25 }, listed);
  // One action for the whole screen (2026-11-14, Marcelo: "esse botão serve para todas as tarefas dos
  // agentes"): the message triage (tasks and incubations, unchanged) plus the questions' analysis.
  const analysis = useAgentWorkAnalysis({ agent_id: agent === "all" ? undefined : agent, context: context === "all" ? undefined : context });
  const [questionAnalysisRequested, setQuestionAnalysisRequested] = useState(false);
  const questionAnalysis = useQuestionAnalysis(questionAnalysisRequested);
  // Pending Moodle approvals are decisions too. The "tasks" group excludes
  // Moodle messages server-side, so adding them here never counts one twice.
  // Only the owner may read them; any other session just shows no number.
  const moodle = useQuery({ queryKey: MOODLE_APPROVALS_KEY, queryFn: () => apiClient.get<MoodleApprovalsSummary>("/api/v1/personal/moodle-approvals"),
    enabled: group === "tasks", refetchInterval: 30_000, retry: false });
  const isAdmin = useAuthStore(state => state.user?.is_admin ?? false);
  const missions = useQuery({ queryKey: missionDecisionsKey, queryFn: () => apiClient.get<unknown[]>("/api/v1/missions/pending-decisions"),
    enabled: isAdmin, refetchInterval: 60_000, retry: false });
  const missionPending = isAdmin && Array.isArray(missions.data) ? missions.data.length : 0;
  const moodlePending = Array.isArray(moodle.data?.items) ? moodle.data.items.length : null;
  const agents = useAgents(), projects = useProjects(), tasks = useTasks();
  const approvals = useGovernedApprovalRequests("pending"), decideApproval = useDecideGovernedApproval();
  const operations = useOperationsViewModel("questions");
  const [archiving, setArchiving] = useState<{ id: string; number: number; question: string } | null>(null);
  const [archiveReason, setArchiveReason] = useState("");
  const [questionFilter, setQuestionFilterState] = useState<QuestionFilter>("all");
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<string[]>([]);
  const [bulkArchiveOpen, setBulkArchiveOpen] = useState(false), [bulkArchiveReason, setBulkArchiveReason] = useState("");
  const [bulkArchiveResults, setBulkArchiveResults] = useState<QuestionBulkResult[]>([]);
  const bulkCancel = useBulkCancelQuestions();
  // Every pending question is the operator's to answer (2026-11-13, Marcelo: all that needs a
  // human goes to Tarefas dos agentes); blocking ones first, then the oldest.
  const pendingQuestions = usePendingQuestions();
  const questions = (pendingQuestions.data ?? []).filter(question => question.status === "pending")
    .sort((x, y) => Number(y.blocking) - Number(x.blocking) || x.created_at.localeCompare(y.created_at));
  const [selectedId, setSelectedId] = useState<string | null>(null), [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [confirmation, setConfirmation] = useState<{ item: AgentWorkItem; action: WorkAction } | null>(null);
  const [bulkConfirmation, setBulkConfirmation] = useState<{ action: "archive" | "restore"; items: AgentWorkItem[] } | null>(null);
  const [bulkResults, setBulkResults] = useState<BulkResult[]>([]);
  const [reason, setReason] = useState(""), [evidence, setEvidence] = useState(""), [postponeAt, setPostponeAt] = useState("");
  const [runConfirmation, setRunConfirmation] = useState("");
  const [notice, setNotice] = useState(false);
  const [promotedTask, setPromotedTask] = useState<{ id: string; number: number } | null>(null);
  const client = useQueryClient(), items = query.data?.items ?? [], page = query.data?.page ?? requestedPage;
  const selected = items.find(row => row.id === selectedId) ?? null;
  const filterKey = `${group}:${view}:${context}:${agent}:${from}:${to}:${debouncedSearch}:${requestedPage}`;
  useEffect(() => { setSelectedId(null); setSelectedIds([]); }, [filterKey]);
  const resultFilterKey = `${group}:${view}:${context}:${agent}:${from}:${to}:${debouncedSearch}`;
  useEffect(() => { setBulkResults([]); }, [resultFilterKey]);
  useEffect(() => { if (listed && query.data && query.data.page !== requestedPage) setParams(prev => { const next = new URLSearchParams(prev); next.set(paramKey("workPage"), String(query.data.page)); return next; }, { replace: true }); }, [listed, query.data?.page, requestedPage, setParams]);
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
    }, onSuccess: async (_, { item, action }) => {
      setConfirmation(null); setNotice(true);
      setSelectedIds(ids => ids.filter(id => id !== item.id));
      setSelectedId(current => current === item.id ? null : current);
      if (action === "approve" && item.origin_type === "incubation") setPromotedTask({ id: item.id, number: item.number });
      await invalidate();
    },
  });
  const bulk = useMutation({
    mutationFn: ({ action, items: selectedItems }: { action: "archive" | "restore"; items: AgentWorkItem[] }) => apiClient.post<{ results: BulkResult[] }>("/api/v1/demands/agent-work/bulk", { action, items: selectedItems.map(item => ({ id: item.id, updated_at: item.updated_at })) }),
    onSuccess: async (result, variables) => {
      const byId = new Map(variables.items.map(item => [item.id, item]));
      setBulkResults(result.results.map(row => ({ ...row, number: byId.get(row.id)?.number, subject: byId.get(row.id)?.subject })));
      setBulkConfirmation(null); setSelectedIds([]); await invalidate();
    },
  });
  const setFilter = (key: string, value: string) => setParams(prev => { const next = new URLSearchParams(prev); next.set("tab", "agent-work"); if (value && value !== "all") next.set(paramKey(key), value); else next.delete(paramKey(key)); if (key !== "workPage") next.delete(paramKey("workPage")); return next; }, { replace: true });
  const agentName = (item: Demand) => agents.data?.find(row => row.id === (item.incubation_owner_id ?? item.target_agent_id))?.name ?? item.from_agent;
  const contextName = (item: AgentWorkItem) => readableContext(item.display_context || (projects.data?.find(row => row.id === item.project_id)?.name ?? item.context_area));
  const setTab = (nextTab: WorkTab) => { setSelectedId(null); setSelectedIds([]); setBulkResults([]); setNotice(false); setPromotedTask(null); setConfirmation(null); setParams(prev => { const next = new URLSearchParams(prev); next.set("tab", "agent-work"); next.set("workTab", nextTab); next.delete("workGroup"); next.delete("questionId"); return next; }); };
  const counts: Record<string, number> = query.data?.counts ?? {};
  const taskApprovals = (approvals.data ?? []).filter(request => request.target_type === "project_task");
  const queueCount = approvalsQueue.data?.counts?.approvals_queue ?? 0;
  // Disjoint sources: the queue excludes Moodle messages, incubations and
  // question-blocked items; missions and governed task approvals aren't messages.
  const approvalsCount = queueCount + (moodlePending ?? 0) + missionPending + taskApprovals.length;
  const cancelQuestion = operations.cancelQuestion;
  const recommendations = new Map<string, QuestionAnalysisItem>((questionAnalysis.data?.items ?? []).map(item => [item.question_id, item]));
  const recommendationFor = (id: string) => recommendations.get(id) ?? null;
  const visibleQuestions = questionFilter === "all" ? questions : questions.filter(item => recommendations.get(item.id)?.recommendation === questionFilter);
  // Only what the operator can see counts as selected: a filter never hides a ticked question.
  const visibleIds = new Set(visibleQuestions.map(item => item.id));
  const checkedQuestionIds = selectedQuestionIds.filter(id => visibleIds.has(id));
  const visibleChecked = visibleQuestions.filter(item => checkedQuestionIds.includes(item.id)).length;
  const suggestedIds = visibleQuestions.filter(item => recommendations.get(item.id)?.recommendation === "archive").map(item => item.id);
  const overQuestionLimit = checkedQuestionIds.length > QUESTION_BULK_MAX;
  const bulkArchiveValid = bulkArchiveReason.trim().length >= 3 && checkedQuestionIds.length > 0 && !overQuestionLimit;
  const questionAnalysisSummary = questionAnalysis.data ? { total: questionAnalysis.data.total, archive: questionAnalysis.data.archive } : null;
  return {
    tab, setTab, group, views, promotedTask,
    approvalsCount, answersCount: questions.length, queueCount, taskApprovals, missionPending,
    archiving, askArchiveQuestion: (item: { id: string; number: number; question: string }) => { cancelQuestion.reset(); setArchiveReason(""); setArchiving(item); },
    archiveReason, setArchiveReason, archiveReasonValid: archiveReason.trim().length >= 3,
    cancelArchiveQuestion: () => { if (!cancelQuestion.isPending) setArchiving(null); },
    confirmArchiveQuestion: () => { if (archiving && archiveReason.trim().length >= 3) cancelQuestion.mutate({ id: archiving.id, reason: archiveReason.trim() }, { onSuccess: () => { setArchiving(null); void invalidate(); } }); },
    archivingQuestion: cancelQuestion.isPending, archiveQuestionError: failureText(cancelQuestion.error),
    moodlePending,

    // "Analisar e encaminhar": message triage + questions, whatever tab is open.
    runAnalysis: () => {
      analysis.start.mutate();
      if (questionAnalysisRequested) void questionAnalysis.refetch(); else setQuestionAnalysisRequested(true);
    },
    analysisBusy: analysis.busy || questionAnalysis.isFetching,
    questionAnalysisStaleDays: questionAnalysis.data?.stale_days ?? 14,
    questionAnalysis: { requested: questionAnalysisRequested, loading: questionAnalysis.isFetching, error: questionAnalysis.isError, summary: questionAnalysisSummary },
    recommendationFor, questionFilter, setQuestionFilter: (value: QuestionFilter) => {
      setQuestionFilterState(value);
      const nextVisible = new Set((value === "all" ? questions : questions.filter(item => recommendations.get(item.id)?.recommendation === value)).map(item => item.id));
      setSelectedQuestionIds(ids => ids.filter(id => nextVisible.has(id)));
    }, visibleQuestions,
    selectedQuestionIds: checkedQuestionIds, questionChecked: (id: string) => checkedQuestionIds.includes(id),
    toggleQuestion: (id: string) => setSelectedQuestionIds(ids => ids.includes(id) ? ids.filter(value => value !== id) : [...ids, id]),
    allVisibleChecked: visibleQuestions.length > 0 && visibleChecked === visibleQuestions.length,
    someVisibleChecked: visibleChecked > 0 && visibleChecked < visibleQuestions.length,
    toggleAllQuestions: () => {
      const visibleIds = visibleQuestions.map(item => item.id);
      setSelectedQuestionIds(ids => visibleChecked === visibleIds.length ? ids.filter(id => !visibleIds.includes(id)) : [...new Set([...ids, ...visibleIds])]);
    },
    suggestedArchiveCount: suggestedIds.length,
    selectSuggestedQuestions: () => setSelectedQuestionIds(ids => [...new Set([...ids, ...suggestedIds])]),
    clearQuestionSelection: () => setSelectedQuestionIds([]),
    overQuestionLimit, questionBulkMax: QUESTION_BULK_MAX, bulkArchiveOpen, bulkArchiveReason, setBulkArchiveReason, bulkArchiveValid, bulkArchiveResults,
    bulkArchiving: bulkCancel.isPending, bulkArchiveError: failureText(bulkCancel.error),
    askBulkArchiveQuestions: () => { bulkCancel.reset(); setBulkArchiveReason(""); setBulkArchiveResults([]); setBulkArchiveOpen(true); },
    cancelBulkArchiveQuestions: () => { if (!bulkCancel.isPending) setBulkArchiveOpen(false); },
    confirmBulkArchiveQuestions: () => {
      if (!bulkArchiveValid) return;
      bulkCancel.mutate({ ids: checkedQuestionIds, reason: bulkArchiveReason.trim() }, { onSuccess: result => {
        setBulkArchiveResults(result.results); setBulkArchiveOpen(false);
        setSelectedQuestionIds(ids => ids.filter(id => !result.results.some(row => row.id === id && row.status === "cancelled")));
        void invalidate();
      } });
    },

    analysis, query, items, filtered: items, view, search, context, agent, from, to, page, total: query.data?.total ?? 0, counts,
    agents: agents.data ?? [], selected, setSelectedId, contextName, agentName, state: (item: AgentWorkItem) => item.status === "archived" ? "archived" : item.operator_state ?? workState(item), setComposing, notice,
    questions, questionsError: pendingQuestions.isError, questionsLoading: pendingQuestions.isLoading, answerQuestion: operations.answerQuestion,
    setView: (value: string) => setFilter("workView", value), setSearch: (value: string) => setFilter("workSearch", value), setContext: (value: string) => setFilter("workContext", value),
    setAgent: (value: string) => setFilter("workAgent", value), setFrom: (value: string) => setFilter("workFrom", value), setTo: (value: string) => setFilter("workTo", value), setPage: (value: number) => setFilter("workPage", String(value)),
    contexts: (query.data?.contexts ?? []).map(row => ({ key: row.project_id ? `project:${row.project_id}` : row.area ? `area:${row.area}` : "unclassified", label: readableContext(row.label ?? projects.data?.find(project => project.id === row.project_id)?.name ?? row.area) })),
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
