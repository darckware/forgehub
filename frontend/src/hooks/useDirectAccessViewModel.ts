import { useEffect, useState } from "react";
import { useAgents, type Agent } from "@/hooks/useAgent";
import {
  DIRECT_RUNTIMES, useCloseDirectAccess, useDirectAccesses, useOpenDirectAccess,
  type DirectAccess, type DirectDuration, type DirectPurpose,
} from "@/hooks/useDirectAccess";
import { useHostGroups } from "@/hooks/useHostInventory";
import { useServers } from "@/hooks/useServers";
import { ApiError } from "@/lib/api";

const MIN_REASON = 5;

/** "Acesso direto" (Remote Access › Machines). idle -> opening -> submitting,
 * and -> confirming when the backend says the selection has sensitive machines:
 * it alone resolves groups and decides what is sensitive, so the warning names
 * what it answered. Any change to the form drops that confirmation. */
export interface DirectAccessViewModel {
  status: "loading" | "idle" | "opening" | "confirming" | "submitting" | "error";
  active: DirectAccess[];
  now: number;
  eligible: Agent[];
  machines: { id: string; name: string }[];
  groups: { id: string; name: string }[];
  formOpen: boolean;
  openForm: () => void;
  closeForm: () => void;
  agentId: string;
  setAgentId: (id: string) => void;
  selectedMachines: Set<string>;
  selectedGroups: Set<string>;
  toggleMachine: (id: string) => void;
  toggleGroup: (id: string) => void;
  reason: string;
  setReason: (value: string) => void;
  purpose: DirectPurpose;
  setPurpose: (value: DirectPurpose) => void;
  hours: DirectDuration;
  setHours: (value: DirectDuration) => void;
  allowElevation: boolean;
  setAllowElevation: (value: boolean) => void;
  /** Sensitive machines awaiting the one-click confirmation. */
  sensitive: string[] | null;
  canSubmit: boolean;
  submit: () => Promise<void>;
  closing: DirectAccess | null;
  askClose: (access: DirectAccess) => void;
  cancelClose: () => void;
  confirmClose: () => Promise<void>;
  closePending: boolean;
  /** Commands still running on the access just closed; null before any close. */
  stillRunning: number | null;
  error: string | null;
}

function sensitiveMachines(error: unknown): string[] | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const detail = (error.body as { detail?: { code?: string; machines?: string[] } } | null)?.detail;
  return detail?.code === "SENSITIVE_CONFIRMATION_REQUIRED" ? detail.machines ?? [] : null;
}

/** The refusal ForgeHub wrote (literal secret in the reason, agent not eligible...). */
function refusalText(error: unknown): string {
  const detail = error instanceof ApiError ? (error.body as { detail?: unknown } | null)?.detail : null;
  if (typeof detail === "string") return detail;
  const message = (detail as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : (error as Error).message;
}

export function useDirectAccessViewModel(): DirectAccessViewModel {
  const accesses = useDirectAccesses();
  const agents = useAgents();
  const servers = useServers();
  const hostGroups = useHostGroups();
  const openMutation = useOpenDirectAccess();
  const closeMutation = useCloseDirectAccess();

  const [now, setNow] = useState(() => Date.now());
  const [formOpen, setFormOpen] = useState(false);
  const [agentId, setAgent] = useState("");
  const [selectedMachines, setSelectedMachines] = useState<Set<string>>(new Set());
  const [selectedGroups, setSelectedGroups] = useState<Set<string>>(new Set());
  const [reason, setReasonText] = useState("");
  const [purpose, setPurposeValue] = useState<DirectPurpose>("support");
  const [hours, setHoursValue] = useState<DirectDuration>(1);
  const [allowElevation, setElevation] = useState(false);
  const [sensitive, setSensitive] = useState<string[] | null>(null);
  const [closing, setClosing] = useState<DirectAccess | null>(null);
  const [stillRunning, setStillRunning] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);

  const edited = <T,>(setter: (value: T) => void) => (value: T) => { setSensitive(null); setter(value); };
  const toggle = (setter: typeof setSelectedMachines, id: string) => {
    setSensitive(null);
    setter((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const eligible = (agents.data ?? [])
    .filter((a) => a.is_active && a.status === "active" && DIRECT_RUNTIMES.includes(a.runtime_type ?? ""))
    .sort((a, b) => a.name.localeCompare(b.name));
  const submitting = openMutation.isPending;
  const complete = Boolean(agentId) && (selectedMachines.size > 0 || selectedGroups.size > 0)
    && reason.trim().length >= MIN_REASON;
  const status = accesses.isLoading ? "loading" : submitting ? "submitting" : error ? "error"
    : sensitive ? "confirming" : formOpen ? "opening" : "idle";

  return {
    status,
    active: (accesses.data ?? []).filter((a) => new Date(a.expires_at).getTime() > now),
    now,
    eligible,
    machines: servers.data ?? [],
    groups: hostGroups.data ?? [],
    formOpen,
    openForm: () => {
      setError(null); setStillRunning(null); setSensitive(null); setAgent(""); setReasonText("");
      setSelectedMachines(new Set()); setSelectedGroups(new Set());
      setPurposeValue("support"); setHoursValue(1); setElevation(false); setNow(Date.now()); setFormOpen(true);
    },
    closeForm: () => setFormOpen(false),
    agentId,
    setAgentId: edited(setAgent),
    selectedMachines,
    selectedGroups,
    toggleMachine: (id) => toggle(setSelectedMachines, id),
    toggleGroup: (id) => toggle(setSelectedGroups, id),
    reason,
    setReason: edited(setReasonText),
    purpose,
    setPurpose: edited(setPurposeValue),
    hours,
    setHours: edited(setHoursValue),
    allowElevation,
    setAllowElevation: edited(setElevation),
    sensitive,
    canSubmit: complete && !submitting,
    submit: async () => {
      if (!complete || submitting) return;
      setError(null);
      try {
        await openMutation.mutateAsync({
          agent_id: agentId, server_ids: [...selectedMachines], group_ids: [...selectedGroups], reason: reason.trim(),
          purpose, duration_hours: hours, allow_elevation: allowElevation, confirm_sensitive: sensitive !== null,
        });
        setSensitive(null);
        setFormOpen(false);
      } catch (e) {
        const machines = sensitiveMachines(e);
        if (machines) setSensitive(machines);
        else setError(refusalText(e));
      }
    },
    closing,
    askClose: (access) => { setError(null); setStillRunning(null); setClosing(access); },
    cancelClose: () => setClosing(null),
    confirmClose: async () => {
      if (!closing) return;
      try {
        const closed = await closeMutation.mutateAsync(closing.id);
        setStillRunning(closed.running_commands);
        setClosing(null);
      } catch (e) {
        setError(refusalText(e));
      }
    },
    closePending: closeMutation.isPending,
    stillRunning,
    error,
  };
}
