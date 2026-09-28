import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, LayoutGrid, Loader2, Network, Radio, RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ActivityPulse } from "@/components/agent-activity/ActivityPulse";
import { ActivityTopology } from "@/components/agent-activity/ActivityTopology";
import { ActivityViewSwitch, readActivityView, type ActivityOperationalView } from "@/components/agent-activity/ActivityViewSwitch";
import { AgentInspector } from "@/components/agent-activity/AgentInspector";
import { ContinuityTimeline } from "@/components/agent-activity/ContinuityTimeline";
import { CurrentFlowBoard } from "@/components/agent-activity/CurrentFlowBoard";
import { LiveAgentCards } from "@/components/agent-activity/LiveAgentCards";
import { isMonitoredAgent } from "@/components/agent-activity/liveState";
import { RequestAthosDialog } from "@/components/agent-activity/RequestAthosDialog";
import { SeverityInbox } from "@/components/agent-activity/SeverityInbox";
import { Button } from "@/components/ui/button";
import { useSyncHermesAgents } from "@/hooks/useAgent";
import {
  useAgentActivity,
  type ActivityAgent,
  type ActivityIncident,
  type ActivityMessageEdge,
  type AgentLiveSnapshotItem,
} from "@/hooks/useAgentActivity";
import { useAgentActivityStreamViewModel } from "@/hooks/useAgentActivityStreamViewModel";
import { cn } from "@/lib/utils";

type MainView = "cards" | "topology";
const MAIN_VIEW_STORAGE_KEY = "forgehub:agent-activity:main:v1";

function readMainView(): MainView {
  try {
    return window.localStorage.getItem(MAIN_VIEW_STORAGE_KEY) === "topology" ? "topology" : "cards";
  } catch {
    return "cards";
  }
}

