import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { cn } from "@/lib/utils";
import { useClickOutside } from "@/hooks/useClickOutside";
import {
  useMarkNotificationsRead,
  useNotifications,
  type AppNotification,
} from "@/hooks/useNotifications";
import { Button } from "@/components/ui/button";

export function formatRelativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

const SEVERITY_DOT: Record<AppNotification["severity"], string> = {
  error: "bg-destructive",
  warning: "bg-amber-500",
  success: "bg-emerald-500",
  info: "bg-sky-500",
};

/** Bell icon + dropdown over the persistent notification record
 * (GET /api/v1/notifications -- one row per cron run, ingested server-side).
 * Read state is stored in the DB (read_at): opening the dropdown marks
 * everything as read. Full history + cleanup live on /notifications. */
export function NotificationBell({
  collapsed,
  stretch = true,
}: {
  collapsed: boolean;
  /** Mirrors UserSettingsMenu's `stretch`: false renders a compact,
   * intrinsic-size icon button meant to sit inline next to it (the
   * expanded user row) instead of the full-width standalone rail row. */
  stretch?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);
  const { data } = useNotifications();
  const markRead = useMarkNotificationsRead();

  const notifications = data?.notifications ?? [];
  const unreadCount = data?.unread_count ?? 0;

  function handleToggle() {
    setOpen((v) => {
      const next = !v;
      if (next && unreadCount > 0) markRead.mutate({ all: true });
      return next;
    });
  }

  return (
    <div className={cn("relative", stretch && "w-full")} ref={containerRef}>
      <Button
        variant="ghost"
        size={collapsed || !stretch ? "icon" : "default"}
        className={cn("relative text-muted-foreground", stretch && "w-full", !collapsed && stretch && "justify-start gap-3")}
        aria-label="Notifications"
        title="Notifications"
        onClick={handleToggle}
      >
        <Bell className="h-4 w-4 shrink-0" />
        {!collapsed && stretch && "Notifications"}
        {unreadCount > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-destructive-foreground">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </Button>
      {open && (
        <div
          className="absolute bottom-0 left-full z-20 ml-1 flex max-h-80 w-72 flex-col rounded-md border border-border bg-card py-1 shadow-md"
        >
          <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
            Notifications
          </p>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {notifications.length === 0 && (
              <p className="px-3 py-3 text-xs italic text-muted-foreground">No notifications recorded.</p>
            )}
            {notifications.slice(0, 20).map((n) => (
              <div key={n.id} className="border-t border-border px-3 py-2 first:border-t-0">
                <p className="flex items-center gap-1.5 text-xs font-medium">
                  <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", SEVERITY_DOT[n.severity])} />
                  <span className="truncate">{n.title}</span>
                </p>
                <p className="text-[10px] text-muted-foreground">
                  {n.profile ?? n.source} · {formatRelativeTime(n.occurred_at)}
                </p>
                {(n.message ?? n.summary) && (
                  <p className="mt-1 line-clamp-3 whitespace-pre-wrap break-words rounded bg-muted/50 px-1.5 py-1 font-mono text-[10px] text-muted-foreground">
                    {n.message ?? n.summary}
                  </p>
                )}
              </div>
            ))}
          </div>
          <Link
            to="/notifications"
            onClick={() => setOpen(false)}
            className="border-t border-border px-3 py-2 text-center text-xs font-medium text-primary hover:underline"
          >
            View all notifications
          </Link>
        </div>
      )}
    </div>
  );
}
