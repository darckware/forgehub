import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Archive,
  ArchiveRestore,
  CalendarDays,
  CheckCircle2,
  Circle,
  ListTodo,
  Loader2,
  MapPin,
  NotebookPen,
  Pin,
  PinOff,
  Plus,
  Repeat,
  Trash2,
  User,
  X,
} from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { splitLocal, todayLocal, type AgendaItem, type PersonalTask, type Recurrence } from "@/hooks/usePersonal";
import {
  usePersonalAgendaViewModel,
  usePersonalDeleteViewModel,
  usePersonalNotesViewModel,
  usePersonalTasksViewModel,
  type DeleteTarget,
  type TaskGroupKey,
} from "@/hooks/usePersonalViewModel";
import { cn } from "@/lib/utils";

const RECURRENCES: Recurrence[] = ["", "daily", "weekly", "monthly", "yearly"];
const fieldClass = "h-9 rounded-md border bg-background px-2 text-sm max-md:text-base";

function formatDay(day: string, locale: string): string {
  const [y, m, d] = day.split("-").map(Number);
  return new Intl.DateTimeFormat(locale, { weekday: "long", day: "2-digit", month: "2-digit", timeZone: "UTC" }).format(
    new Date(Date.UTC(y, m - 1, d)),
  );
}

function whenLabel(task: PersonalTask, locale: string): string | null {
  if (!task.due_at) return null;
  const { date, time } = splitLocal(task.due_at);
  return `${formatDay(date, locale)}${task.due_has_time ? ` · ${time}` : ""}`;
}

export default function PersonalPage() {
  const { t } = useTranslation("personal");
  const [tab, setTab] = useState("tasks");
  const del = usePersonalDeleteViewModel();

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("title")} description={t("description")} icon={<User className="h-6 w-6" />} />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="tasks"><ListTodo className="mr-1.5 h-4 w-4" />{t("tabs.tasks")}</TabsTrigger>
          <TabsTrigger value="agenda"><CalendarDays className="mr-1.5 h-4 w-4" />{t("tabs.agenda")}</TabsTrigger>
          <TabsTrigger value="notes"><NotebookPen className="mr-1.5 h-4 w-4" />{t("tabs.notes")}</TabsTrigger>
        </TabsList>
        <TabsContent value="tasks"><TasksTab onDelete={del.ask} /></TabsContent>
        <TabsContent value="agenda"><AgendaTab onDelete={del.ask} /></TabsContent>
        <TabsContent value="notes"><NotesTab onDelete={del.ask} /></TabsContent>
      </Tabs>
      <ConfirmDialog
        open={Boolean(del.target)}
        title={t("delete.title")}
        description={del.target ? t("delete.description", { title: del.target.title }) : undefined}
        confirmLabel={t("delete.confirm")}
        variant="destructive"
        loading={del.loading}
        error={del.error}
        onConfirm={del.confirm}
        onCancel={del.cancel}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ tasks */

