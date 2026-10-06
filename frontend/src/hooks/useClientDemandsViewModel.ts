import { useState } from "react";
import {
  useClientOpsText,
  localDateTimeToIso,
  useClientFactory,
  useLogTime,
  useCreateProjectFromItem,
  useWorkItem,
  useWorkItemAction,
  useWorkItems,
  type WorkItem,
  type WorkItemAction,
  type FactoryProduct,
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
  /** Resolve only: hours spent, as typed ("1,5" or "1.5"). */
  hours: string;
  serviceType: "remoto" | "presencial";
  withEmail: boolean;
  subject: string;
  body_text: string;
  to_email: string;
}

/** "Criar projeto" (Onda 3): an existing product of the client, or a new one. */
export interface ProjectDraft {
  productChoice: "existing" | "new";
  productId: string;
  newProductName: string;
  projectName: string;
}

/** "Apontar horas": one period of work, in local time. Start and end each have
 * their own day, so a period may cross midnight or span several days. */
export interface TimeDraft {
  startDay: string;
  start: string;
  endDay: string;
  end: string;
  description: string;
  serviceType: "remoto" | "presencial";
}

/** "1,5" / "1.5" / "2" hours -> whole minutes; anything unparsable or negative -> 0. */
export function hoursToMinutes(hours: string): number {
  const value = Number(hours.trim().replace(",", "."));
  return Number.isFinite(value) && value > 0 ? Math.round(value * 60) : 0;
}

/** Whole minutes between start and end; 0 while either is incomplete. */
export function timeDraftMinutes(d: TimeDraft): number {
  if (!d.startDay || !d.start || !d.endDay || !d.end) return 0;
  const minutes = (Date.parse(`${d.endDay}T${d.end}:00`) - Date.parse(`${d.startDay}T${d.start}:00`)) / 60000;
  return Number.isFinite(minutes) ? Math.round(minutes) : 0;
}

export function timeDraftError(d: TimeDraft): "endBeforeStart" | undefined {
  if (!d.startDay || !d.start || !d.endDay || !d.end) return undefined;
  return timeDraftMinutes(d) <= 0 ? "endBeforeStart" : undefined;
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
  /** Whether the open "Dar baixa" dialog must carry hours (item has a client). */
  hoursRequired: boolean;
  errorMessage?: string;
  lastQueuedEmail?: string;
  /** Products the new project can go under: the client's own, then unlinked ones. */
  projectProducts: FactoryProduct[];
  projectDraft?: ProjectDraft;
  canSubmitProject: boolean;
  /** Why the item can't get a project (no client yet), if so. */
  projectBlockedReason?: "noClient";
  timeDraft?: TimeDraft;
  timeDraftError?: "endBeforeStart";
  /** Length of the period being logged, in minutes (0 while incomplete). */
  timeDraftMinutes: number;
  canSubmitTime: boolean;
  setFilter<K extends keyof WorkItemFilters>(key: K, value: WorkItemFilters[K] | undefined): void;
  select(item: WorkItem | undefined): void;
  openAction(action: WorkItemAction): void;
  updateDraft(patch: Partial<ActionDraft>): void;
  cancelAction(): void;
  submitAction(): Promise<void>;
  dismissError(): void;
  openCreateProject(): void;
  updateProjectDraft(patch: Partial<ProjectDraft>): void;
  cancelCreateProject(): void;
  submitCreateProject(): Promise<void>;
  openLogTime(): void;
  updateTimeDraft(patch: Partial<TimeDraft>): void;
  cancelLogTime(): void;
  submitLogTime(): Promise<void>;
}

/** Initial state from a deep link (`?client=<id>&item=<kind>:<id>`, see clientDemandsLink). */
export interface ClientDemandsInitial {
  clientId?: string;
  item?: { kind: WorkItemKind; id: string };
}

export function parseDemandsSearch(search: URLSearchParams): ClientDemandsInitial {
  const clientId = search.get("client") || undefined;
  const raw = search.get("item");
  const [kind, id] = raw ? raw.split(":") : [];
  const item = (kind === "ticket" || kind === "demand") && id ? { kind: kind as WorkItemKind, id } : undefined;
  return { clientId, item };
}

