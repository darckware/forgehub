import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Activity,
  CheckCircle2,
  Loader2,
  RefreshCw,
  RotateCw,
  ShieldCheck,
  TriangleAlert,
  Waypoints,
  Wrench,
  XCircle,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useRemoteAccessViewModel } from "@/hooks/useRemoteAccessViewModel";
import type { VpnNode, VpnOperation } from "@/hooks/useVpn";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import { ExecutionsCard } from "./ExecutionsCard";
import { PrepareDialog } from "./PrepareDialog";
import { RotationDialog } from "./RotationDialog";
import { TailnetPolicyCard } from "./TailnetPolicyCard";
import { MachinesCard } from "./MachinesCard";
import { ExecutionComposer } from "./ExecutionComposer";
import { SchedulesPanel } from "./SchedulesPanel";
import { ScriptLibrary } from "./ScriptLibrary";

type T = (key: string, options?: Record<string, unknown>) => string;

function dateTime(value: string | null, locale: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(date);
}

function stateBadge(node: VpnNode, t: T) {
  const variant = node.state === "online" ? "success" : node.state === "offline" ? "outline" : "destructive";
  return <Badge variant={variant}>{t(`state.${node.state}`)}</Badge>;
}

function operationBadge(operation: VpnOperation, t: T) {
  const variant = operation.status === "succeeded" ? "success" : operation.status === "running" ? "warning" : "destructive";
  return <Badge variant={variant}>{t(`operationStatus.${operation.status}`)}</Badge>;
}

