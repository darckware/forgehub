import { useState } from "react";
import {
  useCancelHostExecution,
  useFollowUpHostExecution,
  useHostExecution,
  type ExecShell,
  type HostExecutionDetail,
  type HostExecutionResult,
} from "@/hooks/useHostExecutions";

/** Execution screen: per-machine results, cancel, and "run a fix on the
 * machines that failed" (a follow-up linked to this execution). */
export interface ExecutionViewModel {
  status: "loading" | "error" | "not_found" | "ready";
  execution: HostExecutionDetail | undefined;
  failedResults: HostExecutionResult[];
  expanded: Set<string>;
  toggleExpanded: (resultId: string) => void;
  canCancel: boolean;
  confirmingCancel: boolean;
  askCancel: () => void;
  dismissCancel: () => void;
  confirmCancel: () => void;
  cancelling: boolean;
  cancelError: string | null;
  followUp: {
    open: boolean;
    start: () => void;
    close: () => void;
    command: string;
    setCommand: (value: string) => void;
    shell: ExecShell;
    setShell: (value: ExecShell) => void;
    timeoutSeconds: number;
    setTimeoutSeconds: (value: number) => void;
    submit: () => void;
    submitting: boolean;
    error: string | null;
  };
}

export function useExecutionViewModel(
  id: string | undefined,
  onFollowUpStarted: (execution: HostExecutionDetail) => void,
): ExecutionViewModel {
  const query = useHostExecution(id);
  const cancel = useCancelHostExecution();
  const followUp = useFollowUpHostExecution();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [confirmingCancel, setConfirmingCancel] = useState(false);
  const [followOpen, setFollowOpen] = useState(false);
  const [command, setCommand] = useState("");
  const [shell, setShell] = useState<ExecShell | null>(null);
  const [timeoutSeconds, setTimeoutSeconds] = useState(300);

  const execution = query.data;
  const failedResults = execution?.results.filter((r) => r.status === "failed") ?? [];
  const notFound = query.isError && /not found/i.test(query.error?.message ?? "");

  return {
    status: query.isLoading ? "loading" : notFound ? "not_found" : query.isError ? "error" : "ready",
    execution,
    failedResults,
    expanded,
    toggleExpanded: (resultId) =>
      setExpanded((cur) => {
        const next = new Set(cur);
        if (next.has(resultId)) next.delete(resultId);
        else next.add(resultId);
        return next;
      }),
    canCancel: execution?.status === "running" && (execution.counts.pending ?? 0) > 0,
    confirmingCancel,
    askCancel: () => {
      cancel.reset();
      setConfirmingCancel(true);
    },
    dismissCancel: () => setConfirmingCancel(false),
    confirmCancel: () => {
      if (!id) return;
      cancel.mutate(id, { onSuccess: () => setConfirmingCancel(false) });
    },
    cancelling: cancel.isPending,
    cancelError: cancel.error?.message ?? null,
    followUp: {
      open: followOpen,
      start: () => {
        followUp.reset();
        setFollowOpen(true);
      },
      close: () => setFollowOpen(false),
      command,
      setCommand,
      shell: shell ?? execution?.shell ?? "sh",
      setShell,
      timeoutSeconds,
      setTimeoutSeconds,
      submit: () => {
        if (!id || !command.trim()) return;
        followUp.mutate(
          { id, command, shell: shell ?? execution?.shell ?? "sh", timeout_seconds: timeoutSeconds },
          {
            onSuccess: (next) => {
              setFollowOpen(false);
              setCommand("");
              onFollowUpStarted(next);
            },
          },
        );
      },
      submitting: followUp.isPending,
      error: followUp.error?.message ?? null,
    },
  };
}
