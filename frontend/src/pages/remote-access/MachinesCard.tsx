/**
 * Remote Access › Machines: every server and workstation in one table,
 * sectioned by how the VPS reaches it -- Tailscale, through a subnet router,
 * or not at all -- plus the tailnet devices not in the inventory yet (phase 3
 * of docs/architecture/REMOTE_ACCESS_SERVERS_UNIFICATION_PLAN.md). State lives
 * in useMachinesViewModel; this file only renders it.
 */
import { Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Activity,
  FolderPlus,
  Vault,
  Wrench,
  KeyRound,
  Loader2,
  MonitorSmartphone,
  Network,
  Pencil,
  Plus,
  Power,
  PowerOff,
  RefreshCw,
  Search,
  SquareTerminal,
  Trash2,
  Upload,
  UserPlus,
  Waypoints,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDarckwareClients } from "@/hooks/useClientOps";
import type { HostReadiness, HostReadinessEntry, ReadinessCounts } from "@/hooks/useHostInventory";
import {
  useMachinesViewModel,
  type KindFilter,
  type MachineRow,
  type MachineSection,
  type PathFilter,
  type ReadinessFilter,
} from "@/hooks/useMachinesViewModel";
import { buildSshCommand, resolveSshCommand, type Server } from "@/hooks/useServers";
import { ImportCsvModal, InstallKeyModal } from "@/pages/servers/ServerDialogs";
import { ServerForm } from "@/pages/servers/ServerForm";
import { ServerServicesPanel } from "@/pages/servers/ServerServicesPanel";
import { serverHome } from "@/pages/workspace/workspaceState";
import { PrepareDialog } from "./PrepareDialog";
import { RevealPasswordDialog } from "./RevealPasswordDialog";

type T = (key: string, options?: Record<string, unknown>) => string;

const READINESS_VARIANT: Record<HostReadiness, "success" | "warning" | "destructive" | "outline" | "secondary"> = {
  ready: "success",
  busy: "secondary",
  online_no_access: "warning",
  not_prepared: "warning",
  offline: "outline",
  disabled: "outline",
  unknown: "outline",
};

function ReadinessBadge({ entry, t }: { entry: HostReadinessEntry | undefined; t: T }) {
  const state = entry?.readiness ?? "unknown";
  return (
    <Badge variant={READINESS_VARIANT[state]} title={entry?.detail ?? undefined} className="whitespace-nowrap">
      {t(`readiness.${state}`)}
    </Badge>
  );
}

function CountsLine({ counts, t }: { counts: ReadinessCounts; t: T }) {
  return (
    <span className="text-xs text-muted-foreground">
      {t("workstations.counts", { ready: counts.ready, total: counts.total })}
      {counts.attention > 0 && ` · ${t("workstations.attentionCount", { count: counts.attention })}`}
      {counts.offline > 0 && ` · ${t("workstations.offlineCount", { count: counts.offline })}`}
    </span>
  );
}

function sectionTitle(section: MachineSection, t: T): string {
  if (section.kind === "subnet") return t("machines.sections.subnet", { router: section.routerName ?? "?" });
  return t(`machines.sections.${section.kind}`);
}

function IconButton({ label, onClick, disabled, className, children }: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      size="icon"
      variant="ghost"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={`h-8 w-8 cursor-pointer ${className ?? ""}`}
    >
      {children}
    </Button>
  );
}

