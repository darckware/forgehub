import { useState } from "react";
import {
  useAgentAccessControl, useDirectAgents, usePauseAgentAccess, useRemoveDirectAgent, useResumeAgentAccess,
  type AgentAccessControl, type DirectAgent, type DirectAgentRemoved,
} from "@/hooks/useDirectAccess";
import { ApiError } from "@/lib/api";

/** The backend's refusal, worded: a string detail, or a detail's message. */
export function refusalText(error: unknown): string {
  const detail = error instanceof ApiError ? (error.body as { detail?: unknown } | null)?.detail : null;
  if (typeof detail === "string") return detail;
  const message = (detail as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : (error as Error).message;
}

/** The list of agents that may get a direct access, and the pause of every
 * agent's access to machines. Who can be added and why not comes from the backend,
 * which reads each runtime's own configuration. The switch starts unknown:
 * until it answers, nothing here offers a pause or an opening. */
export interface DirectAgentsViewModel {
  status: "loading" | "ready" | "confirming" | "submitting" | "error";
  control: AgentAccessControl | null;
  paused: boolean;
  listed: DirectAgent[];
  addable: DirectAgent[];
  unsupported: DirectAgent[];
  removing: DirectAgent | null;
  askRemove: (agent: DirectAgent) => void;
  cancelRemove: () => void;
  confirmRemove: () => Promise<void>;
  removePending: boolean;
  /** What the last removal closed; null before any. */
  removed: DirectAgentRemoved | null;
  confirmingPause: boolean;
  askPause: () => void;
  cancelPause: () => void;
  pauseReason: string;
  setPauseReason: (value: string) => void;
  confirmPause: () => Promise<void>;
  pausePending: boolean;
  resume: () => Promise<void>;
  resumePending: boolean;
  error: string | null;
  retry: () => void;
}

export function useDirectAgentsViewModel(): DirectAgentsViewModel {
  const agents = useDirectAgents();
  const control = useAgentAccessControl();
  const removeMutation = useRemoveDirectAgent();
  const pauseMutation = usePauseAgentAccess();
  const resumeMutation = useResumeAgentAccess();

  const [removing, setRemoving] = useState<DirectAgent | null>(null);
  const [removed, setRemoved] = useState<DirectAgentRemoved | null>(null);
  const [confirmingPause, setConfirmingPause] = useState(false);
  const [pauseReason, setPauseReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const rows = agents.data ?? [];
  const submitting = removeMutation.isPending || pauseMutation.isPending || resumeMutation.isPending;
  const status = agents.isLoading || control.isLoading ? "loading" : submitting ? "submitting" : error ? "error"
    : removing || confirmingPause ? "confirming" : "ready";
  const attempt = async (action: () => Promise<void>) => {
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(refusalText(e));
    }
  };

  return {
    status,
    control: control.data ?? null,
    paused: control.data?.paused ?? false,
    listed: rows.filter((a) => a.allowed),
    addable: rows.filter((a) => !a.allowed && !a.unsupported_reason),
    unsupported: rows.filter((a) => !a.allowed && a.unsupported_reason),
    removing,
    askRemove: (agent) => { setError(null); setRemoved(null); setRemoving(agent); },
    cancelRemove: () => setRemoving(null),
    confirmRemove: () => attempt(async () => {
      if (!removing) return;
      setRemoved(await removeMutation.mutateAsync(removing.id));
      setRemoving(null);
    }),
    removePending: removeMutation.isPending,
    removed,
    confirmingPause,
    askPause: () => { setError(null); setPauseReason(""); setConfirmingPause(true); },
    cancelPause: () => setConfirmingPause(false),
    pauseReason,
    setPauseReason,
    confirmPause: () => attempt(async () => {
      await pauseMutation.mutateAsync(pauseReason.trim());
      setConfirmingPause(false);
    }),
    pausePending: pauseMutation.isPending,
    resume: () => attempt(async () => { await resumeMutation.mutateAsync(); }),
    resumePending: resumeMutation.isPending,
    error: error ?? (agents.error ? refusalText(agents.error) : control.error ? refusalText(control.error) : null),
    retry: () => { void agents.refetch(); void control.refetch(); },
  };
}