export function useClientDemandsViewModel(initial: ClientDemandsInitial = {}): ClientDemandsViewModel {
  const { errorText } = useClientOpsText();
  const [filters, setFilters] = useState<WorkItemFilters>({ stage: "open", client_account_id: initial.clientId });
  const [selected, setSelected] = useState<{ kind: WorkItemKind; id: string } | undefined>(initial.item);
  const [draft, setDraft] = useState<ActionDraft>();
  const [errorMessage, setErrorMessage] = useState<string>();
  const [lastQueuedEmail, setLastQueuedEmail] = useState<string>();

  const list = useWorkItems(filters);
  const detail = useWorkItem(selected?.kind, selected?.id);
  const act = useWorkItemAction();
  const [projectDraft, setProjectDraft] = useState<ProjectDraft>();
  const factory = useClientFactory(detail.data?.project ? undefined : detail.data?.client_account_id);
  const createProject = useCreateProjectFromItem();
  const logTime = useLogTime();
  const [timeDraft, setTimeDraft] = useState<TimeDraft>();
  const timeError = timeDraft ? timeDraftError(timeDraft) : undefined;
  const projectProducts = [...(factory.data?.products ?? []), ...(factory.data?.unlinked_products ?? [])];

  const textOk = !draft || !ACTION_TEXT_REQUIRED[draft.action] || draft.text.trim().length > 0;
  // "Dar baixa" on a client's item must say how long it took: it consumes the quota.
  const resolveMinutes = draft?.action === "resolve" ? hoursToMinutes(draft.hours) : 0;
  const hoursRequired = draft?.action === "resolve" && Boolean(detail.data?.client_account_id);
  const hoursOk = !hoursRequired || resolveMinutes > 0;
  const emailOk = !draft?.withEmail || (draft.subject.trim().length > 0 && draft.body_text.trim().length > 0);

  let status: ClientDemandsStatus;
  if (act.isPending || createProject.isPending || logTime.isPending) status = "submitting";
  else if (draft || projectDraft || timeDraft) status = "acting";
  else if (errorMessage) status = "error";
  else if (list.isLoading) status = "loading";
  else status = "ready";

  return {
    status,
    filters,
    items: list.data?.items ?? [],
    byStage: list.data?.by_stage,
    loadError: list.isError ? errorText(list.error) : undefined,
    selected,
    detail: detail.data,
    detailLoading: detail.isLoading && Boolean(selected),
    detailError: detail.isError ? errorText(detail.error) : undefined,
    draft,
    canSubmitAction: Boolean(draft) && textOk && emailOk && hoursOk && !act.isPending,
    hoursRequired,
    errorMessage,
    lastQueuedEmail,
    projectProducts,
    projectDraft,
    canSubmitProject: Boolean(
      projectDraft &&
        !createProject.isPending &&
        (projectDraft.productChoice === "existing" ? projectDraft.productId : projectDraft.newProductName.trim()),
    ),
    projectBlockedReason: detail.data && !detail.data.client_account_id ? "noClient" : undefined,
    timeDraft,
    timeDraftError: timeError,
    timeDraftMinutes: timeDraft ? timeDraftMinutes(timeDraft) : 0,
    canSubmitTime: Boolean(
      timeDraft && !timeError && timeDraftMinutes(timeDraft) > 0 && timeDraft.description.trim() && !logTime.isPending,
    ),
    setFilter(key, value) {
      setFilters((current) => ({ ...current, [key]: value || undefined }));
      // A new filter is a new list: the detail on the right referred to the old
      // one, so it (and any dialog open for it) is cleared (2026-10-05, Marcelo).
      setSelected(undefined);
      setDraft(undefined);
      setProjectDraft(undefined);
      setTimeDraft(undefined);
      setLastQueuedEmail(undefined);
      setErrorMessage(undefined);
    },
    select(item) {
      setSelected(item ? { kind: item.kind, id: item.id } : undefined);
      setDraft(undefined);
      setProjectDraft(undefined);
      setTimeDraft(undefined);
      setLastQueuedEmail(undefined);
    },
    openAction(action) {
      setErrorMessage(undefined);
      setDraft({
        action,
        text: "",
        hours: "",
        serviceType: "remoto",
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
      if (!selected || !draft || !textOk || !emailOk || !hoursOk) return;
      try {
        const result = await act.mutateAsync({
          kind: selected.kind,
          id: selected.id,
          action: draft.action,
          text: draft.text.trim() || undefined,
          minutes: resolveMinutes,
          serviceType: draft.serviceType,
          email: draft.withEmail
            ? { subject: draft.subject.trim(), body_text: draft.body_text.trim(), to_email: draft.to_email.trim() || undefined }
            : undefined,
        });
        setLastQueuedEmail(result.queued_email?.id);
        setDraft(undefined);
      } catch (error) {
        setErrorMessage(errorText(error));
      }
    },
    dismissError: () => setErrorMessage(undefined),
    openCreateProject() {
      if (!detail.data?.client_account_id) return;
      setErrorMessage(undefined);
      const own = factory.data?.products ?? [];
      setProjectDraft({
        // A client that already has a product most likely means another
        // project of it; one without starts a product of its own.
        productChoice: own.length > 0 ? "existing" : "new",
        productId: own.length === 1 ? own[0].id : "",
        newProductName: detail.data.company_name ?? "",
        projectName: detail.data.title,
      });
    },
    updateProjectDraft(patch) {
      setProjectDraft((current) => (current ? { ...current, ...patch } : current));
    },
    cancelCreateProject: () => setProjectDraft(undefined),
    openLogTime() {
      if (!selected) return;
      setErrorMessage(undefined);
      const now = new Date();
      const pad = (n: number) => String(n).padStart(2, "0");
      const day = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
      setTimeDraft({
        startDay: day,
        start: "",
        endDay: day,
        end: `${pad(now.getHours())}:${pad(now.getMinutes())}`,
        description: "",
        serviceType: "remoto",
      });
    },
    updateTimeDraft(patch) {
      setTimeDraft((current) => (current ? { ...current, ...patch } : current));
    },
    cancelLogTime: () => setTimeDraft(undefined),
    async submitLogTime() {
      if (!selected || !timeDraft || timeError) return;
      try {
        await logTime.mutateAsync({
          kind: selected.kind,
          id: selected.id,
          start_time: localDateTimeToIso(timeDraft.startDay, timeDraft.start),
          end_time: localDateTimeToIso(timeDraft.endDay, timeDraft.end),
          description: timeDraft.description.trim(),
          service_type: timeDraft.serviceType,
        });
        setTimeDraft(undefined);
      } catch (error) {
        setErrorMessage(errorText(error));
      }
    },
    async submitCreateProject() {
      if (!selected || !projectDraft) return;
      try {
        await createProject.mutateAsync({
          kind: selected.kind,
          id: selected.id,
          ...(projectDraft.productChoice === "existing"
            ? { product_id: projectDraft.productId }
            : { new_product_name: projectDraft.newProductName.trim() }),
          project_name: projectDraft.projectName.trim() || undefined,
        });
        setProjectDraft(undefined);
      } catch (error) {
        setErrorMessage(errorText(error));
      }
    },
  };
}
