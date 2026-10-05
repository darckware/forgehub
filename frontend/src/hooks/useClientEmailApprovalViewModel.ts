import { useState } from "react";
import {
  useClientOpsText,
  useApproveOutboundEmail,
  useCancelOutboundEmail,
  useOutboundEmail,
  useOutboundEmails,
  useRejectOutboundEmail,
  useUpdateOutboundEmail,
  type OutboundEmail,
} from "@/hooks/useClientOps";

/**
 * ViewModel Hook (§21) for the client e-mail approval screen (2026-10-04).
 *
 * Every e-mail to a client waits in Darckware's queue until approved here,
 * and an approval is for the exact text shown: `approve` sends the version
 * and hash of the detail being displayed, so an edit made elsewhere in the
 * meantime comes back as a 409 instead of approving text nobody read. Editing
 * creates a new version, which needs approving again.
 */
export type EmailApprovalStatus =
  | "loading"
  | "ready"
  | "editing"
  | "confirming"
  | "rejecting"
  | "cancelling"
  | "submitting"
  | "error";

export type EmailListFilter = "pending" | "aprovado" | "enviado" | "all";

const FILTER_STATUS: Record<EmailListFilter, string | undefined> = {
  pending: "aguardando_aprovacao,falhou,envio_incerto",
  aprovado: "aprovado,enviando",
  enviado: "enviado",
  all: undefined,
};

export interface EmailApprovalViewModel {
  status: EmailApprovalStatus;
  filter: EmailListFilter;
  emails: OutboundEmail[];
  loadError?: string;
  selectedId?: string;
  selected?: OutboundEmail;
  /** Which confirmation is open -- stays set while its request is in flight,
   * so the dialog can show its spinner instead of closing early. */
  dialog?: "approve" | "reject" | "cancel";
  /** Edit form open -- independent of `status`, which reads "submitting" while it saves. */
  editing: boolean;
  detailLoading: boolean;
  draft: { subject: string; body_text: string; to_email: string };
  rejectReason: string;
  errorMessage?: string;
  canApprove: boolean;
  canEdit: boolean;
  setFilter(filter: EmailListFilter): void;
  select(id: string | undefined): void;
  startEdit(): void;
  setDraft(patch: Partial<EmailApprovalViewModel["draft"]>): void;
  cancelEdit(): void;
  saveEdit(): Promise<void>;
  requestApprove(): void;
  confirmApprove(): Promise<void>;
  requestReject(): void;
  setRejectReason(reason: string): void;
  confirmReject(): Promise<void>;
  requestCancel(): void;
  confirmCancel(): Promise<void>;
  dismiss(): void;
}

const APPROVABLE = new Set(["aguardando_aprovacao", "falhou", "envio_incerto"]);
const EDITABLE = new Set(["rascunho", "aguardando_aprovacao", "aprovado", "falhou", "envio_incerto"]);

/** `initialId` comes from a deep link (`/client-emails?id=`): open on that e-mail,
 * in the "all" list so it is found whatever its status. */
export function useClientEmailApprovalViewModel(initialId?: string): EmailApprovalViewModel {
  const { errorText } = useClientOpsText();
  const [filter, setFilter] = useState<EmailListFilter>(initialId ? "all" : "pending");
  const [selectedId, setSelectedId] = useState<string | undefined>(initialId);
  const [mode, setMode] = useState<"view" | "editing" | "confirming" | "rejecting" | "cancelling">("view");
  const [draft, setDraftState] = useState({ subject: "", body_text: "", to_email: "" });
  const [rejectReason, setRejectReason] = useState("");
  const [errorMessage, setErrorMessage] = useState<string>();

  const list = useOutboundEmails(FILTER_STATUS[filter]);
  const detail = useOutboundEmail(selectedId);
  const update = useUpdateOutboundEmail();
  const approve = useApproveOutboundEmail();
  const reject = useRejectOutboundEmail();
  const cancel = useCancelOutboundEmail();

  const selected = detail.data;
  const submitting = update.isPending || approve.isPending || reject.isPending || cancel.isPending;

  let status: EmailApprovalStatus;
  if (submitting) status = "submitting";
  else if (mode === "editing") status = "editing";
  else if (mode === "confirming") status = "confirming";
  else if (mode === "rejecting") status = "rejecting";
  else if (mode === "cancelling") status = "cancelling";
  else if (errorMessage) status = "error";
  else if (list.isLoading) status = "loading";
  else status = "ready";

  /** Runs a request; a failed save keeps the edit form open so the text isn't lost. */
  async function run(action: () => Promise<unknown>, modeOnError: typeof mode = "view") {
    setErrorMessage(undefined);
    try {
      await action();
      setMode("view");
    } catch (error) {
      setErrorMessage(errorText(error));
      setMode(modeOnError);
    }
  }

  return {
    status,
    filter,
    emails: list.data?.items ?? [],
    loadError: list.isError ? errorText(list.error) : undefined,
    selectedId,
    selected,
    dialog:
      mode === "confirming" ? "approve" : mode === "rejecting" ? "reject" : mode === "cancelling" ? "cancel" : undefined,
    editing: mode === "editing",
    detailLoading: detail.isLoading && Boolean(selectedId),
    draft,
    rejectReason,
    errorMessage,
    canApprove: Boolean(selected && APPROVABLE.has(selected.status)),
    canEdit: Boolean(selected && EDITABLE.has(selected.status)),
    setFilter(next) {
      setFilter(next);
      setSelectedId(undefined);
      setMode("view");
    },
    select(id) {
      setSelectedId(id);
      setMode("view");
      setErrorMessage(undefined);
    },
    startEdit() {
      if (!selected) return;
      setDraftState({ subject: selected.subject, body_text: selected.body_text, to_email: selected.to_email });
      setMode("editing");
    },
    setDraft(patch) {
      setDraftState((current) => ({ ...current, ...patch }));
    },
    cancelEdit: () => setMode("view"),
    async saveEdit() {
      if (!selected) return;
      await run(() => update.mutateAsync({ id: selected.id, ...draft }), "editing");
    },
    requestApprove() {
      if (selected && APPROVABLE.has(selected.status)) setMode("confirming");
    },
    async confirmApprove() {
      if (!selected) return;
      await run(() =>
        approve.mutateAsync({ id: selected.id, version: selected.version, body_hash: selected.body_hash }),
      );
    },
    requestReject() {
      setRejectReason("");
      setMode("rejecting");
    },
    setRejectReason,
    async confirmReject() {
      if (!selected || !rejectReason.trim()) return;
      await run(() => reject.mutateAsync({ id: selected.id, reason: rejectReason.trim() }));
    },
    requestCancel: () => setMode("cancelling"),
    async confirmCancel() {
      if (!selected) return;
      await run(() => cancel.mutateAsync(selected.id));
    },
    dismiss() {
      setErrorMessage(undefined);
      setMode("view");
    },
  };
}
