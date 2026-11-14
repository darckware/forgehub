import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { Demand } from "@/hooks/useDemands";

const BASE = "/api/v1/operations";
export type OperationsTab = "agents" | "schedule" | "runs" | "improvements" | "questions" | "instructions" | "evolution";
/** "audit" (2026-11-13): an Auditor frequency tier; runs its checks as one batch, no Messages task. */
export type RoutineKind = "monitoring" | "maintenance" | "improvement" | "report" | "coordination" | "audit";
export type AuditFrequency = "daily" | "weekly" | "monthly" | "quarterly";

export interface AgentSummary {
  agent_id: string;
  agent_name: string;
  profile_slug: string | null;
  runtime_type: string | null;
  has_charter: boolean;
  routines_enabled: number;
  routines_total: number;
  today: Record<string, number>;
  daily_run_budget: number | null;
  runs_counted_today: number;
}
export interface OperationsOverview { agents: AgentSummary[]; policy_version: number | null }
export interface CharterInput {
  mission: string;
  responsibilities: string[];
  monitored_domains: string[];
  coordinates_with: Array<{ agent: string; purpose: string }>;
  never_does: string[];
  daily_run_budget: number;
  daily_cost_budget: number;
  escalation: "telegram_direct" | "via_athos";
}
export interface Charter extends CharterInput {
  id: string;
  agent_id: string;
  agent_name: string | null;
  owned_audit_checks: string[];
  updated_at: string;
}
export interface RoutineInput {
  agent_id: string;
  title: string;
  instructions: string;
  schedule: string;
  timezone: string;
  kind: RoutineKind;
  expected_evidence: string | null;
  linked_audit_checks: string[];
  enabled: boolean;
  priority: number;
  deadline_minutes: number;
}
export interface Routine extends RoutineInput {
  id: string;
  agent_name: string | null;
  last_occurrence_at: string | null;
  next_occurrences: string[];
  /** "agent:<slug>" when an agent created it (2026-11-13), else an admin's username; null before then. */
  created_by?: string | null;
  updated_by?: string | null;
  /** kind="audit" only: the tier it runs. */
  audit_frequency?: AuditFrequency | null;
  created_at: string;
  updated_at: string;
}
export interface RoutineRun {
  id: string;
  routine_id: string;
  routine_title: string | null;
  agent_id: string | null;
  agent_name: string | null;
  occurrence_at: string;
  status: string;
  demand_id: string | null;
  demand_number: number | null;
  detail: string | null;
  finished_at: string | null;
  overdue: boolean;
  /** Audit routines: the Auditor batch that is this occurrence's evidence. */
  audit_batch_id?: string | null;
}
export interface OperationsPolicy {
  id: string;
  version: number;
  content: string;
  author: string;
  change_reason: string | null;
  created_at: string;
}
export interface AgentQuestion {
  origin_demand_id?: string | null;
  id: string;
  number: number;
  agent_id: string;
  agent_name: string | null;
  relay_agent_id: string | null;
  relay_agent_name: string | null;
  question: string;
  context: string | null;
  recommendation: string | null;
  blocking: boolean;
  urgent: boolean;
  status: string;
  notify_after: string;
  telegram_sent_at: string | null;
  telegram_error: string | null;
  answer: string | null;
  answered_at: string | null;
  answered_via: string | null;
  answered_by: string | null;
  reply_demand_id: string | null;
  created_at: string;
}
export interface OperationsChange {
  id: string;
  target_type: string;
  target_id: string;
  summary: string;
  rationale: string;
  autonomy_level: "A0" | "A1" | "A2";
  status: "proposed" | "awaiting_approval" | "evaluating" | "kept" | "reverted" | "rejected";
  metric_name: string | null;
  before_value: number | string | null;
  after_value: number | string | null;
  evaluation_ends_at: string | null;
  created_at: string;
}
export interface OperationsTrendDay {
  date: string;
  routines_completed: number;
  routines_failed: number;
  audit_ok: number;
  audit_failed: number;
  cost_usd: number;
  improvements_delivered: number;
}
export interface OperationsEvolution { changes: OperationsChange[]; trend: OperationsTrendDay[] }

