import { useTranslation } from "react-i18next";
import { Send } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AgentTelegramStatus } from "@/hooks/useAgent";

/**
 * Telegram channel health for one agent, as an icon.
 *
 * Two independent signals behind it (see backend/app/core/agent_telegram.py):
 * the channel is *installed* (bot token + home channel in the agent's own
 * profile .env) and the gateway daemon that serves it is *running*. They fail
 * separately — an installed channel whose gateway is down silently drops
 * every message — so "not_running" is its own state, not a generic error.
 *
 * "unknown" means the systemd check itself could not run (host-bridge
 * unreachable). It is rendered as muted, never as red: we did not observe a
 * failure, we failed to observe.
 */

const ICON_CLASS: Record<AgentTelegramStatus["status"], string> = {
  ok: "text-emerald-500",
  not_running: "text-destructive",
  not_configured: "text-amber-500",
  unknown: "text-muted-foreground",
  not_applicable: "text-muted-foreground/40",
};

export function TelegramStatusBadge({
  status,
  showLabel = false,
  className,
}: {
  status: AgentTelegramStatus | undefined;
  /** Render the state in words next to the icon (detail page); the list and
   *  org chart use the icon alone with the same text as its tooltip. */
  showLabel?: boolean;
  className?: string;
}) {
  const { t } = useTranslation("agent");
  if (!status) return null;

  const label = t(`telegram.status.${status.status}`);
  const detail = [
    label,
    status.home_channel_name
      ? t("telegram.channel", { name: status.home_channel_name })
      : null,
    status.service ?? null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <span
      className={cn("inline-flex items-center gap-1 text-xs", className)}
      title={detail}
      aria-label={t("telegram.ariaLabel", { status: label })}
    >
      <Send className={cn("h-3.5 w-3.5 shrink-0", ICON_CLASS[status.status])} />
      {showLabel && <span className="text-muted-foreground">{label}</span>}
    </span>
  );
}
