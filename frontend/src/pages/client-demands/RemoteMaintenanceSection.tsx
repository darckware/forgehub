/** "Manutenção remota" in a client ticket/demand's detail (remote-access
 * support plan, Fase 3, 2026-11-12): ask an agent for maintenance on the
 * client's machines with this item preselected, see what ran for it, and --
 * per finished agent task -- confirm the proposed note and minutes before
 * anything is written to Darckware. State: useWorkItemMaintenanceViewModel. */
import { useTranslation } from "react-i18next";
import { AlertTriangle, ArrowLeft, Bot, Check, Clock, Loader2, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SidePanel } from "@/components/ui/side-panel";
import { Textarea } from "@/components/ui/textarea";
import { useClientOpsText, type MaintenanceVerdict, type WorkItemDetail } from "@/hooks/useClientOps";
import { useWorkItemMaintenanceViewModel, type WorkItemMaintenanceViewModel } from "@/hooks/useWorkItemMaintenanceViewModel";
import { AgentRequestDialog } from "@/pages/remote-access/AgentRequestDialog";

const VERDICT_VARIANT: Record<MaintenanceVerdict, "success" | "destructive" | "secondary" | "outline"> = {
  succeeded: "success",
  failed: "destructive",
  running: "secondary",
  nothing_ran: "outline",
};

function duration(seconds: number | null, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (seconds == null) return "—";
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return t("maintenance.seconds", { s: seconds });
  return t("time.duration", { h: Math.floor(minutes / 60), m: minutes % 60 });
}

export function RemoteMaintenanceSection({ detail }: { detail: WorkItemDetail }) {
  const vm = useWorkItemMaintenanceViewModel(detail);
  return <RemoteMaintenanceView vm={vm} detail={detail} />;
}

