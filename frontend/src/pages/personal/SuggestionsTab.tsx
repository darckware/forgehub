import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, CheckCheck, Loader2, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useAcceptSuggestion,
  useBulkAcceptSuggestions,
  useBulkDismissSuggestions,
  useCleanupSuggestions,
  useDeleteSuggestions,
  useDismissSuggestion,
  usePersonalSuggestionCounts,
  usePersonalSuggestions,
  type CaptureSuggestion,
  type SuggestionKind,
} from "@/hooks/usePersonalContacts";

const KINDS: SuggestionKind[] = ["demand", "task", "note"];

function when(value: string | null, locale: string): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function statusBadgeVariant(status: CaptureSuggestion["status"]): "warning" | "success" | "secondary" {
  if (status === "pending") return "warning";
  if (status === "accepted") return "success";
  return "secondary";
}

export function SuggestionCard({
  suggestion,
  checked,
  onToggleCheck,
}: {
  suggestion: CaptureSuggestion;
  checked?: boolean;
  onToggleCheck?: (id: string) => void;
}) {
  const { t, i18n } = useTranslation("personal");
  const [kind, setKind] = useState<SuggestionKind>(suggestion.kind);
  const [details, setDetails] = useState(suggestion.details);
  const [confirmDismiss, setConfirmDismiss] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const accept = useAcceptSuggestion();
  const dismiss = useDismissSuggestion();
  const remove = useDeleteSuggestions();
  const busy = accept.isPending || dismiss.isPending || remove.isPending;
  const finishDismiss = () => {
    dismiss.mutate(suggestion.id, { onSettled: () => setConfirmDismiss(false) });
  };
  const finishDelete = () => {
    remove.mutate([suggestion.id], { onSettled: () => setConfirmDelete(false) });
  };

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex min-w-0 flex-1 items-start gap-2.5">
            {onToggleCheck && (
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 shrink-0"
                checked={Boolean(checked)}
                onChange={() => onToggleCheck(suggestion.id)}
                aria-label={t("suggestions.select", { title: suggestion.title })}
              />
            )}
            <div className="min-w-0 flex-1">
              <h2 className="break-words font-medium">{suggestion.title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {suggestion.source_kind === "group"
                  ? `${t("groups.origin")}: ${suggestion.group_name || t("groups.unknown")}`
                  : `${t("origins.contact")}: ${suggestion.contact_name || t("suggestions.unknownContact")}${suggestion.contact_phone ? ` · ${suggestion.contact_phone}` : ""}`}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <Badge variant={statusBadgeVariant(suggestion.status)}>
              {t(`suggestions.status.${suggestion.status}`)}
            </Badge>
            <Button
              size="icon"
              variant="ghost"
              aria-label={t("actions.delete")}
              className="h-8 w-8 opacity-60 hover:opacity-100"
              disabled={busy}
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {suggestion.source_kind === "group" && (
          <p className="break-words text-sm text-muted-foreground">
            {t("origins.requester")}: {suggestion.source_author || suggestion.source_author_id || t("origins.unknownAuthor")}
            {suggestion.source_at ? ` · ${when(suggestion.source_at, i18n.language)}` : ""}
          </p>
        )}
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
        <ConfirmDialog
          open={confirmDelete}
          title={t("suggestions.deleteTitle", { count: 1 })}
          description={t("delete.description", { title: suggestion.title })}
          confirmLabel={t("delete.confirm")}
          variant="destructive"
          loading={remove.isPending}
          onConfirm={finishDelete}
          onCancel={() => setConfirmDelete(false)}
        />
      </CardContent>
    </Card>
  );
}

type BulkActionTarget =
  | { kind: "accept"; ids?: string[]; allPending?: boolean; count: number }
  | { kind: "dismiss"; ids?: string[]; allPending?: boolean; count: number }
  | { kind: "delete"; ids: string[]; count: number }
  | { kind: "cleanup"; keepDays: number };

