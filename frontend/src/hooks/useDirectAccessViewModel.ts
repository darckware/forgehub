import { useEffect, useRef, useState } from "react";
import { useConfigureDirectAgent, useDirectAgents, type DirectAccessInput, type DirectAgent, type DirectDuration, type DirectPurpose } from "@/hooks/useDirectAccess";
import { useHostGroups } from "@/hooks/useHostInventory";
import { useServers } from "@/hooks/useServers";
import { ApiError } from "@/lib/api";

export function refusalText(error: unknown): string {
  const detail = error instanceof ApiError ? (error.body as { detail?: unknown } | null)?.detail : null;
  if (typeof detail === "string") return detail;
  const message = (detail as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : (error as Error).message;
}

/** Inline editor preserves its own draft while background queries refresh. Sensitive
 * coverage is resolved by the backend; any edit cancels the previous confirmation. */
export function useDirectAccessViewModel() {
  const agents = useDirectAgents();
  const servers = useServers();
  const groups = useHostGroups();
  const mutation = useConfigureDirectAgent();
  const [editing, setEditing] = useState<DirectAgent | null>(null);
  const [allMachines, setAll] = useState(true);
  const [selectedMachines, setMachines] = useState<Set<string>>(new Set());
  const [selectedGroups, setGroups] = useState<Set<string>>(new Set());
  const [purpose, setPurpose] = useState<DirectPurpose | "">("");
  const [reason, setReason] = useState("");
  const [hours, setHours] = useState<DirectDuration>(0);
  const [allowElevation, setElevation] = useState(false);
  const [confirmation, setConfirmation] = useState<{ all: boolean; machines: string[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now);
  const submitting = useRef(false);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 30_000); return () => clearInterval(timer); }, []);
  const edited = <T,>(setter: (value: T) => void) => (value: T) => { setConfirmation(null); setter(value); };
  const toggle = (setter: typeof setMachines, id: string) => { setConfirmation(null); setter((old) => { const next = new Set(old); if (next.has(id)) next.delete(id); else next.add(id); return next; }); };
  const inventoryError = Boolean(servers.error || groups.error);
  const canSubmit = Boolean(editing) && !mutation.isPending && !servers.isLoading && !groups.isLoading && !inventoryError;
  const submit = async (confirmed = false) => {
    if (!editing || !canSubmit || submitting.current) return;
    submitting.current = true;
    setError(null);
    const input: DirectAccessInput = { all_machines: allMachines, server_ids: allMachines ? [] : [...selectedMachines], group_ids: allMachines ? [] : [...selectedGroups], reason: reason.trim() || null, purpose: purpose || null, duration_hours: hours, allow_elevation: allowElevation, confirm_sensitive: confirmed && confirmation !== null };
    try { await mutation.mutateAsync({ agentId: editing.id, input }); setSaved(editing.name); setEditing(null); setConfirmation(null); }
    catch (e) {
      const detail = e instanceof ApiError && e.status === 409 ? (e.body as { detail?: { code?: string; all_machines?: boolean; machines?: string[] } })?.detail : null;
      if (detail?.code === "SENSITIVE_CONFIRMATION_REQUIRED") setConfirmation({ all: Boolean(detail.all_machines), machines: detail.machines ?? [] });
      else setError(refusalText(e));
    } finally { submitting.current = false; }
  };
  return {
    agents: agents.data ?? [], loading: agents.isLoading, now, editing,
    open: (agent: DirectAgent) => {
      const config = agent.configuration; setEditing(agent); setError(null); setSaved(null); setConfirmation(null);
      setAll(config?.all_machines ?? true); setMachines(new Set(config?.machines.map((m) => m.id) ?? [])); setGroups(new Set());
      setPurpose(config?.purpose ?? ""); setReason(config?.reason ?? ""); setHours(config?.duration_hours ?? 0); setElevation(config?.allow_elevation ?? false);
    },
    close: () => { if (!mutation.isPending) { setEditing(null); setConfirmation(null); } },
    allMachines, setAllMachines: edited(setAll), selectedMachines, selectedGroups,
    toggleMachine: (id: string) => toggle(setMachines, id), toggleGroup: (id: string) => toggle(setGroups, id),
    machines: servers.data ?? [], groups: groups.data ?? [],
    inventoryError, inventoryLoading: servers.isLoading || groups.isLoading,
    retryInventory: () => { void servers.refetch(); void groups.refetch(); },
    purpose, setPurpose: edited(setPurpose), reason, setReason: edited(setReason), hours, setHours: edited(setHours),
    allowElevation, setAllowElevation: edited(setElevation), confirmation, cancelConfirmation: () => setConfirmation(null),
    error, saved, submit, pending: mutation.isPending, canSubmit,
  };
}
