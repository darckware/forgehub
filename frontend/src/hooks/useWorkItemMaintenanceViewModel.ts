import { useMemo, useState } from "react";
import { z } from "zod";
import {
  useClientOpsText,
  useRecordWorkItemMaintenance,
  useSettleWorkItemMaintenance,
  useWorkItemMaintenance,
  type WorkItemDetail,
  type WorkItemMaintenance,
  type WorkItemMaintenanceTask,
} from "@/hooks/useClientOps";
import { useServers, type Server } from "@/hooks/useServers";

/** Why "Pedir manutenção ao agente" is off; null = it can open. */
export type AskBlock = "noClient" | "noMachines" | "loading" | null;

export type RecordMode = "log_time" | "resolve";

export interface MaintenanceDraft {
  demandId: string;
  number: number;
  note: string;
  minutes: string;
  serviceType: "remoto" | "presencial";
  mode: RecordMode;
  proposedMinutes: number;
  /** The time entry is dated at the last run's end. */
  endTime: string | null;
}

export interface SettleDraft {
  demandId: string;
  number: number;
  outcome: "recorded" | "discard" | null;
  reason: string;
  attempt: NonNullable<WorkItemMaintenanceTask["uncertain"]>;
}

export const maintenanceRecordSchema = z.object({
  note: z.string().trim().min(1, "noteRequired").max(4000, "noteTooLong"),
  minutes: z.coerce.number().int("minutesInvalid").min(1, "minutesInvalid").max(24 * 60, "minutesInvalid"),
});

const OPEN_STAGES = new Set(["novo", "em_andamento", "aguardando_cliente"]);

/** An existing entry on the item that looks like the uncertain attempt
 * (same description: the note, or "Solução: <note>" for a resolve). Only a
 * hint for the operator -- never decides anything by itself. */
export function looksRecorded(detail: WorkItemDetail | undefined, attempt: { note: string } | null | undefined): boolean {
  if (!detail || !attempt?.note) return false;
  const note = attempt.note.trim();
  return (detail.time_entries ?? []).some((e) => {
    const d = (e.description ?? "").trim();
    return d === note || d === `Solução: ${note}`.slice(0, 4000);
  });
}

/** "Manutenção remota" on a client ticket/demand (remote-access support plan,
 * Fase 3, 2026-11-12). Three flows:
 *  - ask: "Pedir manutenção ao agente" opens the Remote Access "Pedir ao
 *    agente" panel with the client's machines (none ticked) and the item;
 *  - record: per finished agent task the backend *proposes* a client-facing
 *    note and minutes; the operator edits them, picks "Registrar horas" or
 *    "Registrar e dar baixa", confirms, and only then ForgeHub writes to
 *    Darckware (once per task);
 *  - settle: an attempt whose outcome is unknown (409
 *    MAINTENANCE_RECORD_UNCERTAIN) is closed by the operator after checking
 *    the item's hours: "foi registrado" or "descartar tentativa".
 * Record/settle flow: idle -> editing -> confirming -> submitting -> success | error. */
export interface WorkItemMaintenanceViewModel {
  data: WorkItemMaintenance | undefined;
  loading: boolean;
  loadError?: string;
  clientMachines: Server[];
  askBlock: AskBlock;
  asking: boolean;
  openAsk: () => void;
  closeAsk: () => void;
  /** "Registrar e dar baixa" only while the item is still open. */
  canResolve: boolean;
  /** The item's existing time entries (Darckware), shown before recording. */
  timeEntries: WorkItemDetail["time_entries"];
  timeEntriesHours: number;
  status: "idle" | "editing" | "confirming" | "submitting" | "success" | "error";
  draft: MaintenanceDraft | null;
  /** Which view of the open panel: the editable proposal or the confirmation. */
  step: "editing" | "confirming";
  draftError?: string;
  openRecord: (task: WorkItemMaintenanceTask) => void;
  updateDraft: (patch: Partial<Pick<MaintenanceDraft, "note" | "minutes" | "serviceType">>) => void;
  /** Editing -> confirming with the chosen action. */
  review: (mode: RecordMode) => void;
  back: () => void;
  confirm: () => void;
  closeRecord: () => void;
  settle: SettleDraft | null;
  /** The item already holds an entry with the attempt's text (hint only). */
  settleLooksRecorded: boolean;
  openSettle: (task: WorkItemMaintenanceTask) => void;
  updateSettle: (patch: Partial<Pick<SettleDraft, "outcome" | "reason">>) => void;
  canSubmitSettle: boolean;
  confirmSettle: () => void;
  closeSettle: () => void;
  successKind: "recorded" | "settled" | null;
  errorMessage?: string;
}