export const operationsKeys = {
  all: ["operations"] as const,
  overview: ["operations", "overview"] as const,
  charters: ["operations", "charters"] as const,
  routines: ["operations", "routines"] as const,
  runs: ["operations", "runs"] as const,
  questions: ["operations", "questions"] as const,
  policy: ["operations", "policy"] as const,
  policyVersions: ["operations", "policy-versions"] as const,
  improvements: ["operations", "improvements"] as const,
  evolution: ["operations", "evolution"] as const,
};

export function useOperationsViewModel(tab: OperationsTab) {
  const client = useQueryClient();
  const refresh = () => client.invalidateQueries({ queryKey: operationsKeys.all });
  const overview = useQuery({
    queryKey: operationsKeys.overview,
    queryFn: () => apiClient.get<OperationsOverview>(`${BASE}/overview`),
    refetchInterval: 30_000,
  });
  const charters = useQuery({
    queryKey: operationsKeys.charters,
    queryFn: () => apiClient.get<Charter[]>(`${BASE}/charters`),
    enabled: tab === "agents",
  });
  const routines = useQuery({
    queryKey: operationsKeys.routines,
    queryFn: () => apiClient.get<Routine[]>(`${BASE}/routines`),
    enabled: tab === "agents" || tab === "schedule",
  });
  const runs = useQuery({
    queryKey: operationsKeys.runs,
    queryFn: () => apiClient.get<RoutineRun[]>(`${BASE}/runs`, { params: { limit: 200 } }),
    enabled: tab === "runs",
    refetchInterval: tab === "runs" ? 30_000 : false,
  });
  const questions = useQuery({
    queryKey: operationsKeys.questions,
    queryFn: () => apiClient.get<AgentQuestion[]>(`${BASE}/questions`),
    enabled: tab === "questions",
  });
  const policy = useQuery({
    queryKey: operationsKeys.policy,
    queryFn: () => apiClient.get<OperationsPolicy | null>(`${BASE}/policy`),
    enabled: tab === "instructions",
  });
  const policyVersions = useQuery({
    queryKey: operationsKeys.policyVersions,
    queryFn: () => apiClient.get<OperationsPolicy[]>(`${BASE}/policy/versions`),
    enabled: tab === "instructions",
  });
  const improvements = useQuery({
    queryKey: operationsKeys.improvements,
    queryFn: async () => (await apiClient.get<Demand[]>("/api/v1/demands"))
      .filter((d) => d.origin_type === "incubation" && d.subject.startsWith("[Melhoria]")),
    enabled: tab === "improvements",
  });
  const evolution = useQuery({
    queryKey: operationsKeys.evolution,
    queryFn: () => apiClient.get<OperationsEvolution>(`${BASE}/evolution`),
    enabled: tab === "evolution",
  });

  const invalidate = (...keys: readonly (readonly string[])[]) => {
    keys.forEach((key) => void client.invalidateQueries({ queryKey: key }));
  };
  const saveCharter = useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: CharterInput }) =>
      apiClient.put<Charter>(`${BASE}/charters/${agentId}`, data),
    onSuccess: () => invalidate(operationsKeys.charters, operationsKeys.overview),
  });
  const saveRoutine = useMutation({
    mutationFn: ({ id, data }: { id?: string; data: RoutineInput }) => id
      ? apiClient.patch<Routine>(`${BASE}/routines/${id}`, data)
      : apiClient.post<Routine>(`${BASE}/routines`, data),
    onSuccess: () => invalidate(operationsKeys.routines, operationsKeys.overview),
  });
  const deleteRoutine = useMutation({
    mutationFn: (id: string) => apiClient.delete<void>(`${BASE}/routines/${id}`),
    onSuccess: () => invalidate(operationsKeys.routines, operationsKeys.overview),
  });
  const runNow = useMutation({
    mutationFn: (id: string) => apiClient.post<RoutineRun>(`${BASE}/routines/${id}:run-now`),
    onSuccess: () => invalidate(operationsKeys.runs, operationsKeys.overview),
  });
  const answerQuestion = useMutation({
    mutationFn: ({ id, answer }: { id: string; answer: string }) =>
      apiClient.post<AgentQuestion>(`${BASE}/questions/${id}:answer`, { answer }),
    onSuccess: () => invalidate(operationsKeys.questions),
  });
  const cancelQuestion = useMutation({
    // The reason goes to the asking agent, who is told no answer will come.
    mutationFn: ({ id, reason }: { id: string; reason: string }) => apiClient.post<AgentQuestion>(`${BASE}/questions/${id}:cancel`, { reason }),
    onSuccess: () => invalidate(operationsKeys.questions),
  });
  const publishPolicy = useMutation({
    mutationFn: (data: { content: string; change_reason: string | null }) =>
      apiClient.post<OperationsPolicy>(`${BASE}/policy`, data),
    onSuccess: () => invalidate(operationsKeys.policy, operationsKeys.policyVersions, operationsKeys.overview),
  });
  const undoChange = useMutation({
    mutationFn: (id: string) => apiClient.post<OperationsChange>(`${BASE}/changes/${id}:undo`),
    onSuccess: () => invalidate(operationsKeys.evolution),
  });

  return { overview, charters, routines, runs, questions, policy, policyVersions, improvements, evolution,
    refresh, saveCharter, saveRoutine, deleteRoutine, runNow, answerQuestion, cancelQuestion, publishPolicy, undoChange };
}