/** Re-renders once a second so elapsed times ("42 s") keep moving between frames. */
function useNow(intervalMs = 1_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

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
  const stream = useAgentActivityStreamViewModel();
  // The stream carries the fast-moving part; while it's up the full read model only
  // refreshes the slower parts (topology, flow, timeline).
  const activity = useAgentActivity({}, { refetchInterval: stream.status === "live" ? 30_000 : 5_000 });
  const now = useNow();
  const [mainView, setMainView] = useState<MainView>(readMainView);
  const syncHermes = useSyncHermesAgents();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [monitoringIncident, setMonitoringIncident] = useState<ActivityIncident | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [operationalView, setOperationalView] = useState<ActivityOperationalView>(readActivityView);

  const handleSyncAgents = async () => {
    try {
      await syncHermes.mutateAsync();
      await activity.refetch();
    } catch {
      // syncHermes.error is displayed in UI
    }
  };

  const data = activity.data;
  const snapshotByAgent = useMemo(
    () => new Map<string, AgentLiveSnapshotItem>((stream.snapshot?.agents ?? []).map((item) => [item.agent_id, item])),
    [stream.snapshot],
  );
  // Live state from the newest stream frame wins over the (slower) read model's. External
  // executors (claude/codex/agy/openclaw) only appear while Messages is running them.
  const agents = useMemo<ActivityAgent[]>(() => {
    const merged = (data?.agents ?? []).map((agent) =>
      stream.snapshot ? { ...agent, live: snapshotByAgent.get(agent.id)?.live ?? null } : agent,
    );
    return merged.filter((agent) => isMonitoredAgent(agent.runtime_type, agent.live, Boolean(agent.current_work)));
  }, [data?.agents, stream.snapshot, snapshotByAgent]);
  const agentIds = useMemo(() => new Set(agents.map((agent) => agent.id)), [agents]);
  const relations = useMemo(
    () => (data?.topology_relations ?? []).filter((relation) => relation.from_type !== "agent" || agentIds.has(relation.from_id)),
    [data?.topology_relations, agentIds],
  );
  const selectMainView = (next: MainView) => {
    try {
      window.localStorage.setItem(MAIN_VIEW_STORAGE_KEY, next);
    } catch {
      // Private mode / blocked storage: the choice just isn't remembered.
    }
    setMainView(next);
  };
  const incidentFallbackAgentId = data?.incidents.find((incident) => incident.affected_agent_id)?.affected_agent_id ?? null;
  const effectiveSelectedAgentId = selectedAgentId === ""
    ? null
    : selectedAgentId !== null && agents.some((agent) => agent.id === selectedAgentId)
    ? selectedAgentId
    : selectedAgentId === null
    ? incidentFallbackAgentId
    : null;
  const selectedAgent = agents.find((agent) => agent.id === effectiveSelectedAgentId) ?? null;
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
            <span
              role="status"
              data-testid="activity-stream-status"
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium",
                stream.status === "live" && "border-emerald-500/40 text-emerald-700 dark:text-emerald-400",
                (stream.status === "connecting" || stream.status === "idle") && "border-border text-muted-foreground",
                stream.status === "reconnecting" && "border-amber-500/40 text-amber-700 dark:text-amber-400",
                stream.status === "error" && "border-destructive/40 text-destructive",
              )}
            >
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  stream.status === "live" ? "bg-emerald-500 motion-safe:animate-pulse" : stream.status === "error" ? "bg-destructive" : "bg-amber-500",
                )}
                aria-hidden="true"
              />
              {t(`stream.${stream.status === "idle" ? "connecting" : stream.status}`)}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          {(stream.receivedAt || data?.generated_at) && (
            <p className="font-mono text-[10px] text-muted-foreground">
              {t("updatedAt", {
                value: new Intl.DateTimeFormat(i18n.language, {
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit",
                }).format(stream.receivedAt ? new Date(stream.receivedAt) : new Date(data!.generated_at)),
              })}
            </p>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleSyncAgents}
            disabled={syncHermes.isPending || activity.isLoading}
            className="h-8 gap-1.5 text-xs"
            title={t("syncAgentsTooltip")}
          >
            <RefreshCw
              className={cn(
                "h-3.5 w-3.5",
                (syncHermes.isPending || activity.isFetching) && "animate-spin"
              )}
            />
            {syncHermes.isPending ? t("syncingAgents") : t("syncAgents")}
          </Button>
        </div>
      </header>

      {syncHermes.isError && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive"
        >
          {t("syncError", {
            message: (syncHermes.error as Error)?.message || "Erro desconhecido",
          })}
        </p>
      )}

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

      <ActivityPulse pulse={stream.snapshot?.pulse ?? null} />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-2">
          <div role="tablist" aria-label={t("mainView.label")} className="inline-flex rounded-md border border-border bg-card p-0.5">
            {([
              { value: "cards" as const, icon: LayoutGrid },
              { value: "topology" as const, icon: Network },
            ]).map((option) => {
              const Icon = option.icon;
              const selected = mainView === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => selectMainView(option.value)}
                  className={cn(
                    "inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded px-3 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    selected && "bg-muted text-foreground shadow-sm",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  {t(`mainView.${option.value}`)}
                </button>
              );
            })}
          </div>
          {activity.isLoading ? (
            <ReservedTopologyState state="loading" />
          ) : activity.isError ? (
            <ReservedTopologyState state="error" />
          ) : mainView === "cards" ? (
            <LiveAgentCards
              agents={agents}
              snapshotByAgent={snapshotByAgent}
              selectedAgentId={effectiveSelectedAgentId}
              onSelectAgent={setSelectedAgentId}
              now={now}
            />
          ) : (
            <ActivityTopology
              agents={agents}
              contexts={data?.contexts ?? []}
              projects={data?.projects ?? []}
              resources={data?.resources ?? []}
              relations={relations}
              edges={data?.message_edges ?? []}
              projectScopeId={data?.project_id ?? null}
              selectedAgentId={effectiveSelectedAgentId}
              onSelectAgent={setSelectedAgentId}
              onOpenMessage={openMessage}
            />
          )}
        </div>

        <aside aria-label={t("rail.title")} className="grid content-start gap-3">
          <SeverityInbox
            incidents={data?.incidents ?? []}
            selectedAgent={selectedAgent}
            onSelectIncident={selectIncident}
            onRequestMonitoring={requestMonitoring}
            onClearFilter={() => setSelectedAgentId("")}
          />
          <AgentInspector
            agent={selectedAgent}
            agents={agents}
            onSelectAgent={(agentId) => setSelectedAgentId(agentId)}
            onClearSelection={() => setSelectedAgentId("")}
            onOpenRecord={openCanonicalRecord}
          />
        </aside>

        <div className="space-y-2 lg:col-span-2">
          <ActivityViewSwitch value={operationalView} onChange={setOperationalView} />
          <div role="tabpanel" aria-label={t(`views.${operationalView}`)}>
            {operationalView === "flow" ? (
              <CurrentFlowBoard items={data?.flow_items ?? []} />
            ) : (
              <ContinuityTimeline events={data?.timeline ?? []} selectedAgentId={effectiveSelectedAgentId} />
            )}
          </div>
        </div>
      </div>

      <RequestAthosDialog incident={monitoringIncident} open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
