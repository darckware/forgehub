import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, Radio } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ActivityTopology } from "@/components/agent-activity/ActivityTopology";
import { AgentInspector } from "@/components/agent-activity/AgentInspector";
import { ContinuityTimeline } from "@/components/agent-activity/ContinuityTimeline";
import { RequestAthosDialog } from "@/components/agent-activity/RequestAthosDialog";
import { SeverityInbox } from "@/components/agent-activity/SeverityInbox";
import {
  useAgentActivity,
  type ActivityIncident,
  type ActivityMessageEdge,
} from "@/hooks/useAgentActivity";
import { cn } from "@/lib/utils";

function openCanonicalRecord(path: string) {
  if (path.startsWith("/")) window.location.assign(path);
}

function ReservedTopologyState({ state }: { state: "loading" | "error" }) {
  const { t } = useTranslation("agentActivity");
  const failed = state === "error";
  return (
    <section
      role="region"
      aria-label={t("topology.title")}
      className="flex min-h-[22rem] flex-col overflow-hidden rounded-lg border border-border bg-card"
    >
      <div className="flex min-h-11 items-center gap-2 border-b border-border px-3 py-2">
        <Radio className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <h2 className="text-sm font-medium">{t("topology.title")}</h2>
      </div>
      <div className="flex min-h-[17rem] flex-1 items-center justify-center px-6 text-center">
        {failed ? (
          <p role="alert" className="max-w-md rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {t("states.requestFailed")}
          </p>
        ) : (
          <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
            {t("states.loading")}
          </p>
        )}
      </div>
    </section>
  );
}

export default function AgentActivityPage() {
  const { t, i18n } = useTranslation("agentActivity");
  const activity = useAgentActivity();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [monitoringIncident, setMonitoringIncident] = useState<ActivityIncident | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const data = activity.data;
  const fallbackAgentId = data?.incidents.find((incident) => incident.affected_agent_id)?.affected_agent_id
    ?? data?.agents[0]?.id
    ?? null;
  const effectiveSelectedAgentId = data?.agents.some((agent) => agent.id === selectedAgentId)
    ? selectedAgentId
    : fallbackAgentId;
  const selectedAgent = data?.agents.find((agent) => agent.id === effectiveSelectedAgentId) ?? null;
  const unavailableSources = data?.source_freshness.filter((source) => source.status === "unavailable") ?? [];
  const staleSources = data?.source_freshness.filter((source) => source.status === "stale") ?? [];
  const recordStatus = activity.isLoading
    ? "loading"
    : activity.isError && !data
      ? "unavailable"
      : unavailableSources.length > 0 || staleSources.length > 0 || activity.isError
        ? "degraded"
        : "live";
  const RecordStatusIcon = recordStatus === "live" ? Radio : recordStatus === "loading" ? Loader2 : AlertTriangle;

  useEffect(() => {
    document.title = t("documentTitle");
  }, [t, i18n.language]);

  const selectIncident = (incident: ActivityIncident) => {
    if (incident.affected_agent_id) setSelectedAgentId(incident.affected_agent_id);
  };

  const requestMonitoring = (incident: ActivityIncident) => {
    selectIncident(incident);
    setMonitoringIncident(incident);
    setDialogOpen(true);
  };

  const openMessage = (edge: ActivityMessageEdge) => openCanonicalRecord(edge.canonical_path);

  return (
    <div className="mx-auto w-full max-w-[100rem] space-y-3">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl font-semibold tracking-tight">{t("title")}</h1>
            <span
              role="status"
              className={cn(
                "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium",
                recordStatus === "live" && "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
                recordStatus === "loading" && "border-border bg-muted text-muted-foreground",
                recordStatus === "degraded" && "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
                recordStatus === "unavailable" && "border-destructive/40 bg-destructive/10 text-destructive",
              )}
            >
              <RecordStatusIcon
                className={cn("h-3 w-3", recordStatus === "loading" && "motion-safe:animate-spin")}
                aria-hidden="true"
              />
              {recordStatus === "live" ? t("liveRecords") : t(`recordStatus.${recordStatus}`)}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        {data?.generated_at && (
          <p className="font-mono text-[10px] text-muted-foreground">
            {t("updatedAt", {
              value: new Intl.DateTimeFormat(i18n.language, {
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              }).format(new Date(data.generated_at)),
            })}
          </p>
        )}
      </header>

      {(unavailableSources.length > 0 || staleSources.length > 0) && (
        <div role="status" className="space-y-2" aria-label={t("states.sourceHealth")}>
          {unavailableSources.map((source) => (
            <p key={source.name} className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {t("states.optionalUnavailable", { source: source.name })}
              {source.detail ? ` — ${source.detail}` : ""}
            </p>
          ))}
          {staleSources.map((source) => (
            <p key={source.name} className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {t("states.stale", { source: source.name })}
              {source.detail ? ` — ${source.detail}` : ""}
            </p>
          ))}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {activity.isLoading ? (
          <ReservedTopologyState state="loading" />
        ) : activity.isError ? (
          <ReservedTopologyState state="error" />
        ) : (
          <ActivityTopology
            agents={data?.agents ?? []}
            projects={data?.projects ?? []}
            resources={data?.resources ?? []}
            relations={data?.topology_relations ?? []}
            edges={data?.message_edges ?? []}
            projectScopeId={data?.project_id ?? null}
            selectedAgentId={effectiveSelectedAgentId}
            onSelectAgent={setSelectedAgentId}
            onOpenMessage={openMessage}
          />
        )}

        <aside aria-label={t("rail.title")} className="grid content-start gap-3">
          <SeverityInbox
            incidents={data?.incidents ?? []}
            onSelectIncident={selectIncident}
            onRequestMonitoring={requestMonitoring}
          />
          <AgentInspector agent={selectedAgent} onOpenRecord={openCanonicalRecord} />
        </aside>

        <ContinuityTimeline events={data?.timeline ?? []} selectedAgentId={effectiveSelectedAgentId} />
      </div>

      <RequestAthosDialog incident={monitoringIncident} open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
