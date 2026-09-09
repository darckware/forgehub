import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, CheckCircle2, Circle, Clock, Download, History, Loader2, Package, RefreshCw } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useClients } from "@/hooks/useClients";
import { useWorkstations } from "@/hooks/useWorkstations";
import { useGenerateNexoPackage, useNexoBuilds, useNexoInstallation, useNexoInstallations, useRefreshNexoBuilds, type NexoBuild, type NexoInstallation } from "@/hooks/useNexoInstallations";
import { ApiError } from "@/lib/api";

const platforms = ["linux", "windows"] as const;
const states = ["none", "package_ready", "downloaded", "online", "outdated", "error"] as const;
const stateStyle: Record<string, { icon: typeof Circle; variant: BadgeProps["variant"] }> = {
  none: { icon: Circle, variant: "outline" }, unknown: { icon: AlertTriangle, variant: "warning" },
  package_ready: { icon: Package, variant: "secondary" }, downloaded: { icon: Download, variant: "outline" },
  online: { icon: CheckCircle2, variant: "success" }, outdated: { icon: AlertTriangle, variant: "warning" }, error: { icon: AlertTriangle, variant: "destructive" },
};
interface Row { id: string; clientId: string; clientName: string; hostname: string; os: string; installation?: NexoInstallation }

