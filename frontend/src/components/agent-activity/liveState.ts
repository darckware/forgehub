import type { TFunction } from "i18next";
import type { ActivityLiveState } from "@/hooks/useAgentActivity";

/** Compact elapsed time ("42 s", "5 min", "2 h", "3 d") -- units read the same in every locale. */
export function formatElapsed(fromIso: string | null | undefined, now: number = Date.now()): string | null {
  if (!fromIso) return null;
  const seconds = Math.max(0, Math.round((now - new Date(fromIso).getTime()) / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.floor(hours / 24)} d`;
}

export const LIVE_STATE_TONE: Record<ActivityLiveState["state"], string> = {
  executing: "bg-amber-500 ring-amber-500/25",
  thinking: "bg-sky-500 ring-sky-500/25",
  conversing: "bg-emerald-500 ring-emerald-500/25",
  waiting: "bg-violet-500 ring-violet-500/25",
  degraded: "bg-orange-500 ring-orange-500/25",
  idle: "bg-muted-foreground/40 ring-transparent",
};

export function isLiveStateActive(live: ActivityLiveState | null | undefined): boolean {
  return Boolean(live && (live.state === "executing" || live.state === "thinking"));
}

/**
 * Two short lines describing what an agent is doing now, from its runtime's own events:
 * headline ("Executando terminal · 42 s") and context ("Você · Telegram").
 */
export function describeLiveState(
  live: ActivityLiveState,
  t: TFunction,
  now: number = Date.now(),
): { headline: string; context: string | null } {
  const elapsed = formatElapsed(live.since, now);
  let headline: string;
  switch (live.state) {
    case "executing":
      headline = live.tool_name
        ? t("live.state.executing", { tool: live.tool_name })
        : t("live.state.executingNoTool");
      break;
    case "waiting":
      headline = t("live.state.waiting", { count: live.pending_count });
      break;
    case "degraded":
      headline = live.reason ? t("live.state.degradedReason", { reason: live.reason }) : t("live.state.degraded");
      break;
    case "idle":
      headline = elapsed ? t("live.state.idleSince", { time: elapsed }) : t("live.state.idle");
      break;
    default:
      headline = t(`live.state.${live.state}`);
  }
  if (elapsed && (live.state === "executing" || live.state === "thinking")) {
    headline = `${headline} · ${elapsed}`;
  }

  const parts: string[] = [];
  if (live.counterpart_kind === "human") {
    parts.push(
      live.counterpart_ref
        ? t("live.counterpart.human", { ref: live.counterpart_ref })
        : t("live.counterpart.humanNoRef"),
    );
  } else if (live.counterpart_kind) {
    parts.push(t(`live.counterpart.${live.counterpart_kind}`));
  }
  if (live.platform) {
    parts.push(t(`live.platform.${live.platform}`, { defaultValue: live.platform }));
  }
  // An idle agent's last conversation is history, not "who it is talking to".
  const context = live.state === "idle" || live.state === "waiting" ? null : parts.join(" · ") || null;
  return { headline, context };
}
