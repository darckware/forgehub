/** Scheduled script runs (once / weekly). State: useSchedulesViewModel. */
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Loader2, Pause, Play, Trash2, Zap } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { HostExecutionDetail } from "@/hooks/useHostExecutions";
import type { HostSchedule } from "@/hooks/useHostScripts";
import { useSchedulesViewModel } from "@/hooks/useSchedulesViewModel";

export function SchedulesPanel({ onRan }: { onRan: (execution: HostExecutionDetail) => void }) {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useSchedulesViewModel(onRan);
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });

  const when = (s: HostSchedule) =>
    s.kind === "once"
      ? t("schedules.once", { at: s.run_at ? fmt.format(new Date(s.run_at)) : "—" })
      : t("schedules.weekly", { days: (s.weekdays ?? []).map((d) => t(`composer.days.${d}`)).join(", "), time: s.time_of_day ?? "" });

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{t("schedules.title")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
        {vm.status === "loading" ? (
          <p className="text-sm text-muted-foreground" role="status">{t("loading")}</p>
        ) : vm.status === "error" ? (
          <p className="text-sm text-destructive" role="alert">{t("schedules.loadFailed")}</p>
        ) : vm.schedules.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("schedules.empty")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("schedules.name")}</TableHead>
                <TableHead>{t("schedules.script")}</TableHead>
                <TableHead>{t("schedules.when")}</TableHead>
                <TableHead>{t("schedules.next")}</TableHead>
                <TableHead>{t("schedules.last")}</TableHead>
                <TableHead className="text-right">{t("devices.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {vm.schedules.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <p className="font-medium">{s.name}</p>
                    <p className="text-xs text-muted-foreground">{t("schedules.machines", { count: s.server_ids.length + s.group_ids.length })} · {s.created_by}</p>
                  </TableCell>
                  <TableCell className="text-xs">{s.script_name ?? "—"}</TableCell>
                  <TableCell className="text-xs">{when(s)}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs">
                    {s.enabled ? (s.next_run_at ? fmt.format(new Date(s.next_run_at)) : "—") : <Badge variant="outline">{t("schedules.paused")}</Badge>}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs">
                    {s.last_execution_id ? (
                      <Link to={`/remote-access/executions/${s.last_execution_id}`} className="text-primary hover:underline">
                        {s.last_run_at ? fmt.format(new Date(s.last_run_at)) : t("schedules.open")}
                      </Link>
                    ) : "—"}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-right">
                    <Button type="button" size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => vm.runNow(s)} disabled={vm.runningId === s.id}
                      aria-label={t("schedules.runNowFor", { name: s.name })} title={t("schedules.runNow")}>
                      {vm.runningId === s.id ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : <Zap className="h-4 w-4" aria-hidden="true" />}
                    </Button>
                    <Button type="button" size="icon" variant="ghost" className="h-8 w-8 cursor-pointer" onClick={() => vm.toggle(s)} disabled={vm.togglingId === s.id}
                      aria-label={t(s.enabled ? "schedules.pauseFor" : "schedules.resumeFor", { name: s.name })} title={t(s.enabled ? "schedules.pause" : "schedules.resume")}>
                      {s.enabled ? <Pause className="h-4 w-4" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
                    </Button>
                    <Button type="button" size="icon" variant="ghost" className="h-8 w-8 cursor-pointer hover:text-destructive" onClick={() => vm.askDelete(s)}
                      aria-label={t("schedules.deleteFor", { name: s.name })} title={t("schedules.delete")}>
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      <ConfirmDialog
        open={vm.deleting !== null}
        title={t("schedules.deleteTitle")}
        description={t("schedules.deleteDescription", { name: vm.deleting?.name ?? "" })}
        confirmLabel={t("schedules.delete")}
        cancelLabel={t("cancel")}
        loading={vm.removing}
        dismissDisabled={vm.removing}
        onConfirm={vm.confirmDelete}
        onCancel={vm.cancelDelete}
      />
    </Card>
  );
}
