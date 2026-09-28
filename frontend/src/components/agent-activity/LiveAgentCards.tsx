import { motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import { AgentAvatar } from "@/components/AgentAvatar";
import type { ActivityAgent, AgentLiveSnapshotItem } from "@/hooks/useAgentActivity";
import { cn } from "@/lib/utils";
import { ActivitySparkline } from "./ActivitySparkline";
import { LIVE_STATE_TONE, describeLiveState, isLiveStateActive } from "./liveState";

/** Most active first; agents with no signal last. */
const STATE_RANK: Record<string, number> = {
  executing: 0,
  thinking: 1,
  conversing: 2,
  degraded: 3,
  waiting: 4,
  idle: 5,
};

const AVATAR_RING: Record<string, string> = {
  executing: "ring-2 ring-amber-500 ring-offset-2 ring-offset-card",
  thinking: "ring-2 ring-sky-500 ring-offset-2 ring-offset-card",
  conversing: "ring-2 ring-emerald-500 ring-offset-2 ring-offset-card",
  degraded: "ring-2 ring-orange-500 ring-offset-2 ring-offset-card",
  waiting: "ring-2 ring-violet-500/70 ring-offset-2 ring-offset-card",
  idle: "",
};

export function sortAgentsByActivity(agents: ActivityAgent[]): ActivityAgent[] {
  return [...agents].sort((a, b) => {
    const rankA = a.live ? STATE_RANK[a.live.state] : 9;
    const rankB = b.live ? STATE_RANK[b.live.state] : 9;
    if (rankA !== rankB) return rankA - rankB;
    const lastA = a.live?.last_event_at ? Date.parse(a.live.last_event_at) : 0;
    const lastB = b.live?.last_event_at ? Date.parse(b.live.last_event_at) : 0;
    if (lastA !== lastB) return lastB - lastA;
    return a.name.localeCompare(b.name);
  });
}

/**
 * One live card per monitored agent: what it is doing, with whom, and its last hour.
 * Cards re-sort as agents become active (framer `layout`), so the busiest are on top.
 */
export function LiveAgentCards({
  agents,
  snapshotByAgent,
  selectedAgentId,
  onSelectAgent,
  now,
}: {
  agents: ActivityAgent[];
  snapshotByAgent: Map<string, AgentLiveSnapshotItem>;
  selectedAgentId: string | null;
  onSelectAgent: (agentId: string) => void;
  now: number;
}) {
  const { t, i18n } = useTranslation("agentActivity");
  const reduceMotion = useReducedMotion();
  const sorted = sortAgentsByActivity(agents);

  if (sorted.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
        {t("cards.empty")}
      </p>
    );
  }

  return (
    <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 2xl:grid-cols-3" aria-label={t("cards.title")} data-testid="live-agent-cards">
      {sorted.map((agent) => {
        const live = agent.live ?? null;
        const snapshot = snapshotByAgent.get(agent.id);
        const text = live ? describeLiveState(live, t, now) : null;
        const active = isLiveStateActive(live);
        const selected = agent.id === selectedAgentId;
        return (
          <motion.li key={agent.id} layout={!reduceMotion} transition={{ duration: 0.3 }}>
            <button
              type="button"
              onClick={() => onSelectAgent(agent.id)}
              aria-pressed={selected}
              className={cn(
                "group relative flex h-full w-full cursor-pointer flex-col gap-2 overflow-hidden rounded-lg border border-border bg-card p-3 text-left transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                selected && "border-primary/60 bg-primary/5",
                !live && "opacity-70",
              )}
            >
              {active && !reduceMotion && (
                <span
                  className="pointer-events-none absolute inset-x-0 top-0 h-0.5 overflow-hidden"
                  aria-hidden="true"
                >
                  <span className="block h-full w-1/3 animate-[activity-sweep_1.6s_ease-in-out_infinite] bg-gradient-to-r from-transparent via-amber-500 to-transparent" />
                </span>
              )}
              <div className="flex items-center gap-3">
                <AgentAvatar
                  name={agent.name}
                  avatarDataUrl={agent.avatar_data_url}
                  imageAlt={`${agent.name} profile`}
                  size="sm"
                  className={cn(live && AVATAR_RING[live.state], active && "motion-safe:animate-pulse")}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-semibold">{agent.name}</span>
                    <span className="shrink-0 rounded border border-border px-1 font-mono text-[9px] uppercase text-muted-foreground">
                      {agent.runtime_type}
                    </span>
                  </div>
                  <p className="flex items-center gap-1.5 text-xs">
                    <span
                      className={cn(
                        "h-1.5 w-1.5 shrink-0 rounded-full ring-2",
                        live ? LIVE_STATE_TONE[live.state] : "bg-muted-foreground/30 ring-transparent",
                      )}
                      aria-hidden="true"
                    />
                    <span className="truncate font-medium">{text?.headline ?? t("live.noSignal")}</span>
                  </p>
                  <p className="truncate text-[11px] text-muted-foreground">{text?.context ?? " "}</p>
                </div>
              </div>
              <ActivitySparkline
                values={snapshot?.spark ?? []}
                barClassName={active ? "fill-amber-500/80" : "fill-primary/60"}
                label={t("cards.sparkLabel")}
              />
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[10px] text-muted-foreground">
                <span>{t("cards.turns", { count: live?.turns_last_hour ?? 0 })}</span>
                <span>{t("cards.tools", { count: live?.tools_last_hour ?? 0 })}</span>
                {snapshot && snapshot.tokens_last_hour > 0 && (
                  <span>
                    {t("cards.tokens", {
                      value: new Intl.NumberFormat(i18n.language, { notation: "compact" }).format(snapshot.tokens_last_hour),
                    })}
                  </span>
                )}
                {live && live.pending_count > 0 && (
                  <span className="text-violet-600 dark:text-violet-400">
                    {t("cards.pending", { count: live.pending_count })}
                  </span>
                )}
                {live && live.failures_last_hour > 0 && (
                  <span className="text-destructive">{t("cards.failures", { count: live.failures_last_hour })}</span>
                )}
              </div>
            </button>
          </motion.li>
        );
      })}
    </ul>
  );
}
