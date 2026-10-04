import { useState } from "react";
import {
  useWorkItem,
  useWorkItemAction,
  useWorkItems,
  type WorkItem,
  type WorkItemAction,
  type WorkItemDetail,
  type WorkItemFilters,
  type WorkItemKind,
} from "@/hooks/useClientOps";

/**
 * ViewModel Hook (§21) for the client demands screen (2026-10-04).
 *
 * One list over Darckware's tickets and demands. A status action ("aguardando
 * cliente", "dar baixa", ...) can carry an e-mail to the customer -- it is
 * only queued for approval, never sent from here, which is why the dialog
 * says "queue e-mail" rather than "send".
 */
export type ClientDemandsStatus = "loading" | "ready" | "acting" | "submitting" | "error";

/** Actions available per stage -- the screen never offers a transition the stage can't take. */
export const ACTIONS_BY_STAGE: Record<string, WorkItemAction[]> = {
  novo: ["start", "wait-customer", "resolve"],
  em_andamento: ["wait-customer", "resolve"],
  aguardando_cliente: ["start", "resolve"],
  resolvido: ["reopen"],
  fechado: ["reopen"],
};

/** Actions whose dialog offers an e-mail, and whether the text field is mandatory. */
export const ACTION_EMAIL: Record<WorkItemAction, boolean> = {
  start: false,
  "wait-customer": true,
  resolve: true,
  reopen: false,
};
export const ACTION_TEXT_REQUIRED: Record<WorkItemAction, boolean> = {
  start: false,
  "wait-customer": false,
  resolve: true,
  reopen: true,
};

export interface ActionDraft {
  action: WorkItemAction;
  text: string;
  withEmail: boolean;
  subject: string;
  body_text: string;
  to_email: string;
}

export interface ClientDemandsViewModel {
  status: ClientDemandsStatus;
  filters: WorkItemFilters;
  items: WorkItem[];
  byStage?: Record<string, number>;
  loadError?: string;
  selected?: { kind: WorkItemKind; id: string };
  detail?: WorkItemDetail;
  detailLoading: boolean;
  detailError?: string;
  draft?: ActionDraft;
  canSubmitAction: boolean;
  errorMessage?: string;
  lastQueuedEmail?: string;
  setFilter<K extends keyof WorkItemFilters>(key: K, value: WorkItemFilters[K] | undefined): void;
  select(item: WorkItem | undefined): void;
  openAction(action: WorkItemAction): void;
  updateDraft(patch: Partial<ActionDraft>): void;
  cancelAction(): void;
  submitAction(): Promise<void>;
  dismissError(): void;
}

export function useClientDemandsViewModel(): ClientDemandsViewModel {
  const [filters, setFilters] = useState<WorkItemFilters>({ stage: "open" });
  const [selected, setSelected] = useState<{ kind: WorkItemKind; id: string }>();
  const [draft, setDraft] = useState<ActionDraft>();
  const [errorMessage, setErrorMessage] = useState<string>();
  const [lastQueuedEmail, setLastQueuedEmail] = useState<string>();

  const list = useWorkItems(filters);
  const detail = useWorkItem(selected?.kind, selected?.id);
  const act = useWorkItemAction();

  const textOk = !draft || !ACTION_TEXT_REQUIRED[draft.action] || draft.text.trim().length > 0;
  const emailOk = !draft?.withEmail || (draft.subject.trim().length > 0 && draft.body_text.trim().length > 0);

  let status: ClientDemandsStatus;
  if (act.isPending) status = "submitting";
  else if (draft) status = "acting";
  else if (errorMessage) status = "error";
  else if (list.isLoading) status = "loading";
  else status = "ready";

  return {
    status,
    filters,
    items: list.data?.items ?? [],
    byStage: list.data?.by_stage,
    loadError: list.isError ? (list.error as Error).message : undefined,
    selected,
    detail: detail.data,
    detailLoading: detail.isLoading && Boolean(selected),
    detailError: detail.isError ? (detail.error as Error).message : undefined,
    draft,
    canSubmitAction: Boolean(draft) && textOk && emailOk && !act.isPending,
    errorMessage,
    lastQueuedEmail,
    setFilter(key, value) {
      setFilters((current) => ({ ...current, [key]: value || undefined }));
    },
    select(item) {
      setSelected(item ? { kind: item.kind, id: item.id } : undefined);
      setDraft(undefined);
      setLastQueuedEmail(undefined);
    },
    openAction(action) {
      setErrorMessage(undefined);
      setDraft({
        action,
        text: "",
        withEmail: ACTION_EMAIL[action],
        subject: detail.data ? `Re: ${detail.data.title}` : "",
        body_text: "",
        to_email: detail.data?.requester_email ?? "",
      });
    },
    updateDraft(patch) {
      setDraft((current) => (current ? { ...current, ...patch } : current));
    },
    cancelAction: () => setDraft(undefined),
    async submitAction() {
      if (!selected || !draft || !textOk || !emailOk) return;
      try {
        const result = await act.mutateAsync({
          kind: selected.kind,
          id: selected.id,
          action: draft.action,
          text: draft.text.trim() || undefined,
          email: draft.withEmail
            ? { subject: draft.subject.trim(), body_text: draft.body_text.trim(), to_email: draft.to_email.trim() || undefined }
            : undefined,
        });
        setLastQueuedEmail(result.queued_email?.id);
        setDraft(undefined);
      } catch (error) {
        setErrorMessage((error as Error).message);
      }
    },
    dismissError: () => setErrorMessage(undefined),
  };
}
