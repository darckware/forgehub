import {
  AlertCircle,
  Brain,
  CheckCircle2,
  Clock,
  Database,
  Eraser,
  Loader2,
  RotateCcw,
  RefreshCw,
  Server,
  Settings2,
  Table2,
  XCircle,
} from "lucide-react";
import type { ComponentType } from "react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDatabaseTables } from "@/hooks/useDatabase";
import {
  useClearHindsightLog,
  useHindsightRestart,
  useHindsightStatus,
  type HindsightLogTarget,
} from "@/hooks/useHindsight";
import { useAuthStore } from "@/store/authStore";

function formatLogTimestamp(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "sem data";
  return new Date(epochSeconds * 1000).toLocaleString();
}

function boolLabel(value: boolean | null | undefined): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "Default";
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <Badge variant={ok ? "success" : "destructive"} className="gap-1">
      {ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {label}
    </Badge>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  ok,
}: {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: string;
  detail?: string;
  ok?: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-4">
        <div className="rounded-md border border-border bg-muted p-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
            {ok !== undefined && <StatusBadge ok={ok} label={ok ? "OK" : "Issue"} />}
          </div>
          <p className="mt-1 truncate text-lg font-semibold">{value}</p>
          {detail && <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{detail}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function getTableGroup(name: string): string {
  if (name === "alembic_version") return "migration";
  if (["async_operations", "graph_maintenance_queue", "llm_requests"].includes(name)) return "operations";
  if (["banks", "documents", "chunks", "memory_units", "memory_links", "entities", "entity_cooccurrences", "unit_entities", "invalidated_memory_units"].includes(name)) {
    return "memory";
  }
  if (["directives", "mental_models", "mental_model_history", "observation_history"].includes(name)) return "policy";
  if (["file_storage", "audit_log", "webhooks"].includes(name)) return "integration";
  if (name === "bank_stats_cache") return "cache";
  return "other";
}

function groupLabel(group: string): string {
  switch (group) {
    case "memory":
      return "Core memory";
    case "operations":
      return "Operations";
    case "policy":
      return "Policy / history";
    case "integration":
      return "Storage / integrations";
    case "cache":
      return "Cache";
    case "migration":
      return "Migration";
    default:
      return "Other";
  }
}

export default function HindsightPage() {
  const { data, isLoading, isError, error, refetch, isFetching } = useHindsightStatus();
  const restartMut = useHindsightRestart();
  const clearLogMut = useClearHindsightLog();
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false);
  const [restartConfirmOpen, setRestartConfirmOpen] = useState(false);
  const [clearLogConfirmOpen, setClearLogConfirmOpen] = useState(false);
  const { data: schemaTables, isLoading: schemaLoading } = useDatabaseTables(
    "hindsight",
    "foundation_postgres",
    "foundation"
  );

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading Hindsight status...
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        Failed to load Hindsight status: {(error as Error)?.message ?? "unknown error"}
      </div>
    );
  }

  const activeProfiles = data.profiles.filter((p) => p.uses_hindsight);
  const unconfiguredProfiles = activeProfiles.filter((p) => !p.hindsight_configured);
  const latestLogTarget: HindsightLogTarget = data.logs.runtime.lines.length > 0 ? "runtime" : "default";
  const latestLog = data.logs[latestLogTarget];
  const inventory = (schemaTables ?? []).map((table) => ({
    ...table,
    group: getTableGroup(table.name),
  }));
  const tableGroups = inventory.reduce<Record<string, number>>((acc, table) => {
    acc[table.group] = (acc[table.group] ?? 0) + 1;
    return acc;
  }, {});
  const memoryUnits = inventory.find((table) => table.name === "memory_units")?.row_count ?? 0;
  const documents = inventory.find((table) => table.name === "documents")?.row_count ?? 0;
  const entities = inventory.find((table) => table.name === "entities")?.row_count ?? 0;
  const asyncOps = inventory.find((table) => table.name === "async_operations")?.row_count ?? 0;
  const pendingOps = data.summary.daemon_active
    ? "Check async_operations status in schema inventory"
    : "Daemon offline";

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Hindsight</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Continuous memory status across Hermes agents, daemon runtime, LLM configuration, and retention policy.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isAdmin && (
            <Button
              variant="outline"
              onClick={() => setRestartConfirmOpen(true)}
              disabled={restartMut.isPending}
              className="gap-2"
            >
              {restartMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RotateCcw className="h-4 w-4" />}
              Restart Hindsight
            </Button>
          )}
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching} className="gap-2">
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh
          </Button>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Server}
          label="Daemon"
          value={data.summary.daemon_active ? "Active" : "Offline"}
          detail={data.probe.error ?? data.connection.api_url ?? "No endpoint configured"}
          ok={data.summary.daemon_active}
        />
        <MetricCard
          icon={Brain}
          label="Recording"
          value={data.summary.recording_effective ? "Recording" : "Not recording"}
          detail={`Configured: ${boolLabel(data.summary.recording_configured)}; auto_retain: ${boolLabel(data.memory.auto_retain)}`}
          ok={data.summary.recording_effective}
        />
        <MetricCard
          icon={Settings2}
          label="LLM"
          value={data.llm.model ?? "Not configured"}
          detail={`${data.llm.provider ?? "provider unknown"}${data.llm.base_url ? ` at ${data.llm.base_url}` : ""}`}
          ok={Boolean(data.llm.model && data.llm.api_key_present)}
        />
        <MetricCard
          icon={Database}
          label="Memory Bank"
          value={data.memory.bank_id}
          detail={`Mode: ${data.connection.mode}; recall: ${data.memory.recall_budget ?? "default"}`}
          ok={data.memory.bank_enabled !== false}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Table2}
          label="Tables"
          value={String(inventory.length || 21)}
          detail={`${Object.keys(tableGroups).length} active groups; foundation_postgres/hindsight`}
          ok={Boolean(inventory.length)}
        />
        <MetricCard
          icon={Brain}
          label="Memory Units"
          value={memoryUnits.toLocaleString()}
          detail={`${documents.toLocaleString()} documents; ${entities.toLocaleString()} entities`}
          ok={memoryUnits > 0}
        />
        <MetricCard
          icon={Clock}
          label="Async Ops"
          value={asyncOps.toLocaleString()}
          detail={pendingOps}
          ok={asyncOps >= 0}
        />
        <MetricCard
          icon={Database}
          label="Schema Health"
          value={schemaLoading ? "Loading..." : "Indexed"}
          detail="Read-only inventory from foundation_postgres"
          ok={!schemaLoading}
        />
      </div>

      {data.logs.latest_errors.length > 0 && (
        <Card className="border-destructive/40">
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-destructive">
              <AlertCircle className="h-4 w-4" />
              Recent Hindsight Errors
            </div>
            <div className="max-h-44 overflow-auto rounded-md bg-muted/40 p-3 font-mono text-xs">
              {data.logs.latest_errors.map((entry, index) => (
                <p key={`${entry.source}-${index}`} className="whitespace-pre-wrap break-all">
                  [{entry.source}] {entry.line}
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardContent className="space-y-4 p-4">
            <div>
              <h2 className="text-base font-semibold">Configuration</h2>
              <p className="text-xs text-muted-foreground">
                Primary profile: {data.summary.primary_profile ?? "none"}; explicit Hindsight configs: {data.summary.profile_config_count}.
              </p>
            </div>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs uppercase text-muted-foreground">API URL</p>
                <p className="break-all font-mono text-xs">{data.connection.api_url ?? "not configured"}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Config file</p>
                <p className="break-all font-mono text-xs">{data.connection.config_path ?? "inherited/default"}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Retain</p>
                <p>Every {data.memory.retain_every_n_turns} turn(s), async {boolLabel(data.memory.retain_async)}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Integration</p>
                <p>{data.memory.memory_mode}; auto recall {boolLabel(data.memory.auto_recall)}</p>
              </div>
            </div>
            {unconfiguredProfiles.length > 0 && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                {unconfiguredProfiles.length} agent(s) use Hindsight but do not have a profile-scoped
                `hindsight/config.json`; they depend on defaults or environment.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4 p-4">
            <div>
              <h2 className="text-base font-semibold">Runtime</h2>
              <p className="text-xs text-muted-foreground">Processes and local endpoint probe.</p>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">Health status</span>
                <span>{data.probe.status_code ?? data.probe.error ?? "no response"}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">Idle timeout</span>
                <span>{data.connection.idle_timeout ?? "default"}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">Processes</span>
                <span>{data.processes.length}</span>
              </div>
            </div>
            {data.processes.length > 0 && (
              <div className="max-h-32 overflow-auto rounded-md bg-muted/40 p-2 font-mono text-xs">
                {data.processes.map((proc) => (
                  <p key={proc.pid} className="truncate">
                    {proc.pid} ({formatUptime(proc.uptime_seconds)}) {proc.command}
                  </p>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-4 p-4">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-base font-semibold">Schema Inventory</h2>
              <p className="text-xs text-muted-foreground">
                foundation_postgres / hindsight contains {inventory.length} tables and {asyncOps.toLocaleString()} async operations.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(tableGroups).map(([group, count]) => (
                <Badge key={group} variant="outline" className="gap-1">
                  {groupLabel(group)}: {count}
                </Badge>
              ))}
            </div>
          </div>
          <div className="overflow-hidden rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Table</TableHead>
                  <TableHead>Rows</TableHead>
                  <TableHead>Cols</TableHead>
                  <TableHead>Group</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {inventory.map((table) => (
                  <TableRow key={table.name}>
                    <TableCell className="font-mono text-xs">{table.name}</TableCell>
                    <TableCell>{table.row_count.toLocaleString()}</TableCell>
                    <TableCell>{table.column_count}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {groupLabel(table.group)}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
                {inventory.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-sm text-muted-foreground">
                      {schemaLoading ? "Loading schema inventory..." : "No tables found in hindsight schema."}
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="border-b border-border px-4 py-3">
            <h2 className="text-base font-semibold">Agents Using Hindsight</h2>
            <p className="text-xs text-muted-foreground">{activeProfiles.length} of {data.profiles.length} profiles use `memory.provider: hindsight`.</p>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Profile Memory</TableHead>
                <TableHead>Config</TableHead>
                <TableHead>Limits</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.profiles.map((profile) => (
                <TableRow key={profile.profile}>
                  <TableCell className="font-medium">{profile.profile}</TableCell>
                  <TableCell>
                    <Badge variant={profile.uses_hindsight ? "success" : "outline"}>
                      {profile.uses_hindsight ? "Hindsight" : "Built-in only"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    memory {boolLabel(profile.memory_enabled)}; user {boolLabel(profile.user_profile_enabled)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {profile.hindsight_configured ? profile.hindsight_config_path : "inherits/default"}
                  </TableCell>
                  <TableCell className="text-xs">
                    memory {profile.memory_char_limit ?? "default"} / user {profile.user_char_limit ?? "default"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={restartConfirmOpen}
        title="Restart Hindsight daemon"
        description="This restarts the Hindsight container and briefly interrupts memory recording and reads while it comes back up."
        confirmLabel="Restart"
        cancelLabel="Cancel"
        variant="default"
        loading={restartMut.isPending}
        onCancel={() => setRestartConfirmOpen(false)}
        onConfirm={async () => {
          await restartMut.mutateAsync();
          setRestartConfirmOpen(false);
          await refetch();
        }}
      />

      <ConfirmDialog
        open={clearLogConfirmOpen}
        title="Limpar log do Hindsight"
        description={`Apaga o conteúdo de ${latestLog.path ?? "este arquivo"} -- não afeta o daemon em execução, só o histórico exibido aqui.`}
        confirmLabel="Limpar"
        cancelLabel="Cancelar"
        variant="default"
        loading={clearLogMut.isPending}
        onCancel={() => setClearLogConfirmOpen(false)}
        onConfirm={async () => {
          await clearLogMut.mutateAsync(latestLogTarget);
          setClearLogConfirmOpen(false);
          await refetch();
        }}
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <h2 className="text-base font-semibold">Latest Log</h2>
              </div>
              {isAdmin && (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5"
                  disabled={clearLogMut.isPending || latestLog.lines.length === 0}
                  onClick={() => setClearLogConfirmOpen(true)}
                >
                  {clearLogMut.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Eraser className="h-3.5 w-3.5" />
                  )}
                  Limpar log
                </Button>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="break-all text-xs text-muted-foreground">{latestLog.path ?? "No log file found"}</p>
              <p className="shrink-0 text-xs text-muted-foreground">
                Atualizado em {formatLogTimestamp(latestLog.updated_at)}
              </p>
            </div>
            <pre className="max-h-80 overflow-auto rounded-md bg-muted/40 p-3 text-xs">
              <code>{latestLog.lines.join("\n") || "No log lines."}</code>
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <h2 className="text-base font-semibold">Database Control Analysis</h2>
            <p className="text-sm text-muted-foreground">{data.analysis.storage_source}</p>
            <p className="text-sm text-muted-foreground">{data.analysis.database_control_recommendation}</p>
            <p className="text-sm text-muted-foreground">{data.analysis.current_risk}</p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
