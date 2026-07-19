import { useState } from "react";
import { Bell, Check, ChevronDown, ChevronRight, Loader2, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { formatRelativeTime } from "@/components/layout/NotificationBell";
import {
  useCleanupNotifications,
  useMarkNotificationsRead,
  useNotifications,
  type AppNotification,
  type CleanupMode,
} from "@/hooks/useNotifications";
type Filter = "all" | "unread" | "error";

const SEVERITY_BADGE: Record<AppNotification["severity"], string> = {
  error: "border-destructive/40 text-destructive",
  warning: "border-amber-500/40 text-amber-600",
  success: "border-emerald-500/40 text-emerald-600",
  info: "border-sky-500/40 text-sky-600",
};

const CLEANUP_OPTIONS: { key: string; labelKey: string; descriptionKey: string; payload: CleanupMode }[] = [
  {
    key: "keep30",
    labelKey: "cleanup.keep30Label",
    descriptionKey: "cleanup.keep30Description",
    payload: { mode: "keep_days", keep_days: 30 },
  },
  {
    key: "keep15",
    labelKey: "cleanup.keep15Label",
    descriptionKey: "cleanup.keep15Description",
    payload: { mode: "keep_days", keep_days: 15 },
  },
  {
    key: "clearAll",
    labelKey: "cleanup.clearAllLabel",
    descriptionKey: "cleanup.clearAllDescription",
    payload: { mode: "all" },
  },
];

const FILTER_OPTIONS: [Filter, string][] = [
  ["all", "filters.all"],
  ["unread", "filters.unread"],
  ["error", "filters.error"],
];

/** Full record of notifications (one per cron run, ingested server-side).
 * Read state is persistent (read_at); the cleanup menu purges the record
 * entirely or keeps only the last 15/30 days. */
export default function NotificationsPage() {
  const { t } = useTranslation("notifications");
  const [filter, setFilter] = useState<Filter>("all");
  const { data, isLoading } = useNotifications(
    filter === "all" ? {} : filter === "unread" ? { unreadOnly: true } : { severity: "error" }
  );
  const markRead = useMarkNotificationsRead();
  const cleanup = useCleanupNotifications();
  const [pendingCleanup, setPendingCleanup] = useState<(typeof CLEANUP_OPTIONS)[number] | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const notifications = data?.notifications ?? [];
  const unreadCount = data?.unread_count ?? 0;

  const toggleExpanded = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const confirmCleanup = async () => {
    if (!pendingCleanup) return;
    await cleanup.mutateAsync(pendingCleanup.payload);
    setPendingCleanup(null);
  };

  return (
    // Full-bleed page (see AppLayout): header/filters stay fixed and the
    // notification list scrolls inside its own card.
    <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Bell className="h-5 w-5" /> {t("title")}
          {unreadCount > 0 && (
            <Badge variant="outline" className="border-destructive/40 text-destructive">
              {t("unreadCount", { count: unreadCount })}
            </Badge>
          )}
        </h1>
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={unreadCount === 0 || markRead.isPending}
            onClick={() => markRead.mutate({ all: true })}
          >
            <Check className="h-4 w-4" /> {t("markAllRead")}
          </Button>
          {CLEANUP_OPTIONS.map((opt) => (
            <Button
              key={opt.key}
              size="sm"
              variant={opt.payload.mode === "all" ? "destructive" : "outline"}
              className="gap-1.5"
              onClick={() => setPendingCleanup(opt)}
            >
              <Trash2 className="h-4 w-4" /> {t(opt.labelKey)}
            </Button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-1">
        {FILTER_OPTIONS.map(([value, labelKey]) => (
          <Button
            key={value}
            size="sm"
            variant={filter === value ? "secondary" : "ghost"}
            onClick={() => setFilter(value)}
          >
            {t(labelKey)}
          </Button>
        ))}
        {data && (
          <span className="ml-2 text-xs text-muted-foreground">
            {t("totalRecorded", { count: data.total })}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {!isLoading && notifications.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            {t("empty")}
          </CardContent>
        </Card>
      )}

      {notifications.length > 0 && (
        <Card className="min-h-0 flex-1 overflow-hidden">
          <CardContent className="h-full divide-y divide-border/50 overflow-y-auto p-0">
            {notifications.map((n) => {
              const isExpanded = expanded.has(n.id);
              const detail = n.message ?? n.summary;
              return (
                <div
                  key={n.id}
                  className={cn("px-4 py-3", !n.read_at && "bg-primary/[0.04]")}
                >
                  {/* div, not <button>: the per-row "Read" action is a real
                      <Button> inside and buttons can't nest */}
                  <div
                    role="button"
                    tabIndex={0}
                    className="flex w-full cursor-pointer items-start gap-2 text-left"
                    onClick={() => toggleExpanded(n.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") toggleExpanded(n.id);
                    }}
                  >
                    {isExpanded ? (
                      <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    ) : (
                      <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        {!n.read_at && <span className="h-2 w-2 shrink-0 rounded-full bg-primary" />}
                        <span className="text-sm font-medium">{n.title}</span>
                        <Badge variant="outline" className={SEVERITY_BADGE[n.severity]}>
                          {n.severity}
                        </Badge>
                        {n.profile && (
                          <Badge variant="outline" className="text-muted-foreground">
                            {n.profile}
                          </Badge>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {n.script_name && <span className="font-mono">{n.script_name} · </span>}
                        {new Date(n.occurred_at).toLocaleString()} ({formatRelativeTime(n.occurred_at)})
                      </p>
                      {!isExpanded && detail && (
                        <p className="mt-1 line-clamp-2 whitespace-pre-wrap break-words text-xs text-muted-foreground">
                          {detail}
                        </p>
                      )}
                    </div>
                    {!n.read_at && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="shrink-0 gap-1 text-xs text-muted-foreground"
                        onClick={(e) => {
                          e.stopPropagation();
                          markRead.mutate({ ids: [n.id] });
                        }}
                      >
                        <Check className="h-3.5 w-3.5" /> {t("read")}
                      </Button>
                    )}
                  </div>
                  {isExpanded && (
                    <div className="ml-6 mt-2 space-y-2">
                      {n.message && (
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                            {t("errorLabel")}
                          </p>
                          <pre className="mt-0.5 whitespace-pre-wrap break-words rounded bg-destructive/5 px-2 py-1.5 font-mono text-xs text-destructive/90">
                            {n.message}
                          </pre>
                        </div>
                      )}
                      {n.summary && (
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                            {t("runSummary")}
                          </p>
                          <pre className="mt-0.5 whitespace-pre-wrap break-words rounded bg-muted/50 px-2 py-1.5 font-mono text-xs text-muted-foreground">
                            {n.summary}
                          </pre>
                        </div>
                      )}
                      {!detail && (
                        <p className="text-xs italic text-muted-foreground">
                          {t("noRunOutput")}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={pendingCleanup !== null}
        title={pendingCleanup ? t(pendingCleanup.labelKey) : ""}
        description={pendingCleanup ? t(pendingCleanup.descriptionKey) : undefined}
        confirmLabel={t("cleanup.confirmLabel")}
        loading={cleanup.isPending}
        onConfirm={confirmCleanup}
        onCancel={() => setPendingCleanup(null)}
      />
    </div>
  );
}