export function MachinesCard() {
  const { t } = useTranslation("remoteAccess");
  const navigate = useNavigate();
  const vm = useMachinesViewModel();
  const { data: clientList } = useDarckwareClients();
  const [revealing, setRevealing] = useState<{ machine: Server; kind: "login" | "rustdesk" } | null>(null);

  const syncSummary = vm.syncResult
    ? (["created", "linked", "updated"] as const)
        .map((outcome) => ({ outcome, count: vm.syncResult!.entries.filter((e) => e.outcome === outcome).length }))
        .filter((x) => x.count > 0)
        .map((x) => t(`workstations.sync.${x.outcome}`, { count: x.count }))
        .concat(vm.syncResult.missing_server_ids.length
          ? [t("workstations.sync.missing", { count: vm.syncResult.missing_server_ids.length })]
          : [])
        .join(" · ") || t("workstations.sync.nothing")
    : null;

  // Same resolution as the Workspace SSH menu: a ForgeVault key goes through
  // the bridge's in-memory agent, never a key file.
  const openTerminal = (s: Server) => {
    const launch = (command: string) =>
      navigate("/workspace", {
        state: { openSsh: { label: s.name, command, server: { id: s.id, name: s.name, home: serverHome(s.remote_user) } } },
      });
    void resolveSshCommand(s).then(launch).catch(() => launch(buildSshCommand(s)));
  };

  const renderRow = ({ machine, readiness, node }: MachineRow) => {
    const ready = readiness?.readiness === "ready";
    const routes = node?.subnet_routes ?? [];
    const lanAddressWithTailscale =
      readiness?.tailscale_ipv4 && readiness.tailscale_ipv4 !== machine.ip_address ? readiness.tailscale_ipv4 : null;
    return (
      <Fragment key={machine.id}>
        <TableRow className={machine.access_enabled ? "" : "opacity-60"}>
          <TableCell>
            <p className="font-medium">{machine.name}</p>
            <p className="font-mono text-xs text-muted-foreground">{machine.ip_address || "—"}</p>
            {lanAddressWithTailscale && (
              <p className="font-mono text-xs text-muted-foreground" title={t("machines.tailscaleIpHint")}>
                Tailscale {lanAddressWithTailscale}
              </p>
            )}
            <div className="mt-1 md:hidden"><ReadinessBadge entry={readiness} t={t} /></div>
            {routes.length > 0 && (
              <Badge variant="secondary" className="mt-1 gap-1 whitespace-nowrap font-mono text-[10px]">
                <Waypoints className="h-3 w-3" aria-hidden="true" /> {t("machines.routerOf", { routes: routes.join(", ") })}
              </Badge>
            )}
          </TableCell>
          <TableCell className="text-xs max-md:hidden">
            <p>{t(`machines.kind.${machine.kind}`)}</p>
            <p className="text-muted-foreground">{machine.os_family ? t(`os.${machine.os_family}`) : "—"}</p>
          </TableCell>
          <TableCell className="text-xs max-md:hidden">
            <p>{machine.darckware_client_name ?? "—"}</p>
            <p className="text-muted-foreground">
              {machine.group_ids.map((id) => vm.groupsById.get(id)?.name).filter(Boolean).join(", ") || machine.location || ""}
            </p>
          </TableCell>
          <TableCell className="font-mono text-xs max-md:hidden">{machine.remote_user || "—"}</TableCell>
          <TableCell className="max-md:hidden"><ReadinessBadge entry={readiness} t={t} /></TableCell>
          <TableCell className="whitespace-nowrap text-right">
            <div className="flex justify-end gap-0.5">
              {machine.access_enabled && ready && (
                <IconButton label={t("machines.actions.terminal", { name: machine.name })} onClick={() => openTerminal(machine)} className="text-emerald-600">
                  <SquareTerminal className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
              {vm.isAdmin && machine.access_enabled && !ready && (
                <IconButton label={t("machines.actions.configure", { name: machine.name })} onClick={() => vm.configure(machine)} className="text-amber-500">
                  <Wrench className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
              {vm.isAdmin && node && (
                <IconButton
                  label={t("machines.actions.testTailscale", { name: machine.name })}
                  onClick={() => vm.testNode(node.id)}
                  disabled={vm.testing !== null}
                >
                  {vm.testing === node.id
                    ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
                    : <Activity className="h-4 w-4" aria-hidden="true" />}
                </IconButton>
              )}
              {vm.isAdmin && machine.rustdesk_password_stored && (
                <IconButton label={t("password.rustdeskFor", { name: machine.name })} onClick={() => setRevealing({ machine, kind: "rustdesk" })}>
                  <MonitorSmartphone className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
              {vm.isAdmin && machine.login_password_stored && (
                <IconButton label={t("password.for", { name: machine.name })} onClick={() => setRevealing({ machine, kind: "login" })}>
                  <KeyRound className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
              {machine.kind === "server" && (
                <IconButton label={t("machines.actions.services", { name: machine.name })} onClick={() => vm.toggleExpanded(machine.id)}>
                  <Network className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
              {vm.canWrite && (
                <IconButton
                  label={t(machine.access_enabled ? "machines.actions.turnOff" : "machines.actions.turnOn", { name: machine.name })}
                  onClick={() => vm.toggleAccess(machine)}
                  disabled={vm.togglingAccess}
                  className={machine.access_enabled ? "text-emerald-600" : "text-muted-foreground"}
                >
                  {machine.access_enabled ? <Power className="h-4 w-4" aria-hidden="true" /> : <PowerOff className="h-4 w-4" aria-hidden="true" />}
                </IconButton>
              )}
              {vm.canWrite && (
                <IconButton label={t("workstations.editFor", { name: machine.name })} onClick={() => vm.openForm(machine)}>
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
              {vm.canDelete && (
                <IconButton label={t("machines.actions.delete", { name: machine.name })} onClick={() => vm.askDelete(machine)} className="text-destructive hover:text-destructive">
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </IconButton>
              )}
            </div>
          </TableCell>
        </TableRow>
        {vm.expandedId === machine.id && (
          <TableRow>
            <TableCell colSpan={6} className="p-0">
              <ServerServicesPanel server={machine} />
            </TableCell>
          </TableRow>
        )}
      </Fragment>
    );
  };

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="text-base">{t("machines.title")}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("machines.totals", { ready: vm.totals.ready, total: vm.totals.total, attention: vm.totals.attention, offline: vm.totals.offline })}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {vm.canWrite && (
              <Button type="button" size="sm" onClick={() => vm.openForm("new")} className="cursor-pointer gap-1.5">
                <Plus className="h-3.5 w-3.5" aria-hidden="true" /> {t("machines.new")}
              </Button>
            )}
            {vm.isAdmin && (
              <Button type="button" size="sm" variant="outline" onClick={vm.sync} disabled={vm.syncing} className="cursor-pointer gap-1.5">
                {vm.syncing ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Waypoints className="h-3.5 w-3.5" aria-hidden="true" />}
                {t("workstations.syncTailnet")}
              </Button>
            )}
            {vm.isAdmin && (
              <Button type="button" size="sm" variant="outline" onClick={vm.askMigrate} disabled={vm.migrating} className="cursor-pointer gap-1.5">
                {vm.migrating ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Vault className="h-3.5 w-3.5" aria-hidden="true" />}
                {t("machines.migrate.action")}
              </Button>
            )}
            <Button type="button" size="sm" variant="outline" onClick={vm.probeNow} disabled={vm.probing} className="cursor-pointer gap-1.5">
              {vm.probing ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
              {t("workstations.probeNow")}
            </Button>
            {vm.canWrite && (
              <Button type="button" size="sm" variant="outline" onClick={() => vm.setImportingCsv(true)} className="cursor-pointer gap-1.5">
                <Upload className="h-3.5 w-3.5" aria-hidden="true" /> {t("machines.importCsv")}
              </Button>
            )}
            {vm.canWrite && (
              <Button type="button" size="sm" variant="outline" onClick={vm.startGroup} className="cursor-pointer gap-1.5">
                <FolderPlus className="h-3.5 w-3.5" aria-hidden="true" /> {t("workstations.newGroup")}
              </Button>
            )}
          </div>
        </div>

        {vm.migration && (
          <div role="status" className="space-y-1 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">
            <p>{t("machines.migrate.summary", { switched: vm.migration.switched.length, already: vm.migration.already.length, failed: Object.keys(vm.migration.failed).length })}</p>
            {Object.entries(vm.migration.failed).map(([name, reason]) => (
              <p key={name} className="text-amber-700 dark:text-amber-400"><span className="font-medium">{name}</span>: {reason}</p>
            ))}
          </div>
        )}
        {syncSummary && <p role="status" className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">{syncSummary}</p>}
        {vm.syncError && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs">{t("workstations.sync.failed")}</p>}
        {vm.testResult && (
          <p role="status" className={`rounded-md border px-3 py-2 text-xs ${vm.testResult.success ? "border-emerald-500/40 bg-emerald-500/10" : "border-destructive/40 bg-destructive/10"}`}>
            {vm.testResult.target_name ?? ""} — {vm.testResult.summary}
          </p>
        )}
        {!vm.tailnetAvailable && (
          <p role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">{t("workstations.tailnetUnavailable")}</p>
        )}

        {vm.groupDraft && (
          <form
            className="grid grid-cols-1 gap-2 rounded-md border border-border p-3 sm:grid-cols-[minmax(0,1fr)_220px_auto]"
            onSubmit={(e) => {
              e.preventDefault();
              vm.saveGroup(clientList?.items.find((c) => c.id === vm.groupDraft?.clientId)?.company_name ?? null);
            }}
          >
            <label>
              <span className="sr-only">{t("workstations.groupName")}</span>
              <Input
                autoFocus
                value={vm.groupDraft.name}
                onChange={(e) => vm.setGroupDraft({ ...vm.groupDraft!, name: e.target.value })}
                placeholder={t("workstations.groupName")}
                className="max-md:text-base"
              />
            </label>
            <label>
              <span className="sr-only">{t("workstations.client")}</span>
              <Select
                value={vm.groupDraft.clientId}
                onChange={(e) => vm.setGroupDraft({ ...vm.groupDraft!, clientId: e.target.value })}
                className="max-md:text-base"
              >
                <option value="">{t("workstations.noClient")}</option>
                {clientList?.items.map((c) => <option key={c.id} value={c.id}>{c.company_name}</option>)}
              </Select>
            </label>
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={vm.savingGroup || !vm.groupDraft.name.trim()} className="cursor-pointer gap-1.5">
                {vm.savingGroup && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                {t("workstations.createGroup")}
              </Button>
              <Button type="button" size="icon" variant="ghost" onClick={vm.cancelGroup} aria-label={t("cancel")} className="cursor-pointer">
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            {vm.groupError && <p role="alert" className="text-xs text-destructive sm:col-span-3">{vm.groupError}</p>}
          </form>
        )}

        <div className="grid grid-cols-2 gap-2 lg:grid-cols-[minmax(0,1fr)_repeat(4,190px)]">
          <label className="relative col-span-2 lg:col-span-1">
            <span className="sr-only">{t("machines.search")}</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input value={vm.filters.query} onChange={(e) => vm.setFilter("query", e.target.value)} placeholder={t("machines.search")} className="pl-8 max-md:text-base" />
          </label>
          <label>
            <span className="sr-only">{t("machines.filters.path")}</span>
            <Select value={vm.filters.path} onChange={(e) => vm.setFilter("path", e.target.value as PathFilter)} className="max-md:text-base">
              <option value="all">{t("machines.filters.allPaths")}</option>
              <option value="tailscale">{t("machines.sections.tailscale")}</option>
              <option value="subnet">{t("machines.filters.subnet")}</option>
              <option value="none">{t("machines.sections.none")}</option>
              <option value="unregistered">{t("machines.sections.unregistered")}</option>
            </Select>
          </label>
          <label>
            <span className="sr-only">{t("machines.filters.kind")}</span>
            <Select value={vm.filters.kind} onChange={(e) => vm.setFilter("kind", e.target.value as KindFilter)} className="max-md:text-base">
              <option value="all">{t("machines.filters.allKinds")}</option>
              <option value="server">{t("machines.kind.server")}</option>
              <option value="workstation">{t("machines.kind.workstation")}</option>
            </Select>
          </label>
          <label>
            <span className="sr-only">{t("workstations.client")}</span>
            <Select value={vm.filters.client} onChange={(e) => vm.setFilter("client", e.target.value)} className="max-md:text-base">
              <option value="all">{t("machines.filters.allClients")}</option>
              <option value="none">{t("workstations.noClient")}</option>
              {vm.clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </label>
          <label>
            <span className="sr-only">{t("workstations.filter")}</span>
            <Select value={vm.filters.readiness} onChange={(e) => vm.setFilter("readiness", e.target.value as ReadinessFilter)} className="max-md:text-base">
              <option value="all">{t("workstations.filters.all")}</option>
              <option value="ready">{t("readiness.ready")}</option>
              <option value="attention">{t("workstations.filters.attention")}</option>
              <option value="offline">{t("readiness.offline")}</option>
            </Select>
          </label>
        </div>

        {vm.groups.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">{t("machines.groups")}</span>
            {vm.groups.map((group) => {
              const counts = vm.groupCounts.get(group.id);
              return (
                <span key={group.id} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-0.5 text-xs">
                  {group.name}
                  <span className="text-muted-foreground">{counts ? `${counts.ready}/${counts.total}` : "0/0"}</span>
                  {vm.canDelete && <button
                    type="button"
                    onClick={() => vm.askDeleteGroup(group)}
                    aria-label={t("workstations.deleteGroupFor", { name: group.name })}
                    className="cursor-pointer text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="h-3 w-3" aria-hidden="true" />
                  </button>}
                </span>
              );
            })}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-6">
        {vm.status === "loading" ? (
          <p className="py-6 text-center text-sm text-muted-foreground" role="status">{t("loading")}</p>
        ) : vm.status === "error" ? (
          <p className="py-6 text-center text-sm text-destructive" role="alert">{t("machines.loadFailed")}</p>
        ) : vm.sections.length === 0 && vm.unregistered.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t("machines.empty")}</p>
        ) : (
          <>
            {vm.sections.map((section) => (
              <section key={section.key} aria-label={sectionTitle(section, t)}>
                <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                  <div>
                    <h2 className="text-sm font-semibold">{sectionTitle(section, t)}</h2>
                    <p className="text-xs text-muted-foreground">
                      {section.kind === "subnet"
                        ? t("machines.sectionHelp.subnet", { routes: section.routes.join(", ") || "—" })
                        : t(`machines.sectionHelp.${section.kind}`)}
                    </p>
                    {section.notAccepted && (
                      <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">{t("machines.notAccepted")}</p>
                    )}
                  </div>
                  <CountsLine counts={section.counts} t={t} />
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("machines.columns.name")}</TableHead>
                      <TableHead className="max-md:hidden">{t("machines.columns.kind")}</TableHead>
                      <TableHead className="max-md:hidden">{t("machines.columns.client")}</TableHead>
                      <TableHead className="max-md:hidden">{t("workstations.columns.login")}</TableHead>
                      <TableHead className="max-md:hidden">{t("workstations.columns.readiness")}</TableHead>
                      <TableHead className="text-right">{t("devices.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>{section.rows.map(renderRow)}</TableBody>
                </Table>
              </section>
            ))}

            {vm.unregistered.length > 0 && (
              <section aria-label={t("machines.sections.unregistered")}>
                <div className="mb-2">
                  <h2 className="text-sm font-semibold">{t("machines.sections.unregistered")}</h2>
                  <p className="text-xs text-muted-foreground">{t("machines.sectionHelp.unregistered")}</p>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("devices.name")}</TableHead>
                      <TableHead className="max-md:hidden">{t("devices.os")}</TableHead>
                      <TableHead>{t("devices.status")}</TableHead>
                      <TableHead className="text-right">{t("devices.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {vm.unregistered.map((device) => (
                      <TableRow key={device.id}>
                        <TableCell>
                          <p className="font-medium">{device.name ?? device.hostname ?? device.id}</p>
                          <p className="font-mono text-xs text-muted-foreground">{device.tailscale_ipv4 ?? "—"}</p>
                          <p className="text-xs text-muted-foreground md:hidden">{device.os ?? ""}</p>
                          {(device.subnet_routes ?? []).length > 0 && (
                            <Badge variant="secondary" className="mt-1 gap-1 whitespace-nowrap font-mono text-[10px]">
                              <Waypoints className="h-3 w-3" aria-hidden="true" /> {t("machines.routerOf", { routes: device.subnet_routes!.join(", ") })}
                            </Badge>
                          )}
                        </TableCell>
                        <TableCell className="text-xs max-md:hidden">{device.os ?? "—"}</TableCell>
                        <TableCell>
                          <Badge variant={device.online ? "success" : "outline"}>{t(`state.${device.state}`)}</Badge>
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-right">
                          <div className="flex justify-end gap-0.5">
                            <IconButton
                              label={t("machines.actions.testTailscale", { name: device.name ?? device.id })}
                              onClick={() => vm.testNode(device.id)}
                              disabled={vm.testing !== null}
                            >
                              {vm.testing === device.id
                                ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
                                : <Activity className="h-4 w-4" aria-hidden="true" />}
                            </IconButton>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => vm.register(device.id)}
                              disabled={vm.registering !== null}
                              className="cursor-pointer gap-1.5"
                            >
                              {vm.registering === device.id
                                ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />
                                : <UserPlus className="h-3.5 w-3.5" aria-hidden="true" />}
                              {t("machines.actions.register")}
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </section>
            )}
          </>
        )}
      </CardContent>

      {vm.form !== null && <ServerForm initial={vm.form === "new" ? null : vm.form} onClose={vm.closeForm} />}
      {vm.importingCsv && <ImportCsvModal onClose={() => vm.setImportingCsv(false)} />}
      {vm.installing && (
        <InstallKeyModal server={vm.installing} onClose={vm.closeInstall} onInstalled={vm.probeNow} />
      )}
      {vm.preparing && (
        <PrepareDialog
          initialServerId={vm.preparing.id}
          onClose={vm.closePrepare}
          onExecution={(id) => navigate(`/remote-access/executions/${id}`)}
        />
      )}
      <ConfirmDialog
        open={vm.confirmingMigration}
        title={t("machines.migrate.title")}
        description={t("machines.migrate.description")}
        confirmLabel={t("machines.migrate.confirm")}
        cancelLabel={t("cancel")}
        icon="wrench"
        variant="default"
        loading={vm.migrating}
        dismissDisabled={vm.migrating}
        error={vm.confirmingMigration ? vm.migrationError : null}
        onConfirm={vm.confirmMigrate}
        onCancel={vm.cancelMigrate}
      />
      {revealing && <RevealPasswordDialog machine={revealing.machine} kind={revealing.kind} onClose={() => setRevealing(null)} />}

      <ConfirmDialog
        open={vm.deleting !== null}
        title={t("machines.deleteTitle")}
        description={t("machines.deleteDescription", { name: vm.deleting?.name ?? "" })}
        confirmLabel={t("machines.delete")}
        cancelLabel={t("cancel")}
        loading={vm.removing}
        dismissDisabled={vm.removing}
        onConfirm={vm.confirmDelete}
        onCancel={vm.cancelDelete}
      />
      <ConfirmDialog
        open={vm.deletingGroup !== null}
        title={t("workstations.deleteGroupTitle")}
        description={t("workstations.deleteGroupDescription", { name: vm.deletingGroup?.name ?? "" })}
        confirmLabel={t("workstations.deleteGroup")}
        cancelLabel={t("cancel")}
        loading={vm.removingGroup}
        dismissDisabled={vm.removingGroup}
        onConfirm={vm.confirmDeleteGroup}
        onCancel={vm.cancelDeleteGroup}
      />
    </Card>
  );
}
