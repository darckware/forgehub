/**
 * Client workstations on the Remote Access page (phase 2 of
 * docs/architecture/REMOTE_MAINTENANCE_PLAN.md): bucketed by client, with
 * groups, a live readiness badge per machine and "Sync from tailnet". State
 * lives in useWorkstationsViewModel; this file only renders it.
 */
import { useTranslation } from "react-i18next";
import { FolderPlus, Loader2, Monitor, Pencil, RefreshCw, Search, Trash2, Waypoints, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDarckwareClients } from "@/hooks/useClientOps";
import type { HostReadiness, HostReadinessEntry, ReadinessCounts } from "@/hooks/useHostInventory";
import { useWorkstationsViewModel, type ReadinessFilter } from "@/hooks/useWorkstationsViewModel";
import { ServerForm } from "@/pages/servers/ServerForm";

const READINESS_VARIANT: Record<HostReadiness, "success" | "warning" | "destructive" | "outline" | "secondary"> = {
  ready: "success",
  busy: "secondary",
  online_no_access: "warning",
  not_prepared: "warning",
  offline: "outline",
  disabled: "outline",
  unknown: "outline",
};

function ReadinessBadge({ entry, t }: { entry: HostReadinessEntry | undefined; t: (k: string) => string }) {
  const state = entry?.readiness ?? "unknown";
  return (
    <Badge variant={READINESS_VARIANT[state]} title={entry?.detail ?? undefined} className="whitespace-nowrap">
      {t(`readiness.${state}`)}
    </Badge>
  );
}

function CountsLine({ counts, t }: { counts: ReadinessCounts; t: (k: string, o?: Record<string, unknown>) => string }) {
  return (
    <span className="text-xs text-muted-foreground">
      {t("workstations.counts", { ready: counts.ready, total: counts.total })}
      {counts.attention > 0 && ` · ${t("workstations.attentionCount", { count: counts.attention })}`}
      {counts.offline > 0 && ` · ${t("workstations.offlineCount", { count: counts.offline })}`}
    </span>
  );
}