function TasksTab({ onDelete }: { onDelete: (t: DeleteTarget) => void }) {
  const { t, i18n } = useTranslation("personal");
  const vm = usePersonalTasksViewModel();
  const order: TaskGroupKey[] = ["overdue", "today", "upcoming", "noDate"];

  return (
    <div className="flex flex-col gap-4 pt-4">
      <Card>
        <CardContent className="p-4">
          <form
            className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,3fr)_auto_auto_minmax(0,1fr)_auto]"
            onSubmit={(e) => {
              e.preventDefault();
              void vm.submit();
            }}
          >
            <Input
              placeholder={t("tasks.newPlaceholder")}
              value={vm.draft.title}
              onChange={(e) => vm.setDraft({ ...vm.draft, title: e.target.value })}
              className="max-md:text-base"
            />
            <input type="date" className={fieldClass} value={vm.draft.date} aria-label={t("fields.date")}
              onChange={(e) => vm.setDraft({ ...vm.draft, date: e.target.value })} />
            <input type="time" className={fieldClass} value={vm.draft.time} aria-label={t("fields.time")}
              disabled={!vm.draft.date} onChange={(e) => vm.setDraft({ ...vm.draft, time: e.target.value })} />
            <Input placeholder={t("fields.list")} value={vm.draft.listName}
              onChange={(e) => vm.setDraft({ ...vm.draft, listName: e.target.value })} className="max-md:text-base" />
            <Button type="submit" disabled={vm.status === "submitting" || !vm.draft.title.trim()}>
              {vm.status === "submitting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              <span className="ml-1">{t("actions.add")}</span>
            </Button>
          </form>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <select className={fieldClass} value={vm.draft.priority} aria-label={t("fields.priority")}
              onChange={(e) => vm.setDraft({ ...vm.draft, priority: e.target.value as "low" | "normal" | "high" })}>
              {(["low", "normal", "high"] as const).map((p) => <option key={p} value={p}>{t(`priority.${p}`)}</option>)}
            </select>
            <select className={fieldClass} value={vm.draft.recurrence} aria-label={t("fields.recurrence")}
              onChange={(e) => vm.setDraft({ ...vm.draft, recurrence: e.target.value as Recurrence })}>
              {RECURRENCES.map((r) => <option key={r} value={r}>{t(`recurrence.${r || "none"}`)}</option>)}
            </select>
            {vm.error && <span className="text-destructive">{vm.error}</span>}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant={vm.listFilter === "" ? "default" : "outline"} onClick={() => vm.setListFilter("")}>
          {t("tasks.allLists")}
        </Button>
        {vm.lists.map((l) => (
          <Button key={l} size="sm" variant={vm.listFilter === l ? "default" : "outline"} onClick={() => vm.setListFilter(l)}>
            {l}
          </Button>
        ))}
        <Button size="sm" variant="ghost" className="ml-auto" onClick={() => vm.setShowDone(!vm.showDone)}>
          {vm.showDone ? t("tasks.showPending") : t("tasks.showDone")}
        </Button>
      </div>

      {vm.query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
      {vm.query.isError && <p className="text-sm text-destructive">{String(vm.query.error)}</p>}
      {!vm.query.isLoading && order.every((k) => vm.groups[k].length === 0) && (
        <p className="text-sm text-muted-foreground">{vm.showDone ? t("tasks.emptyDone") : t("tasks.empty")}</p>
      )}

      {order.map((key) =>
        vm.groups[key].length === 0 ? null : (
          <section key={key} className="flex flex-col gap-2">
            <h3 className={cn("text-sm font-semibold", key === "overdue" && "text-destructive")}>
              {t(`tasks.group.${key}`)} <span className="text-muted-foreground">({vm.groups[key].length})</span>
            </h3>
            <Card>
              <ul className="divide-y">
                {vm.groups[key].map((task) => (
                  <li key={task.id} className="flex items-start gap-3 p-3">
                    <button
                      type="button"
                      className="mt-0.5 text-muted-foreground hover:text-primary"
                      aria-label={task.status === "done" ? t("actions.reopen") : t("actions.complete")}
                      disabled={vm.busyId === task.id}
                      onClick={() => (task.status === "done" ? vm.reopen(task.id) : vm.complete(task.id))}
                    >
                      {vm.busyId === task.id ? <Loader2 className="h-5 w-5 animate-spin" />
                        : task.status === "done" ? <CheckCircle2 className="h-5 w-5 text-primary" /> : <Circle className="h-5 w-5" />}
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className={cn("break-words text-sm font-medium", task.status === "done" && "text-muted-foreground line-through")}>
                        {task.title}
                      </p>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        {whenLabel(task, i18n.language) && <span>{whenLabel(task, i18n.language)}</span>}
                        <Badge variant="outline">{task.list_name}</Badge>
                        {task.priority === "high" && <Badge variant="destructive">{t("priority.high")}</Badge>}
                        {task.recurrence && <span className="inline-flex items-center gap-0.5"><Repeat className="h-3 w-3" />{t(`recurrence.${task.recurrence}`)}</span>}
                        {task.created_by !== "marcelo" && <span>· {t("byAgent", { agent: task.created_by })}</span>}
                      </div>
                      {task.notes && <p className="mt-1 whitespace-pre-wrap break-words text-xs text-muted-foreground">{task.notes}</p>}
                    </div>
                    <Button size="icon" variant="ghost" aria-label={t("actions.delete")}
                      className="opacity-60 hover:opacity-100"
                      onClick={() => onDelete({ kind: "tasks", id: task.id, title: task.title })}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        ),
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ agenda */

function AgendaTab({ onDelete }: { onDelete: (t: DeleteTarget) => void }) {
  const { t, i18n } = useTranslation("personal");
  const vm = usePersonalAgendaViewModel();

  function renderItem(item: AgendaItem) {
    const { time } = splitLocal(item.starts_at);
    return (
      <li key={`${item.kind}-${item.id}`} className="flex items-start gap-3 p-3">
        <span className="w-12 shrink-0 pt-0.5 text-sm tabular-nums text-muted-foreground">
          {item.has_time ? time : t("agenda.allDay")}
        </span>
        <div className="min-w-0 flex-1">
          <p className="break-words text-sm font-medium">
            {item.kind === "task" ? <ListTodo className="mr-1 inline h-3.5 w-3.5" /> : <CalendarDays className="mr-1 inline h-3.5 w-3.5" />}
            {item.title}
          </p>
          <div className="mt-1 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
            {item.location && <span className="inline-flex items-center gap-0.5"><MapPin className="h-3 w-3" />{item.location}</span>}
            {item.list_name && <Badge variant="outline">{item.list_name}</Badge>}
            {item.overdue && <Badge variant="destructive">{t("tasks.group.overdue")}</Badge>}
          </div>
        </div>
        {item.kind === "task" ? (
          <Button size="sm" variant="ghost" onClick={() => vm.completeTask(item.id)}>{t("actions.complete")}</Button>
        ) : (
          <>
            <Button size="sm" variant="ghost" onClick={() => vm.cancelEvent(item.id)}>{t("actions.cancel")}</Button>
            <Button size="icon" variant="ghost" aria-label={t("actions.delete")} className="opacity-60 hover:opacity-100"
              onClick={() => onDelete({ kind: "events", id: item.id, title: item.title })}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </>
        )}
      </li>
    );
  }

  return (
    <div className="flex flex-col gap-4 pt-4">
      <Card>
        <CardContent className="p-4">
          <form
            className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,3fr)_auto_auto_minmax(0,2fr)_auto]"
            onSubmit={(e) => {
              e.preventDefault();
              void vm.submit();
            }}
          >
            <Input placeholder={t("agenda.newPlaceholder")} value={vm.draft.title}
              onChange={(e) => vm.setDraft({ ...vm.draft, title: e.target.value })} className="max-md:text-base" />
            <input type="date" className={fieldClass} value={vm.draft.date} aria-label={t("fields.date")}
              onChange={(e) => vm.setDraft({ ...vm.draft, date: e.target.value })} />
            <input type="time" className={fieldClass} value={vm.draft.time} aria-label={t("fields.time")}
              onChange={(e) => vm.setDraft({ ...vm.draft, time: e.target.value })} />
            <Input placeholder={t("fields.location")} value={vm.draft.location}
              onChange={(e) => vm.setDraft({ ...vm.draft, location: e.target.value })} className="max-md:text-base" />
            <Button type="submit" disabled={vm.status === "submitting" || !vm.draft.title.trim() || !vm.draft.date}>
              {vm.status === "submitting" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              <span className="ml-1">{t("actions.add")}</span>
            </Button>
          </form>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <select className={fieldClass} value={vm.draft.reminder} aria-label={t("fields.reminder")}
              onChange={(e) => vm.setDraft({ ...vm.draft, reminder: Number(e.target.value) })}>
              {[-1, 0, 15, 60, 120, 1440].map((m) => <option key={m} value={m}>{t(`reminder.${m}`)}</option>)}
            </select>
            <select className={fieldClass} value={vm.draft.recurrence} aria-label={t("fields.recurrence")}
              onChange={(e) => vm.setDraft({ ...vm.draft, recurrence: e.target.value as Recurrence })}>
              {RECURRENCES.map((r) => <option key={r} value={r}>{t(`recurrence.${r || "none"}`)}</option>)}
            </select>
            {vm.error && <span className="text-destructive">{vm.error}</span>}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Label htmlFor="agenda-start">{t("agenda.from")}</Label>
        <input id="agenda-start" type="date" className={fieldClass} value={vm.start} onChange={(e) => vm.setStart(e.target.value || todayLocal())} />
        <span className="text-muted-foreground">{t("agenda.next14")}</span>
      </div>

      {vm.query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
      {vm.query.isError && <p className="text-sm text-destructive">{String(vm.query.error)}</p>}
      {!vm.query.isLoading && vm.days.length === 0 && <p className="text-sm text-muted-foreground">{t("agenda.empty")}</p>}
      {vm.days.map(([day, items]) => (
        <section key={day} className="flex flex-col gap-2">
          <h3 className={cn("text-sm font-semibold capitalize", day === "overdue" && "text-destructive")}>
            {day === "overdue" ? t("tasks.group.overdue") : formatDay(day, i18n.language)}
          </h3>
          <Card><ul className="divide-y">{items.map(renderItem)}</ul></Card>
        </section>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ notes */

function NotesTab({ onDelete }: { onDelete: (t: DeleteTarget) => void }) {
  const { t, i18n } = useTranslation("personal");
  const vm = usePersonalNotesViewModel();

  return (
    <div className="flex flex-col gap-4 pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input placeholder={t("notes.search")} value={vm.search} onChange={(e) => vm.setSearch(e.target.value)}
          className="max-w-sm max-md:text-base" />
        <Button size="sm" variant={vm.archived ? "default" : "outline"} onClick={() => vm.setArchived(!vm.archived)}>
          {vm.archived ? t("notes.showActive") : t("notes.showArchived")}
        </Button>
        <Button size="sm" className="ml-auto" onClick={() => vm.open()}>
          <Plus className="mr-1 h-4 w-4" />{t("notes.new")}
        </Button>
      </div>

      {vm.query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
      {vm.query.isError && <p className="text-sm text-destructive">{String(vm.query.error)}</p>}
      {!vm.query.isLoading && vm.notes.length === 0 && <p className="text-sm text-muted-foreground">{t("notes.empty")}</p>}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {vm.notes.map((note) => (
          <Card key={note.id} className="flex flex-col">
            <CardContent className="flex flex-1 flex-col gap-2 p-4">
              <div className="flex items-start gap-2">
                <button type="button" className="min-w-0 flex-1 text-left" onClick={() => vm.open(note)}>
                  <p className="break-words font-medium">{note.title}</p>
                </button>
                <Button size="icon" variant="ghost" aria-label={note.pinned ? t("actions.unpin") : t("actions.pin")}
                  onClick={() => vm.togglePin(note)}>
                  {note.pinned ? <PinOff className="h-4 w-4" /> : <Pin className="h-4 w-4" />}
                </Button>
              </div>
              <button type="button" className="text-left" onClick={() => vm.open(note)}>
                <p className="line-clamp-6 whitespace-pre-wrap break-words text-sm text-muted-foreground">{note.content}</p>
              </button>
              <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-2 text-xs text-muted-foreground">
                {note.tags.map((tag) => <Badge key={tag} variant="outline">{tag}</Badge>)}
                <span className="ml-auto">{new Intl.DateTimeFormat(i18n.language, { dateStyle: "short" }).format(new Date(note.updated_at))}</span>
                <Button size="icon" variant="ghost" aria-label={note.archived ? t("actions.unarchive") : t("actions.archive")}
                  onClick={() => vm.toggleArchive(note)}>
                  {note.archived ? <ArchiveRestore className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
                </Button>
                <Button size="icon" variant="ghost" aria-label={t("actions.delete")}
                  onClick={() => onDelete({ kind: "notes", id: note.id, title: note.title })}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {vm.editing && (
        <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4">
          <div className="fixed inset-0 bg-black/50" onClick={() => vm.setEditing(null)} />
          <Card className="relative my-auto w-full max-w-2xl">
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">{vm.editing.id ? t("notes.edit") : t("notes.new")}</h3>
                <Button size="icon" variant="ghost" aria-label={t("actions.close")} onClick={() => vm.setEditing(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <Input placeholder={t("fields.title")} value={vm.editing.title} className="max-md:text-base"
                onChange={(e) => vm.setEditing({ ...vm.editing!, title: e.target.value })} />
              <Textarea rows={12} placeholder={t("fields.content")} value={vm.editing.content} className="max-md:text-base"
                onChange={(e) => vm.setEditing({ ...vm.editing!, content: e.target.value })} />
              <Input placeholder={t("fields.tags")} value={vm.editing.tags} className="max-md:text-base"
                onChange={(e) => vm.setEditing({ ...vm.editing!, tags: e.target.value })} />
              {vm.error && <p className="text-sm text-destructive">{vm.error}</p>}
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => vm.setEditing(null)}>{t("actions.cancel")}</Button>
                <Button onClick={() => void vm.save()} disabled={vm.status === "submitting" || !vm.editing.title.trim()}>
                  {vm.status === "submitting" && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
                  {t("actions.save")}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

