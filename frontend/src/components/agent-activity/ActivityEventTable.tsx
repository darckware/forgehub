import { useMemo, useState } from "react";
import { ArrowUpRight, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ActivityAgent } from "@/hooks/useAgentActivity";
import type { TimelineEvent } from "@/hooks/useAgentActivityTimeline";
import type { ActivityTraceViewModel } from "@/hooks/useActivityTraceViewModel";
import { cn } from "@/lib/utils";
import { formatDuration } from "./swimlaneLayout";

export type EventFilter = "all" | "turns" | "tools" | "messages" | "failures";
const FILTERS: EventFilter[] = ["all", "turns", "tools", "messages", "failures"];

export function isFailureEvent(event: TimelineEvent): boolean {
  return (
    event.status === "failed" ||
    event.status === "error" ||
    event.kind === "dispatch_failed" ||
    Boolean(event.error_type)
  );
}

export function matchesEventFilter(event: TimelineEvent, filter: EventFilter): boolean {
  switch (filter) {
    case "turns":
      return event.kind.startsWith("turn_") || event.kind === "workspace_turn";
    case "tools":
      return event.kind.startsWith("tool_");
    case "messages":
      return event.source === "messages";
    case "failures":
      return isFailureEvent(event);
    default:
      return true;
  }
}

/**
 * The raw records behind the lanes, newest first. Clicking a row moves the replay cursor
 * to that instant; the arrow opens its canonical record.
 */
export function ActivityEventTable({
  trace,
  agents,
  selectedAgentId,
  onOpenRecord,
}: {
  trace: ActivityTraceViewModel;
  agents: ActivityAgent[];
  selectedAgentId: string | null;
  onOpenRecord: (path: string) => void;
}) {
  const { t, i18n } = useTranslation("agentActivity");
  const [filter, setFilter] = useState<EventFilter>("all");
  const names = useMemo(() => new Map(agents.map((agent) => [agent.id, agent.name])), [agents]);
  const format = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }),
    [i18n.language],
  );
  const rows = useMemo(
    () =>
      (trace.timeline?.events ?? []).filter(
        (event) => (!selectedAgentId || event.agent_id === selectedAgentId) && matchesEventFilter(event, filter),
      ),
    [trace.timeline, selectedAgentId, filter],
  );

  const counterpart = (event: TimelineEvent) => {
    if (!event.counterpart_kind) return null;
    if (event.counterpart_kind === "human") {
      return event.counterpart_ref ? t("live.counterpart.human", { ref: event.counterpart_ref }) : t("live.counterpart.humanNoRef");
    }
    return t(`live.counterpart.${event.counterpart_kind}`, { defaultValue: event.counterpart_kind });
  };

  return (
    <section aria-label={t("trace.events.title")} className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex flex-col gap-2 border-b border-border px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-sm font-medium">
          {t("trace.events.title")}
          <span className="ml-2 text-xs font-normal text-muted-foreground">{t("trace.events.count", { count: rows.length })}</span>
        </h2>
        <div role="radiogroup" aria-label={t("trace.events.filter")} className="inline-flex flex-wrap rounded-md border border-border p-0.5">
          {FILTERS.map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={filter === option}
              onClick={() => setFilter(option)}
              className={cn(
                "min-h-7 rounded px-2 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                filter === option && "bg-muted text-foreground shadow-sm",
              )}
            >
              {t(`trace.events.filters.${option}`)}
            </button>
          ))}
        </div>
      </div>
      {trace.status === "loading" ? (
        <p className="inline-flex w-full items-center justify-center gap-2 px-3 py-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          {t("states.loading")}
        </p>
      ) : trace.status === "error" ? (
        <p role="alert" className="px-3 py-8 text-center text-sm text-destructive">{t("states.requestFailed")}</p>
      ) : rows.length === 0 ? (
        <p className="px-3 py-8 text-center text-sm text-muted-foreground">{t("trace.events.empty")}</p>
      ) : (
        <div className="max-h-[28rem] overflow-y-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="whitespace-nowrap">{t("trace.events.columns.time")}</TableHead>
                <TableHead>{t("trace.events.columns.agent")}</TableHead>
                <TableHead>{t("trace.events.columns.event")}</TableHead>
                <TableHead>{t("trace.events.columns.channel")}</TableHead>
                <TableHead>{t("trace.events.columns.detail")}</TableHead>
                <TableHead>{t("trace.events.columns.status")}</TableHead>
                <TableHead className="sr-only">{t("trace.events.columns.record")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((event) => {
                const at = Date.parse(event.occurred_at);
                const selected = trace.cursor !== null && Math.abs(trace.cursor - at) < 1_000;
                const detail = [
                  event.tool_name,
                  counterpart(event),
                  event.message_number !== null ? `#${event.message_number}` : null,
                  event.duration_ms !== null ? formatDuration(event.duration_ms) : null,
                  event.model,
                ].filter(Boolean).join(" · ");
                return (
                  <TableRow
                    key={event.key}
                    onClick={() => trace.setCursor(at)}
                    aria-selected={selected}
                    className={cn("cursor-pointer text-xs", selected && "bg-amber-500/10")}
                  >
                    <TableCell className="whitespace-nowrap font-mono">{format.format(at)}</TableCell>
                    <TableCell className="whitespace-nowrap">{(event.agent_id && names.get(event.agent_id)) ?? event.profile ?? "—"}</TableCell>
                    <TableCell className="whitespace-nowrap">{t(`trace.events.kind.${event.kind}`, { defaultValue: event.kind })}</TableCell>
                    <TableCell className="whitespace-nowrap">
                      {event.platform ? t(`live.platform.${event.platform}`, { defaultValue: event.platform }) : "—"}
                    </TableCell>
                    <TableCell className="min-w-[12rem]">{detail || "—"}</TableCell>
                    <TableCell className={cn("whitespace-nowrap", isFailureEvent(event) && "text-destructive")}>
                      {event.error_type ?? (event.status ? t(`trace.status.${event.status}`, { defaultValue: event.status }) : "—")}
                    </TableCell>
                    <TableCell className="text-right">
                      {event.canonical_path && (
                        <button
                          type="button"
                          onClick={(click) => {
                            click.stopPropagation();
                            onOpenRecord(event.canonical_path!);
                          }}
                          aria-label={t("trace.events.open")}
                          title={t("trace.events.open")}
                          className="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <ArrowUpRight className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      {trace.timeline?.truncated && (
        <p className="border-t border-border px-3 py-2 text-xs text-muted-foreground">{t("trace.events.truncated")}</p>
      )}
    </section>
  );
}