export function WorkstationsCard() {
  const { t } = useTranslation("remoteAccess");
  const vm = useWorkstationsViewModel();
  const { data: clientList } = useDarckwareClients();

  const syncSummary = vm.syncResult
    ? (["created", "linked", "updated", "available"] as const)
        .map((outcome) => ({ outcome, count: vm.syncResult!.entries.filter((e) => e.outcome === outcome).length }))
        .filter((x) => x.count > 0)
        .map((x) => t(`workstations.sync.${x.outcome}`, { count: x.count }))
        .concat(vm.syncResult.missing_server_ids.length
          ? [t("workstations.sync.missing", { count: vm.syncResult.missing_server_ids.length })]
          : [])
        .join(" · ") || t("workstations.sync.nothing")
    : null;

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <Monitor className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> {t("workstations.title")}
            </CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("workstations.totals", { ready: vm.totals.ready, total: vm.totals.total, attention: vm.totals.attention, offline: vm.totals.offline })}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={vm.sync} disabled={vm.syncing} className="cursor-pointer gap-1.5 max-md:h-auto max-md:whitespace-normal">
              {vm.syncing ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Waypoints className="h-3.5 w-3.5" aria-hidden="true" />}
              {t("workstations.syncTailnet")}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={vm.probeNow} disabled={vm.probing} className="cursor-pointer gap-1.5">
              {vm.probing ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
              {t("workstations.probeNow")}
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => vm.startGroup()} className="cursor-pointer gap-1.5">
              <FolderPlus className="h-3.5 w-3.5" aria-hidden="true" /> {t("workstations.newGroup")}
            </Button>
          </div>
        </div>

        {syncSummary && <p role="status" className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs">{syncSummary}</p>}
        {vm.available.length > 0 && (
          <div className="space-y-2 rounded-md border border-border p-3">
            <p className="text-xs text-muted-foreground">{t("workstations.import.help")}</p>
            <ul className="space-y-1">
              {vm.available.map((device) => (
                <li key={device.node_id}>
                  <label className="flex flex-wrap items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={vm.importSelection.has(device.node_id)}
                      onChange={() => vm.toggleImport(device.node_id)}
                    />
                    <span className="font-medium">{device.name ?? device.node_id}</span>
                    <span className="font-mono text-xs text-muted-foreground">{device.tailscale_ipv4}</span>
                    <span className="text-xs text-muted-foreground">{device.os}</span>
                    {device.tags.length > 0 && <span className="text-xs text-muted-foreground">{device.tags.join(", ")}</span>}
                    {!device.online && <Badge variant="outline">{t("readiness.offline")}</Badge>}
                  </label>
                </li>
              ))}
            </ul>
            <Button
              type="button"
              size="sm"
              onClick={vm.importSelected}
              disabled={vm.importing || vm.importSelection.size === 0}
              className="cursor-pointer gap-1.5"
            >
              {vm.importing && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
              {t("workstations.import.action", { count: vm.importSelection.size })}
            </Button>
          </div>
        )}
        {vm.syncError && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs">{t("workstations.sync.failed")}</p>}
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

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_200px]">
          <label className="relative">
            <span className="sr-only">{t("workstations.search")}</span>
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <Input value={vm.query} onChange={(e) => vm.setQuery(e.target.value)} placeholder={t("workstations.search")} className="pl-8 max-md:text-base" />
          </label>
          <label>
            <span className="sr-only">{t("workstations.filter")}</span>
            <Select value={vm.filter} onChange={(e) => vm.setFilter(e.target.value as ReadinessFilter)} className="max-md:text-base">
              <option value="all">{t("workstations.filters.all")}</option>
              <option value="ready">{t("readiness.ready")}</option>
              <option value="attention">{t("workstations.filters.attention")}</option>
              <option value="offline">{t("readiness.offline")}</option>
            </Select>
          </label>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {vm.status === "loading" ? (
          <p className="py-6 text-center text-sm text-muted-foreground" role="status">{t("loading")}</p>
        ) : vm.status === "error" ? (
          <p className="py-6 text-center text-sm text-destructive" role="alert">{t("workstations.loadFailed")}</p>
        ) : vm.buckets.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t("workstations.empty")}</p>
        ) : (
          vm.buckets.map((bucket) => (
            <section key={bucket.key} aria-label={bucket.clientName ?? t("workstations.noClient")}>
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-sm font-semibold">{bucket.clientName ?? t("workstations.noClient")}</h2>
                <CountsLine counts={bucket.counts} t={t} />
              </div>
              {bucket.groups.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
                  {bucket.groups.map((group) => {
                    const counts = bucket.groupCounts.get(group.id);
                    return (
                      <span key={group.id} className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-0.5 text-xs">
                        {group.name}
                        <span className="text-muted-foreground">{counts ? `${counts.ready}/${counts.total}` : "0/0"}</span>
                        <button
                          type="button"
                          onClick={() => vm.askDeleteGroup(group)}
                          aria-label={t("workstations.deleteGroupFor", { name: group.name })}
                          className="cursor-pointer text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="h-3 w-3" aria-hidden="true" />
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              {bucket.machines.length === 0 ? (
                <p className="text-xs text-muted-foreground">{t("workstations.noMachines")}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("workstations.columns.name")}</TableHead>
                      <TableHead>{t("workstations.columns.os")}</TableHead>
                      <TableHead>{t("workstations.columns.location")}</TableHead>
                      <TableHead>{t("workstations.columns.groups")}</TableHead>
                      <TableHead>{t("workstations.columns.login")}</TableHead>
                      <TableHead>{t("workstations.columns.readiness")}</TableHead>
                      <TableHead className="text-right">{t("devices.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {bucket.machines.map((machine) => (
                      <TableRow key={machine.id}>
                        <TableCell>
                          <p className="font-medium">{machine.name}</p>
                          <p className="font-mono text-xs text-muted-foreground">{machine.ip_address}</p>
                        </TableCell>
                        <TableCell>{machine.os_family ? t(`os.${machine.os_family}`) : "—"}</TableCell>
                        <TableCell className="text-xs">{machine.location ?? "—"}</TableCell>
                        <TableCell className="text-xs">
                          {machine.group_ids.map((id) => vm.groupsById.get(id)?.name).filter(Boolean).join(", ") || "—"}
                        </TableCell>
                        <TableCell className="font-mono text-xs">{machine.remote_user || "—"}</TableCell>
                        <TableCell><ReadinessBadge entry={vm.readinessOf(machine.id)} t={t} /></TableCell>
                        <TableCell className="text-right">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => vm.edit(machine)}
                            aria-label={t("workstations.editFor", { name: machine.name })}
                            className="cursor-pointer gap-1.5"
                          >
                            <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> {t("workstations.edit")}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </section>
          ))
        )}
      </CardContent>

      {vm.editing && <ServerForm initial={vm.editing} onClose={vm.closeEdit} />}

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
