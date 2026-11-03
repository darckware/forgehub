import { useTranslation } from "react-i18next";
import { useMissionTimeline } from "@/hooks/useMissions";

/** Decisions and transitions (AuditEvent), mission-wide or for one task. */
export function MissionTimeline({ projectId, taskId }: { projectId: string; taskId?: string | null }) {
  const { t, i18n } = useTranslation("missions");
  const query = useMissionTimeline(projectId, taskId);
  return (
    <section className="space-y-1" data-testid="mission-timeline">
      <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("timeline.title")}</h3>
      {query.isLoading ? <div className="h-10 animate-pulse rounded bg-muted" /> : query.isError ? (
        <p className="text-xs text-amber-700">{t("timeline.error")}</p>
      ) : (query.data?.items.length ?? 0) === 0 ? (
        <p className="text-xs text-muted-foreground">{t("timeline.empty")}</p>
      ) : (
        <ol className="space-y-1 text-xs">
          {query.data!.items.map((event) => (
            <li key={event.id} className="break-words">
              <span className="text-muted-foreground">{new Date(event.at).toLocaleString(i18n.language)}</span>{" "}
              <b>{event.event_type}</b>{event.task_number ? ` #${event.task_number}` : ""} · {event.actor}
              {typeof event.payload.reason === "string" && ` — ${event.payload.reason}`}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
