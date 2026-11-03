import { useCallback, useMemo, useState } from "react";
import { ApiError } from "@/lib/api";
import {
  useMissionAction,
  useMissionBoard,
  type MissionActionKind,
  type MissionBoard,
  type MissionTask,
} from "@/hooks/useMissions";

/** ViewModel Hook for the mission executions screen (M0.7,
 * MISSION_EXECUTIONS_SCREEN_SPEC.md §9; CLAUDE.md §21 ViewModel pattern).
 *
 * The page renders this and calls its actions; it owns no state. Every action
 * goes through a confirmation step (`confirming`) and then its own guarded
 * route (`submitting`); the action's availability and the reason it is
 * blocked come from the board (`allowed_actions`/`blocked_actions`), which
 * the backend computes by dry-running the route's guards -- nothing here
 * decides eligibility. A refused request keeps the dialog open with the
 * backend's own message and the typed reason. */
export type MissionExecutionsStatus = "loading" | "ready" | "empty" | "error" | "confirming" | "submitting";
export type MissionErrorKind = "not_found" | "forbidden" | "server";

/** Actions that need a written reason (spec §7; transitions per §3). */
export const REASON_REQUIRED: ReadonlySet<MissionActionKind> = new Set([
  "assign", "return", "pause", "resume", "cancel", "decide_item",
]);
const AGENT_REQUIRED: ReadonlySet<MissionActionKind> = new Set(["assign", "request_review"]);
const DESTRUCTIVE: ReadonlySet<MissionActionKind> = new Set(["return", "cancel"]);

export interface PendingMissionAction {
  kind: MissionActionKind;
  taskId?: string;
  itemId?: string;
}

export interface MissionExecutionsViewModel {
  status: MissionExecutionsStatus;
  errorKind: MissionErrorKind | null;
  board: MissionBoard | undefined;
  tasks: MissionTask[];
  selectedTask: MissionTask | null;
  selectTask: (taskId: string | null) => void;
  taskView: "list" | "graph";
  setTaskView: (view: "list" | "graph") => void;
  /** Live streaming is paused while the board relies on periodic polling. */
  live: "live" | "paused";
  pending: PendingMissionAction | null;
  pendingTask: MissionTask | null;
  destructive: boolean;
  reason: string;
  setReason: (value: string) => void;
  agentId: string;
  setAgentId: (value: string) => void;
  scheduledAt: string;
  setScheduledAt: (value: string) => void;
  decision: string;
  setDecision: (value: string) => void;
  needsReason: boolean;
  needsAgent: boolean;
  canConfirm: boolean;
  actionError: string | null;
  lastResult: MissionActionKind | null;
  /** The backend's reason an action is blocked for a task (null = allowed). */
  blockedReason: (task: MissionTask | null, action: MissionActionKind) => string | null;
  missionBlockedReason: (action: MissionActionKind) => string | null;
  openAction: (kind: MissionActionKind, options?: { taskId?: string; itemId?: string }) => void;
  cancelAction: () => void;
  confirmAction: () => Promise<void>;
  retry: () => void;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const { code, message } = detail as { code?: string; message?: string };
      if (code || message) return [code, message].filter(Boolean).join(": ");
    }
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

function errorKindOf(error: unknown): MissionErrorKind {
  if (error instanceof ApiError && error.status === 404) return "not_found";
  if (error instanceof ApiError && error.status === 403) return "forbidden";
  return "server";
}