function NetworkTab() {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useRemoteAccessViewModel();
  const locale = i18n.language;

  if (vm.status === "loading") {
    return (
      <div className="flex min-h-64 items-center justify-center rounded-lg border border-border" role="status">
        <Loader2 className="mr-2 h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
        <span className="text-sm text-muted-foreground">{t("loading")}</span>
      </div>
    );
  }

  if (vm.status === "error" || !vm.data) {
    return (
      <div className="space-y-4 rounded-lg border border-destructive/40 bg-destructive/10 p-5" role="alert">
        <div className="flex items-start gap-3">
          <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
          <div>
            <h1 className="font-semibold">{t("unavailable.title")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t("unavailable.description")}</p>
          </div>
        </div>
        <Button variant="outline" onClick={vm.refresh} className="cursor-pointer gap-2">
          <RefreshCw className="h-4 w-4" aria-hidden="true" /> {t("refresh")}
        </Button>
      </div>
    );
  }

  const server = vm.data.server;
  const serverName = server.name ?? server.hostname ?? t("server.title");

  return (
    <div className="space-y-6 max-md:break-words">
      <div className="flex justify-end">
        <Button variant="outline" onClick={vm.refresh} disabled={vm.refreshing} aria-busy={vm.refreshing} className="cursor-pointer gap-2">
          {vm.refreshing ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
          {t("refresh")}
        </Button>
      </div>

      <p className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-muted-foreground" role="note">
        {t("privateOnly")}
      </p>

      {vm.degraded && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm" role="status">
          <p className="font-medium text-amber-700 dark:text-amber-300">{t("degraded.title")}</p>
          <p className="mt-1 text-muted-foreground">{t("degraded.description")}</p>
        </div>
      )}

      {vm.lastResult && (
        <p
          role="status"
          className={cn(
            "flex items-start gap-2 rounded-md border px-4 py-3 text-sm",
            vm.lastResult.success ? "border-emerald-500/30 bg-emerald-500/10" : "border-amber-500/40 bg-amber-500/10",
          )}
        >
          {vm.lastResult.success ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" aria-hidden="true" /> : <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />}
          {t(vm.lastResult.success ? "result.success" : "result.failure", { summary: vm.lastResult.summary })}
        </p>
      )}
      {vm.actionError && !vm.confirmingRestart && (
        <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">{vm.actionError}</p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("server.title")}</p>
                <CardTitle className="mt-1 truncate text-base">{serverName}</CardTitle>
                <p className="mt-1 font-mono text-xs text-muted-foreground">{server.tailscale_ipv4 ?? "—"}</p>
              </div>
              {stateBadge(server, t)}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">{t("server.daemon")}</dt>
              <dd className="text-right">{t(`daemon.${server.daemon_state ?? "unavailable"}`, { defaultValue: server.daemon_state ?? "—" })}</dd>
              {server.posture && (
                <>
                  <dt className="text-muted-foreground">{t("server.dns")}</dt>
                  <dd className="text-right">{t(server.posture.accept_dns ? "common.enabled" : "common.disabled")}</dd>
                  <dt className="text-muted-foreground">{t("server.routes")}</dt>
                  <dd className="text-right">{t(server.posture.accept_routes ? "common.enabled" : "common.disabled")}</dd>
                  <dt className="text-muted-foreground">{t("server.ssh")}</dt>
                  <dd className="text-right">{t(server.posture.tailscale_ssh ? "common.enabled" : "common.disabled")}</dd>
                  <dt className="text-muted-foreground">{t("server.exitNode")}</dt>
                  <dd className="text-right">{t(server.posture.exit_node || server.posture.advertise_exit_node ? "common.enabled" : "common.disabled")}</dd>
                </>
              )}
            </dl>
            <div className="border-t border-border pt-4">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={vm.askRestart}
                disabled={vm.restarting}
                className="cursor-pointer gap-1.5"
              >
                {vm.restarting ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />}
                {t("server.restart")}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-3 gap-3 self-start">
          <StatTile label={t("totals.devices")} value={vm.totals.devices} />
          <StatTile label={t("totals.online")} value={vm.totals.online} tone="good" />
          <StatTile label={t("totals.offline")} value={vm.totals.offline} tone={vm.totals.offline > 0 ? "muted" : undefined} />
        </div>
      </div>


      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Waypoints className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> {t("routes.title")}
          </CardTitle>
          <p className="text-xs text-muted-foreground">{t("routes.description")}</p>
        </CardHeader>
        <CardContent className="space-y-3">
          {vm.acceptRoutes === false && vm.routers.length > 0 && (
            <p role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">{t("routes.notAccepted")}</p>
          )}
          {vm.routers.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">{t("routes.empty")}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("routes.router")}</TableHead>
                  <TableHead>{t("devices.status")}</TableHead>
                  <TableHead>{t("routes.routes")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {vm.routers.map((router) => (
                  <TableRow key={router.id}>
                    <TableCell>
                      <p className="font-medium">{router.name ?? router.hostname ?? router.id}</p>
                      <p className="font-mono text-xs text-muted-foreground">{router.tailscale_ipv4 ?? "—"}</p>
                    </TableCell>
                    <TableCell>{stateBadge(router, t)}</TableCell>
                    <TableCell className="font-mono text-xs">{(router.subnet_routes ?? []).join(", ")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <p className="text-xs text-muted-foreground">{t("routes.approvedOnly")}</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> {t("history.title")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {vm.operationsLoading ? (
            <p className="py-6 text-center text-sm text-muted-foreground" role="status">{t("history.loading")}</p>
          ) : vm.operations.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">{t("history.empty")}</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("history.time")}</TableHead>
                  <TableHead>{t("history.actor")}</TableHead>
                  <TableHead>{t("history.target")}</TableHead>
                  <TableHead>{t("history.action")}</TableHead>
                  <TableHead>{t("history.result")}</TableHead>
                  <TableHead>{t("history.summary")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {vm.operations.map((operation) => (
                  <TableRow key={operation.id}>
                    <TableCell className="whitespace-nowrap text-xs">{dateTime(operation.started_at, locale)}</TableCell>
                    <TableCell>{operation.actor_username ?? "—"}</TableCell>
                    <TableCell>{operation.target_name ?? t(`target.${operation.target}`, { defaultValue: operation.target })}</TableCell>
                    <TableCell>{t(`action.${operation.action}`, { defaultValue: operation.action })}</TableCell>
                    <TableCell>{operationBadge(operation, t)}</TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground" title={operation.summary ?? undefined}>{operation.summary ?? operation.result_code ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <TailnetPolicyCard />

      <ConfirmDialog
        open={vm.confirmingRestart}
        title={t("confirmRestart.title")}
        description={t("confirmRestart.description", { hostname: serverName })}
        confirmLabel={t("confirmRestart.confirm")}
        cancelLabel={t("cancel")}
        icon="wrench"
        loading={vm.restarting}
        dismissDisabled={vm.restarting}
        error={vm.confirmingRestart ? vm.actionError : null}
        onConfirm={vm.confirmRestart}
        onCancel={vm.cancelRestart}
      />
    </div>
  );
}

type MainTab = "machines" | "scripts" | "network";
type ScriptsTab = "run" | "library" | "schedules" | "history";

/** Remote Access (2026-10-16 restructure, docs/architecture/REMOTE_MAINTENANCE_PLAN.md):
 * Machines / Scripts and executions / Network. Tabs live in the URL
 * (?tab=&sub=&system=) so the Machines tab's install buttons can open the
 * execution screen with a system script already chosen.
 *
 * Since 2026-10-17 this is also the old Servers page (/servers redirects
 * here), so it opens for the "servers" module. Everything past the machine
 * list -- quick actions, scripts, network -- is admin-only, as the backend
 * routes behind them are; a non-admin sees Machines with no tab strip. */
export default function RemoteAccessPage() {
  const { t } = useTranslation("remoteAccess");
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const isAdmin = useAuthStore((state) => state.user?.is_admin ?? false);
  const requested = (params.get("tab") as MainTab) || "machines";
  const tab: MainTab = isAdmin ? requested : "machines";
  const sub = (params.get("sub") as ScriptsTab) || "run";
  const system = params.get("system");
  const [preparing, setPreparing] = useState(false);
  const [rotating, setRotating] = useState<"login_password" | "ssh_key" | null>(null);

  useEffect(() => {
    document.title = `${t("title")} · ForgeHub`;
  }, [t]);

  const go = (next: Record<string, string | null>) => {
    const merged = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) {
      if (v === null) merged.delete(k);
      else merged.set(k, v);
    }
    setParams(merged, { replace: true });
  };

  return (
    <div className="space-y-6 max-md:break-words">
      <PageHeader
        icon={<ShieldCheck className="h-7 w-7 text-primary" aria-hidden="true" />}
        title={t("title")}
        description={t("subtitle")}
      />
      <Tabs value={tab} onValueChange={(v) => go({ tab: v, system: null })} className="space-y-6">
        {isAdmin && (
          <TabsList>
            <TabsTrigger value="machines">{t("tabs.machines")}</TabsTrigger>
            <TabsTrigger value="scripts">{t("tabs.scripts")}</TabsTrigger>
            <TabsTrigger value="network">{t("tabs.network")}</TabsTrigger>
          </TabsList>
        )}

        <TabsContent value="machines" className="space-y-6">
          {isAdmin && <div className="flex flex-wrap gap-2" role="group" aria-label={t("quick.title")}>
            <Button type="button" size="sm" className="cursor-pointer gap-1.5" onClick={() => setPreparing(true)}>
              <Wrench className="h-3.5 w-3.5" aria-hidden="true" /> {t("quick.prepare")}
            </Button>
            {(["login_password", "ssh_key"] as const).map((kind) => (
              <Button key={kind} type="button" variant="outline" size="sm" className="cursor-pointer gap-1.5" onClick={() => setRotating(kind)}>
                <RotateCw className="h-3.5 w-3.5" aria-hidden="true" /> {t(`quick.rotate_${kind}`)}
              </Button>
            ))}
            {(["remote_access_install", "tailscale_install", "rustdesk_install", "rustdesk_password"] as const).map((action) => (
              <Button key={action} type="button" variant="outline" size="sm" className="cursor-pointer gap-1.5"
                onClick={() => go({ tab: "scripts", sub: "run", system: action })}>
                <Wrench className="h-3.5 w-3.5" aria-hidden="true" /> {t(`quick.${action}`)}
              </Button>
            ))}
          </div>}
          <MachinesCard />
          {rotating && (
            <RotationDialog
              kind={rotating}
              onClose={() => setRotating(null)}
              onExecution={(id) => navigate(`/remote-access/executions/${id}`)}
            />
          )}
          {preparing && (
            <PrepareDialog
              onClose={() => setPreparing(false)}
              onExecution={(id) => navigate(`/remote-access/executions/${id}`)}
            />
          )}
        </TabsContent>

        <TabsContent value="scripts" className="space-y-6">
          <Tabs value={sub} onValueChange={(v) => go({ sub: v, system: null })} className="space-y-4">
            <TabsList>
              <TabsTrigger value="run">{t("tabs.run")}</TabsTrigger>
              <TabsTrigger value="library">{t("tabs.library")}</TabsTrigger>
              <TabsTrigger value="schedules">{t("tabs.schedules")}</TabsTrigger>
              <TabsTrigger value="history">{t("tabs.history")}</TabsTrigger>
            </TabsList>
            <TabsContent value="run">
              <ExecutionComposer
                key={system ?? "free"}
                initialSystem={system}
                onRan={(execution) => navigate(`/remote-access/executions/${execution.id}`)}
                onScheduled={() => go({ sub: "schedules", system: null })}
              />
            </TabsContent>
            <TabsContent value="library"><ScriptLibrary /></TabsContent>
            <TabsContent value="schedules">
              <SchedulesPanel onRan={(execution) => navigate(`/remote-access/executions/${execution.id}`)} />
            </TabsContent>
            <TabsContent value="history"><ExecutionsCard /></TabsContent>
          </Tabs>
        </TabsContent>

        <TabsContent value="network" className="space-y-6">
          <NetworkTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function StatTile({ label, value, tone }: { label: string; value: number; tone?: "good" | "muted" }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-2xl font-semibold tabular-nums", tone === "good" && "text-emerald-500", tone === "muted" && "text-muted-foreground")}>{value}</p>
    </div>
  );
}
