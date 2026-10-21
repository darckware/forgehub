import { useState } from "react";
import { ApiError } from "@/lib/api";
import {
  toOffsiteTargetPayload,
  useDeleteOffsiteTarget,
  useOffsiteBackupOverview,
  useRunOffsiteBackup,
  useSaveOffsiteTarget,
  type OffsiteBackupOverview,
  type OffsiteBackupTarget,
  type OffsiteTargetFormInput,
} from "@/hooks/useOffsiteBackup";

/** ViewModel Hook (§21) for System Control's "Backup externo" card (2026-10-20,
 * Marcelo: "adicione esse controle na tela Controle do sistema como backup
 * externo. onde posso adicionar outras pastas"). The card lists one target per
 * project, opens the form to add or edit one, confirms removal, and starts a
 * run of everything or of a single target. */
export type OffsiteBackupStatus = "loading" | "ready" | "submitting" | "error";

/** A target whose newest good snapshot is older than this is flagged: the
 * schedule is daily, so one missed night already deserves a look. */
export const OFFSITE_STALE_AFTER_MS = 36 * 60 * 60 * 1000;

export type OffsiteDialog = { mode: "create" } | { mode: "edit"; target: OffsiteBackupTarget };

/** `code` picks the translated message; `detail` carries what the server named. */
export interface OffsiteError {
  code: "missing" | "duplicate" | "running" | "load" | "generic";
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
  startedTargets: string[] | null;
  startingTarget: string | null | "all";
  historyFor: string | null;
  enabledCount: number;
  isStale(target: OffsiteBackupTarget): boolean;
  refresh(): void;
  openCreate(): void;
  openEdit(target: OffsiteBackupTarget): void;
  closeDialog(): void;
  submit(input: OffsiteTargetFormInput): Promise<void>;
  toggleEnabled(target: OffsiteBackupTarget): Promise<void>;
  requestDelete(target: OffsiteBackupTarget): void;
  cancelDelete(): void;
  confirmDelete(): Promise<void>;
  runAll(): Promise<void>;
  runTarget(target: OffsiteBackupTarget): Promise<void>;
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
      return { code: /already running/i.test(text) ? "running" : "duplicate", detail: text };
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

export function useOffsiteBackupViewModel(): OffsiteBackupViewModel {
  const overview = useOffsiteBackupOverview();
  const save = useSaveOffsiteTarget();
  const remove = useDeleteOffsiteTarget();
  const runBackup = useRunOffsiteBackup();
  const [dialog, setDialog] = useState<OffsiteDialog | null>(null);
  const [formError, setFormError] = useState<OffsiteError>();
  const [deleting, setDeleting] = useState<OffsiteBackupTarget | null>(null);
  const [actionError, setActionError] = useState<OffsiteError>();
  const [startedTargets, setStartedTargets] = useState<string[] | null>(null);
  const [startingTarget, setStartingTarget] = useState<string | null | "all">(null);
  const [historyFor, setHistoryFor] = useState<string | null>(null);

  const targets = overview.data?.targets ?? [];
  const submitting = save.isPending || remove.isPending || runBackup.isPending;

  let status: OffsiteBackupStatus;
  if (overview.isLoading) status = "loading";
  else if (submitting) status = "submitting";
  else if (actionError || overview.isError) status = "error";
  else status = "ready";

  async function start(names: string[], marker: string | "all") {
    setActionError(undefined);
    setStartedTargets(null);
    setStartingTarget(marker);
    try {
      const result = await runBackup.mutateAsync(names);
      setStartedTargets(result.targets);
    } catch (error) {
      setActionError(toOffsiteError(error));
    } finally {
      setStartingTarget(null);
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
    startedTargets,
    startingTarget,
    historyFor,
    enabledCount: targets.filter((t) => t.enabled).length,
    isStale(target) {
      if (!target.enabled) return false;
      const finished = target.last_success?.finished_at;
      return !finished || Date.now() - new Date(finished).getTime() > OFFSITE_STALE_AFTER_MS;
    },
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
          payload: { ...toOffsiteTargetPayload(input), sort_order: dialog?.mode === "edit" ? dialog.target.sort_order : nextSortOrder(targets) },
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
    runAll: () => start([], "all"),
    runTarget: (target) => start([target.name], target.name),
    toggleHistory(target) {
      setHistoryFor((current) => (current === target.name ? null : target.name));
    },
    dismissNotice() {
      setStartedTargets(null);
      setActionError(undefined);
    },
  };
}

function nextSortOrder(targets: OffsiteBackupTarget[]): number {
  return targets.reduce((max, t) => Math.max(max, t.sort_order), 0) + 10;
}
