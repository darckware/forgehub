/** ViewModels of the Personal page (tasks, agenda, notes, demands) -- §21 pattern: state and actions here,
 * the page renders them. Each tab has its own small state machine; destructive actions go through
 * a `confirming` target the page shows in a ConfirmDialog. */
import { useMemo, useState } from "react";
import {
  addDays,
  joinLocal,
  todayLocal,
  useCompletePersonalEvent,
  useCompletePersonalTask,
  useCreatePersonalDemand,
  useCreatePersonalDemandType,
  useDeletePersonalDemands,
  useDeletePersonalDemandType,
  usePersonalDemandTypes,
  usePersonalDemands,
  useUpdatePersonalDemand,
  useCreatePersonalEvent,
  useCreatePersonalNote,
  useCreatePersonalTask,
  useDeletePersonalItem,
  usePersonalAgenda,
  usePersonalDailySummaries,
  usePersonalLocation,
  usePersonalNotes,
  useSetPersonalLocation,
  usePersonalTasks,
  useUpdatePersonalEvent,
  useUpdatePersonalNote,
  useUpdatePersonalTask,
  type AgendaItem,
  type PersonalDemand,
  type LocationFix,
  type PersonalDemandType,
  type PersonalNote,
  type PersonalTask,
  type Recurrence,
} from "./usePersonal";

export type FormStatus = "idle" | "submitting" | "error";

export interface DeleteTarget {
  kind: "tasks" | "events" | "notes";
  id: string;
  title: string;
}

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/* ---------------------------------------------------------------- tasks */

export interface TaskDraft {
  title: string;
  date: string;
  time: string;
  listName: string;
  priority: "low" | "normal" | "high";
  recurrence: Recurrence;
}

const EMPTY_TASK: TaskDraft = { title: "", date: "", time: "", listName: "Pessoal", priority: "normal", recurrence: "" };

export type TaskGroupKey = "overdue" | "today" | "upcoming" | "noDate";

export function groupTasks(tasks: PersonalTask[], today: string): Record<TaskGroupKey, PersonalTask[]> {
  const groups: Record<TaskGroupKey, PersonalTask[]> = { overdue: [], today: [], upcoming: [], noDate: [] };
  for (const t of tasks) {
    if (!t.due_at) groups.noDate.push(t);
    else if (t.due_at.slice(0, 10) < today) groups.overdue.push(t);
    else if (t.due_at.slice(0, 10) === today) groups.today.push(t);
    else groups.upcoming.push(t);
  }
  return groups;
}

export function usePersonalTasksViewModel() {
  const [showDone, setShowDone] = useState(false);
  const query = usePersonalTasks(showDone ? "done" : "pending");
  const create = useCreatePersonalTask();
  const update = useUpdatePersonalTask();
  const complete = useCompletePersonalTask();
  const [draft, setDraft] = useState<TaskDraft>(EMPTY_TASK);
  const [status, setStatus] = useState<FormStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [listFilter, setListFilter] = useState<string>("");

  const tasks = query.data ?? [];
  const lists = useMemo(() => Array.from(new Set(tasks.map((t) => t.list_name))).sort(), [tasks]);
  const visible = listFilter ? tasks.filter((t) => t.list_name === listFilter) : tasks;
  const groups = useMemo(() => groupTasks(visible, todayLocal()), [visible]);

  async function submit() {
    if (!draft.title.trim()) return;
    setStatus("submitting");
    setError(null);
    try {
      await create.mutateAsync({
        title: draft.title.trim(),
        list_name: draft.listName.trim() || "Pessoal",
        priority: draft.priority,
        recurrence: draft.recurrence,
        ...(draft.date ? { due_at: joinLocal(draft.date, draft.time), due_has_time: Boolean(draft.time) } : {}),
      });
      setDraft({ ...EMPTY_TASK, listName: draft.listName });
      setStatus("idle");
    } catch (e) {
      setError(errorText(e));
      setStatus("error");
    }
  }

  return {
    query,
    groups,
    lists,
    listFilter,
    setListFilter,
    showDone,
    setShowDone,
    draft,
    setDraft,
    status,
    error,
    submit,
    complete: (id: string) => complete.mutate(id),
    reopen: (id: string) => update.mutate({ id, body: { status: "pending" } }),
    busyId: complete.isPending ? complete.variables : update.isPending ? update.variables?.id : undefined,
  };
}

/* ---------------------------------------------------------------- agenda */

