import { AlertTriangle, ArrowUpRight, Inbox, Send } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ActivityAgent, ActivityIncident } from "@/hooks/useAgentActivity";
import { cn } from "@/lib/utils";

interface SeverityInboxProps {
  incidents: ActivityIncident[];
  selectedAgent?: ActivityAgent | null;
  onSelectIncident: (incident: ActivityIncident) => void;
  onRequestMonitoring: (incident: ActivityIncident) => void;
  onClearFilter?: () => void;
}

const SEVERITY_CLASS: Record<ActivityIncident["severity"], string> = {
  info: "border-sky-500/40 text-sky-700 dark:text-sky-400",
  warning: "border-amber-500/40 text-amber-700 dark:text-amber-400",
  error: "border-orange-500/40 text-orange-700 dark:text-orange-400",
  critical: "border-destructive/40 text-destructive",
};

const SEVERITY_RANK: Record<ActivityIncident["severity"], number> = {
  info: 0,
  warning: 1,
  error: 2,
  critical: 3,
};

export function SeverityInbox({
  incidents,
  selectedAgent,
  onSelectIncident,
  onRequestMonitoring,
}: SeverityInboxProps) {
  const { t } = useTranslation("agentActivity");
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    setShowAll(false);
  }, [selectedAgent?.id]);

  const displayedIncidents = useMemo(() => {
    if (!selectedAgent || showAll) return incidents;
    return incidents.filter((incident) => incident.affected_agent_id === selectedAgent.id);
  }, [incidents, selectedAgent, showAll]);

  const orderedIncidents = useMemo(() => {
    return [...displayedIncidents].sort((left, right) => {
      const severityDifference = SEVERITY_RANK[right.severity] - SEVERITY_RANK[left.severity];
      if (severityDifference !== 0) return severityDifference;
      const leftTime = Date.parse(left.occurred_at);
      const rightTime = Date.parse(right.occurred_at);
      if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
        return rightTime - leftTime;
      }
      return left.key.localeCompare(right.key);
    });
  }, [displayedIncidents]);

  const monitorableIncident = orderedIncidents.find(
    (incident) => incident.recommended_action === "request_athos_monitoring" && incident.execution_id,
  );

  return (
    <section aria-labelledby="severity-inbox-title" className="overflow-hidden rounded-lg border border-border bg-card">
      <div className="flex min-h-10 items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <Inbox className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <h2 id="severity-inbox-title" className="truncate text-xs font-medium">{t("severity.title")}</h2>
          {selectedAgent && !showAll && (
            <Badge variant="secondary" className="shrink-0 px-1.5 py-0 text-[9px] font-normal truncate max-w-[90px]">
              {selectedAgent.name}
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {selectedAgent && (
            <a
              href="#toggle-incidents-filter"
              onClick={(e) => {
                e.preventDefault();
                setShowAll((prev) => !prev);
              }}
              className="text-[10px] text-primary hover:underline cursor-pointer"
            >
              {showAll ? selectedAgent.name : t("severity.showAll")}
            </a>
          )}
          <Badge variant="outline" className="font-mono text-[10px]">
            {orderedIncidents.length}{selectedAgent && !showAll && incidents.length !== orderedIncidents.length ? ` / ${incidents.length}` : ""}
          </Badge>
        </div>
      </div>

      <div className="max-h-44 divide-y divide-border overflow-y-auto">
        {orderedIncidents.length === 0 ? (
          <div className="px-3 py-5 text-center text-xs text-muted-foreground">
            <p>{selectedAgent && !showAll ? t("severity.emptyForAgent") : t("severity.empty")}</p>
            {selectedAgent && !showAll && incidents.length > 0 && (
              <a
                href="#show-all-incidents"
                onClick={(e) => {
                  e.preventDefault();
                  setShowAll(true);
                }}
                className="mt-1 inline-block text-[11px] text-primary underline cursor-pointer"
              >
                {t("severity.showAll")} ({incidents.length})
              </a>
            )}
          </div>
        ) : (
          orderedIncidents.map((incident) => (
            <button
              key={incident.key}
              type="button"
              onClick={() => onSelectIncident(incident)}
              className="flex w-full cursor-pointer items-start gap-2 px-3 py-2 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring active:bg-muted"
            >
              <AlertTriangle className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", SEVERITY_CLASS[incident.severity])} aria-hidden="true" />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-[11px] font-medium">{incident.title}</span>
                  <Badge variant="outline" className={cn("shrink-0 px-1.5 py-0 text-[9px]", SEVERITY_CLASS[incident.severity])}>
                    {t(`severity.level.${incident.severity}`)}
                  </Badge>
                </span>
                <span className="mt-0.5 block truncate font-mono text-[9px] text-muted-foreground">
                  {incident.error_code ?? incident.blocker_code ?? incident.kind}
                </span>
              </span>
              <ArrowUpRight className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" aria-hidden="true" />
            </button>
          ))
        )}
      </div>

      <div className="border-t border-border p-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full cursor-pointer gap-1.5 text-[11px]"
          disabled={!monitorableIncident}
          onClick={() => monitorableIncident && onRequestMonitoring(monitorableIncident)}
        >
          <Send className="h-3.5 w-3.5" aria-hidden="true" />
          {t("severity.requestMonitoring")}
        </Button>
      </div>
    </section>
  );
}