export function useMissionExecutionsViewModel(projectId: string | undefined): MissionExecutionsViewModel {
  const query = useMissionBoard(projectId);
  const mutation = useMissionAction(projectId);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [taskView, setTaskView] = useState<"list" | "graph">("list");
  const [pending, setPending] = useState<PendingMissionAction | null>(null);
  const [reason, setReason] = useState("");
  const [agentId, setAgentId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [decision, setDecision] = useState("accept");
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<MissionActionKind | null>(null);

  const board = query.data;
  const tasks = useMemo(() => board?.tasks ?? [], [board]);
  const selectedTask = tasks.find((task) => task.task_id === selectedTaskId) ?? null;
  const pendingTask = pending?.taskId ? tasks.find((task) => task.task_id === pending.taskId) ?? null : null;

  let status: MissionExecutionsStatus;
  if (query.isLoading) status = "loading";
  else if (query.isError && !board) status = "error";
  else if (pending && mutation.isPending) status = "submitting";
  else if (pending) status = "confirming";
  else if (board && board.tasks.length === 0 && !board.planning) status = "empty";
  else status = "ready";

  const blockedReason = useCallback((task: MissionTask | null, action: MissionActionKind) => {
    if (!task) return "NO_TASK";
    if (task.allowed_actions.includes(action)) return null;
    return task.blocked_actions.find((b) => b.action === action)?.reason ?? "NOT_OFFERED";
  }, []);

  const missionBlockedReason = useCallback((action: MissionActionKind) => {
    if (!board) return "NOT_LOADED";
    if (board.mission.allowed_actions.includes(action)) return null;
    return board.mission.blocked_actions.find((b) => b.action === action)?.reason ?? "NOT_OFFERED";
  }, [board]);

  const openAction = useCallback((kind: MissionActionKind, options: { taskId?: string; itemId?: string } = {}) => {
    const task = options.taskId ? tasks.find((t) => t.task_id === options.taskId) : undefined;
    setPending({ kind, ...options });
    setReason("");
    setActionError(null);
    setLastResult(null);
    setDecision("accept");
    setScheduledAt("");
    const candidates = kind === "assign" ? task?.executor_candidates ?? []
      : kind === "request_review" ? (task?.reviewer_candidates ?? []).filter((c) => c.eligible) : [];
    setAgentId(candidates[0]?.agent_id ?? "");
    mutation.reset();
  }, [mutation, tasks]);

  const cancelAction = useCallback(() => {
    if (mutation.isPending) return;
    setPending(null);
    setActionError(null);
  }, [mutation.isPending]);

  const needsReason = pending ? REASON_REQUIRED.has(pending.kind) : false;
  const needsAgent = pending ? AGENT_REQUIRED.has(pending.kind) : false;
  const canConfirm = Boolean(pending) && !mutation.isPending
    && (!needsReason || reason.trim().length > 0)
    && (!needsAgent || agentId !== "")
    && (pending?.kind !== "schedule" || scheduledAt !== "");

  const confirmAction = useCallback(async () => {
    if (!pending || !board || !canConfirm) return;
    const mission = board.mission;
    const toState = pending.kind === "pause" ? "paused" : pending.kind === "cancel" ? "cancelled"
      : pending.kind === "resume" ? mission.paused_from_state : undefined;
    try {
      await mutation.mutateAsync({
        kind: pending.kind,
        taskId: pending.taskId,
        itemId: pending.itemId,
        executionId: pendingTask?.execution?.execution_id ?? null,
        agentId: agentId || undefined,
        reason: reason.trim() || undefined,
        scheduledAt: scheduledAt ? new Date(scheduledAt).toISOString() : undefined,
        decision,
        toState,
        rowVersion: mission.row_version,
      });
      setLastResult(pending.kind);
      setPending(null);
    } catch (error) {
      setActionError(errorMessage(error));
    }
  }, [agentId, board, canConfirm, decision, mutation, pending, pendingTask, reason, scheduledAt]);

  return {
    status,
    errorKind: status === "error" ? errorKindOf(query.error) : null,
    board,
    tasks,
    selectedTask,
    selectTask: setSelectedTaskId,
    taskView,
    setTaskView,
    // Until the mission SSE endpoint is connected, polling is the fallback,
    // not a live connection. Do not present periodic snapshots as live.
    live: "paused",
    pending,
    pendingTask,
    destructive: pending ? DESTRUCTIVE.has(pending.kind) : false,
    reason,
    setReason,
    agentId,
    setAgentId,
    scheduledAt,
    setScheduledAt,
    decision,
    setDecision,
    needsReason,
    needsAgent,
    canConfirm,
    actionError,
    lastResult,
    blockedReason,
    missionBlockedReason,
    openAction,
    cancelAction,
    confirmAction,
    retry: () => void query.refetch(),
  };
}
