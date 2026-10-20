import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  Check,
  Lightbulb,
  Loader2,
  MessageSquareText,
  Pencil,
  RotateCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ContactMessage, SuggestionKind } from "@/hooks/usePersonalContacts";
import { usePersonalContactsViewModel, type PersonalContactsViewModel } from "@/hooks/usePersonalContactsViewModel";
import { cn } from "@/lib/utils";

const fieldClass = "h-9 rounded-md border bg-background px-2 text-sm max-md:text-base";
const KINDS: SuggestionKind[] = ["task", "demand", "note"];

function when(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
}

export function ContactsTab() {
  const { t, i18n } = useTranslation("personal");
  const vm = usePersonalContactsViewModel();

  return (
    <div className="grid grid-cols-1 gap-4 pt-4 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
      <Card className={cn(vm.selectedPhone && "max-md:hidden")}>
        <CardContent className="flex flex-col gap-3 p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              className="pl-8 max-md:text-base"
              placeholder={t("contacts.search")}
              value={vm.search}
              onChange={(e) => vm.setSearch(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select className={fieldClass} value={vm.category} aria-label={t("contacts.category")}
              onChange={(e) => vm.setCategory(e.target.value)}>
              <option value="">{t("contacts.allCategories")}</option>
              {vm.categories.map((c) => <option key={c} value={c}>{t(`contacts.categories.${c}`, c)}</option>)}
            </select>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" className="h-4 w-4" checked={vm.onlyWithSuggestions}
                onChange={(e) => vm.setOnlyWithSuggestions(e.target.checked)} />
              {t("contacts.onlyWithSuggestions")}
            </label>
          </div>
          {vm.status === "loading" && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
          {vm.listError && <p className="text-sm text-destructive">{vm.listError}</p>}
          {vm.status !== "loading" && vm.contacts.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("contacts.empty")}</p>
          )}
          <ul className="-mx-4 divide-y border-t">
            {vm.contacts.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => vm.select(c.phone)}
                  className={cn("w-full space-y-1 px-4 py-3 text-left hover:bg-muted/50", vm.selectedPhone === c.phone && "bg-muted")}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className={cn("truncate font-medium", c.blocked && "text-muted-foreground line-through")}>
                      {c.name || c.phone_display}
                    </span>
                    {c.pending_suggestions > 0 && (
                      <Badge variant="warning" className="shrink-0">
                        <Lightbulb className="mr-1 h-3 w-3" />{c.pending_suggestions}
                      </Badge>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                    <span>{t(`contacts.categories.${c.category}`, c.category)}</span>
                    {c.relation && <span>{c.relation}</span>}
                    {c.last_contact_at && <span>{when(c.last_contact_at, i18n.language)}</span>}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card className={cn(!vm.selectedPhone && "max-md:hidden")}>
        <CardContent className="space-y-5 p-4">
          {vm.selectedPhone && (
            <button type="button" className="flex items-center gap-1 text-sm text-muted-foreground md:hidden"
              onClick={() => vm.select(undefined)}>
              <ArrowLeft className="h-4 w-4" /> {t("contacts.back")}
            </button>
          )}
          {!vm.selectedPhone && <p className="text-sm text-muted-foreground">{t("contacts.selectHint")}</p>}
          {vm.contactLoading && <Loader2 className="h-5 w-5 animate-spin" />}
          {vm.error && (
            <div className="flex items-start justify-between gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              <span className="break-words">{vm.error}</span>
              <button type="button" onClick={vm.dismissError} aria-label={t("actions.close")}><X className="h-4 w-4" /></button>
            </div>
          )}
          {vm.contact && <ContactDetail vm={vm} />}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={vm.confirmDelete}
        title={t("contacts.delete.title")}
        description={t("contacts.delete.description", { name: vm.contact?.name || vm.contact?.phone_display })}
        confirmLabel={t("delete.confirm")}
        variant="destructive"
        loading={vm.deleting}
        onConfirm={() => void vm.deleteContact()}
        onCancel={vm.cancelDelete}
      />
    </div>
  );
}

function ContactDetail({ vm }: { vm: PersonalContactsViewModel }) {
  const { t, i18n } = useTranslation("personal");
  const c = vm.contact!;
  const extras = Object.entries(c.other_data ?? {});

  return (
    <>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="break-words text-lg font-semibold">{c.name || c.phone_display}</h2>
          <p className="text-sm text-muted-foreground">{c.phone_display}</p>
        </div>
        {!vm.draft && (
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={vm.startEdit}><Pencil className="mr-1 h-4 w-4" />{t("actions.edit")}</Button>
            <Button size="sm" variant="outline" className="text-destructive hover:text-destructive" onClick={vm.askDelete}>
              <Trash2 className="mr-1 h-4 w-4" />{t("actions.delete")}
            </Button>
          </div>
        )}
      </div>

      {vm.draft ? <ContactForm vm={vm} /> : (
        <div className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline">{t(`contacts.categories.${c.category}`, c.category)}</Badge>
            {c.relation && <Badge variant="outline">{c.relation}</Badge>}
            {c.birthday && <Badge variant="outline">{t("contacts.birthday")}: {c.birthday}</Badge>}
            {c.blocked && <Badge variant="destructive"><Ban className="mr-1 h-3 w-3" />{t("contacts.blocked")}</Badge>}
          </div>
          <Field label={t("contacts.whoIs")} value={c.who_is} empty={t("contacts.notFilled")} />
          <Field label={t("contacts.howToTreat")} value={c.how_to_treat} empty={t("contacts.notFilled")} />
          {c.observations && <Field label={t("contacts.observations")} value={c.observations} />}
          {extras.length > 0 && (
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("contacts.otherData")}</p>
              <dl className="mt-1 grid grid-cols-1 gap-x-3 gap-y-1 sm:grid-cols-[auto_1fr]">
                {extras.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="break-words">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      )}

      {vm.suggestions.length > 0 && (
        <section className="space-y-2 rounded-md border border-amber-500/40 bg-amber-500/5 p-3">
          <h3 className="flex items-center gap-1.5 text-sm font-semibold">
            <Lightbulb className="h-4 w-4" />{t("contacts.suggestions.title")} ({vm.suggestions.length})
          </h3>
          <p className="text-xs text-muted-foreground">{t("contacts.suggestions.help")}</p>
          <ul className="space-y-2">
            {vm.suggestions.map((s) => {
              const kind = vm.kindFor(s.id, s.kind);
              const busy = vm.busySuggestion === s.id;
              return (
                <li key={s.id} className="rounded-md border bg-background p-3">
                  <p className="break-words text-sm font-medium">{s.title}</p>
                  {s.details && <p className="mt-0.5 whitespace-pre-wrap break-words text-xs text-muted-foreground">{s.details}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <select className={cn(fieldClass, "h-8 text-xs")} value={kind} aria-label={t("contacts.suggestions.kind")}
                      onChange={(e) => vm.setKindFor(s.id, e.target.value as SuggestionKind)}>
                      {KINDS.map((k) => <option key={k} value={k}>{t(`contacts.suggestions.kinds.${k}`)}</option>)}
                    </select>
                    <Button size="sm" disabled={busy} onClick={() => void vm.acceptSuggestion(s.id, kind)}>
                      {busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                      {t("contacts.suggestions.accept")}
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => void vm.dismissSuggestion(s.id)}>
                      {t("contacts.suggestions.dismiss")}
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <section className="space-y-3">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          <MessageSquareText className="h-4 w-4" />{t("contacts.history")} ({c.message_count})
        </h3>
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={(e) => { e.preventDefault(); void vm.addNote(); }}>
          <Input className="max-md:text-base" placeholder={t("contacts.notePlaceholder")} value={vm.note}
            onChange={(e) => vm.setNote(e.target.value)} />
          <Button type="submit" variant="outline" disabled={!vm.note.trim() || vm.status === "submitting"}>
            {t("contacts.addNote")}
          </Button>
        </form>
        {vm.messagesLoading && <Loader2 className="h-5 w-5 animate-spin" />}
        {!vm.messagesLoading && vm.messages.length === 0 && <p className="text-sm text-muted-foreground">{t("contacts.noHistory")}</p>}
        <ol className="space-y-3 border-l pl-4">
          {vm.messages.map((m) => <MessageRow key={m.id} m={m} vm={vm} locale={i18n.language} />)}
        </ol>
        {vm.hasMoreMessages && (
          <Button size="sm" variant="ghost" onClick={vm.loadMoreMessages} disabled={vm.loadingMoreMessages}>
            {vm.loadingMoreMessages && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}{t("contacts.loadMore")}
          </Button>
        )}
      </section>
    </>
  );
}

function Field({ label, value, empty }: { label: string; value: string; empty?: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cn("mt-0.5 whitespace-pre-wrap break-words", !value && "text-muted-foreground")}>{value || empty}</p>
    </div>
  );
}

function MessageRow({ m, vm, locale }: { m: ContactMessage; vm: PersonalContactsViewModel; locale: string }) {
  const { t } = useTranslation("personal");
  return (
    <li className="space-y-1">
      <div className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
        <span className={cn("font-medium", m.direction === "in" ? "text-foreground" : m.direction === "out" && "text-primary")}>
          {m.author || t(`contacts.direction.${m.direction}`)}
        </span>
        <span>{when(m.at, locale)}</span>
        {m.direction === "note" && <Badge variant="outline" className="h-4 px-1 text-[10px]">{t("contacts.direction.note")}</Badge>}
      </div>
      <p className="whitespace-pre-wrap text-sm [overflow-wrap:anywhere]">{m.text}</p>
      {m.context && (
        <p className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
          <span className="font-medium">{t("contacts.context")}:</span> {m.context}
        </p>
      )}
      {m.context_status === "pending" && (
        <p className="flex items-center gap-1 text-xs text-muted-foreground"><Loader2 className="h-3 w-3 animate-spin" />{t("contacts.contextPending")}</p>
      )}
      {m.context_status === "failed" && (
        <p className="flex flex-wrap items-center gap-2 text-xs text-destructive">
          <AlertTriangle className="h-3 w-3" />{t("contacts.contextFailed")}
          <button type="button" className="inline-flex items-center gap-1 underline" disabled={vm.reprocessing === m.id}
            onClick={() => vm.reprocess(m.id)}>
            <RotateCw className={cn("h-3 w-3", vm.reprocessing === m.id && "animate-spin")} />{t("contacts.retry")}
          </button>
        </p>
      )}
    </li>
  );
}

function ContactForm({ vm }: { vm: PersonalContactsViewModel }) {
  const { t } = useTranslation("personal");
  const d = vm.draft!;
  const set = (patch: Partial<typeof d>) => vm.setDraft({ ...d, ...patch });
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void vm.saveEdit(); }}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="contact-name">{t("contacts.name")}</Label>
          <Input id="contact-name" className="max-md:text-base" value={d.name} onChange={(e) => set({ name: e.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="contact-category">{t("contacts.category")}</Label>
          <select id="contact-category" className={cn(fieldClass, "w-full")} value={d.category} onChange={(e) => set({ category: e.target.value })}>
            {vm.categories.map((c) => <option key={c} value={c}>{t(`contacts.categories.${c}`, c)}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="contact-relation">{t("contacts.relation")}</Label>
          <Input id="contact-relation" className="max-md:text-base" value={d.relation} onChange={(e) => set({ relation: e.target.value })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="contact-birthday">{t("contacts.birthday")}</Label>
          <Input id="contact-birthday" className="max-md:text-base" placeholder="dd/mm" value={d.birthday}
            onChange={(e) => set({ birthday: e.target.value })} />
          {vm.birthdayError && <p className="text-xs text-destructive">{t("contacts.birthdayInvalid")}</p>}
        </div>
      </div>
      <div className="space-y-1">
        <Label htmlFor="contact-who">{t("contacts.whoIs")}</Label>
        <Textarea id="contact-who" rows={3} className="max-md:text-base" value={d.who_is} onChange={(e) => set({ who_is: e.target.value })} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="contact-how">{t("contacts.howToTreat")}</Label>
        <Textarea id="contact-how" rows={3} className="max-md:text-base" value={d.how_to_treat} onChange={(e) => set({ how_to_treat: e.target.value })} />
        <p className="text-xs text-muted-foreground">{t("contacts.howToTreatHelp")}</p>
      </div>
      <div className="space-y-1">
        <Label htmlFor="contact-obs">{t("contacts.observations")}</Label>
        <Textarea id="contact-obs" rows={2} className="max-md:text-base" value={d.observations} onChange={(e) => set({ observations: e.target.value })} />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="h-4 w-4" checked={d.blocked} onChange={(e) => set({ blocked: e.target.checked })} />
        {t("contacts.blockedLabel")}
      </label>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={vm.status === "submitting" || Boolean(vm.birthdayError)}>
          {vm.status === "submitting" && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}{t("actions.save")}
        </Button>
        <Button type="button" variant="outline" onClick={vm.cancelEdit}>{t("actions.cancel")}</Button>
      </div>
    </form>
  );
}
