import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Loader2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useAcceptSuggestion,
  useDismissSuggestion,
  usePersonalSuggestions,
  type CaptureSuggestion,
  type SuggestionKind,
} from "@/hooks/usePersonalContacts";

const KINDS: SuggestionKind[] = ["demand", "task", "note"];

function when(value: string | null, locale: string): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

export function SuggestionCard({ suggestion }: { suggestion: CaptureSuggestion }) {
  const { t, i18n } = useTranslation("personal");
  const [kind, setKind] = useState<SuggestionKind>(suggestion.kind);
  const [details, setDetails] = useState(suggestion.details);
  const [confirmDismiss, setConfirmDismiss] = useState(false);
  const accept = useAcceptSuggestion();
  const dismiss = useDismissSuggestion();
  const busy = accept.isPending || dismiss.isPending;
  const finishDismiss = () => {
    dismiss.mutate(suggestion.id, { onSettled: () => setConfirmDismiss(false) });
  };

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="break-words font-medium">{suggestion.title}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {suggestion.source_kind === 'group'
                ? `${t('groups.origin')}: ${suggestion.group_name || t('groups.unknown')}`
                : `${t('origins.contact')}: ${suggestion.contact_name || t("suggestions.unknownContact")}${suggestion.contact_phone ? ` · ${suggestion.contact_phone}` : ''}`}
            </p>
          </div>
          <Badge variant={suggestion.status === "pending" ? "secondary" : "outline"}>
            {t(`suggestions.status.${suggestion.status}`)}
          </Badge>
        </div>
        {suggestion.source_kind === 'group' && <p className="break-words text-sm text-muted-foreground">{t('origins.requester')}: {suggestion.source_author || suggestion.source_author_id || t('origins.unknownAuthor')}{suggestion.source_at ? ` · ${when(suggestion.source_at, i18n.language)}` : ''}</p>}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{t("suggestions.suggestedKind")}: {t(`contacts.suggestions.kinds.${suggestion.kind}`)}</span>
          <span>{t("suggestions.createdAt")}: {when(suggestion.created_at, i18n.language)}</span>
          {suggestion.decided_at && <span>{t("suggestions.decidedAt")}: {when(suggestion.decided_at, i18n.language)}</span>}
        </div>
        {suggestion.status === "pending" ? (
          <>
            <Textarea value={details} onChange={(e) => setDetails(e.target.value)} aria-label={t("suggestions.details")} />
            <div className="flex flex-wrap items-center gap-2">
              <Select
                className="h-9 rounded-md border bg-background px-2 text-sm max-md:text-base"
                value={kind}
                onChange={(e) => setKind(e.target.value as SuggestionKind)}
                aria-label={t("suggestions.kind")}
              >
                {KINDS.map((item) => <option key={item} value={item}>{t(`contacts.suggestions.kinds.${item}`)}</option>)}
              </Select>
              <Button disabled={busy} onClick={() => accept.mutate({ id: suggestion.id, kind, details })}>
                {accept.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Check className="mr-1 h-4 w-4" />}
                {t("contacts.suggestions.accept")}
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => setConfirmDismiss(true)}>
                <X className="mr-1 h-4 w-4" />
                {t("contacts.suggestions.dismiss")}
              </Button>
              <ConfirmDialog
                open={confirmDismiss}
                title={t("suggestions.dismissTitle")}
                description={t("suggestions.dismissDescription")}
                confirmLabel={t("contacts.suggestions.dismiss")}
                loading={dismiss.isPending}
                onConfirm={finishDismiss}
                onCancel={() => setConfirmDismiss(false)}
              />
            </div>
          </>
        ) : (
          suggestion.details && <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">{suggestion.details}</p>
        )}
      </CardContent>
    </Card>
  );
}

/** The Maia's capture suggestions, a tab of Pessoal since 2026-10-19 (it was its own /suggestions page). */
export function SuggestionsTab() {
  const { t } = useTranslation("personal");
  const [status, setStatus] = useState("pending");
  const query = usePersonalSuggestions(status || "all");
  const suggestions = query.data?.pages.flat() ?? [];

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">{t("suggestions.description")}</p>
      <div className="flex flex-wrap items-center gap-2">
        {(["pending", "accepted", "dismissed", ""] as const).map((value) => (
          <Button key={value || "all"} size="sm" variant={status === value ? "default" : "outline"} onClick={() => setStatus(value)}>
            {t(value ? `suggestions.status.${value}` : "suggestions.all")}
          </Button>
        ))}
      </div>
      {query.isLoading && <Loader2 className="mx-auto h-5 w-5 animate-spin" />}
      {query.isError && (
        <div className="space-y-2 text-sm text-destructive">
          <p>{t("suggestions.loadError")}</p>
          <Button variant="outline" size="sm" onClick={() => query.refetch()}>{t("suggestions.retry")}</Button>
        </div>
      )}
      {!query.isLoading && suggestions.length === 0 && <p className="text-sm text-muted-foreground">{t("suggestions.empty")}</p>}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        {suggestions.map((suggestion) => <SuggestionCard key={suggestion.id} suggestion={suggestion} />)}
      </div>
      {query.hasNextPage && (
        <Button variant="outline" className="self-center" disabled={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
          {query.isFetchingNextPage && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          {t("suggestions.loadMore")}
        </Button>
      )}
    </div>
  );
}
