import { useState } from "react";
import { ApiError } from "@/lib/api";
import {
  toOffsiteTargetPayload,
  useCancelQueuedRun,
  useDeleteOffsiteTarget,
  useOffsiteBackupOverview,
  useRunOffsiteBackup,
  useSaveOffsiteTarget,
  type OffsiteBackupOverview,
  type OffsiteBackupTarget,
  type OffsiteQueueResult,
  type OffsiteTargetFormInput,
} from "@/hooks/useOffsiteBackup";

/** ViewModel Hook (§21) for System Control's "Backup externo" card (2026-10-20,
 * Marcelo: "adicione esse controle na tela Controle do sistema como backup
 * externo. onde posso adicionar outras pastas"). The card lists one target per
 * project, opens the form to add or edit one, confirms removal, and queues runs:
 * every enabled target, the selected ones, or one row (2026-10-21: "posso fazer
 * de todos em fila ou individual"). A run asked for while a backup is going
 * waits its turn in the queue rather than being refused. */
export type OffsiteBackupStatus = "loading" | "ready" | "submitting" | "error";

/** A target whose newest good snapshot is older than this is flagged: the
 * schedule is daily, so one missed night already deserves a look. */
export const OFFSITE_STALE_AFTER_MS = 36 * 60 * 60 * 1000;

export type OffsiteDialog = { mode: "create" } | { mode: "edit"; target: OffsiteBackupTarget };

/** `code` picks the translated message; `detail` carries what the server named. */
export interface OffsiteError {
  code: "missing" | "duplicate" | "notQueued" | "load" | "generic";
  detail: string;
}

export interface OffsiteBackupViewModel {
  status: OffsiteBackupStatus;
  data?: OffsiteBackupOverview;
  refreshing: boolean;
  loadError?: OffsiteError;
  dialog: OffsiteDialog | null;
  formError?: OffsiteError;
  saving: boolean;
  deleting: OffsiteBackupTarget | null;
  actionError?: OffsiteError;
  queueResult: OffsiteQueueResult | null;
  /** "all", "selected" or a target name while that request is in flight. */
  queueing: string | null;
  historyFor: string | null;
  enabledCount: number;
  selected: Set<string>;
  selectableNames: string[];
  isStale(target: OffsiteBackupTarget): boolean;
  /** Queued or running: asking for it again would be a no-op. */
  isInQueue(target: OffsiteBackupTarget): boolean;
  refresh(): void;
  openCreate(): void;
  openEdit(target: OffsiteBackupTarget): void;
  closeDialog(): void;
  submit(input: OffsiteTargetFormInput): Promise<void>;
  toggleEnabled(target: OffsiteBackupTarget): Promise<void>;
  requestDelete(target: OffsiteBackupTarget): void;
  cancelDelete(): void;
  confirmDelete(): Promise<void>;
  toggleSelected(target: OffsiteBackupTarget): void;
  toggleSelectAll(): void;
  runAll(): Promise<void>;
  runSelected(): Promise<void>;
  runTarget(target: OffsiteBackupTarget): Promise<void>;
  cancelQueued(target: OffsiteBackupTarget): Promise<void>;
  toggleHistory(target: OffsiteBackupTarget): void;
  dismissNotice(): void;
}

export function toOffsiteError(error: unknown): OffsiteError {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail;
    if (detail && typeof detail === "object" && "missing" in detail) {
      return { code: "missing", detail: ((detail as { missing: string[] }).missing ?? []).join(", ") };
    }
    if (error.status === 409) {
      const text = typeof detail === "string" ? detail : "";
      return { code: /queued run/i.test(text) ? "notQueued" : "duplicate", detail: text };
    }
    if (typeof detail === "string") return { code: "generic", detail };
    if (Array.isArray(detail)) {
      return { code: "generic", detail: detail.map((d) => (d as { msg?: string }).msg ?? "").filter(Boolean).join("; ") };
    }
    if (detail && typeof detail === "object" && "message" in detail) {
      return { code: "generic", detail: String((detail as { message: unknown }).message) };
    }
    return { code: "generic", detail: error.message };
  }
  return { code: "generic", detail: error instanceof Error ? error.message : String(error) };
}

function inQueue(target: OffsiteBackupTarget): boolean {
  return target.last_run?.status === "queued" || target.last_run?.status === "running";
}

