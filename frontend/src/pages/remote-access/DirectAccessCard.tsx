/** Human-confirmed access configuration lives on each agent row. */
import { useTranslation } from "react-i18next";
import { Bot, Loader2, Pause, Play, Settings2, TerminalSquare, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DIRECT_DURATIONS, DIRECT_PURPOSES, type DirectDuration, type DirectPurpose } from "@/hooks/useDirectAccess";
import { useDirectAccessViewModel } from "@/hooks/useDirectAccessViewModel";
import { useDirectAgentsViewModel } from "@/hooks/useDirectAgentsViewModel";

export function DirectAccessCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useDirectAccessViewModel();
  const list = useDirectAgentsViewModel();
  const fmt = (value: string) => new Date(value).toLocaleString(i18n.language);
  const rows = [...vm.agents].sort((a, b) => Number(b.allowed) - Number(a.allowed));
  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
        <div><CardTitle className="flex items-center gap-2 text-base"><TerminalSquare className="h-4 w-4" aria-hidden="true" />{t("direct.title")}</CardTitle>
          <p className="mt-1 max-w-3xl text-xs text-muted-foreground">{t("direct.subtitle")}</p></div>
        <Button type="button" size="sm" variant="outline" onClick={list.paused ? () => void list.resume() : list.askPause}
          disabled={!list.control || list.resumePending} className="cursor-pointer gap-1.5">
          {list.resumePending ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : list.paused ? <Play className="h-4 w-4" aria-hidden="true" /> : <Pause className="h-4 w-4" aria-hidden="true" />}
          {list.paused ? t("direct.resume") : t("direct.pause")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className={list.paused ? "rounded-md border border-amber-500/50 px-3 py-2 text-sm" : "text-xs text-muted-foreground"}>
          {list.paused && <p className="break-words font-medium">{t("direct.pausedState", { who: list.control?.paused_by ?? "?", when: list.control?.paused_at ? fmt(list.control.paused_at) : "?" })}</p>}
          {list.paused && list.control?.reason && <p className="mt-1 break-words text-xs">{list.control.reason}</p>}
          <p className={list.paused ? "mt-1 text-xs text-muted-foreground" : undefined}>{t("direct.pauseScope")}</p>
        </div>
        {list.error && !list.removing && !list.confirmingPause && <div role="alert" className="text-xs text-destructive">{list.error}<Button type="button" variant="ghost" size="sm" onClick={list.retry}>{t("direct.retry")}</Button></div>}
        {vm.loading && <div className="flex min-h-24 items-center justify-center"><Loader2 className="h-5 w-5 motion-safe:animate-spin" aria-label={t("maintenance.loading")} /></div>}
        {!vm.loading && !list.error && rows.length === 0 && <p className="text-sm text-muted-foreground">{t("direct.agentsEmpty")}</p>}
        <ul className="divide-y divide-border rounded-md border border-border">
          {rows.map((agent) => {
            const config = agent.configuration;
            const expired = config?.expires_at ? new Date(config.expires_at).getTime() <= vm.now : false;
            const noScope = !config || (!config.all_machines && config.machines.length === 0);
            const editor = vm.editing?.id === agent.id;
            return <li key={agent.id} className="min-w-0 space-y-2 px-3 py-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Bot className="h-4 w-4 text-muted-foreground" aria-hidden="true" /><span className="min-w-0 break-words font-medium">{agent.name}</span>
                {agent.runtime_type && <Badge variant="secondary">{agent.runtime_type}</Badge>}
                <Badge variant={agent.allowed && !noScope && !expired ? "secondary" : "warning"}>{t(!agent.allowed ? "direct.notListed" : noScope ? "direct.pendingConfiguration" : expired ? "direct.expired" : "direct.configured")}</Badge>
                {config?.allow_elevation && <Badge variant="warning">{t("direct.elevationBadge")}</Badge>}
                <div className="ml-auto flex flex-wrap gap-1">
                  <Button type="button" variant="outline" size="sm" disabled={Boolean(agent.unsupported_reason) || vm.pending}
                    onClick={() => vm.open(agent)} className="cursor-pointer gap-1.5"><Settings2 className="h-3.5 w-3.5" aria-hidden="true" />{t("direct.configure", { name: agent.name })}</Button>
                  {agent.allowed && <Button type="button" variant="ghost" size="sm" disabled={vm.pending} onClick={() => list.askRemove(agent)} aria-label={t("direct.removeAgent", { name: agent.name })} className="cursor-pointer text-destructive hover:text-destructive"><Trash2 className="h-4 w-4" aria-hidden="true" /></Button>}
                </div>
              </div>
              {agent.unsupported_reason && <p className="text-xs text-muted-foreground">{t(`direct.unsupported.${agent.unsupported_reason}`)}</p>}
              {config && <div className="space-y-1 break-words text-xs text-muted-foreground">
                <p>{config.all_machines ? t("direct.allMachines") : config.machines.map((m) => m.name).join(", ") || t("direct.noMachines")}</p>
                <p><span>{config.open_ended ? t("direct.indefinite") : t("direct.until", { when: config.expires_at ? fmt(config.expires_at) : "?" })}</span> · {t("direct.since", { when: fmt(config.opened_at) })}</p>
                {vm.now - new Date(config.opened_at).getTime() > 7 * 86400000 && !expired && !noScope && <p className="text-amber-500">{t("direct.oldAccess")}</p>}
                {config.purpose && <p>{t(`direct.purposes.${config.purpose}`)}</p>}{config.reason && <p>{config.reason}</p>}
              </div>}
              {editor && <form noValidate aria-label={t("direct.configure", { name: agent.name })} onSubmit={(event) => { event.preventDefault(); void vm.submit(); }} className="space-y-4 rounded-md border border-border bg-muted/20 p-3">
                <p className="text-xs text-muted-foreground">{t("direct.applyNextCommand")}</p>
                <fieldset disabled={vm.pending} className="space-y-4">
                  <label className="flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={vm.allMachines} onChange={(e) => vm.setAllMachines(e.target.checked)} />{t("direct.allMachines")}</label>
                  {!vm.allMachines && <div className="grid gap-3 sm:grid-cols-2">{[
                    { label: t("agents.pickMachines"), rows: vm.machines, chosen: vm.selectedMachines, toggle: vm.toggleMachine },
                    { label: t("agents.pickGroups"), rows: vm.groups, chosen: vm.selectedGroups, toggle: vm.toggleGroup },
                  ].map((section) => <fieldset key={section.label} className="min-w-0 space-y-1"><legend className="text-sm font-medium">{section.label}</legend>
                    <div className="max-h-48 overflow-y-auto rounded-md border border-border p-2">{section.rows.map((row) => <label key={row.id} className="flex cursor-pointer items-start gap-2 py-1 text-sm"><input type="checkbox" className="mt-1" checked={section.chosen.has(row.id)} onChange={() => section.toggle(row.id)} /><span className="min-w-0 break-words">{row.name}</span></label>)}{!vm.inventoryLoading && section.rows.length === 0 && <p className="text-xs text-muted-foreground">{t("direct.noOptions")}</p>}</div>
                  </fieldset>)}</div>}
                  {!vm.allMachines && vm.selectedMachines.size === 0 && vm.selectedGroups.size === 0 && <p className="text-xs text-muted-foreground">{t("direct.noMachines")}</p>}
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1"><Label htmlFor="direct-hours">{t("direct.duration")}</Label><Select id="direct-hours" value={String(vm.hours)} onChange={(e) => vm.setHours(Number(e.target.value) as DirectDuration)} className="max-md:text-base">{DIRECT_DURATIONS.map((h) => <option key={h} value={h}>{h === 0 ? t("direct.indefinite") : t("direct.hours", { count: h })}</option>)}</Select></div>
                    <div className="space-y-1"><Label htmlFor="direct-purpose">{t("direct.optionalPurpose")}</Label><Select id="direct-purpose" value={vm.purpose} onChange={(e) => vm.setPurpose(e.target.value as DirectPurpose | "")} className="max-md:text-base"><option value="">{t("direct.unspecified")}</option>{DIRECT_PURPOSES.map((p) => <option key={p} value={p}>{t(`direct.purposes.${p}`)}</option>)}</Select></div>
                  </div>
                  <label className="flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={vm.allowElevation} onChange={(e) => vm.setAllowElevation(e.target.checked)} />{t("direct.allowElevation")}</label>
                  <div className="space-y-1"><Label htmlFor="direct-reason">{t("direct.pauseReason")}</Label><Textarea id="direct-reason" rows={2} maxLength={2000} value={vm.reason} onChange={(e) => vm.setReason(e.target.value)} className="resize-none max-md:text-base" /></div>
                </fieldset>
                {vm.inventoryLoading && <p className="text-xs text-muted-foreground">{t("maintenance.loading")}</p>}
                {vm.inventoryError && <div role="alert" className="text-xs text-destructive">{t("direct.inventoryError")}<Button type="button" variant="ghost" size="sm" onClick={vm.retryInventory}>{t("direct.retry")}</Button></div>}
                {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
                <div className="flex flex-wrap justify-end gap-2"><Button type="button" variant="outline" size="sm" onClick={vm.close} disabled={vm.pending}>{t("cancel")}</Button><Button type="submit" size="sm" disabled={!vm.canSubmit} aria-busy={vm.pending} className="min-w-40 cursor-pointer gap-1.5">{vm.pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}{t("direct.save")}</Button></div>
              </form>}
            </li>;
          })}
        </ul>
        {vm.saved && <p role="status" className="text-xs text-muted-foreground">{t("direct.saved", { name: vm.saved })}</p>}
        {list.removed && <p role="status" className="text-xs text-muted-foreground">{t("direct.agentRemoved", { count: list.removed.closed_accesses })}{list.removed.running_commands > 0 && ` ${t("direct.closedRunning", { count: list.removed.running_commands })}`}</p>}
      </CardContent>
      <ConfirmDialog open={vm.confirmation !== null} title={t("direct.confirmTitle", { name: vm.editing?.name ?? "" })}
        description={vm.confirmation?.all ? t("direct.allSensitive") : t("direct.selectedSensitive", { machines: vm.confirmation?.machines.join(", ") })}
        confirmLabel={t("direct.confirm")} variant="default" icon="warning" loading={vm.pending} dismissDisabled={vm.pending}
        error={vm.error} onConfirm={() => void vm.submit(true)} onCancel={vm.cancelConfirmation} />
      <ConfirmDialog open={list.removing !== null} title={t("direct.removeTitle", { name: list.removing?.name ?? "" })} description={t("direct.removeText")}
        confirmLabel={t("direct.removeConfirm")} loading={list.removePending} dismissDisabled={list.removePending} error={list.removing ? list.error : undefined}
        onConfirm={() => void list.confirmRemove()} onCancel={list.cancelRemove} />
      <ConfirmDialog open={list.confirmingPause} title={t("direct.pauseTitle")} description={t("direct.pauseText")} confirmLabel={t("direct.pause")}
        variant="default" icon="warning" loading={list.pausePending} dismissDisabled={list.pausePending} error={list.confirmingPause ? list.error : undefined}
        onConfirm={() => void list.confirmPause()} onCancel={list.cancelPause}>
        <Label htmlFor="direct-pause-reason">{t("direct.pauseReason")}</Label><Textarea className="resize-none max-md:text-base" id="direct-pause-reason" rows={2} value={list.pauseReason} onChange={(e) => list.setPauseReason(e.target.value)} />
      </ConfirmDialog>
    </Card>
  );
}