export function useWorkItemMaintenanceViewModel(detail: WorkItemDetail | undefined): WorkItemMaintenanceViewModel {
  const { errorText } = useClientOpsText();
  const query = useWorkItemMaintenance(detail?.kind, detail?.id);
  const servers = useServers();
  const record = useRecordWorkItemMaintenance();
  const settleMutation = useSettleWorkItemMaintenance();
  const [asking, setAsking] = useState(false);
  const [draft, setDraft] = useState<MaintenanceDraft | null>(null);
  const [settle, setSettle] = useState<SettleDraft | null>(null);
  const [step, setStep] = useState<"editing" | "confirming">("editing");
  const [errorMessage, setErrorMessage] = useState<string>();
  const [successKind, setSuccessKind] = useState<"recorded" | "settled" | null>(null);

  const clientId = detail?.client_account_id ?? "";
  const clientMachines = useMemo(
    () => (clientId ? (servers.data ?? []).filter((s) => s.darckware_client_id === clientId) : []),
    [servers.data, clientId],
  );
  let askBlock: AskBlock = null;
  if (!clientId) askBlock = "noClient";
  else if (servers.isLoading) askBlock = "loading";
  else if (clientMachines.length === 0) askBlock = "noMachines";

  const parsed = draft ? maintenanceRecordSchema.safeParse({ note: draft.note, minutes: draft.minutes }) : null;
  const draftError = parsed && !parsed.success ? parsed.error.issues[0]?.message : undefined;
  const timeEntries = detail?.time_entries ?? [];
  const pending = record.isPending || settleMutation.isPending;

  let status: WorkItemMaintenanceViewModel["status"] = "idle";
  if (pending) status = "submitting";
  else if (errorMessage) status = "error";
  else if (draft || settle) status = step;
  else if (successKind) status = "success";

  const reset = () => {
    setStep("editing");
    setErrorMessage(undefined);
  };

  return {
    data: query.data,
    loading: query.isLoading,
    loadError: query.isError ? errorText(query.error) : undefined,
    clientMachines,
    askBlock,
    asking,
    openAsk: () => {
      if (askBlock === null) setAsking(true);
    },
    closeAsk: () => setAsking(false),
    canResolve: Boolean(detail && OPEN_STAGES.has(detail.stage)),
    timeEntries,
    timeEntriesHours: timeEntries.reduce((sum, e) => sum + (Number(e.billable_hours) || 0), 0),
    status,
    draft,
    step,
    draftError,
    openRecord: (task) => {
      if (!task.proposal) return;
      setSettle(null);
      setDraft({
        demandId: task.demand_id,
        number: task.number,
        note: task.proposal.note,
        minutes: String(task.proposal.minutes),
        serviceType: "remoto",
        mode: "log_time",
        proposedMinutes: task.proposal.minutes,
        endTime: task.proposal.end_time,
      });
      reset();
      setSuccessKind(null);
    },
    updateDraft: (patch) => setDraft((cur) => (cur ? { ...cur, ...patch } : cur)),
    review: (mode) => {
      if (!draft || draftError) return;
      if (mode === "resolve" && !(detail && OPEN_STAGES.has(detail.stage))) return;
      setDraft({ ...draft, mode });
      setStep("confirming");
      setErrorMessage(undefined);
    },
    back: reset,
    confirm: () => {
      if (!detail || !draft || draftError || pending) return;
      record.mutate(
        {
          kind: detail.kind,
          id: detail.id,
          demandId: draft.demandId,
          mode: draft.mode,
          note: draft.note.trim(),
          minutes: Number(draft.minutes),
          serviceType: draft.serviceType,
        },
        {
          onSuccess: () => {
            setSuccessKind("recorded");
            setDraft(null);
            setStep("editing");
          },
          onError: (error) => setErrorMessage(errorText(error)),
        },
      );
    },
    closeRecord: () => {
      if (pending) return;
      setDraft(null);
      reset();
    },
    settle,
    settleLooksRecorded: looksRecorded(detail, settle?.attempt),
    openSettle: (task) => {
      if (!task.uncertain) return;
      setDraft(null);
      setSettle({ demandId: task.demand_id, number: task.number, outcome: null, reason: "", attempt: task.uncertain });
      reset();
      setSuccessKind(null);
    },
    updateSettle: (patch) => setSettle((cur) => (cur ? { ...cur, ...patch } : cur)),
    canSubmitSettle: Boolean(settle?.outcome && settle.reason.trim().length >= 5 && !pending),
    confirmSettle: () => {
      if (!detail || !settle?.outcome || settle.reason.trim().length < 5 || pending) return;
      settleMutation.mutate(
        { kind: detail.kind, id: detail.id, demandId: settle.demandId, outcome: settle.outcome, reason: settle.reason.trim() },
        {
          onSuccess: () => {
            setSuccessKind("settled");
            setSettle(null);
          },
          onError: (error) => setErrorMessage(errorText(error)),
        },
      );
    },
    closeSettle: () => {
      if (pending) return;
      setSettle(null);
      reset();
    },
    successKind,
    errorMessage,
  };
}