export function useOffsiteBackupViewModel(): OffsiteBackupViewModel {
  const overview = useOffsiteBackupOverview();
  const save = useSaveOffsiteTarget();
  const remove = useDeleteOffsiteTarget();
  const runBackup = useRunOffsiteBackup();
  const cancelRun = useCancelQueuedRun();
  const [dialog, setDialog] = useState<OffsiteDialog | null>(null);
  const [formError, setFormError] = useState<OffsiteError>();
  const [deleting, setDeleting] = useState<OffsiteBackupTarget | null>(null);
  const [actionError, setActionError] = useState<OffsiteError>();
  const [queueResult, setQueueResult] = useState<OffsiteQueueResult | null>(null);
  const [queueing, setQueueing] = useState<string | null>(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);
  const [selectedRaw, setSelected] = useState<Set<string>>(new Set());

  const targets = overview.data?.targets ?? [];
  // Only enabled targets can be queued; one that was disabled or removed
  // after being ticked silently leaves the selection.
  const selectableNames = targets.filter((t) => t.enabled).map((t) => t.name);
  const selected = new Set([...selectedRaw].filter((name) => selectableNames.includes(name)));
  const submitting = save.isPending || remove.isPending || runBackup.isPending || cancelRun.isPending;

  let status: OffsiteBackupStatus;
  if (overview.isLoading) status = "loading";
  else if (submitting) status = "submitting";
  else if (actionError || overview.isError) status = "error";
  else status = "ready";

  async function enqueue(names: string[], marker: string) {
    setActionError(undefined);
    setQueueResult(null);
    setQueueing(marker);
    try {
      setQueueResult(await runBackup.mutateAsync(names));
      if (marker === "selected") setSelected(new Set());
    } catch (error) {
      setActionError(toOffsiteError(error));
    } finally {
      setQueueing(null);
    }
  }

  return {
    status,
    data: overview.data,
    refreshing: overview.isFetching,
    loadError: overview.isError ? { code: "load", detail: toOffsiteError(overview.error).detail } : undefined,
    dialog,
    formError,
    saving: save.isPending,
    deleting,
    actionError,
    queueResult,
    queueing,
    historyFor,
    enabledCount: selectableNames.length,
    selected,
    selectableNames,
    isStale(target) {
      if (!target.enabled) return false;
      const finished = target.last_success?.finished_at;
      return !finished || Date.now() - new Date(finished).getTime() > OFFSITE_STALE_AFTER_MS;
    },
    isInQueue: inQueue,
    refresh: () => void overview.refetch(),
    openCreate() {
      setFormError(undefined);
      setDialog({ mode: "create" });
    },
    openEdit(target) {
      setFormError(undefined);
      setDialog({ mode: "edit", target });
    },
    closeDialog() {
      if (save.isPending) return;
      setDialog(null);
      setFormError(undefined);
    },
    async submit(input) {
      setFormError(undefined);
      try {
        await save.mutateAsync({
          id: dialog?.mode === "edit" ? dialog.target.id : undefined,
          payload: {
            ...toOffsiteTargetPayload(input),
            sort_order: dialog?.mode === "edit" ? dialog.target.sort_order : nextSortOrder(targets),
          },
        });
        setDialog(null);
      } catch (error) {
        setFormError(toOffsiteError(error));
      }
    },
    async toggleEnabled(target) {
      setActionError(undefined);
      try {
        await save.mutateAsync({
          id: target.id,
          payload: {
            label: target.label,
            paths: target.paths,
            excludes: target.excludes,
            postgres_container: target.postgres_container,
            include_system_state: target.include_system_state,
            enabled: !target.enabled,
            sort_order: target.sort_order,
          },
        });
      } catch (error) {
        setActionError(toOffsiteError(error));
      }
    },
    requestDelete(target) {
      setActionError(undefined);
      setDeleting(target);
    },
    cancelDelete() {
      if (!remove.isPending) setDeleting(null);
    },
    async confirmDelete() {
      if (!deleting) return;
      try {
        await remove.mutateAsync(deleting.id);
        if (historyFor === deleting.name) setHistoryFor(null);
        setDeleting(null);
      } catch (error) {
        setDeleting(null);
        setActionError(toOffsiteError(error));
      }
    },
    toggleSelected(target) {
      if (!target.enabled) return;
      setSelected((current) => {
        const next = new Set(current);
        if (next.has(target.name)) next.delete(target.name);
        else next.add(target.name);
        return next;
      });
    },
    toggleSelectAll() {
      setSelected(selected.size === selectableNames.length ? new Set() : new Set(selectableNames));
    },
    runAll: () => enqueue([], "all"),
    // In the order the targets are listed, not the order they were ticked.
    runSelected: () => enqueue(selectableNames.filter((name) => selected.has(name)), "selected"),
    runTarget: (target) => enqueue([target.name], target.name),
    async cancelQueued(target) {
      if (target.last_run?.status !== "queued") return;
      setActionError(undefined);
      try {
        await cancelRun.mutateAsync(target.last_run.id);
      } catch (error) {
        setActionError(toOffsiteError(error));
      }
    },
    toggleHistory(target) {
      setHistoryFor((current) => (current === target.name ? null : target.name));
    },
    dismissNotice() {
      setQueueResult(null);
      setActionError(undefined);
    },
  };
}

function nextSortOrder(targets: OffsiteBackupTarget[]): number {
  return targets.reduce((max, t) => Math.max(max, t.sort_order), 0) + 10;
}
