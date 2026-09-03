import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Activity,
  Cable,
  CircleOff,
  Cloud,
  Laptop,
  Loader2,
  Power,
  RefreshCw,
  RotateCw,
  Server,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  type VpnAction,
  type VpnNode,
  type VpnNodeRole,
  type VpnOperation,
  useVpnAction,
  useVpnOperations,
  useVpnStatus,
} from "@/hooks/useVpn";
import { cn } from "@/lib/utils";

type PendingAction = { node: VpnNodeRole; action: VpnAction; hostname: string };

function bytes(value: number, locale: string): string {
  if (value < 1024) return `${value} B`;
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / 1024)} KB`;
}

function dateTime(value: string | null, locale: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "medium" }).format(date);
}

function stateBadge(node: VpnNode, t: (key: string) => string) {
  const variant = node.state === "online" ? "success" : node.state === "offline" ? "warning" : "destructive";
  return <Badge variant={variant}>{t(`state.${node.state}`)}</Badge>;
}

function operationBadge(operation: VpnOperation, t: (key: string) => string) {
  const variant = operation.status === "succeeded" ? "success" : operation.status === "running" ? "warning" : "destructive";
  return <Badge variant={variant}>{t(`operationStatus.${operation.status}`)}</Badge>;
}

export default function VpnPage() {
  const { t, i18n } = useTranslation("vpn");
  const status = useVpnStatus();
  const operations = useVpnOperations();
  const actionMutation = useVpnAction();
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    document.title = `${t("title")} · ForgeHub`;
  }, [t]);

  const nodes = useMemo(() => {
    const result = new Map<VpnNodeRole, VpnNode>();
    status.data?.nodes.forEach((node) => result.set(node.role, node));
    return result;
  }, [status.data]);

  const requestAction = (node: VpnNode, action: VpnAction) => {
    setSuccessMessage(null);
    if (action === "test" || action === "connect") {
      actionMutation.mutate(
        { node: node.role, action },
        { onSuccess: (result) => setSuccessMessage(result.summary) },
      );
      return;
    }
    setPendingAction({ node: node.role, action, hostname: node.hostname ?? t(`node.${node.role}`) });
  };

  const confirmAction = () => {
    if (!pendingAction) return;
    actionMutation.mutate(
      { node: pendingAction.node, action: pendingAction.action },
      {
        onSuccess: (result) => {
          setSuccessMessage(result.summary);
          setPendingAction(null);
        },
      },
    );
  };

  if (status.isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center rounded-lg border border-border" role="status">
        <Loader2 className="mr-2 h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
        <span className="text-sm text-muted-foreground">{t("loading")}</span>
      </div>
    );
  }

  if (status.isError || !status.data) {
    return (
      <div className="space-y-4 rounded-lg border border-destructive/40 bg-destructive/10 p-5" role="alert">
        <div className="flex items-start gap-3">
          <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden="true" />
          <div>
            <h1 className="font-semibold">{t("unavailable.title")}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t("unavailable.description")}</p>
          </div>
        </div>
        <Button variant="outline" onClick={() => status.refetch()} className="cursor-pointer gap-2">
          <RefreshCw className="h-4 w-4" aria-hidden="true" /> {t("refresh")}
        </Button>
      </div>
    );
  }

  const local = nodes.get("local");
  const remote = nodes.get("remote");
  const connection = status.data.connection;
  const operationsList = operations.data?.operations ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-7 w-7 text-primary" aria-hidden="true" />
            <h1 className="text-3xl font-bold tracking-tight">{t("title")}</h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button
          variant="outline"
          onClick={() => status.refetch()}
          disabled={status.isFetching}
          aria-busy={status.isFetching}
          className="cursor-pointer gap-2 self-start"
        >
          {status.isFetching ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : <RefreshCw className="h-4 w-4" aria-hidden="true" />}
          {t("refresh")}
        </Button>
      </header>

      <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-4 text-sm" role="note">
        <div className="flex items-start gap-3">
          <Cloud className="mt-0.5 h-5 w-5 shrink-0 text-sky-500" aria-hidden="true" />
          <div>
            <p className="font-medium">{t("independence.title")}</p>
            <p className="mt-1 text-muted-foreground">{t("independence.description")}</p>
          </div>
        </div>
      </div>

      {(status.data.source_error || status.data.sources.some((source) => source.status === "unavailable")) && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm" role="status">
          <p className="font-medium text-amber-700 dark:text-amber-300">{t("degraded.title")}</p>
          <p className="mt-1 text-muted-foreground">{t("degraded.description")}</p>
        </div>
      )}

      {successMessage && <p role="status" className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm">{successMessage}</p>}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t("topology.title")}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid items-center gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr]">
            <TopologyPoint icon={Laptop} label={local?.hostname ?? t("node.local")} detail={local?.tailscale_ipv4 ?? "—"} active={local?.online === true} />
            <Cable className="mx-auto h-5 w-5 rotate-90 text-muted-foreground md:rotate-0" aria-hidden="true" />
            <TopologyPoint icon={ShieldCheck} label={t("topology.tailnet")} detail={t(`path.${connection.kind}`, { relay: connection.relay ?? "—" })} active={connection.kind !== "unavailable"} />
            <Cable className="mx-auto h-5 w-5 rotate-90 text-muted-foreground md:rotate-0" aria-hidden="true" />
            <TopologyPoint icon={Server} label={remote?.hostname ?? t("node.remote")} detail={remote?.tailscale_ipv4 ?? "—"} active={remote?.online === true} />
          </div>
          <p className="mt-4 text-center text-xs text-muted-foreground">
            {connection.latency_ms == null ? t("topology.notMeasured") : t("topology.latency", { value: connection.latency_ms })}
          </p>
        </CardContent>
      </Card>

      <section className="grid gap-4 xl:grid-cols-2" aria-label={t("nodes.title")}>
        {local && <NodeCard node={local} peerHostname={remote?.hostname ?? t("nodeName.remote")} locale={i18n.language} busy={actionMutation.isPending && actionMutation.variables?.node === "local"} onAction={requestAction} t={t} />}
        {remote && <NodeCard node={remote} peerHostname={local?.hostname ?? t("nodeName.local")} locale={i18n.language} busy={actionMutation.isPending && actionMutation.variables?.node === "remote"} onAction={requestAction} t={t} />}
      </section>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> {t("history.title")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {operations.isLoading ? (
            <p className="py-6 text-center text-sm text-muted-foreground" role="status">{t("history.loading")}</p>
          ) : operationsList.length === 0 ? (
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
                {operationsList.map((operation) => (
                  <TableRow key={operation.id}>
                    <TableCell className="whitespace-nowrap text-xs">{dateTime(operation.started_at, i18n.language)}</TableCell>
                    <TableCell>{operation.actor_username ?? "—"}</TableCell>
                    <TableCell>{t(`node.${operation.target}`)}</TableCell>
                    <TableCell>{t(`action.${operation.action}`)}</TableCell>
                    <TableCell>{operationBadge(operation, t)}</TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground" title={operation.summary ?? undefined}>{operation.summary ?? operation.result_code ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={pendingAction !== null}
        title={pendingAction ? t(`confirm.${pendingAction.action}.title`) : undefined}
        description={pendingAction ? t(`confirm.${pendingAction.action}.description`, { hostname: pendingAction.hostname }) : undefined}
        confirmLabel={pendingAction ? t(`confirm.${pendingAction.action}.confirm`) : undefined}
        cancelLabel={t("cancel")}
        variant={pendingAction?.action === "disconnect" ? "destructive" : "default"}
        icon={pendingAction?.action === "restart" ? "wrench" : "warning"}
        loading={actionMutation.isPending}
        dismissDisabled={actionMutation.isPending}
        error={actionMutation.error?.message ?? null}
        onConfirm={confirmAction}
        onCancel={() => setPendingAction(null)}
      />
    </div>
  );
}

function TopologyPoint({ icon: Icon, label, detail, active }: { icon: typeof Laptop; label: string; detail: string; active: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-md border border-border bg-muted/20 p-3">
      <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full", active ? "bg-emerald-500/15 text-emerald-500" : "bg-muted text-muted-foreground")}>
        <Icon className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{label}</p>
        <p className="truncate font-mono text-xs text-muted-foreground">{detail}</p>
      </div>
    </div>
  );
}

function NodeCard({ node, peerHostname, locale, busy, onAction, t }: { node: VpnNode; peerHostname: string; locale: string; busy: boolean; onAction: (node: VpnNode, action: VpnAction) => void; t: (key: string, options?: Record<string, unknown>) => string }) {
  const name = node.hostname ?? t(`node.${node.role}`);
  const remoteUnavailable = node.role === "remote" && !node.online;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">{name}</CardTitle>
            <p className="mt-1 font-mono text-xs text-muted-foreground">{node.tailscale_ipv4 ?? "—"}</p>
          </div>
          {stateBadge(node, t)}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <dt className="text-muted-foreground">{t("nodeDetails.daemon")}</dt><dd className="text-right">{t(`daemon.${node.daemon_state}`, { defaultValue: node.daemon_state })}</dd>
          <dt className="text-muted-foreground">{t("nodeDetails.lastSeen")}</dt><dd className="text-right">{dateTime(node.last_seen, locale)}</dd>
          <dt className="text-muted-foreground">{t("nodeDetails.received")}</dt><dd className="text-right font-mono text-xs">{bytes(node.rx_bytes, locale)}</dd>
          <dt className="text-muted-foreground">{t("nodeDetails.sent")}</dt><dd className="text-right font-mono text-xs">{bytes(node.tx_bytes, locale)}</dd>
        </dl>
        <div className="rounded-md border border-border bg-muted/20 p-3 text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{t("posture.title")}</span>
            {node.posture?.restricted ? <Badge variant="success">{t("posture.restricted")}</Badge> : <Badge variant="outline">{t("posture.unavailable")}</Badge>}
          </div>
          {node.posture && (
            <p className="mt-2 text-muted-foreground">
              {t("posture.summary", {
                dns: t(node.posture.accept_dns ? "common.enabled" : "common.disabled"),
                routes: t(node.posture.accept_routes ? "common.enabled" : "common.disabled"),
                ssh: t(node.posture.tailscale_ssh ? "common.enabled" : "common.disabled"),
              })}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2 border-t border-border pt-4">
          {node.role === "local" && (
            <ActionButton icon={Power} label={t("button.connect", { hostname: name })} disabled={node.online || busy} onClick={() => onAction(node, "connect")} />
          )}
          {node.role === "local" && (
            <ActionButton icon={CircleOff} label={t("button.disconnect", { hostname: name })} disabled={!node.online || busy} variant="destructive" onClick={() => onAction(node, "disconnect")} />
          )}
          {!remoteUnavailable && (
            <ActionButton icon={RotateCw} label={t("button.restart", { hostname: name })} disabled={busy} onClick={() => onAction(node, "restart")} />
          )}
          <ActionButton icon={Cable} label={t("button.test", { hostname: peerHostname })} disabled={!node.online || busy} onClick={() => onAction(node, "test")} />
        </div>
        {remoteUnavailable && <p className="text-xs text-muted-foreground">{t("nodeDetails.remoteRestartUnavailable")}</p>}
      </CardContent>
    </Card>
  );
}

function ActionButton({ icon: Icon, label, onClick, disabled, variant = "outline" }: { icon: typeof Power; label: string; onClick: () => void; disabled?: boolean; variant?: "outline" | "destructive" }) {
  return (
    <Button type="button" size="sm" variant={variant} onClick={onClick} disabled={disabled} aria-label={label} className="cursor-pointer gap-1.5">
      <Icon className="h-3.5 w-3.5" aria-hidden="true" /> {label}
    </Button>
  );
}