/** Pure render of the ViewModel (exported for tests). */
export function RemoteMaintenanceView({ vm, detail }: { vm: WorkItemMaintenanceViewModel; detail: WorkItemDetail }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  const executions = vm.data?.executions ?? [];
  const tasks = vm.data?.tasks ?? [];
  const reasonId = "maintenance-ask-block";
  return (
    <section className="space-y-3 rounded-md border p-3" aria-labelledby="maintenance-title">
      <h3 id="maintenance-title" className="flex items-center gap-2 text-sm font-semibold">
        <Wrench className="h-4 w-4" aria-hidden="true" /> {t("maintenance.title")}
      </h3>
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
        <Button
          size="sm"
          variant="outline"
          className="shrink-0 sm:w-56 max-md:h-auto max-md:whitespace-normal"
          onClick={vm.openAsk}
          disabled={vm.askBlock !== null}
          aria-describedby={vm.askBlock ? reasonId : undefined}
        >
          {vm.askBlock === "loading" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Bot className="mr-2 h-4 w-4" />}
          {t("maintenance.ask")}
        </Button>
        <span id={reasonId} className="text-xs text-muted-foreground">
          {vm.askBlock && vm.askBlock !== "loading"
            ? t(`maintenance.askBlock.${vm.askBlock}`)
            : t("maintenance.askHelp", { count: vm.clientMachines.length })}
        </span>
      </div>

      {vm.status === "success" && vm.successKind && (
        <p role="status" className="flex items-center gap-2 rounded-md border border-emerald-500/40 bg-emerald-500/10 p-2 text-sm">
          <Check className="h-4 w-4 text-emerald-600" aria-hidden="true" />
          {t(vm.successKind === "settled" ? "maintenance.settledOk" : "maintenance.recordedOk")}
        </p>
      )}
      {vm.loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {vm.loadError && <p className="break-words text-sm text-destructive">{vm.loadError}</p>}

      {!vm.loading && !vm.loadError && tasks.length === 0 && executions.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("maintenance.empty")}</p>
      )}

      {tasks.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("maintenance.tasks")}</p>
          <ul className="space-y-2">
            {tasks.map((task) => (
              <li key={task.demand_id} className="space-y-1 rounded-md border p-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{t("maintenance.task", { number: task.number })}</span>
                  {task.agent_name && <span className="text-muted-foreground">· {task.agent_name}</span>}
                  <Badge variant="outline">
                    {t(`maintenance.dispatch.${task.dispatch_status ?? "queued"}`, { defaultValue: task.dispatch_status ?? "—" })}
                  </Badge>
                </div>
                <p className="break-words text-xs text-muted-foreground">{task.subject}</p>
                {task.recorded ? (
                  <p className="text-xs">
                    {t(`maintenance.recorded.${task.recorded.mode}`, {
                      minutes: task.recorded.minutes,
                      who: task.recorded.by,
                      at: fmt.dateTime(task.recorded.at),
                    })}
                    {task.recorded.confirmed_by_operator && ` ${t("maintenance.confirmedByOperator")}`}
                  </p>
                ) : task.uncertain ? (
                  <div className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 p-2">
                    <p className="flex items-start gap-2 text-xs">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" aria-hidden="true" />
                      {t("maintenance.uncertain", { minutes: task.uncertain.minutes, at: fmt.dateTime(task.uncertain.at) })}
                    </p>
                    <Button size="sm" variant="outline" onClick={() => vm.openSettle(task)} className="max-md:h-auto max-md:whitespace-normal">
                      {t("maintenance.settle")}
                    </Button>
                  </div>
                ) : task.runs_in_progress ? (
                  <p className="text-xs text-muted-foreground">{t("maintenance.runsInProgress")}</p>
                ) : task.proposal ? (
                  <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
                    <Button size="sm" onClick={() => vm.openRecord(task)} className="shrink-0 max-md:h-auto max-md:whitespace-normal">
                      <Clock className="mr-2 h-4 w-4" /> {t("maintenance.review")}
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      {t("maintenance.proposed", { minutes: task.proposal.minutes, count: task.proposal.execution_count })}
                    </span>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground">
                    {t(task.finished ? "maintenance.nothingRan" : "maintenance.notFinished")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {executions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{t("maintenance.runs")}</p>
          <ul className="space-y-2">
            {executions.map((e) => (
              <li key={e.id} className="space-y-1 rounded-md border p-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={VERDICT_VARIANT[e.verdict] ?? "outline"}>{t(`maintenance.verdict.${e.verdict}`)}</Badge>
                  <span className="break-all font-medium">{e.machines.map((m) => m.name).join(", ") || "—"}</span>
                </div>
                <p className="break-words text-xs">{e.what}</p>
                <p className="text-xs text-muted-foreground">
                  {e.agent_name
                    ? t("maintenance.byAgent", { name: e.agent_name, number: e.demand_number ?? "—" })
                    : t("maintenance.byPerson", { name: e.requested_by })}
                  {" · "}
                  {fmt.dateTime(e.started_at)} → {fmt.dateTime(e.finished_at)} · {duration(e.duration_seconds, t)}
                </p>
              </li>
            ))}
          </ul>
          {executions.some((e) => !e.agent_demand_id) && (
            <p className="text-xs text-muted-foreground">{t("maintenance.manualNote")}</p>
          )}
        </div>
      )}

      {vm.asking && (
        <AgentRequestDialog machines={vm.clientMachines} onClose={vm.closeAsk} selectableMachines initialItem={detail} />
      )}
      {vm.draft && <RecordPanel vm={vm} />}
      {vm.settle && <SettlePanel vm={vm} />}
    </section>
  );
}

function ExistingEntries({ vm }: { vm: WorkItemMaintenanceViewModel }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {t("maintenance.existing", { total: fmt.hours(vm.timeEntriesHours) })}
      </p>
      {vm.timeEntries.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("maintenance.existingNone")}</p>
      ) : (
        <ul className="max-h-48 space-y-1 overflow-y-auto text-xs">
          {vm.timeEntries.map((e) => (
            <li key={e.id} className="break-words rounded border p-1.5">
              <span className="font-medium">{fmt.hours(e.billable_hours)}</span>
              {e.start_time && <span className="text-muted-foreground"> · {fmt.dateTime(e.start_time)}</span>}
              {e.recorded_by && <span className="text-muted-foreground"> · {e.recorded_by}</span>}
              <div className="whitespace-pre-wrap">{e.description}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SettlePanel({ vm }: { vm: WorkItemMaintenanceViewModel }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  const st = vm.settle!;
  const busy = vm.status === "submitting";
  return (
    <SidePanel
      onClose={vm.closeSettle}
      busy={busy}
      size="xl"
      titleId="maintenance-settle-title"
      icon={<AlertTriangle className="h-4 w-4" aria-hidden="true" />}
      title={t("maintenance.settleTitle", { number: st.number })}
      description={t("maintenance.settleHelp")}
      closeLabel={t("demands.dialog.cancel")}
      footer={
        <>
          <Button type="button" variant="outline" size="sm" onClick={vm.closeSettle} disabled={busy}>
            {t("demands.dialog.cancel")}
          </Button>
          <Button type="button" size="sm" onClick={vm.confirmSettle} disabled={!vm.canSubmitSettle}>
            {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t("maintenance.confirm")}
          </Button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <div className="space-y-1">
          <p className="font-medium">{t("maintenance.attempt", { minutes: st.attempt.minutes, at: fmt.dateTime(st.attempt.at), who: st.attempt.by })}</p>
          <p className="whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">{st.attempt.note}</p>
        </div>
        <p className={vm.settleLooksRecorded ? "text-xs text-amber-700 dark:text-amber-400" : "text-xs text-muted-foreground"}>
          {t(vm.settleLooksRecorded ? "maintenance.looksRecorded" : "maintenance.notFound")}
        </p>
        <ExistingEntries vm={vm} />
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">{t("maintenance.settleChoice")}</legend>
          {(["recorded", "discard"] as const).map((o) => (
            <label key={o} className="flex cursor-pointer items-start gap-2">
              <input type="radio" name="settle-outcome" className="mt-1" checked={st.outcome === o}
                onChange={() => vm.updateSettle({ outcome: o })} />
              <span>
                <span className="font-medium">{t(`maintenance.outcome.${o}`)}</span>
                <span className="block text-xs text-muted-foreground">{t(`maintenance.outcomeHelp.${o}`)}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <div className="space-y-1">
          <Label htmlFor="ms-reason">{t("maintenance.settleReason")}</Label>
          <Textarea id="ms-reason" rows={3} className="max-md:text-base" value={st.reason}
            onChange={(e) => vm.updateSettle({ reason: e.target.value })} />
        </div>
        {vm.errorMessage && <p role="alert" className="break-words text-sm text-destructive">{vm.errorMessage}</p>}
      </div>
    </SidePanel>
  );
}

function RecordPanel({ vm }: { vm: WorkItemMaintenanceViewModel }) {
  const { t } = useTranslation("clientOps");
  const fmt = useClientOpsText();
  const d = vm.draft!;
  const busy = vm.status === "submitting";
  const confirming = vm.step === "confirming";
  return (
    <SidePanel
      onClose={vm.closeRecord}
      busy={busy}
      size="xl"
      titleId="maintenance-record-title"
      icon={<Clock className="h-4 w-4" aria-hidden="true" />}
      title={t("maintenance.recordTitle", { number: d.number })}
      description={t("maintenance.recordHelp")}
      closeLabel={t("demands.dialog.cancel")}
      footer={
        confirming ? (
          <>
            <Button type="button" variant="outline" size="sm" onClick={vm.back} disabled={busy}>
              <ArrowLeft className="mr-2 h-4 w-4" /> {t("maintenance.back")}
            </Button>
            <Button type="button" size="sm" onClick={vm.confirm} disabled={busy}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t("maintenance.confirm")}
            </Button>
          </>
        ) : (
          <>
            <Button type="button" variant="outline" size="sm" onClick={vm.closeRecord}>
              {t("demands.dialog.cancel")}
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => vm.review("log_time")} disabled={Boolean(vm.draftError)}>
              {t("maintenance.logTime")}
            </Button>
            {vm.canResolve && (
              <Button type="button" size="sm" onClick={() => vm.review("resolve")} disabled={Boolean(vm.draftError)}>
                {t("maintenance.logAndResolve")}
              </Button>
            )}
          </>
        )
      }
    >
      {confirming ? (
        <div className="space-y-3 text-sm">
          <p className="font-medium">{t(`maintenance.confirmText.${d.mode}`, { minutes: d.minutes })}</p>
          <p className="whitespace-pre-wrap break-words rounded-md bg-muted p-3 text-xs">{d.note}</p>
          <p className="text-xs text-muted-foreground">{t("maintenance.clientSees")}</p>
          {d.endTime && <p className="text-xs text-muted-foreground">{t("maintenance.datedAt", { at: fmt.dateTime(d.endTime) })}</p>}
          <p className="text-xs text-muted-foreground">{t("maintenance.noEmail")}</p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="mr-note">{t("maintenance.note")}</Label>
            <Textarea id="mr-note" rows={8} className="max-md:text-base" value={d.note}
              onChange={(e) => vm.updateDraft({ note: e.target.value })} />
            <p className="text-xs text-amber-700 dark:text-amber-400">{t("maintenance.clientSees")}</p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="mr-minutes">{t("maintenance.minutes")}</Label>
              <Input id="mr-minutes" inputMode="numeric" className="max-md:text-base" value={d.minutes}
                onChange={(e) => vm.updateDraft({ minutes: e.target.value })} />
              <p className="text-xs text-muted-foreground">{t("maintenance.minutesHelp", { minutes: d.proposedMinutes })}</p>
            </div>
            <div className="space-y-1">
              <Label htmlFor="mr-service">{t("time.serviceType")}</Label>
              <Select id="mr-service" className="max-md:text-base" value={d.serviceType}
                onChange={(e) => vm.updateDraft({ serviceType: e.target.value as "remoto" | "presencial" })}>
                <option value="remoto">{t("time.remoto")}</option>
                <option value="presencial">{t("time.presencial")}</option>
              </Select>
            </div>
          </div>
          {vm.draftError && <p className="text-xs text-destructive">{t(`maintenance.errors.${vm.draftError}`)}</p>}
          {d.endTime && <p className="text-xs text-muted-foreground">{t("maintenance.datedAt", { at: fmt.dateTime(d.endTime) })}</p>}
          {!vm.canResolve && <p className="text-xs text-muted-foreground">{t("maintenance.resolveClosed")}</p>}
          <ExistingEntries vm={vm} />
        </div>
      )}
      {vm.errorMessage && <p role="alert" className="mt-3 break-words text-sm text-destructive">{vm.errorMessage}</p>}
    </SidePanel>
  );
}