export interface EventDraft {
  title: string;
  date: string;
  time: string;
  location: string;
  reminder: number;
  recurrence: Recurrence;
}

export function groupAgendaByDay(items: AgendaItem[]): [string, AgendaItem[]][] {
  const map = new Map<string, AgendaItem[]>();
  for (const it of items) {
    const day = it.overdue ? "overdue" : it.starts_at.slice(0, 10);
    map.set(day, [...(map.get(day) ?? []), it]);
  }
  return Array.from(map.entries()).sort(([a], [b]) => (a === "overdue" ? -1 : b === "overdue" ? 1 : a.localeCompare(b)));
}

export function usePersonalAgendaViewModel() {
  const [start, setStart] = useState(todayLocal());
  const end = addDays(start, 14);
  const query = usePersonalAgenda(start, end);
  const create = useCreatePersonalEvent();
  const cancel = useUpdatePersonalEvent();
  const completeEvent = useCompletePersonalEvent();
  const completeTask = useCompletePersonalTask();
  const [draft, setDraft] = useState<EventDraft>({ title: "", date: todayLocal(), time: "", location: "", reminder: 60, recurrence: "" });
  const [status, setStatus] = useState<FormStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!draft.title.trim() || !draft.date) return;
    setStatus("submitting");
    setError(null);
    try {
      await create.mutateAsync({
        title: draft.title.trim(),
        starts_at: joinLocal(draft.date, draft.time),
        all_day: !draft.time,
        location: draft.location.trim() || null,
        reminders: draft.reminder >= 0 ? [draft.reminder] : [],
        recurrence: draft.recurrence,
      });
      setDraft({ ...draft, title: "", time: "", location: "" });
      setStatus("idle");
    } catch (e) {
      setError(errorText(e));
      setStatus("error");
    }
  }

  return {
    query,
    days: groupAgendaByDay(query.data ?? []),
    start,
    setStart,
    end,
    draft,
    setDraft,
    status,
    error,
    submit,
    cancelEvent: (id: string) => cancel.mutate({ id, body: { status: "cancelled" } }),
    completeEvent: (id: string) => completeEvent.mutate(id),
    completeTask: (id: string) => completeTask.mutate(id),
  };
}

/* ---------------------------------------------------------------- notes */

export interface NoteDraft {
  id?: string;
  title: string;
  content: string;
  tags: string;
  pinned: boolean;
}

export function usePersonalNotesViewModel() {
  const [search, setSearch] = useState("");
  const [archived, setArchived] = useState(false);
  const query = usePersonalNotes(search.trim(), archived);
  const create = useCreatePersonalNote();
  const update = useUpdatePersonalNote();
  const [editing, setEditing] = useState<NoteDraft | null>(null);
  const [status, setStatus] = useState<FormStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  function open(note?: PersonalNote) {
    setError(null);
    setStatus("idle");
    setEditing(
      note
        ? { id: note.id, title: note.title, content: note.content, tags: note.tags.join(", "), pinned: note.pinned }
        : { title: "", content: "", tags: "", pinned: false },
    );
  }

  async function save() {
    if (!editing || !editing.title.trim()) return;
    setStatus("submitting");
    setError(null);
    const body = {
      title: editing.title.trim(),
      content: editing.content,
      tags: editing.tags.split(",").map((t) => t.trim()).filter(Boolean),
      pinned: editing.pinned,
    };
    try {
      if (editing.id) await update.mutateAsync({ id: editing.id, body });
      else await create.mutateAsync(body);
      setEditing(null);
      setStatus("idle");
    } catch (e) {
      setError(errorText(e));
      setStatus("error");
    }
  }

  return {
    query,
    notes: query.data ?? [],
    search,
    setSearch,
    archived,
    setArchived,
    editing,
    setEditing,
    open,
    save,
    status,
    error,
    togglePin: (n: PersonalNote) => update.mutate({ id: n.id, body: { pinned: !n.pinned } }),
    toggleArchive: (n: PersonalNote) => update.mutate({ id: n.id, body: { archived: !n.archived } }),
  };
}

/* ---------------------------------------------------------------- location + daily summaries */

/** Why the browser gave no GPS fix -- each is an i18n key under location.gpsError. */
export type GpsErrorKind = "unsupported" | "denied" | "unavailable" | "timeout";

export class GpsError extends Error {
  constructor(readonly kind: GpsErrorKind) {
    super(kind);
  }
}