/** Every pending question, for Pessoal → Tarefas dos agentes › Respostas. Its own query: the
 * Operações list is the newest 100 of every status, which would hide an old pending question.
 * Same key prefix as operationsKeys.questions, so answer/cancel invalidations refresh it too. */
export function usePendingQuestions() {
  return useQuery({
    queryKey: [...operationsKeys.questions, "pending"] as const,
    queryFn: () => apiClient.get<AgentQuestion[]>(`${BASE}/questions?status=pending&limit=500`),
  });
}

/** GET /operations/questions:analysis — the deterministic, read-only part of
 * "Analisar e encaminhar" that covers pending questions (archive | answer). */
export type QuestionRecommendation = "archive" | "answer";
export type QuestionReasonCode = "agent_inactive" | "origin_archived" | "origin_consolidated" | "origin_completed"
  | "origin_cancelled" | "stale" | "blocking" | "open";
export interface QuestionAnalysisItem {
  question_id: string;
  number: number;
  recommendation: QuestionRecommendation;
  reason_code: QuestionReasonCode;
  reason: string;
  days_idle: number;
}
export interface QuestionAnalysis {
  analyzed_at: string;
  stale_days: number;
  total: number;
  archive: number;
  answer: number;
  items: QuestionAnalysisItem[];
}
export type QuestionBulkStatus = "cancelled" | "already_closed" | "not_found" | "error";
export interface QuestionBulkResult { id: string; number: number | null; status: QuestionBulkStatus; detail: string | null; reply_demand_id: string | null }

export function useQuestionAnalysis(enabled: boolean) {
  return useQuery({
    queryKey: [...operationsKeys.questions, "analysis"] as const,
    queryFn: () => apiClient.get<QuestionAnalysis>(`${BASE}/questions:analysis`),
    enabled, retry: false,
  });
}

/** One reason for many questions; each one is cancelled (and its agent told) on its own. */
export function useBulkCancelQuestions() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, reason }: { ids: string[]; reason: string }) =>
      apiClient.post<{ results: QuestionBulkResult[]; cancelled: number }>(`${BASE}/questions:cancel`, { ids, reason }),
    onSuccess: () => client.invalidateQueries({ queryKey: operationsKeys.questions }),
  });
}
