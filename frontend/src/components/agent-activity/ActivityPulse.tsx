import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useTranslation } from "react-i18next";
import type { ActivityPulse as ActivityPulseData } from "@/hooks/useAgentActivity";
import { cn } from "@/lib/utils";
import { ActivitySparkline } from "./ActivitySparkline";

function formatCompact(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

/** A number that briefly slides in when it changes, so a live update is noticed. */
function LiveNumber({ value, className }: { value: string; className?: string }) {
  const reduceMotion = useReducedMotion();
  return (
    <span className={cn("relative inline-flex overflow-hidden", className)}>
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={value}
          initial={reduceMotion ? false : { y: -10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={reduceMotion ? undefined : { y: 10, opacity: 0 }}
          transition={{ duration: 0.25 }}
          className="tabular-nums"
        >
          {value}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}

function Tile({
  label,
  value,
  hint,
  tone,
  children,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "alert" | "active";
  children?: React.ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-lg border border-border bg-card px-3 py-2">
      <p className="truncate text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <LiveNumber
        value={value}
        className={cn(
          "text-lg font-semibold leading-tight",
          tone === "alert" && "text-destructive",
          tone === "active" && "text-amber-600 dark:text-amber-400",
        )}
      />
      {hint && <p className="truncate text-[10px] text-muted-foreground">{hint}</p>}
      {children}
    </div>
  );
}

/** Page-wide "what is happening now" strip, fed by the live stream's pulse. */
export function ActivityPulse({ pulse }: { pulse: ActivityPulseData | null }) {
  const { t, i18n } = useTranslation("agentActivity");
  if (!pulse) {
    return (
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" aria-hidden="true">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="h-[4.25rem] animate-pulse rounded-lg border border-border bg-muted/40" />
        ))}
      </div>
    );
  }
  const unknown = "—";
  return (
    <section aria-label={t("pulse.title")} className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6" data-testid="activity-pulse">
      <Tile
        label={t("pulse.activeAgents")}
        value={`${pulse.agents_active}/${pulse.agents_total}`}
        hint={t("pulse.inTurn", { count: pulse.agents_in_turn })}
        tone={pulse.agents_in_turn > 0 ? "active" : undefined}
      />
      <Tile label={t("pulse.turnsHour")} value={String(pulse.turns_last_hour)}>
        <ActivitySparkline
          values={pulse.turns_per_minute}
          className="mt-1 h-5"
          label={t("pulse.turnsPerMinute")}
        />
      </Tile>
      <Tile
        label={t("pulse.toolsHour")}
        value={String(pulse.tools_last_hour)}
        hint={
          pulse.llm_calls_last_hour === null
            ? undefined
            : t("pulse.llmCalls", { count: pulse.llm_calls_last_hour })
        }
      />
      <Tile
        label={t("pulse.tokensHour")}
        value={pulse.tokens_last_hour === null ? unknown : formatCompact(pulse.tokens_last_hour, i18n.language)}
        hint={pulse.tokens_last_hour === null ? t("pulse.forgerouterUnavailable") : undefined}
      />
      <Tile
        label={t("pulse.costToday")}
        value={
          pulse.cost_today === null
            ? unknown
            : new Intl.NumberFormat(i18n.language, { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(pulse.cost_today)
        }
      />
      <Tile
        label={t("pulse.attention")}
        value={String(pulse.failures_last_hour)}
        hint={t("pulse.pending", { count: pulse.pending_total })}
        tone={pulse.failures_last_hour > 0 || pulse.agents_degraded > 0 ? "alert" : undefined}
      />
    </section>
  );
}