/** One high-accuracy fix from the browser (needs HTTPS and Marcelo's permission). */
export function readCurrentPosition(geolocation: Geolocation | undefined = globalThis.navigator?.geolocation): Promise<LocationFix> {
  return new Promise((resolve, reject) => {
    if (!geolocation) {
      reject(new GpsError("unsupported"));
      return;
    }
    geolocation.getCurrentPosition(
      (position) => resolve({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy_m: Number.isFinite(position.coords.accuracy) ? Math.round(position.coords.accuracy) : null,
      }),
      (err) => reject(new GpsError(err.code === 1 ? "denied" : err.code === 3 ? "timeout" : "unavailable")),
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 },
    );
  });
}

export type LocationStatus = "idle" | "locating" | "submitting" | "error";

/** Marcelo's current GPS location (one, replaced on each share) and the Maia's daily summaries. */
export function usePersonalLocationViewModel(geolocation?: Geolocation) {
  const location = usePersonalLocation();
  const setLocation = useSetPersonalLocation();
  const [status, setStatus] = useState<LocationStatus>("idle");
  const [error, setError] = useState<{ gps: GpsErrorKind } | { message: string } | null>(null);

  const [start, setStart] = useState(() => addDays(todayLocal(), -30));
  const [end, setEnd] = useState(todayLocal);
  const summaries = usePersonalDailySummaries(start, end);
  const [expanded, setExpanded] = useState<string | null>(null);

  async function shareMyLocation() {
    setError(null);
    setStatus("locating");
    try {
      const fix = await readCurrentPosition(geolocation ?? globalThis.navigator?.geolocation);
      setStatus("submitting");
      await setLocation.mutateAsync(fix);
      setStatus("idle");
    } catch (e) {
      setError(e instanceof GpsError ? { gps: e.kind } : { message: errorText(e) });
      setStatus("error");
    }
  }

  return {
    location,
    current: location.data ?? null,
    shareMyLocation,
    status,
    error,
    summaries,
    summaryList: summaries.data ?? [],
    start,
    setStart,
    end,
    setEnd,
    expanded,
    toggle: (id: string) => setExpanded((current) => (current === id ? null : id)),
  };
}

/* ---------------------------------------------------------------- delete */

export function usePersonalDeleteViewModel() {
  const del = useDeletePersonalItem();
  const [target, setTarget] = useState<DeleteTarget | null>(null);
  return {
    target,
    ask: setTarget,
    cancel: () => setTarget(null),
    confirm: async () => {
      if (!target) return;
      await del.mutateAsync({ kind: target.kind, id: target.id });
      setTarget(null);
    },
    loading: del.isPending,
    error: del.error ? errorText(del.error) : null,
  };
}

/* ---------------------------------------------------------------- demands */

/** Group key of demands with no type (never registered, or their type was removed). */
export const NO_TYPE = "";

export interface DemandGroup {
  typeId: string;
  name: string | null;
  demands: PersonalDemand[];
}

/** One group per type in the types' own order, then "Sem tipo"; empty groups are left out. */
export function groupDemands(demands: PersonalDemand[], types: PersonalDemandType[]): DemandGroup[] {
  const known = new Set(types.map((t) => t.id));
  const groups: DemandGroup[] = types.map((t) => ({ typeId: t.id, name: t.name, demands: [] }));
  const untyped: DemandGroup = { typeId: NO_TYPE, name: null, demands: [] };
  const byId = new Map(groups.map((g) => [g.typeId, g]));
  for (const d of demands) {
    (d.type_id && known.has(d.type_id) ? byId.get(d.type_id)! : untyped).demands.push(d);
  }
  return [...groups, untyped].filter((g) => g.demands.length > 0);
}

export interface DemandDraft {
  title: string;
  notes: string;
  typeId: string;
}

/** Either demands (one or many) or a type awaiting the delete confirmation. */
export type DemandDeleteTarget =
  | { kind: "demands"; ids: string[]; title?: string }
  | { kind: "type"; id: string; name: string; count: number };