export default function NexoAgentsPage() {
  const { t, i18n } = useTranslation("nexoAgents");
  const [params, setParams] = useSearchParams();
  const builds = useNexoBuilds();
  const refresh = useRefreshNexoBuilds();
  const installations = useNexoInstallations();
  const workstations = useWorkstations();
  const clients = useClients();
  const generate = useGenerateNexoPackage();
  const [target, setTarget] = useState<{ row: Row; build: NexoBuild } | null>(null);
  const [historyId, setHistoryId] = useState<string | null>(null);
  const history = useNexoInstallation(historyId);
  const [notice, setNotice] = useState("");
  useEffect(() => { document.title = `${t("title")} — ForgeHub`; }, [t]);
  const date = (value?: string | null) => value ? new Intl.DateTimeFormat(i18n.resolvedLanguage, { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : t("notReported");
  const clientNames = useMemo(() => new Map([
    ...(installations.data ?? []).map((item) => [item.client_id, item.client_name] as const),
    ...(clients.data ?? []).map((item) => [item.id, item.name] as const),
  ]), [clients.data, installations.data]);
  // Both endpoints currently return the complete registry. Merge before local
  // filtering so a first package can be generated for an untracked workstation.
  const rows = useMemo(() => {
    const byWorkstation = new Map((installations.data ?? []).map((item) => [item.workstation_id, item]));
    const result = new Map<string, Row>();
    for (const item of installations.data ?? []) result.set(item.workstation_id, { id: item.workstation_id, clientId: item.client_id, clientName: item.client_name, hostname: item.workstation_hostname || item.workstation_id, os: item.os_kind, installation: item });
    for (const item of workstations.data ?? []) result.set(item.id, { id: item.id, clientId: item.client_id, clientName: clientNames.get(item.client_id) || item.client_id, hostname: item.hostname || item.id, os: item.os_kind, installation: byWorkstation.get(item.id) });
    return [...result.values()].sort((a, b) => a.clientName.localeCompare(b.clientName, i18n.resolvedLanguage) || a.hostname.localeCompare(b.hostname, i18n.resolvedLanguage));
  }, [installations.data, workstations.data, clientNames, i18n.resolvedLanguage]);
  const rowStatus = (row: Row) => row.installation?.status ?? (installations.isError ? "unknown" : "none");
  const filtered = rows.filter((row) => (!params.get("client") || row.clientId === params.get("client")) && (!params.get("workstation") || row.id === params.get("workstation")) && (!params.get("os") || row.os === params.get("os")) && (!params.get("status") || rowStatus(row) === params.get("status")));
  const setFilter = (key: string, value: string) => setParams((previous) => { const next = new URLSearchParams(previous); if (value) next.set(key, value); else next.delete(key); return next; });
  const clearFilters = () => setParams((previous) => { const next = new URLSearchParams(previous); ["client", "workstation", "os", "status"].forEach((key) => next.delete(key)); return next; });
  const hasFilters = ["client", "workstation", "os", "status"].some((key) => params.has(key));
  const loading = (installations.isLoading || workstations.isLoading) && rows.length === 0;
  const partial = installations.isError || workstations.isError || clients.isError;
  const forbidden = [installations.error, workstations.error, clients.error, builds.error].some((error) => error instanceof ApiError && error.status === 403);
  const readyBuild = (os: string) => builds.data?.builds.find((build) => build.os_kind === os && build.status === "ready" && build.git_sha === builds.data?.source.git_sha)
    ?? builds.data?.builds.find((build) => build.os_kind === os && build.status === "ready");
  const retryRegistry = () => { void installations.refetch(); void workstations.refetch(); void clients.refetch(); };

  return <div className="mx-auto w-full max-w-7xl space-y-5">
    <header>
      <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
    </header>
    {forbidden ? <div role="alert" className="min-h-48 rounded-lg border border-border p-6">{t("forbidden")}</div> : <>
      <section aria-labelledby="nexo-source" className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 id="nexo-source" className="text-sm font-semibold">{t("builds.title")}</h2>
            <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{builds.data ? `${builds.data.source.agent_version} · ${builds.data.source.git_sha}` : t("builds.sourceUnknown")}</p>
          </div>
          <Button size="sm" variant="outline" className="gap-2" disabled={builds.isLoading || refresh.isPending} aria-busy={refresh.isPending} onClick={() => refresh.mutate()}>
            <RefreshCw className={`h-4 w-4 ${refresh.isPending ? "motion-safe:animate-spin" : ""}`} aria-hidden="true" />{t("builds.refresh")}
          </Button>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {platforms.map((os) => {
            const build = builds.data?.builds.find((item) => item.os_kind === os && item.git_sha === builds.data?.source.git_sha);
            const lastReady = readyBuild(os);
            return <div key={os} className="min-h-24 border-l border-border pl-3 text-xs">
              <div className="flex items-center gap-2"><h3 className="font-semibold">{t(`os.${os}`)}</h3><Badge variant={build?.status === "failed" ? "destructive" : build?.status === "ready" ? "success" : "outline"}>{t(`builds.states.${builds.isLoading ? "loading" : builds.isError && !builds.data ? "unknown" : build?.status ?? "missing"}`)}</Badge></div>
              <p className="mt-2 text-muted-foreground">{t("builds.lastReady")}: {lastReady ? date(lastReady.completed_at) : t("builds.none")}</p>
              {lastReady && <p className="mt-1 break-all font-mono text-muted-foreground">{lastReady.agent_version} · {lastReady.sha256}</p>}
              {build?.build_log_excerpt && build.status === "failed" && <p className="mt-2 break-words text-destructive">{build.build_log_excerpt}</p>}
            </div>;
          })}
        </div>
        <div className="mt-2 min-h-10 text-sm" role={builds.isError || refresh.isError ? "alert" : "status"}>
          {builds.isError ? <div className="flex flex-wrap items-center gap-2"><span>{t("builds.loadError")}</span><Button size="sm" variant="ghost" onClick={() => builds.refetch()}>{t("builds.retry")}</Button></div>
            : refresh.isPending ? t("builds.pending") : refresh.isError ? t("builds.refreshError") : refresh.isSuccess ? t("builds.refreshed") : null}
        </div>
      </section>
      <section aria-labelledby="nexo-registry" className="min-w-0 rounded-lg border border-border bg-card">
        <div className="space-y-3 p-4">
          <h2 id="nexo-registry" className="text-sm font-semibold">{t("registry")}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="space-y-1 text-xs font-medium" htmlFor="nexo-client"><span>{t("filters.client")}</span><Select id="nexo-client" value={params.get("client") ?? ""} onChange={(event) => setFilter("client", event.target.value)}><option value="">{t("filters.all")}</option>{params.get("client") && !clientNames.has(params.get("client")!) && <option value={params.get("client")!}>{params.get("client")}</option>}{[...clientNames].map(([id, name]) => <option key={id} value={id}>{name}</option>)}</Select></label>
            <label className="space-y-1 text-xs font-medium" htmlFor="nexo-os"><span>{t("filters.os")}</span><Select id="nexo-os" value={params.get("os") ?? ""} onChange={(event) => setFilter("os", event.target.value)}><option value="">{t("filters.all")}</option>{platforms.map((os) => <option key={os} value={os}>{t(`os.${os}`)}</option>)}</Select></label>
            <label className="space-y-1 text-xs font-medium" htmlFor="nexo-status"><span>{t("filters.status")}</span><Select id="nexo-status" value={params.get("status") ?? ""} onChange={(event) => setFilter("status", event.target.value)}><option value="">{t("filters.all")}</option>{states.map((state) => <option key={state} value={state}>{t(`states.${state}`)}</option>)}</Select></label>
            <label className="space-y-1 text-xs font-medium" htmlFor="nexo-workstation"><span>{t("filters.workstation")}</span><Select id="nexo-workstation" value={params.get("workstation") ?? ""} onChange={(event) => setFilter("workstation", event.target.value)}><option value="">{t("filters.all")}</option>{params.get("workstation") && !rows.some((row) => row.id === params.get("workstation")) && <option value={params.get("workstation")!}>{params.get("workstation")}</option>}{rows.map((row) => <option key={row.id} value={row.id}>{row.hostname}</option>)}</Select></label>
          </div>
          <div className="flex min-h-9 flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground"><span role="status">{t("count", { count: filtered.length, total: rows.length })}</span>{hasFilters && <Button size="sm" variant="ghost" onClick={clearFilters}>{t("filters.clear")}</Button>}</div>
          <div className="min-h-10 text-sm" role={partial ? "alert" : "status"}>{partial ? <div className="flex flex-wrap items-center gap-2"><AlertTriangle className="h-4 w-4" aria-hidden="true" /><span>{t("partial")}</span><Button size="sm" variant="outline" onClick={retryRegistry}>{t("retry")}</Button></div> : notice}</div>
        </div>
        <div className="min-h-60">
          <Table aria-labelledby="nexo-registry" aria-busy={loading} className="min-w-[1050px]">
            <TableHeader className="bg-muted/50"><TableRow>{["workstation", "client", "os", "status", "versions", "times", "actions"].map((column) => <TableHead key={column} scope="col">{t(`columns.${column}`)}</TableHead>)}</TableRow></TableHeader>
            <TableBody>
              {loading ? <TableRow><TableCell colSpan={7} className="h-48 text-center"><span role="status" className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />{t("loading")}</span></TableCell></TableRow>
                : filtered.length === 0 ? <TableRow><TableCell colSpan={7} className="h-48 text-center"><p>{partial && rows.length === 0 ? t("loadError") : hasFilters ? t("noResults") : t("empty")}</p>{!hasFilters && !partial && <Link to="/clients" className={buttonVariants({ variant: "outline", size: "sm", className: "mt-3" })}>{t("openClients")}</Link>}</TableCell></TableRow>
                  : filtered.map((row) => {
                    const status = rowStatus(row); const { icon: Icon, variant } = stateStyle[status]; const build = readyBuild(row.os);
                    return <TableRow key={row.id}>
                      <TableCell><p className="max-w-48 break-words font-medium">{row.hostname}</p></TableCell>
                      <TableCell><Link className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" to={`/clients/${row.clientId}`}>{row.clientName}</Link></TableCell>
                      <TableCell>{platforms.includes(row.os as typeof platforms[number]) ? t(`os.${row.os}`) : row.os}</TableCell>
                      <TableCell><Badge variant={variant} className="gap-1 whitespace-nowrap"><Icon className="h-3.5 w-3.5" aria-hidden="true" />{t(`states.${status}`)}</Badge>{row.installation?.last_error && <p className="mt-1 max-w-48 break-words text-xs text-destructive">{row.installation.last_error}</p>}</TableCell>
                      <TableCell className="text-xs"><p>{t("expected")}: <span className="font-mono">{row.installation?.expected_version ?? "—"}</span></p><p className="mt-1 text-muted-foreground">{t("detected")}: <span className="font-mono">{row.installation?.detected_version ?? "—"}</span></p></TableCell>
                      <TableCell className="whitespace-nowrap text-xs"><p>{t("packageTime")}: {row.installation ? date(row.installation.package_generated_at) : "—"}</p><p className="mt-1 text-muted-foreground">{t("reportTime")}: {date(row.installation?.last_report_at)}</p></TableCell>
                      <TableCell><div className="flex flex-col items-start gap-1"><Button size="sm" variant="outline" className="gap-1.5" disabled={!build || generate.isPending} aria-describedby={!build ? `build-help-${row.id}` : undefined} onClick={() => { if (build) { generate.reset(); setNotice(""); setTarget({ row, build }); } }}><Download className="h-3.5 w-3.5" aria-hidden="true" />{t("generate")}</Button>{!build ? <p id={`build-help-${row.id}`} className="max-w-48 text-xs text-muted-foreground">{t("builds.required")}</p> : <p className="text-xs text-muted-foreground">{t("builds.packageVersion", { version: build.agent_version })}</p>}{row.installation && <Button size="sm" variant="ghost" className="gap-1.5" onClick={() => setHistoryId(row.installation!.id)}><History className="h-3.5 w-3.5" aria-hidden="true" />{t("history.open")}</Button>}</div></TableCell>
                    </TableRow>;
                  })}
            </TableBody>
          </Table>
        </div>
      </section>
    </>}
    <ConfirmDialog open={Boolean(target)} title={t("confirmation.title", { workstation: target?.row.hostname })} description={t("confirmation.description", { version: target?.build.agent_version })} confirmLabel={t("confirmation.confirm")} cancelLabel={t("cancel")} icon="warning" loading={generate.isPending} dismissDisabled={generate.isPending} onCancel={() => setTarget(null)} onConfirm={() => { if (!target || generate.isPending) return; generate.mutate({ workstationId: target.row.id, buildId: target.build.id }, { onSuccess: () => { setTarget(null); setNotice(t("generated")); } }); }}>
      <div data-testid="generation-feedback" className="min-h-16 text-sm" role={generate.isError ? "alert" : "status"}>{generate.isError ? t("generationError") : generate.isPending ? t("generating") : null}</div>
    </ConfirmDialog>
    <ConfirmDialog open={Boolean(historyId)} title={t("history.title", { workstation: history.data?.workstation_hostname ?? rows.find((row) => row.installation?.id === historyId)?.hostname ?? "" })} description={t("history.description")} variant="default" icon="wrench" confirmLabel={t("close")} cancelLabel={t("back")} onCancel={() => setHistoryId(null)} onConfirm={() => setHistoryId(null)}>
      <div className="min-h-48 text-sm">
        {history.isLoading ? <p role="status">{t("history.loading")}</p> : history.isError ? <div role="alert"><p>{t("history.error")}</p><Button size="sm" variant="outline" className="mt-3" onClick={() => history.refetch()}>{t("retry")}</Button></div> : !history.data?.events.length ? <p>{t("history.empty")}</p> : <ol className="ml-2 border-l border-border pl-4">{history.data.events.map((event) => {
          const Icon = event.event_type === "package_generated" ? Package : event.event_type === "downloaded" ? Download : event.event_type === "first_report" ? Activity : AlertTriangle;
          return <li key={event.id} className="relative pb-5 last:pb-0"><Icon className="absolute -left-[1.55rem] top-0.5 h-4 w-4 bg-card text-muted-foreground" aria-hidden="true" /><p className="font-medium">{t(`history.events.${event.event_type}`)}</p><p className="mt-1 text-xs text-muted-foreground"><Clock className="mr-1 inline h-3 w-3" aria-hidden="true" /><time dateTime={event.created_at}>{date(event.created_at)}</time> · {t(`states.${event.to_status}`)}</p><p className="mt-1 break-all text-xs text-muted-foreground">{event.actor_user_id ? t("history.actor", { id: event.actor_user_id }) : t("history.agent")}</p>{event.detail && <p className="mt-1 break-words text-xs">{event.detail}</p>}</li>;
        })}</ol>}
      </div>
    </ConfirmDialog>
  </div>;
}
