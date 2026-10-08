/** Personal domain (Marcelo's tasks, agenda and notes -- api/routes/personal.py).
 *
 * Datetimes travel as naive São Paulo wall time ("2026-10-08T15:00:00"), the backend's convention:
 * the agenda belongs to one person in one city. Helpers below build/split those strings from the
 * native date/time inputs without going through `Date`, so no timezone shift can creep in. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

const BASE = "/api/v1/personal";

export type Recurrence = "" | "daily" | "weekly" | "monthly" | "yearly";
export type TaskStatus = "pending" | "done" | "cancelled";
export type TaskPriority = "low" | "normal" | "high";

export interface PersonalTask {
  id: string;
  title: string;
  notes: string | null;
  list_name: string;
  priority: TaskPriority;
  status: TaskStatus;
  due_at: string | null;
  due_has_time: boolean;
  recurrence: Recurrence;
  reminders: number[];
  completed_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface PersonalEvent {
  id: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  all_day: boolean;
  location: string | null;
  notes: string | null;
  status: "scheduled" | "cancelled";
  recurrence: Recurrence;
  reminders: number[];
  created_by: string;
}

export interface PersonalNote {
  id: string;
  title: string;
  content: string;
  tags: string[];
  pinned: boolean;
  archived: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AgendaItem {
  kind: "event" | "task";
  id: string;
  title: string;
  starts_at: string;
  ends_at: string | null;
  has_time: boolean;
  location: string | null;
  status: string;
  list_name: string | null;
  overdue: boolean;
}

export type TaskInput = Partial<Pick<PersonalTask, "title" | "notes" | "list_name" | "priority" | "due_at" | "due_has_time" | "recurrence" | "reminders" | "status">>;
export type EventInput = Partial<Pick<PersonalEvent, "title" | "starts_at" | "ends_at" | "all_day" | "location" | "notes" | "recurrence" | "reminders" | "status">>;
export type NoteInput = Partial<Pick<PersonalNote, "title" | "content" | "tags" | "pinned" | "archived">>;

const keys = {
  all: ["personal"] as const,
  tasks: (status: string) => ["personal", "tasks", status] as const,
  agenda: (start: string, end: string) => ["personal", "agenda", start, end] as const,
  notes: (q: string, archived: boolean) => ["personal", "notes", q, archived] as const,
};

function qs(params: Record<string, string | boolean | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  return entries.length ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}` : "";
}

/** "2026-10-08" + "15:30" -> "2026-10-08T15:30:00"; no time -> midnight. */
export function joinLocal(date: string, time?: string): string {
  return `${date}T${time || "00:00"}:00`;
}

/** "2026-10-08T15:30:00" -> { date: "2026-10-08", time: "15:30" }. */
export function splitLocal(value: string | null | undefined): { date: string; time: string } {
  if (!value) return { date: "", time: "" };
  const [date, rest = ""] = value.split("T");
  return { date, time: rest.slice(0, 5) };
}

/** Today in São Paulo as "YYYY-MM-DD". */
export function todayLocal(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
}

export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + days));
  return dt.toISOString().slice(0, 10);
}

function useInvalidatePersonal() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: keys.all });
}

export function usePersonalTasks(status: TaskStatus | "" = "pending") {
  return useQuery<PersonalTask[]>({
    queryKey: keys.tasks(status),
    queryFn: () => apiClient.get(`${BASE}/tasks${qs({ status })}`),
  });
}

export function usePersonalAgenda(start: string, end: string) {
  return useQuery<AgendaItem[]>({
    queryKey: keys.agenda(start, end),
    queryFn: () => apiClient.get(`${BASE}/agenda${qs({ start: joinLocal(start), end: joinLocal(end) })}`),
  });
}

export function usePersonalNotes(q: string, archived: boolean) {
  return useQuery<PersonalNote[]>({
    queryKey: keys.notes(q, archived),
    queryFn: () => apiClient.get(`${BASE}/notes${qs({ q, archived })}`),
  });
}

export function useCreatePersonalTask() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalTask, Error, TaskInput>({
    mutationFn: (body) => apiClient.post(`${BASE}/tasks`, body),
    onSettled: invalidate,
  });
}

export function useUpdatePersonalTask() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalTask, Error, { id: string; body: TaskInput }>({
    mutationFn: ({ id, body }) => apiClient.patch(`${BASE}/tasks/${id}`, body),
    onSettled: invalidate,
  });
}

export function useCompletePersonalTask() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalTask, Error, string>({
    mutationFn: (id) => apiClient.post(`${BASE}/tasks/${id}:complete`),
    onSettled: invalidate,
  });
}

export function useCreatePersonalEvent() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalEvent, Error, EventInput>({
    mutationFn: (body) => apiClient.post(`${BASE}/events`, body),
    onSettled: invalidate,
  });
}

export function useUpdatePersonalEvent() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalEvent, Error, { id: string; body: EventInput }>({
    mutationFn: ({ id, body }) => apiClient.patch(`${BASE}/events/${id}`, body),
    onSettled: invalidate,
  });
}

export function useCreatePersonalNote() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalNote, Error, NoteInput>({
    mutationFn: (body) => apiClient.post(`${BASE}/notes`, body),
    onSettled: invalidate,
  });
}

export function useUpdatePersonalNote() {
  const invalidate = useInvalidatePersonal();
  return useMutation<PersonalNote, Error, { id: string; body: NoteInput }>({
    mutationFn: ({ id, body }) => apiClient.patch(`${BASE}/notes/${id}`, body),
    onSettled: invalidate,
  });
}

export function useDeletePersonalItem() {
  const invalidate = useInvalidatePersonal();
  return useMutation<void, Error, { kind: "tasks" | "events" | "notes"; id: string }>({
    mutationFn: ({ kind, id }) => apiClient.delete(`${BASE}/${kind}/${id}`),
    onSettled: invalidate,
  });
}
