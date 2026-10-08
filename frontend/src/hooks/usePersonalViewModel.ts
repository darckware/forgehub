/** ViewModels of the Personal page (tasks, agenda, notes) -- §21 pattern: state and actions here,
 * the page renders them. Each tab has its own small state machine; destructive actions go through
 * a `confirming` target the page shows in a ConfirmDialog. */
import { useMemo, useState } from "react";
import {
  addDays,
  joinLocal,
  todayLocal,
  useCompletePersonalTask,
  useCreatePersonalEvent,
  useCreatePersonalNote,
  useCreatePersonalTask,
  useDeletePersonalItem,
  usePersonalAgenda,
  usePersonalNotes,
  usePersonalTasks,
  useUpdatePersonalEvent,
  useUpdatePersonalNote,
  useUpdatePersonalTask,
  type AgendaItem,
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