export function usePersonalDemandsViewModel() {
  const [showDone, setShowDone] = useState(false);
  const query = usePersonalDemands(showDone ? "done" : "open");
  const typesQuery = usePersonalDemandTypes();
  const create = useCreatePersonalDemand();
  const update = useUpdatePersonalDemand();
  const remove = useDeletePersonalDemands();
  const createType = useCreatePersonalDemandType();
  const removeType = useDeletePersonalDemandType();
  const [draft, setDraft] = useState<DemandDraft>({ title: "", notes: "", typeId: NO_TYPE });
  const [status, setStatus] = useState<FormStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [typeName, setTypeName] = useState("");
  const [typeError, setTypeError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);
  const [checked, setChecked] = useState<string[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<DemandDeleteTarget | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const demands = query.data ?? [];
  const types = typesQuery.data ?? [];
  const groups = useMemo(() => groupDemands(demands, types), [demands, types]);
  const visibleGroups = typeFilter === null ? groups : groups.filter((g) => g.typeId === typeFilter);
  const visibleIds = visibleGroups.flatMap((g) => g.demands.map((d) => d.id));
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const g of groups) c[g.typeId] = g.demands.length;
    return c;
  }, [groups]);
  const allChecked = visibleIds.length > 0 && visibleIds.every((id) => checked.includes(id));

  return {
    query,
    types,
    groups: visibleGroups,
    counts,
    typeName: (id: string | null) => types.find((t) => t.id === id)?.name ?? null,
    showDone,
    setShowDone(value: boolean) {
      setShowDone(value);
      setChecked([]);
    },
    typeFilter,
    setTypeFilter(value: string | null) {
      setTypeFilter(value);
      setChecked([]);
    },
    draft,
    setDraft,
    status: create.isPending ? ("submitting" as const) : status,
    error,
    async submit() {
      if (!draft.title.trim()) return;
      try {
        await create.mutateAsync({
          title: draft.title.trim(),
          notes: draft.notes.trim() || null,
          type_id: draft.typeId || null,
        });
        // Keeps the chosen type: several demands of the same type are usually added in a row.
        setDraft({ title: "", notes: "", typeId: draft.typeId });
        setStatus("idle");
        setError(null);
      } catch (e) {
        setStatus("error");
        setError(errorText(e));
      }
    },
    newTypeName: typeName,
    setNewTypeName: setTypeName,
    typeError,
    addingType: createType.isPending,
    async addType() {
      const name = typeName.trim();
      if (!name) return;
      try {
        const created = await createType.mutateAsync(name);
        setTypeName("");
        setTypeError(null);
        setDraft((d) => ({ ...d, typeId: d.typeId || created.id }));
      } catch (e) {
        setTypeError(errorText(e));
      }
    },
    busyId,
    async toggleDone(demand: PersonalDemand) {
      setBusyId(demand.id);
      try {
        await update.mutateAsync({ id: demand.id, body: { status: demand.status === "done" ? "open" : "done" } });
        setChecked((c) => c.filter((id) => id !== demand.id));
      } finally {
        setBusyId(null);
      }
    },
    async changeType(demand: PersonalDemand, typeId: string) {
      await update.mutateAsync({ id: demand.id, body: { type_id: typeId || null } });
    },
    checked,
    isChecked: (id: string) => checked.includes(id),
    toggleChecked(id: string) {
      setChecked((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
    },
    allChecked,
    toggleAll() {
      setChecked(allChecked ? [] : visibleIds);
    },
    deleteTarget,
    deleteError,
    deleting: remove.isPending || removeType.isPending,
    askDeleteDemands(ids: string[], title?: string) {
      setDeleteError(null);
      if (ids.length > 0) setDeleteTarget({ kind: "demands", ids, title });
    },
    askDeleteType(type: PersonalDemandType) {
      setDeleteError(null);
      setDeleteTarget({ kind: "type", id: type.id, name: type.name, count: counts[type.id] ?? 0 });
    },
    cancelDelete: () => setDeleteTarget(null),
    async confirmDelete() {
      if (!deleteTarget) return;
      try {
        if (deleteTarget.kind === "demands") {
          await remove.mutateAsync(deleteTarget.ids);
          setChecked((c) => c.filter((id) => !deleteTarget.ids.includes(id)));
        } else {
          await removeType.mutateAsync(deleteTarget.id);
          if (typeFilter === deleteTarget.id) setTypeFilter(null);
          if (draft.typeId === deleteTarget.id) setDraft((d) => ({ ...d, typeId: NO_TYPE }));
        }
        setDeleteTarget(null);
      } catch (e) {
        setDeleteError(errorText(e));
      }
    },
  };
}

export type PersonalDemandsViewModel = ReturnType<typeof usePersonalDemandsViewModel>;
