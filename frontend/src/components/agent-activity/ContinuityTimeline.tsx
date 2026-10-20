import { GitCommitHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ActivityTimelineEvent } from "@/hooks/useAgentActivity";
import { cn } from "@/lib/utils";

interface ContinuityTimelineProps {
  events: ActivityTimelineEvent[];
  selectedAgentId: string | null;
}

type TimelineLane = ActivityTimelineEvent["lane"];

const LANE_ORDER: TimelineLane[] = ["communication", "planning", "execution", "checkpoint", "governance"];

function formatEventTime(value: string, locale: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
}

function compareEvents(left: ActivityTimelineEvent, right: ActivityTimelineEvent): number {
  const leftTime = Date.parse(left.occurred_at);
  const rightTime = Date.parse(right.occurred_at);
  if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) return left.occurred_at.localeCompare(right.occurred_at);
  return leftTime - rightTime || left.key.localeCompare(right.key);
}

export function ContinuityTimeline({ events, selectedAgentId }: ContinuityTimelineProps) {
  const { t, i18n } = useTranslation("agentActivity");

  return (
    <section
      aria-label={t("timeline.ariaLabel")}
      className="overflow-hidden rounded-lg border border-border bg-card lg:col-span-2"
    >
      <div className="flex min-h-10 items-center gap-2 border-b border-border px-3 py-2">
        <GitCommitHorizontal className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <h2 className="text-xs font-medium">{t("timeline.title")}</h2>
        <span className="font-mono text-[9px] text-muted-foreground">{t("timeline.subtitle")}</span>
      </div>

      {events.length === 0 ? (
        <p className="px-4 py-8 text-center text-xs text-muted-foreground">{t("timeline.empty")}</p>
      ) : (
        <div className="space-y-2 overflow-x-auto p-3">
          {LANE_ORDER.map((lane) => {
            const laneEvents = events.filter((event) => event.lane === lane).sort(compareEvents);
            const laneLabel = t(`timeline.lane.${lane}`);
            return (
              <section key={lane} role="group" aria-label={laneLabel} className="grid min-w-[46rem] grid-cols-[8rem_minmax(0,1fr)] rounded-md border border-border bg-background/35">
                <div className="border-r border-border px-3 py-2">
                  <h3 className="text-[11px] font-medium">{laneLabel}</h3>
                  <p className="mt-1 font-mono text-[9px] text-muted-foreground">{laneEvents.length}</p>
                </div>
                {laneEvents.length === 0 ? (
                  <p className="self-center px-3 py-3 text-[10px] text-muted-foreground">{t("timeline.laneEmpty")}</p>
                ) : (
                  <ol className="flex min-w-0 gap-2 overflow-x-auto p-2" aria-label={laneLabel}>
                    {laneEvents.map((event, index) => {
                      const selected = Boolean(selectedAgentId && event.agent_id === selectedAgentId);
                      return (
                        <li key={event.key} className="relative w-56 shrink-0 before:absolute before:-left-2.5 before:top-4 before:h-px before:w-2.5 before:bg-border first:before:hidden">
                          <a
                            href={event.canonical_path}
                            className={cn(
                              "block h-full cursor-pointer rounded-md border border-border bg-card px-3 py-2 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 active:bg-muted",
                              selected && "border-primary/60 bg-primary/5",
                            )}
                          >
                            <span className="mb-1 flex items-center justify-between gap-2">
                              <span className="font-mono text-[9px] text-muted-foreground">{formatEventTime(event.occurred_at, i18n.language)}</span>
                              <span className="font-mono text-[9px] text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
                            </span>
                            <span className="block text-[11px] font-medium">
                              {event.title}
                              {selected && <span className="sr-only"> — {t("timeline.selectedAgentEvent")}</span>}
                            </span>
                            {event.summary && <span className="mt-1 line-clamp-2 text-[10px] text-muted-foreground">{event.summary}</span>}
                            <span className="mt-1.5 block truncate font-mono text-[9px] text-muted-foreground">
                              {event.source_type} · {event.source_status}
                            </span>
                          </a>
                        </li>
                      );
                    })}
                  </ol>
                )}
              </section>
            );
          })}
        </div>
      )}
    </section>
  );
}
