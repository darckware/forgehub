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
  ExternalLink,
  Settings2,
  Table2,
  XCircle,
} from "lucide-react";
import type { ComponentType } from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
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
  if (!epochSeconds) return "no date";
  return new Date(epochSeconds * 1000).toLocaleString();
}

function boolLabel(
  value: boolean | null | undefined,
  t: (key: string) => string
): string {
  if (value === true) return t("common.yes");
  if (value === false) return t("common.no");
  return t("common.default");
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
  const { t } = useTranslation("hindsight");
  return (
    <Card>
      <CardContent className="flex items-start gap-3 p-4">
        <div className="rounded-md border border-border bg-muted p-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase text-muted-foreground">{label}</p>
            {ok !== undefined && (
              <StatusBadge ok={ok} label={ok ? t("common.ok") : t("common.issue")} />
            )}
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

function groupLabel(group: string, t: (key: string) => string): string {
  switch (group) {
    case "memory":
      return t("groups.coreMemory");
    case "operations":
      return t("groups.operations");
    case "policy":
      return t("groups.policyHistory");
    case "integration":
      return t("groups.storageIntegrations");
    case "cache":
      return t("groups.cache");
    case "migration":
      return t("groups.migration");
    default:
      return t("groups.other");
  }
}

/** O console do Hindsight (control plane), servido pelo próprio daemon numa
 * porta separada da API (8888 é a API; 9999 é o console). Derivado do host
 * que serve o ForgeHub em vez de "localhost" fixo: o iframe é carregado pelo
 * navegador do usuário, então um localhost fixo quebraria todo acesso que não
 * seja da própria máquina (LAN, túnel) -- o mesmo motivo pelo qual o chat usa
 * `window.location.origin`. */
const CONTROL_PLANE_URL =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:9999/banks/hermes?view=data&subTab=world`
    : "";

export default function HindsightPage() {
  const { t } = useTranslation("hindsight");
  const { data, isLoading, isError, error, refetch, isFetching } = useHindsightStatus();
  const restartMut = useHindsightRestart();
  const clearLogMut = useClearHindsightLog();
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false);
  const [restartConfirmOpen, setRestartConfirmOpen] = useState(false);
  // Aba ativa. Começa em "status" para a tela abrir como sempre abriu -- o
  // control plane é uma consulta ocasional, não a visão padrão.
  const [tab, setTab] = useState("status");
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
        {t("loading")}
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        {t("loadError", { message: (error as Error)?.message ?? t("unknownError") })}
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
    ? t("metrics.asyncOps.checkStatus")
    : t("metrics.asyncOps.daemonOffline");

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("description")}
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
              {t("actions.restart")}
            </Button>
          )}
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching} className="gap-2">
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            {t("actions.refresh")}
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="status">{t("tabs.status")}</TabsTrigger>
          <TabsTrigger value="controlPlane">{t("tabs.controlPlane")}</TabsTrigger>
        </TabsList>

        <TabsContent value="controlPlane" className="mt-4">
          <Card>
            <CardContent className="p-0">
              <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
                <p className="text-xs text-muted-foreground">{t("controlPlane.hint")}</p>
                <a
                  href={CONTROL_PLANE_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {t("controlPlane.openInTab")}
                </a>
              </div>
              {/* Só monta o iframe quando a aba está aberta: o control plane
                  é uma aplicação inteira, e carregá-la em segundo plano
                  custaria a cada visita à tela de status. */}
              <iframe
                src={CONTROL_PLANE_URL}
                title={t("tabs.controlPlane")}
                className="h-[calc(100vh-16rem)] w-full border-0"
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="status" className="mt-4 space-y-6">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Server}
          label={t("metrics.daemon.label")}
          value={data.summary.daemon_active ? t("metrics.daemon.active") : t("metrics.daemon.offline")}
          detail={data.probe.error ?? data.connection.api_url ?? t("metrics.daemon.noEndpoint")}
          ok={data.summary.daemon_active}
        />
        <MetricCard
          icon={Brain}
          label={t("metrics.recording.label")}
          value={data.summary.recording_effective ? t("metrics.recording.value") : t("metrics.recording.notRecording")}
          detail={`${t("metrics.recording.configured")}: ${boolLabel(data.summary.recording_configured, t)}; ${t("metrics.recording.autoRetain")}: ${boolLabel(data.memory.auto_retain, t)}`}
          ok={data.summary.recording_effective}
        />
        <MetricCard
          icon={Settings2}
          label={t("metrics.llm.label")}
          value={data.llm.model ?? t("metrics.llm.notConfigured")}
          detail={`${data.llm.provider ?? t("metrics.llm.providerUnknown")}${data.llm.base_url ? ` ${t("metrics.llm.at", { url: data.llm.base_url })}` : ""}`}
          ok={Boolean(data.llm.model && data.llm.api_key_present)}
        />
        <MetricCard
          icon={Database}
          label={t("metrics.memoryBank.label")}
          value={data.memory.bank_id}
          detail={t("metrics.memoryBank.detail", { mode: data.connection.mode, recall: data.memory.recall_budget ?? t("runtime.default") })}
          ok={data.memory.bank_enabled !== false}
        />
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Table2}
          label={t("metrics.tables.label")}
          value={String(inventory.length || 21)}
          detail={t("metrics.tables.detail", { count: Object.keys(tableGroups).length })}
          ok={Boolean(inventory.length)}
        />
        <MetricCard
          icon={Brain}
          label={t("metrics.memoryUnits.label")}
          value={memoryUnits.toLocaleString()}
          detail={t("metrics.memoryUnits.detail", { documents: documents.toLocaleString(), entities: entities.toLocaleString() })}
          ok={memoryUnits > 0}
        />
        <MetricCard
          icon={Clock}
          label={t("metrics.asyncOps.label")}
          value={asyncOps.toLocaleString()}
          detail={pendingOps}
          ok={asyncOps >= 0}
        />
        <MetricCard
          icon={Database}
          label={t("metrics.schemaHealth.label")}
          value={schemaLoading ? t("metrics.schemaHealth.loading") : t("metrics.schemaHealth.indexed")}
          detail={t("metrics.schemaHealth.detail")}
          ok={!schemaLoading}
        />
      </div>

      {data.logs.latest_errors.length > 0 && (
        <Card className="border-destructive/40">
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-destructive">
              <AlertCircle className="h-4 w-4" />
              {t("recentErrors")}
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
              <h2 className="text-base font-semibold">{t("configuration.title")}</h2>
              <p className="text-xs text-muted-foreground">
                {t("configuration.primaryProfile", {
                  profile: data.summary.primary_profile ?? t("configuration.none"),
                  count: data.summary.profile_config_count,
                })}
              </p>
            </div>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="text-xs uppercase text-muted-foreground">{t("configuration.apiUrl")}</p>
                <p className="break-all font-mono text-xs">{data.connection.api_url ?? t("configuration.notConfigured")}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">{t("configuration.configFile")}</p>
                <p className="break-all font-mono text-xs">{data.connection.config_path ?? t("configuration.inheritsDefault")}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">{t("configuration.retain")}</p>
                <p>{t("configuration.retainDetail", { turns: data.memory.retain_every_n_turns, async: boolLabel(data.memory.retain_async, t) })}</p>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">{t("configuration.integration")}</p>
                <p>{t("configuration.integrationDetail", { mode: data.memory.memory_mode, autoRecall: boolLabel(data.memory.auto_recall, t) })}</p>
              </div>
            </div>
            {unconfiguredProfiles.length > 0 && (
              <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                {t("configuration.unconfiguredWarning", { count: unconfiguredProfiles.length })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-4 p-4">
            <div>
              <h2 className="text-base font-semibold">{t("runtime.title")}</h2>
              <p className="text-xs text-muted-foreground">{t("runtime.description")}</p>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">{t("runtime.healthStatus")}</span>
                <span>{data.probe.status_code ?? data.probe.error ?? t("runtime.noResponse")}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">{t("runtime.idleTimeout")}</span>
                <span>{data.connection.idle_timeout ?? t("runtime.default")}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted-foreground">{t("runtime.processes")}</span>
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
              <h2 className="text-base font-semibold">{t("schemaInventory.title")}</h2>
              <p className="text-xs text-muted-foreground">
                {t("schemaInventory.detail", { tables: inventory.length, asyncOps: asyncOps.toLocaleString() })}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(tableGroups).map(([group, count]) => (
                <Badge key={group} variant="outline" className="gap-1">
                  {groupLabel(group, t)}: {count}
                </Badge>
              ))}
            </div>
          </div>
          <div className="max-h-80 overflow-y-auto rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("schemaInventory.table")}</TableHead>
                  <TableHead>{t("schemaInventory.rows")}</TableHead>
                  <TableHead>{t("schemaInventory.cols")}</TableHead>
                  <TableHead>{t("schemaInventory.group")}</TableHead>
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
                        {groupLabel(table.group, t)}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
                {inventory.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-sm text-muted-foreground">
                      {schemaLoading ? t("schemaInventory.loading") : t("schemaInventory.empty")}
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
            <h2 className="text-base font-semibold">{t("agents.title")}</h2>
            <p className="text-xs text-muted-foreground">
              {t("agents.detail", { active: activeProfiles.length, total: data.profiles.length })}
            </p>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("agents.agent")}</TableHead>
                <TableHead>{t("agents.status")}</TableHead>
                <TableHead>{t("agents.profileMemory")}</TableHead>
                <TableHead>{t("agents.config")}</TableHead>
                <TableHead>{t("agents.limits")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.profiles.map((profile) => (
                <TableRow key={profile.profile}>
                  <TableCell className="font-medium">{profile.profile}</TableCell>
                  <TableCell>
                    <Badge variant={profile.uses_hindsight ? "success" : "outline"}>
                      {profile.uses_hindsight ? t("agents.hindsight") : t("agents.builtInOnly")}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">
                    {t("agents.memoryDetail", {
                      memory: boolLabel(profile.memory_enabled, t),
                      user: boolLabel(profile.user_profile_enabled, t),
                    })}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {profile.hindsight_configured ? profile.hindsight_config_path : t("configuration.inheritsDefault")}
                  </TableCell>
                  <TableCell className="text-xs">
                    {t("agents.limitsDetail", {
                      memoryLimit: profile.memory_char_limit ?? t("runtime.default"),
                      userLimit: profile.user_char_limit ?? t("runtime.default"),
                    })}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={restartConfirmOpen}
        title={t("restartDialog.title")}
        description={t("restartDialog.description")}
        confirmLabel={t("restartDialog.confirm")}
        cancelLabel={t("restartDialog.cancel")}
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
        title={t("clearLogDialog.title")}
        description={t("clearLogDialog.description", { path: latestLog.path ?? t("latestLog.noFile") })}
        confirmLabel={t("clearLogDialog.confirm")}
        cancelLabel={t("clearLogDialog.cancel")}
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
                <h2 className="text-base font-semibold">{t("latestLog.title")}</h2>
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
                  {t("latestLog.clear")}
                </Button>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="break-all text-xs text-muted-foreground">{latestLog.path ?? t("latestLog.noFile")}</p>
              <p className="shrink-0 text-xs text-muted-foreground">
                {t("latestLog.updatedAt", { time: formatLogTimestamp(latestLog.updated_at) })}
              </p>
            </div>
            <pre className="max-h-80 overflow-auto rounded-md bg-muted/40 p-3 text-xs">
              <code>{latestLog.lines.join("\n") || t("latestLog.noLines")}</code>
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-4">
            <h2 className="text-base font-semibold">{t("databaseControlAnalysis")}</h2>
            <p className="text-sm text-muted-foreground">{data.analysis.storage_source}</p>
            <p className="text-sm text-muted-foreground">{data.analysis.database_control_recommendation}</p>
            <p className="text-sm text-muted-foreground">{data.analysis.current_risk}</p>
          </CardContent>
        </Card>
      </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