/** The Maia's capture suggestions, a tab of Pessoal since 2026-10-19 (it was its own /suggestions page). */
export function SuggestionsTab() {
  const { t } = useTranslation("personal");
  const [status, setStatus] = useState("pending");
  const [checked, setChecked] = useState<string[]>([]);
  const [bulkTarget, setBulkTarget] = useState<BulkActionTarget | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const query = usePersonalSuggestions(status || "all");
  const countsQuery = usePersonalSuggestionCounts();
  const bulkAccept = useBulkAcceptSuggestions();
  const bulkDismiss = useBulkDismissSuggestions();
  const bulkDelete = useDeleteSuggestions();
  const cleanup = useCleanupSuggestions();

  const suggestions = query.data?.pages.flat() ?? [];
  const counts = countsQuery.data;
  const visibleIds = suggestions.map((s) => s.id);
  const allChecked = visibleIds.length > 0 && visibleIds.every((id) => checked.includes(id));

  const selectedPendingIds = suggestions
    .filter((s) => checked.includes(s.id) && s.status === "pending")
    .map((s) => s.id);
  const totalPendingCount = counts?.pending ?? suggestions.filter((s) => s.status === "pending").length;
  const olderCount = counts?.older_than_15_days ?? 0;

  const toggleCheck = (id: string) => {
    setChecked((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const toggleAll = () => {
    setChecked(allChecked ? [] : visibleIds);
  };

  const changeStatus = (next: string) => {
    setStatus(next);
    setChecked([]);
  };

  const countFor = (filter: "pending" | "accepted" | "dismissed" | ""): number | undefined => {
    if (!counts) return undefined;
    if (filter === "pending") return counts.pending;
    if (filter === "accepted") return counts.accepted;
    if (filter === "dismissed") return counts.dismissed;
    return counts.all;
  };

  const bulkLoading = bulkAccept.isPending || bulkDismiss.isPending || bulkDelete.isPending || cleanup.isPending;

  const confirmBulkAction = async () => {
    if (!bulkTarget) return;
    setBulkError(null);
    try {
      if (bulkTarget.kind === "accept") {
        await bulkAccept.mutateAsync({
          ids: bulkTarget.ids,
          all_pending: bulkTarget.allPending,
        });
      } else if (bulkTarget.kind === "dismiss") {
        await bulkDismiss.mutateAsync({
          ids: bulkTarget.ids,
          all_pending: bulkTarget.allPending,
        });
      } else if (bulkTarget.kind === "delete") {
        await bulkDelete.mutateAsync(bulkTarget.ids);
      } else {
        await cleanup.mutateAsync({ keep_days: bulkTarget.keepDays });
      }
      setChecked([]);
      setBulkTarget(null);
    } catch (e) {
      setBulkError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="flex flex-col gap-4 pt-4">
      <p className="text-sm text-muted-foreground">{t("suggestions.description")}</p>
      <div className="flex flex-wrap items-center gap-2">
        {(["pending", "accepted", "dismissed", ""] as const).map((value) => {
          const count = countFor(value);
          const label = t(value ? `suggestions.status.${value}` : "suggestions.all");
          return (
            <Button
              key={value || "all"}
              size="sm"
              variant={status === value ? "default" : "outline"}
              onClick={() => changeStatus(value)}
            >
              {count !== undefined ? `${label} (${count})` : label}
            </Button>
          );
        })}
        {status === "" && counts && (
          <span className="text-xs text-muted-foreground">
            {t("suggestions.allSummary", {
              pending: counts.pending,
              accepted: counts.accepted,
              dismissed: counts.dismissed,
            })}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {suggestions.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" className="h-4 w-4" checked={allChecked} onChange={toggleAll} />
            {checked.length > 0 ? t("suggestions.selected", { count: checked.length }) : t("suggestions.selectAll")}
          </label>
        )}

        {checked.length > 0 ? (
          <>
            {selectedPendingIds.length > 0 && (
              <>
                <Button
                  size="sm"
                  onClick={() => {
                    setBulkError(null);
                    setBulkTarget({ kind: "accept", ids: selectedPendingIds, count: selectedPendingIds.length });
                  }}
                >
                  <CheckCheck className="mr-1 h-4 w-4" />
                  {t("suggestions.acceptSelected", { count: selectedPendingIds.length })}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setBulkError(null);
                    setBulkTarget({ kind: "dismiss", ids: selectedPendingIds, count: selectedPendingIds.length });
                  }}
                >
                  <X className="mr-1 h-4 w-4" />
                  {t("suggestions.dismissSelected", { count: selectedPendingIds.length })}
                </Button>
              </>
            )}
            <Button
              size="sm"
              variant="destructive"
              onClick={() => {
                setBulkError(null);
                setBulkTarget({ kind: "delete", ids: checked, count: checked.length });
              }}
            >
              <Trash2 className="mr-1 h-4 w-4" />
              {t("suggestions.deleteSelected", { count: checked.length })}
            </Button>
          </>
        ) : (
          totalPendingCount > 0 && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setBulkError(null);
                  setBulkTarget({ kind: "accept", allPending: true, count: totalPendingCount });
                }}
              >
                <CheckCheck className="mr-1 h-4 w-4" />
                {t("suggestions.acceptAll", { count: totalPendingCount })}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setBulkError(null);
                  setBulkTarget({ kind: "dismiss", allPending: true, count: totalPendingCount });
                }}
              >
                <X className="mr-1 h-4 w-4" />
                {t("suggestions.dismissAll", { count: totalPendingCount })}
              </Button>
            </>
          )
        )}

        <Button
          size="sm"
          variant="outline"
          className="ml-auto"
          onClick={() => {
            setBulkError(null);
            setBulkTarget({ kind: "cleanup", keepDays: 15 });
          }}
        >
          <Trash2 className="mr-1 h-4 w-4" />
          {olderCount > 0 ? t("suggestions.cleanup15DaysCount", { count: olderCount }) : t("suggestions.cleanup15Days")}
        </Button>
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
        {suggestions.map((suggestion) => (
          <SuggestionCard
            key={suggestion.id}
            suggestion={suggestion}
            checked={checked.includes(suggestion.id)}
            onToggleCheck={toggleCheck}
          />
        ))}
      </div>
      {query.hasNextPage && (
        <Button variant="outline" className="self-center" disabled={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
          {query.isFetchingNextPage && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
          {t("suggestions.loadMore")}
        </Button>
      )}

      <ConfirmDialog
        open={Boolean(bulkTarget)}
        title={
          bulkTarget?.kind === "accept"
            ? t("suggestions.bulkAcceptTitle", { count: bulkTarget.count })
            : bulkTarget?.kind === "dismiss"
              ? t("suggestions.bulkDismissTitle", { count: bulkTarget.count })
              : bulkTarget?.kind === "cleanup"
                ? t("suggestions.cleanupTitle")
                : t("suggestions.deleteTitle", { count: bulkTarget?.kind === "delete" ? bulkTarget.count : 0 })
        }
        description={
          bulkTarget?.kind === "accept"
            ? t("suggestions.bulkAcceptDescription")
            : bulkTarget?.kind === "dismiss"
              ? t("suggestions.bulkDismissDescription")
              : bulkTarget?.kind === "cleanup"
                ? t("suggestions.cleanupDescription")
                : t("suggestions.deleteDescription", { count: bulkTarget?.kind === "delete" ? bulkTarget.count : 0 })
        }
        confirmLabel={
          bulkTarget?.kind === "accept"
            ? t("contacts.suggestions.accept")
            : bulkTarget?.kind === "dismiss"
              ? t("contacts.suggestions.dismiss")
              : bulkTarget?.kind === "cleanup"
                ? t("suggestions.cleanupConfirm")
                : t("delete.confirm")
        }
        variant={bulkTarget?.kind === "delete" || bulkTarget?.kind === "cleanup" ? "destructive" : "default"}
        loading={bulkLoading}
        error={bulkError}
        onConfirm={() => void confirmBulkAction()}
        onCancel={() => setBulkTarget(null)}
      />
    </div>
  );
}
