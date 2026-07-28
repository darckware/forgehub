import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, CheckCircle2, Clock, MessagesSquare, Users } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { useAgents } from "@/hooks/useAgent";
import type { Demand } from "@/hooks/useDemands";

const IN_FLIGHT_STATUSES = new Set(["pending", "dispatched", "running"]);
const DAY_MS = 24 * 60 * 60 * 1000;
const HISTORY_DAYS = 14;

function StatTile({
  icon,
  label,
  value,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums leading-none">{value}</p>
          {hint && <p className="mt-1.5 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <span className="shrink-0 rounded-md bg-muted p-2 text-muted-foreground">{icon}</span>
      </CardContent>
    </Card>
  );
}

function BarRow({ label, value, max }: { label: string; value: number; max: number }) {
  const width = max > 0 ? Math.max((value / max) * 100, value > 0 ? 3 : 0) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="truncate font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{value}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-[#2a78d6] dark:bg-[#3987e5]" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export function DemandsStatsPanel({ demands }: { demands: Demand[] }) {
  const { t } = useTranslation("demands");
  const { data: agents } = useAgents();

  const answeredOriginIds = useMemo(() => {
    const ids = new Set<string>();
    for (const d of demands) {
      if (d.reply_to_id) ids.add(d.reply_to_id);
    }
    return ids;
  }, [demands]);
  const awaitingReplyCount = demands.filter((d) => d.requires_response && !answeredOriginIds.has(d.id)).length;

  const activeAgentIds = useMemo(() => {
    const ids = new Set<string>();
    for (const d of demands) {
      if (d.from_agent_id) ids.add(d.from_agent_id);
      if (d.target_agent_id) ids.add(d.target_agent_id);
    }
    return ids;
  }, [demands]);

  const dispatched = demands.filter((d) => d.dispatch_status === "completed" || d.dispatch_status === "failed");
  const completed = dispatched.filter((d) => d.dispatch_status === "completed").length;
  const successRate = dispatched.length > 0 ? Math.round((completed / dispatched.length) * 100) : null;

  const volumeByAgent = useMemo(() => {
    const counts = new Map<string, number>();
    for (const d of demands) {
      if (d.from_agent_id) counts.set(d.from_agent_id, (counts.get(d.from_agent_id) ?? 0) + 1);
      if (d.target_agent_id) counts.set(d.target_agent_id, (counts.get(d.target_agent_id) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([id, count]) => ({ id, count, name: agents?.find((a) => a.id === id)?.name ?? id }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
  }, [demands, agents]);
  const maxVolume = Math.max(1, ...volumeByAgent.map((v) => v.count));

  const statusTotals = useMemo(() => {
    let ok = 0;
    let inFlight = 0;
    let failed = 0;
    for (const d of demands) {
      if (d.dispatch_status === "completed") ok += 1;
      else if (d.dispatch_status === "failed") failed += 1;
      else if (d.dispatch_status && IN_FLIGHT_STATUSES.has(d.dispatch_status)) inFlight += 1;
    }
    return { ok, inFlight, failed, total: ok + inFlight + failed };
  }, [demands]);

  const dailyHistory = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const buckets: { date: Date; count: number }[] = [];
    for (let i = HISTORY_DAYS - 1; i >= 0; i--) {
      buckets.push({ date: new Date(today.getTime() - i * DAY_MS), count: 0 });
    }
    for (const d of demands) {
      const created = new Date(d.created_at);
      created.setHours(0, 0, 0, 0);
      const diffDays = Math.round((today.getTime() - created.getTime()) / DAY_MS);
      if (diffDays >= 0 && diffDays < HISTORY_DAYS) {
        buckets[HISTORY_DAYS - 1 - diffDays].count += 1;
      }
    }
    return buckets;
  }, [demands]);
  const maxDaily = Math.max(1, ...dailyHistory.map((b) => b.count));

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon={<MessagesSquare className="h-4 w-4" />}
          label={t("stats.totalMessages")}
          value={String(demands.length)}
        />
        <StatTile
          icon={<Users className="h-4 w-4" />}
          label={t("stats.activeAgents")}
          value={String(activeAgentIds.size)}
        />
        <StatTile
          icon={<Clock className="h-4 w-4" />}
          label={t("stats.awaitingReply")}
          value={String(awaitingReplyCount)}
        />
        <StatTile
          icon={successRate !== null && successRate < 80 ? <AlertCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          label={t("stats.dispatchSuccessRate")}
          value={successRate !== null ? `${successRate}%` : "—"}
          hint={successRate === null ? t("stats.noDispatchData") : undefined}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 p-4">
            <h3 className="text-sm font-semibold">{t("stats.volumeByAgent")}</h3>
            {volumeByAgent.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("overview.emptyState")}</p>
            ) : (
              <div className="space-y-2.5">
                {volumeByAgent.map((v) => (
                  <BarRow key={v.id} label={v.name} value={v.count} max={maxVolume} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <h3 className="text-sm font-semibold">{t("stats.statusBreakdown")}</h3>
            {statusTotals.total === 0 ? (
              <p className="text-xs text-muted-foreground">{t("stats.noDispatchData")}</p>
            ) : (
              <>
                <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted">
                  {statusTotals.ok > 0 && (
                    <div
                      className="h-full bg-emerald-600"
                      style={{ width: `${(statusTotals.ok / statusTotals.total) * 100}%` }}
                    />
                  )}
                  {statusTotals.inFlight > 0 && (
                    <div
                      className="h-full bg-amber-500"
                      style={{ width: `${(statusTotals.inFlight / statusTotals.total) * 100}%`, marginLeft: statusTotals.ok > 0 ? 2 : 0 }}
                    />
                  )}
                  {statusTotals.failed > 0 && (
                    <div
                      className="h-full bg-destructive"
                      style={{ width: `${(statusTotals.failed / statusTotals.total) * 100}%`, marginLeft: statusTotals.inFlight > 0 || statusTotals.ok > 0 ? 2 : 0 }}
                    />
                  )}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-600" /> {t("stats.status.completed")} ({statusTotals.ok})
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-amber-500" /> {t("stats.status.inFlight")} ({statusTotals.inFlight})
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-destructive" /> {t("stats.status.failed")} ({statusTotals.failed})
                  </span>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <h3 className="text-sm font-semibold">{t("stats.messagesOverTime")}</h3>
          <svg viewBox="0 0 560 140" className="h-32 w-full" role="img" aria-label={t("stats.messagesOverTime")}>
            {dailyHistory.map((bucket, i) => {
              const barWidth = 560 / HISTORY_DAYS - 4;
              const x = i * (560 / HISTORY_DAYS) + 2;
              const barHeight = (bucket.count / maxDaily) * 110;
              const y = 120 - barHeight;
              return (
                <g key={bucket.date.toISOString()}>
                  <rect
                    x={x}
                    y={y}
                    width={barWidth}
                    height={Math.max(barHeight, bucket.count > 0 ? 2 : 0)}
                    rx={2}
                    className="fill-[#2a78d6] dark:fill-[#3987e5]"
                  >
                    <title>
                      {bucket.date.toLocaleDateString()}: {bucket.count}
                    </title>
                  </rect>
                  {i % 2 === 0 && (
                    <text x={x + barWidth / 2} y={134} textAnchor="middle" className="fill-muted-foreground text-[9px]">
                      {bucket.date.getDate()}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>
        </CardContent>
      </Card>
    </div>
  );
}
