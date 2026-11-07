/** Remote Access › Machines: temporary direct access (2026-11-06). A human admin
 * opens it for a listed agent on chosen machines; inside it the agent runs
 * commands through ForgeHub with no approval per command, and never gets the
 * SSH key. The card also edits that list and pauses every agent's access to
 * machines. State: useDirectAccessViewModel + useDirectAgentsViewModel. */
import { useTranslation } from "react-i18next";
import { Bot, Loader2, Pause, Play, Plus, TerminalSquare, Trash2, TriangleAlert, X } from "lucide-react";

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

function remaining(expiresAt: string, now: number): { hours: number; minutes: number } {
  const total = Math.max(1, Math.ceil((new Date(expiresAt).getTime() - now) / 60_000));
  return { hours: Math.floor(total / 60), minutes: total % 60 };
}

export function DirectAccessCard() {
  const { t } = useTranslation("remoteAccess");
  const vm = useDirectAccessViewModel();
  const list = useDirectAgentsViewModel();
  const busy = vm.status === "submitting";
  const controlKnown = list.control !== null;

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <TerminalSquare className="h-4 w-4" aria-hidden="true" /> {t("direct.title")}
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">{t("direct.subtitle")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {list.paused ? (
            <Button type="button" size="sm" onClick={() => void list.resume()} disabled={list.resumePending} className="cursor-pointer gap-1.5">
              {list.resumePending ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Play className="h-3.5 w-3.5" aria-hidden="true" />}
              {t("direct.resume")}
            </Button>
          ) : (
            <Button type="button" size="sm" variant="outline" onClick={list.askPause} disabled={!controlKnown} className="cursor-pointer gap-1.5">
              <Pause className="h-3.5 w-3.5" aria-hidden="true" /> {t("direct.pause")}
            </Button>
          )}
          <Button type="button" size="sm" onClick={vm.openForm} disabled={list.paused || !controlKnown} className="cursor-pointer gap-1.5">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> {t("direct.open")}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div role="status" className={list.paused ? "rounded-md border border-amber-500/50 px-3 py-2 text-sm" : "text-xs text-muted-foreground"}>
          {list.paused && (
            <p className="flex items-start gap-2 font-medium">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="min-w-0 break-words">
                {t("direct.pausedState", {
                  who: list.control?.paused_by ?? "?",
                  when: list.control?.paused_at ? new Date(list.control.paused_at).toLocaleString() : "?",
                })}
              </span>
            </p>
          )}
          {list.paused && list.control?.reason && <p className="mt-1 break-words text-xs">{list.control.reason}</p>}
          <p className={list.paused ? "mt-1 text-xs text-muted-foreground" : undefined}>{t("direct.pauseScope")}</p>
        </div>
        {vm.status === "loading" && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-label={t("maintenance.loading")} />}
        {vm.status !== "loading" && vm.active.length === 0 && <p className="text-sm text-muted-foreground">{t("direct.empty")}</p>}
        {vm.active.length > 0 && (
          <ul className="divide-y divide-border rounded-md border border-border">
            {vm.active.map((access) => (
              <li key={access.id} className="space-y-1 px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <Bot className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  <span className="font-medium">{access.agent_name}</span>
                  <Badge variant="secondary">{t(`direct.purposes.${access.purpose}`)}</Badge>
                  {access.allow_elevation && <Badge variant="warning">{t("direct.elevationBadge")}</Badge>}
                  <span className="text-xs text-muted-foreground">{t("direct.remaining", remaining(access.expires_at, vm.now))}</span>
                  <Button type="button" size="sm" variant="ghost" onClick={() => vm.askClose(access)}
                    className="ml-auto cursor-pointer text-destructive hover:text-destructive">
                    {t("direct.close")}
                  </Button>
                </div>
                <p className="break-words text-xs text-muted-foreground">{access.machines.map((m) => m.name).join(", ")}</p>
                {access.reason && <p className="break-words text-xs">{access.reason}</p>}
              </li>
            ))}
          </ul>
        )}
        {vm.stillRunning !== null && (
          <p role="status" className="text-xs text-muted-foreground">
            {vm.stillRunning > 0 ? t("direct.closedRunning", { count: vm.stillRunning }) : t("direct.closedIdle")}
          </p>
        )}
        {vm.error && !vm.closing && !vm.formOpen && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}

        <section aria-labelledby="direct-agents-title" className="space-y-2 border-t border-border pt-3">
          <h3 id="direct-agents-title" className="text-sm font-medium">{t("direct.agentsTitle")}</h3>
          {list.status === "loading" && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-label={t("maintenance.loading")} />}
          {list.status !== "loading" && list.listed.length === 0 && <p className="text-sm text-muted-foreground">{t("direct.agentsEmpty")}</p>}
          {list.listed.length > 0 && (
            <ul className="divide-y divide-border rounded-md border border-border">
              {list.listed.map((agent) => (
                <li key={agent.id} className="flex flex-wrap items-center gap-2 px-3 py-1.5 text-sm">
                  <Bot className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  <span className="min-w-0 break-words font-medium">{agent.name}</span>
                  {agent.runtime_type && <Badge variant="secondary">{agent.runtime_type}</Badge>}
                  {agent.unsupported_reason && <Badge variant="warning">{t(`direct.unsupported.${agent.unsupported_reason}`)}</Badge>}
                  <Button type="button" size="sm" variant="ghost" onClick={() => list.askRemove(agent)}
                    aria-label={t("direct.removeAgent", { name: agent.name })}
                    className="ml-auto cursor-pointer text-destructive hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Select aria-label={t("direct.addAgentLabel")} value={list.candidateId} onChange={(e) => list.setCandidateId(e.target.value)}
              className="sm:max-w-xs max-md:text-base">
              <option value="">{t("direct.pickAgentToAdd")}</option>
              {list.addable.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
            <Button type="button" size="sm" variant="outline" onClick={() => void list.add()}
              disabled={!list.candidateId || list.addPending} className="cursor-pointer gap-1.5">
              {list.addPending ? <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              {t("direct.addAgent")}
            </Button>
          </div>
          {list.unsupported.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">{t("direct.unsupportedTitle")}</p>
              <ul className="space-y-0.5 text-xs text-muted-foreground">
                {list.unsupported.map((agent) => (
                  <li key={agent.id} className="break-words">
                    <span className="font-medium">{agent.name}</span>: {t(`direct.unsupported.${agent.unsupported_reason}`)}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {list.removed && (
            <p role="status" className="text-xs text-muted-foreground">
              {t("direct.agentRemoved", { count: list.removed.closed_accesses })}
              {list.removed.running_commands > 0 && ` ${t("direct.closedRunning", { count: list.removed.running_commands })}`}
            </p>
          )}
          {list.error && !list.removing && !list.confirmingPause && <p role="alert" className="text-xs text-destructive">{list.error}</p>}
        </section>
      </CardContent>

      {vm.formOpen && (
        <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-labelledby="direct-title">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={busy ? undefined : vm.closeForm} />
          <div className="relative z-10 my-auto w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <h2 id="direct-title" className="text-base font-semibold">{t("direct.formTitle")}</h2>
              <button type="button" onClick={vm.closeForm} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="space-y-4 px-6 py-4">
              <div className="space-y-1">
                <Label htmlFor="direct-agent">{t("direct.agent")}</Label>
                <Select id="direct-agent" value={vm.agentId} onChange={(e) => vm.setAgentId(e.target.value)} className="max-md:text-base">
                  <option value="">{t("direct.pickAgent")}</option>
                  {vm.eligible.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </Select>
                <p className="text-xs text-muted-foreground">{t("direct.eligibleHelp")}</p>
              </div>
              {[{ label: t("agents.pickMachines"), rows: vm.machines, chosen: vm.selectedMachines, toggle: vm.toggleMachine },
                { label: t("agents.pickGroups"), rows: vm.groups, chosen: vm.selectedGroups, toggle: vm.toggleGroup }].map((section) => (
                <fieldset key={section.label} className="space-y-1">
                  <legend className="text-sm font-medium">{section.label}</legend>
                  <div className="max-h-40 space-y-1 overflow-y-auto">
                    {section.rows.map((row) => (
                      <label key={row.id} className="flex cursor-pointer items-center gap-2 py-1 text-sm">
                        <input type="checkbox" checked={section.chosen.has(row.id)} onChange={() => section.toggle(row.id)} />
                        <span className="min-w-0 break-words">{row.name}</span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              ))}
              <div className="space-y-1">
                <Label htmlFor="direct-reason">{t("direct.reason")}</Label>
                <Textarea id="direct-reason" rows={2} value={vm.reason} onChange={(e) => vm.setReason(e.target.value)} className="max-md:text-base" />
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="direct-purpose">{t("direct.purpose")}</Label>
                  <Select id="direct-purpose" value={vm.purpose} onChange={(e) => vm.setPurpose(e.target.value as DirectPurpose)} className="max-md:text-base">
                    {DIRECT_PURPOSES.map((p) => <option key={p} value={p}>{t(`direct.purposes.${p}`)}</option>)}
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="direct-hours">{t("direct.duration")}</Label>
                  <Select id="direct-hours" value={String(vm.hours)} onChange={(e) => vm.setHours(Number(e.target.value) as DirectDuration)} className="max-md:text-base">
                    {DIRECT_DURATIONS.map((h) => <option key={h} value={h}>{t("direct.hours", { count: h })}</option>)}
                  </Select>
                </div>
              </div>
              <label className="flex cursor-pointer items-start gap-2 text-sm">
                <input type="checkbox" className="mt-0.5" checked={vm.allowElevation} onChange={(e) => vm.setAllowElevation(e.target.checked)} />
                <span>{t("direct.allowElevation")}</span>
              </label>
              <p className="text-xs text-muted-foreground">{t("direct.warning")}</p>
              {vm.sensitive && (
                <p role="alert" className="flex items-start gap-2 rounded-md border border-amber-500/50 px-3 py-2 text-sm">
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span className="min-w-0 break-words">{t("direct.sensitive", { machines: vm.sensitive.join(", ") })}</span>
                </p>
              )}
              {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
              <Button type="button" variant="outline" size="sm" onClick={vm.closeForm} disabled={busy} className="cursor-pointer">{t("cancel")}</Button>
              <Button type="button" size="sm" onClick={() => void vm.submit()} disabled={!vm.canSubmit} className="cursor-pointer gap-1.5">
                {busy && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                {vm.sensitive ? t("direct.confirm") : t("direct.submit")}
              </Button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={vm.closing !== null}
        title={t("direct.closeTitle", { name: vm.closing?.agent_name ?? "" })}
        description={t("direct.closeText")}
        confirmLabel={t("direct.close")}
        loading={vm.closePending}
        error={vm.closing ? vm.error ?? undefined : undefined}
        onConfirm={() => void vm.confirmClose()}
        onCancel={vm.cancelClose}
      />

      <ConfirmDialog
        open={list.removing !== null}
        title={t("direct.removeTitle", { name: list.removing?.name ?? "" })}
        description={t("direct.removeText")}
        confirmLabel={t("direct.removeConfirm")}
        loading={list.removePending}
        error={list.removing ? list.error ?? undefined : undefined}
        onConfirm={() => void list.confirmRemove()}
        onCancel={list.cancelRemove}
      />

      <ConfirmDialog
        open={list.confirmingPause}
        title={t("direct.pauseTitle")}
        description={t("direct.pauseText")}
        confirmLabel={t("direct.pause")}
        variant="default"
        icon="warning"
        loading={list.pausePending}
        error={list.confirmingPause ? list.error ?? undefined : undefined}
        onConfirm={() => void list.confirmPause()}
        onCancel={list.cancelPause}
      >
        <div className="space-y-1">
          <Label htmlFor="direct-pause-reason">{t("direct.pauseReason")}</Label>
          <Textarea id="direct-pause-reason" rows={2} value={list.pauseReason} onChange={(e) => list.setPauseReason(e.target.value)} className="max-md:text-base" />
        </div>
      </ConfirmDialog>
    </Card>
  );
}
