import { CalendarClock } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { TimelineRoutine } from "@/hooks/useAgentActivityTimeline";
import { cn } from "@/lib/utils";
import { ROUTINE_MARK, formatInRoutineZone, type RoutineGroups } from "./routineOccurrences";

const UPCOMING_SHOWN = 10;

/**
 * Below the lanes (A.2): what the window's routines did -- the missed and failed ones in
 * words -- and what is scheduled for the next 24 h, which the lanes (ending now) can't show.
 * Outside the lanes' horizontal scroll, so it reads on a phone without scrolling sideways.
 */
export function RoutineOccurrencesPanel({
  groups,
  agentName,
  onOpenRecord,
}: {
  groups: RoutineGroups;
  agentName: (id: string | null) => string | null;
  onOpenRecord: (path: string) => void;
}) {
  const { t, i18n } = useTranslation("agentActivity");
  const { attention, upcoming, counts, past } = groups;
  if (past.length === 0 && upcoming.length === 0) return null;

  const row = (item: TimelineRoutine, withDate: boolean, later = 0) => {
    const mark = ROUTINE_MARK[item.outcome];
    return (
      <li key={item.key} className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 py-1 text-xs">
        <span
          aria-hidden="true"
          className={cn("inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border text-[10px] font-bold leading-none", mark.tone)}
        >
          {mark.glyph}
        </span>
        <span className="font-medium">{t(`trace.routine.outcome.${item.outcome}`)}</span>
        {item.canonical_path ? (
          <button
            type="button"
            onClick={() => onOpenRecord(item.canonical_path!)}
            className="min-w-0 break-words text-left underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {item.title}
          </button>
        ) : (
          <span className="min-w-0 break-words">{item.title}</span>
        )}
        <span className="text-muted-foreground">{agentName(item.agent_id) ?? "?"}</span>
        <span className="font-mono text-muted-foreground">
          {formatInRoutineZone(item.occurrence_at, item.timezone, i18n.language, withDate)}
        </span>
        {item.message_number !== null && (
          <span className="text-muted-foreground">{t("trace.routine.message", { number: item.message_number })}</span>
        )}
        {later > 0 && <span className="text-muted-foreground">{t("trace.routine.later", { count: later })}</span>}
        {item.outcome === "missed" && !item.recorded ? (
          // Computed here (no run row at all): say so in the viewer's language.
          <span className="w-full break-words text-muted-foreground md:w-auto">{t("trace.routine.noRun")}</span>
        ) : (
          item.detail && <span className="w-full break-words text-muted-foreground md:w-auto">{item.detail}</span>
        )}
      </li>
    );
  };

  return (
    <section aria-label={t("trace.routine.title")} className="border-t border-border px-3 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <h3 className="text-sm font-medium">{t("trace.routine.title")}</h3>
        <p className="text-xs text-muted-foreground">
          {[
            t("trace.routine.count.done", { count: counts.done }),
            t("trace.routine.count.failed", { count: counts.failed }),
            t("trace.routine.count.missed", { count: counts.missed }),
          ].join(" · ")}
        </p>
      </div>
      <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="min-w-0">
          <h4 className="text-xs font-medium text-muted-foreground">{t("trace.routine.attention")}</h4>
          {attention.length === 0 ? (
            <p className="py-1 text-xs text-muted-foreground">{t("trace.routine.attentionEmpty")}</p>
          ) : (
            <ul aria-label={t("trace.routine.attention")} className="divide-y divide-border/50">
              {attention.map((item) => row(item, true))}
            </ul>
          )}
        </div>
        <div className="min-w-0">
          <h4 className="text-xs font-medium text-muted-foreground">{t("trace.routine.upcoming")}</h4>
          {upcoming.length === 0 ? (
            <p className="py-1 text-xs text-muted-foreground">{t("trace.routine.upcomingEmpty")}</p>
          ) : (
            <>
              <ul aria-label={t("trace.routine.upcoming")} className="divide-y divide-border/50">
                {upcoming.slice(0, UPCOMING_SHOWN).map(({ next, later }) => row(next, true, later))}
              </ul>
              {upcoming.length > UPCOMING_SHOWN && (
                <p className="py-1 text-xs text-muted-foreground">
                  {t("trace.routine.more", { count: upcoming.length - UPCOMING_SHOWN })}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
