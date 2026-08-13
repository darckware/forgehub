import { useMemo } from "react";
import { AlertCircle, CheckCircle2, Clock, DollarSign, Timer, Users, Zap } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { AgentTelemetryRow } from "@/hooks/useFactory";

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

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return remaining > 0 ? `${minutes}m ${remaining}s` : `${minutes}m`;
}

function formatCost(cost: number): string {
  return cost.toLocaleString("pt-BR", { style: "currency", currency: "USD" });
}

function AgentSparkline({ history }: { history: AgentTelemetryRow["history"] }) {
  const buckets = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const byDate = new Map(history.map((h) => [h.date, h.count]));
    const out: { date: string; count: number }[] = [];
    for (let i = HISTORY_DAYS - 1; i >= 0; i--) {
      const d = new Date(today.getTime() - i * 24 * 60 * 60 * 1000);
      const key = d.toISOString().slice(0, 10);
      out.push({ date: key, count: byDate.get(key) ?? 0 });
    }
    return out;
  }, [history]);
  const max = Math.max(1, ...buckets.map((b) => b.count));

  return (
    <svg viewBox="0 0 280 40" className="h-8 w-full" role="img" aria-label="Execuções nos últimos 14 dias">
      {buckets.map((bucket, i) => {
        const barWidth = 280 / HISTORY_DAYS - 2;
        const x = i * (280 / HISTORY_DAYS) + 1;
        const barHeight = (bucket.count / max) * 32;
        const y = 36 - barHeight;
        return (
          <rect
            key={bucket.date}
            x={x}
            y={y}
            width={barWidth}
            height={Math.max(barHeight, bucket.count > 0 ? 2 : 0)}
            rx={1}
            className="fill-[#2a78d6] dark:fill-[#3987e5]"
          >
            <title>{bucket.date}: {bucket.count}</title>
          </rect>
        );
      })}
    </svg>
  );
}

function AgentStatusBar({ agent }: { agent: AgentTelemetryRow }) {
  const total = agent.executions_total;
  if (total === 0) return <p className="text-xs text-muted-foreground">Sem execuções registradas.</p>;
  return (
    <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted">
      {agent.executions_successful > 0 && (
        <div className="h-full bg-emerald-600" style={{ width: `${(agent.executions_successful / total) * 100}%` }} />
      )}
      {agent.executions_other > 0 && (
        <div
          className="h-full bg-amber-500"
          style={{ width: `${(agent.executions_other / total) * 100}%`, marginLeft: agent.executions_successful > 0 ? 2 : 0 }}
        />
      )}
      {agent.executions_failed > 0 && (
        <div
          className="h-full bg-destructive"
          style={{
            width: `${(agent.executions_failed / total) * 100}%`,
            marginLeft: agent.executions_other > 0 || agent.executions_successful > 0 ? 2 : 0,
          }}
        />
      )}
    </div>
  );
}

export function AgentTelemetryPanel({ agents }: { agents: AgentTelemetryRow[] }) {
  const totals = useMemo(() => {
    const executions = agents.reduce((sum, a) => sum + a.executions_total, 0);
    const successful = agents.reduce((sum, a) => sum + a.executions_successful, 0);
    const failed = agents.reduce((sum, a) => sum + a.executions_failed, 0);
    const cost = agents.reduce((sum, a) => sum + a.total_cost, 0);
    const denominator = successful + failed;
    return {
      executions,
      cost,
      successRate: denominator > 0 ? successful / denominator : null,
    };
  }, [agents]);

  const volumeByAgent = useMemo(
    () => [...agents].sort((a, b) => b.executions_total - a.executions_total).slice(0, 8),
    [agents]
  );
  const maxVolume = Math.max(1, ...volumeByAgent.map((a) => a.executions_total));

  if (agents.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          Nenhuma execução de agente registrada ainda.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile icon={<Users className="h-4 w-4" />} label="Agentes ativos" value={String(agents.length)} />
        <StatTile icon={<Zap className="h-4 w-4" />} label="Execuções totais" value={String(totals.executions)} />
        <StatTile
          icon={totals.successRate !== null && totals.successRate < 0.8 ? <AlertCircle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
          label="Taxa de sucesso"
          value={totals.successRate !== null ? `${Math.round(totals.successRate * 100)}%` : "—"}
          hint={totals.successRate === null ? "Sem execuções terminais" : undefined}
        />
        <StatTile icon={<DollarSign className="h-4 w-4" />} label="Custo total" value={formatCost(totals.cost)} />
      </div>

      <Card>
        <CardContent className="space-y-3 p-4">
          <h3 className="text-sm font-semibold">Volume por agente</h3>
          <div className="space-y-2.5">
            {volumeByAgent.map((a) => (
              <BarRow key={a.agent_id} label={a.agent_name} value={a.executions_total} max={maxVolume} />
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {agents.map((agent) => (
          <Card key={agent.agent_id}>
            <CardContent className="space-y-3 p-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold">{agent.agent_name}</h3>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {agent.success_rate !== null ? `${Math.round((agent.success_rate ?? 0) * 100)}% sucesso` : "sem histórico"}
                </span>
              </div>
              <AgentStatusBar agent={agent} />
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{agent.executions_total} execuções</span>
                <span className="flex items-center gap-1"><Timer className="h-3 w-3" />{formatDuration(agent.avg_duration_seconds)} médio</span>
                <span className="flex items-center gap-1"><DollarSign className="h-3 w-3" />{formatCost(agent.total_cost)}</span>
                {agent.dispatch_total > 0 && (
                  <span>
                    Despachos: {agent.dispatch_completed}/{agent.dispatch_total}
                    {agent.dispatch_success_rate !== null && ` (${Math.round((agent.dispatch_success_rate ?? 0) * 100)}%)`}
                  </span>
                )}
              </div>
              <AgentSparkline history={agent.history} />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
