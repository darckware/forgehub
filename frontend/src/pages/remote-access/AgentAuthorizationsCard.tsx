/** Remote Access › Agents: "Agentes autorizados" (2026-11-11, plan
 * REMOTE_ACCESS_SUPPORT_ADJUSTMENTS_PLAN Fase 2 items 1 and 6). One row per
 * agent with any machine permission -- library scripts and/or free commands
 * -- and one right-hand panel per agent to change both. It replaces the two
 * cards "Agentes autorizados a fazer manutenção" (scripts) and "Acesso
 * direto" (commands); the backend still stores them as two delegations.
 * Pausing every agent's access lives in this card's header. State:
 * useAgentAuthorizationViewModel. */
import { useTranslation } from "react-i18next";
import { Bot, Eye, Loader2, Pause, Play, Plus, Search, Settings2, ShieldCheck, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SidePanel } from "@/components/ui/side-panel";
import { Textarea } from "@/components/ui/textarea";
import { RISK_LEVELS, type RiskLevel } from "@/hooks/useAgentMaintenance";
import {
  useAgentAuthorizationViewModel,
  VALIDITY_DAYS,
  type AgentAuthorizationRow,
  type AgentAuthorizationViewModel,
  type PermissionOutcome,
  type PermissionScope,
  type ScriptGrant,
} from "@/hooks/useAgentAuthorizationViewModel";
import { DIRECT_DURATIONS, DIRECT_PURPOSES, type DirectDuration, type DirectPurpose } from "@/hooks/useDirectAccess";
import type { GrantMachineHint } from "@/hooks/useMachineScope";
import { STATUS_BADGE, statusKey } from "./machineStatus";

type T = (key: string, options?: Record<string, unknown>) => string;

/** The note beside a machine in the panel, and its tooltip. */
const HINT_LABEL: Record<GrantMachineHint, string> = {
  not_prepared: "agents.prepareFirst",
  disabled: "agents.accessDisabled",
  offline: "agents.offlineNow",
  unknown: "agents.statusUnknown",
};
const HINT_HELP: Record<GrantMachineHint, string> = {
  not_prepared: "agents.prepareFirstHelp",
  disabled: "agents.accessDisabledHelp",
  offline: "agents.offlineNowHelp",
  unknown: "agents.statusUnknownHelp",
};

const RISK_BADGE: Record<string, "secondary" | "warning" | "destructive"> = { low: "secondary", medium: "warning", high: "destructive" };

function ineligible(t: T, code: string | null) {
  return code ? t(`direct.unsupported.${code}`, { defaultValue: t("agents.ineligibleUnknown") }) : null;
}

function scopeText(t: T, machines: number, groups: number) {
  return [t("agents.summary.machines", { count: machines }), groups > 0 ? t("agents.summary.groups", { count: groups }) : null]
    .filter(Boolean).join(" · ");
}

/** One script delegation: risk, scope, expiry, and what makes it special. */
function GrantLine({ grant, t, fmtDate }: { grant: ScriptGrant; t: T; fmtDate: (v: string) => string }) {
  return (
    <>
      <Badge variant={RISK_BADGE[grant.risk] ?? "destructive"}>
        {t("authz.riskUpTo", { level: t(`authz.risk.${grant.risk}`, { defaultValue: grant.risk }) })}
      </Badge>
      <span>{scopeText(t, grant.machines.length, grant.groups.length)}</span>
      <span>· {t("agents.until", { date: fmtDate(grant.expiresAt) })}</span>
      {grant.futureFrom && <Badge variant="warning">{t("authz.startsAt", { date: fmtDate(grant.futureFrom) })}</Badge>}
      {grant.projectScoped && <Badge variant="warning">{t("authz.projectScoped")}</Badge>}
    </>
  );
}

function RowPermissions({ row, t, fmtDate, fmtDateTime }: {
  row: AgentAuthorizationRow; t: T; fmtDate: (v: string) => string; fmtDateTime: (v: string) => string;
}) {
  const config = row.commands?.config ?? null;
  return (
    <dl className="grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
      <div className="min-w-0 space-y-1">
        <dt className="font-medium text-foreground">{t("authz.scripts")}</dt>
        {row.scripts ? row.scripts.grants.map((g) => (
          <dd key={g.id} className="flex flex-wrap items-center gap-1.5 text-muted-foreground" data-testid="authz-script-grant">
            <GrantLine grant={g} t={t} fmtDate={fmtDate} />
          </dd>
        )) : <dd className="text-muted-foreground">{t("authz.notAuthorized")}</dd>}
      </div>
      <div className="min-w-0 space-y-1">
        <dt className="font-medium text-foreground">{t("authz.commands")}</dt>
        <dd className="flex flex-wrap items-center gap-1.5 break-words text-muted-foreground">
          {!row.commands ? <span>{t("authz.notAuthorized")}</span> : !config ? (
            <Badge variant="warning">{t("direct.pendingConfiguration")}</Badge>
          ) : (
            <>
              {row.commands.expired && <Badge variant="warning">{t("direct.expired")}</Badge>}
              {!row.commands.expired && row.commands.noScope && <Badge variant="warning">{t("direct.noMachines")}</Badge>}
              <span className="min-w-0 break-words">
                {config.all_machines ? t("direct.allMachines") : config.machines.map((m) => m.name).join(", ") || t("authz.noMachine")}
              </span>
              <span>· {config.open_ended ? t("direct.indefinite") : t("direct.until", { when: config.expires_at ? fmtDateTime(config.expires_at) : "?" })}</span>
              {config.allow_elevation && <Badge variant="warning">{t("direct.elevationBadge")}</Badge>}
              {row.commands.old && <span className="text-amber-600 dark:text-amber-400">{t("direct.oldAccess")}</span>}
              <span className="w-full">{t("direct.since", { when: fmtDateTime(config.opened_at) })}</span>
              {config.purpose && <span className="w-full">{t(`direct.purposes.${config.purpose}`)}</span>}
              {config.reason && <span className="w-full break-words">{config.reason}</span>}
            </>
          )}
        </dd>
      </div>
    </dl>
  );
}

function OutcomeLine({ label, outcome, t }: { label: string; outcome: PermissionOutcome | undefined; t: T }) {
  if (!outcome) return null;
  const text = outcome.state === "saved" ? t("authz.outcome.saved")
    : outcome.state === "cancelled" ? t("authz.outcome.cancelled")
    : outcome.state === "pending_revoke" ? t("authz.outcome.pendingRevoke", { message: outcome.message })
    : t("authz.outcome.failed", { message: outcome.message });
  return (
    <p className={outcome.state === "saved" ? "text-emerald-700 dark:text-emerald-400"
      : outcome.state === "pending_revoke" ? "text-amber-700 dark:text-amber-400" : "text-destructive"}>
      <span className="font-medium">{label}:</span> {text}
    </p>
  );
}

/** What the footer says will be saved, one line per permission. */
function summaryLines(vm: AgentAuthorizationViewModel, t: T): string[] {
  const f = vm.form;
  const scopeOf = (s: PermissionScope) => (s.all ? t("direct.allMachines") : scopeText(t, s.machines.length, s.groups.length));
  const scripts = vm.scriptsChange === "none" ? t("authz.summary.unchanged")
    : vm.scriptsChange === "revoke" ? t("authz.summary.revoke")
    : vm.scriptsChange === "finish_revoke" ? t("authz.summary.finishRevoke")
    : [
        t(vm.scriptsChange === "grant" ? "authz.summary.grant" : "authz.summary.update"),
        t("authz.riskUpTo", { level: t(`authz.risk.${f.risk}`) }),
        scopeOf(vm.scriptsScope),
        f.days === 0 ? t("authz.keepExpiry") : t("agents.days", { count: f.days }),
      ].join(" · ");
  const commands = vm.commandsChange === "none" ? t("authz.summary.unchanged")
    : vm.commandsChange === "remove" ? t("authz.summary.remove")
    : [
        t("authz.summary.save"),
        scopeOf(vm.commandsScope),
        f.hours === 0 ? t("direct.indefinite") : t("direct.hours", { count: f.hours }),
        t(f.elevation ? "authz.withElevation" : "authz.withoutElevation"),
      ].join(" · ");
  return [`${t("authz.scripts")}: ${scripts}`, `${t("authz.commands")}: ${commands}`];
}

function AgentPanel({ vm }: { vm: AgentAuthorizationViewModel }) {
  const { t, i18n } = useTranslation("remoteAccess");
  const busy = vm.status === "submitting";
  const scope = vm.scope;
  const f = vm.form;
  const fmtDate = (v: string) => new Intl.DateTimeFormat(i18n.language, { dateStyle: "short" }).format(new Date(v));
  const scriptsReason = ineligible(t, vm.scriptsReason);
  const commandsReason = ineligible(t, vm.commandsReason);
  const scriptsLocked = Boolean(vm.scriptsReason) && !f.scriptsEnabled;
  const commandsLocked = Boolean(vm.commandsReason) && !f.commandsEnabled;

  return (
    <SidePanel
      onClose={vm.close}
      busy={busy}
      size="2xl"
      titleId="authz-title"
      icon={<ShieldCheck className="h-4 w-4" aria-hidden="true" />}
      title={vm.editing?.isNew ? t("authz.addTitle") : t("authz.editTitle", { name: vm.agent?.name ?? "" })}
      description={t("authz.panelHelp")}
      closeLabel={t("cancel")}
      footer={
        <>
          {vm.agent && (
            <div className="mr-auto w-full space-y-0.5 text-xs text-muted-foreground sm:w-auto" aria-live="polite" data-testid="authz-summary">
              {summaryLines(vm, t).map((line) => <p key={line}>{line}</p>)}
            </div>
          )}
          <Button type="button" variant="outline" size="sm" onClick={vm.close} disabled={busy} className="cursor-pointer">{t("cancel")}</Button>
          <Button type="button" size="sm" onClick={() => void vm.save()} disabled={!vm.canSave} aria-busy={busy} className="cursor-pointer gap-1.5">
            {busy && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
            {t("authz.save")}
          </Button>
        </>
      }
    >
      {vm.editing?.isNew && (
        <div className="space-y-1">
          <Label htmlFor="authz-agent">{t("authz.agent")}</Label>
          {vm.addable.length === 0 && !vm.agent ? (
            <p className="text-xs text-muted-foreground">{t("authz.noneToAdd")}</p>
          ) : (
            <Select id="authz-agent" value={vm.agent?.id ?? ""} onChange={(e) => vm.chooseAgent(e.target.value)} className="max-md:text-base">
              <option value="">{t("authz.pickAgent")}</option>
              {vm.addable.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </Select>
          )}
        </div>
      )}

      {vm.agent && (
        <>
          {vm.outcomes && (vm.outcomes.scripts || vm.outcomes.commands) && (
            <div role="alert" className="space-y-1 rounded-md border border-border px-3 py-2 text-xs">
              <OutcomeLine label={t("authz.scripts")} outcome={vm.outcomes.scripts} t={t} />
              <OutcomeLine label={t("authz.commands")} outcome={vm.outcomes.commands} t={t} />
            </div>
          )}

          <div className="space-y-1 rounded-md border border-border bg-muted/20 p-3">
            <Button type="button" variant={vm.isReadOnly ? "secondary" : "outline"} size="sm" onClick={vm.applyReadOnly}
              aria-pressed={vm.isReadOnly} disabled={busy} className="cursor-pointer gap-1.5 max-md:h-auto max-md:whitespace-normal">
              <Eye className="h-3.5 w-3.5" aria-hidden="true" /> {t("authz.readOnly")}
            </Button>
            <p className="text-xs text-muted-foreground">{t(vm.isHermes ? "authz.readOnlyHermes" : "authz.readOnlyHelp")}</p>
          </div>

          {vm.eligibilityPending && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden="true" /> {t("agents.eligibilityPending")}
            </p>
          )}

          <fieldset className="space-y-2" disabled={busy}>
            <legend className="text-sm font-medium">{t("authz.scope")}</legend>
            <p className="text-xs text-muted-foreground">{t("authz.scopeHelp")}</p>
            {scope.pruned !== null && (
              <p role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
                {t("authz.pruned", { count: scope.pruned })}
              </p>
            )}
            {vm.scopesDiffer && (
              <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">{t("authz.scopesDiffer")}</p>
            )}
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input type="search" value={scope.machineQuery} onChange={(e) => scope.setMachineQuery(e.target.value)}
                placeholder={t("agents.searchMachines")} aria-label={t("agents.searchMachines")} className="pl-8 max-md:text-base" />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              {scope.readinessPending ? (
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden="true" /> {t("agents.readinessPending")}
                </span>
              ) : <span />}
              {scope.machines.some((m) => m.selectable) && (
                <button type="button" onClick={scope.toggleAllVisible} className="cursor-pointer text-primary hover:underline">
                  {t(scope.allVisibleSelected ? "agents.clearVisible" : "agents.selectAllVisible")}
                </button>
              )}
            </div>
            {scope.machineCount > 0 && scope.machines.length === 0 && <p className="text-xs text-muted-foreground">{t("agents.noMachinesMatch")}</p>}
            <ul className="max-h-64 divide-y divide-border overflow-y-auto rounded-md border border-border empty:hidden">
              {scope.machines.map((m) => {
                const hintId = `authz-machine-hint-${m.id}`;
                const status = m.readiness?.status ?? "unknown";
                return (
                  <li key={m.id} className={`flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-1.5 ${m.selectable ? "" : "opacity-60"}`}>
                    <label className={`flex min-w-0 items-center gap-2 text-sm ${m.selectable ? "cursor-pointer" : "cursor-not-allowed"}`}>
                      <input type="checkbox" checked={scope.selectedMachines.has(m.id)} disabled={!m.selectable} onChange={() => scope.toggleMachine(m.id)}
                        aria-describedby={m.hint ? hintId : undefined} />
                      <span className="break-words font-medium">{m.name}</span>
                    </label>
                    {m.detail && <span className="text-xs text-muted-foreground">{m.detail}</span>}
                    <span className="ml-auto flex items-center gap-2">
                      {m.readiness && (
                        <Badge variant="outline" title={m.readiness.detail ?? undefined} className={`whitespace-nowrap ${STATUS_BADGE[status]}`}>
                          {t(`status.${statusKey(m.readiness)}`)}
                        </Badge>
                      )}
                      {m.hint && (
                        <span id={hintId} title={t(HINT_HELP[m.hint])}
                          className={`whitespace-nowrap text-xs ${m.selectable ? "text-muted-foreground" : "text-amber-700 dark:text-amber-400"}`}>
                          {t(HINT_LABEL[m.hint])}
                        </span>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
            {scope.groups.length > 0 && (
              <fieldset className="space-y-1">
                <legend className="text-xs font-medium text-muted-foreground">{t("agents.pickGroups")}</legend>
                {scope.groups.map((g) => (
                  <label key={g.id} className="flex cursor-pointer items-center gap-2 py-1 text-sm">
                    <input type="checkbox" checked={scope.selectedGroups.has(g.id)} onChange={() => scope.toggleGroup(g.id)} />{g.name}
                  </label>
                ))}
              </fieldset>
            )}
            {scope.inventoryError && (
              <div role="alert" className="text-xs text-destructive">
                {t("direct.inventoryError")}
                <Button type="button" variant="ghost" size="sm" onClick={scope.retryInventory}>{t("direct.retry")}</Button>
              </div>
            )}
          </fieldset>

          <fieldset className="space-y-3 rounded-md border border-border p-3" disabled={busy}>
            <legend className="px-1 text-sm font-medium">{t("authz.scripts")}</legend>
            <label className={`flex items-center gap-2 text-sm ${scriptsLocked ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}>
              <input type="checkbox" checked={f.scriptsEnabled} disabled={scriptsLocked}
                onChange={(e) => vm.setScriptsEnabled(e.target.checked)}
                aria-describedby={scriptsReason ? "authz-scripts-reason" : undefined} />
              {t("authz.scriptsToggle")}
            </label>
            {scriptsReason && <p id="authz-scripts-reason" className="text-xs text-muted-foreground">{scriptsReason}</p>}
            {f.scriptsEnabled && (
              <>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor="authz-risk">{t("agents.maxRisk")}</Label>
                    <Select id="authz-risk" value={f.risk} onChange={(e) => vm.setRisk(e.target.value as RiskLevel)} className="max-md:text-base">
                      {RISK_LEVELS.map((r) => <option key={r} value={r}>{t(`authz.risk.${r}`)}</option>)}
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="authz-days">{t("agents.validity")}</Label>
                    <Select id="authz-days" value={String(f.days)} onChange={(e) => vm.setDays(Number(e.target.value))} className="max-md:text-base">
                      {vm.current?.scripts && (
                        <option value="0">{t("authz.keepUntil", { date: fmtDate(vm.current.scripts.until) })}</option>
                      )}
                      {VALIDITY_DAYS.map((d) => <option key={d} value={d}>{t("agents.days", { count: d })}</option>)}
                    </Select>
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">{t(`agents.riskHelp.${f.risk}`)}</p>
                {vm.scriptsNeedScope && <p className="text-xs text-amber-700 dark:text-amber-400">{t("authz.scriptsNeedScope")}</p>}
                {vm.current?.scripts?.irregular && (
                  <div className="space-y-1 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs" data-testid="authz-irregular">
                    <p className="font-medium">{t("authz.irregular", { count: vm.current.scripts.grants.length })}</p>
                    <ul className="space-y-0.5">
                      {vm.current.scripts.grants.map((g) => (
                        <li key={g.id} className="flex flex-wrap items-center gap-1.5"><GrantLine grant={g} t={t} fmtDate={fmtDate} /></li>
                      ))}
                    </ul>
                    {vm.scriptsChange === "replace" && (
                      <label className="flex cursor-pointer items-start gap-2 pt-1">
                        <input type="checkbox" className="mt-0.5" checked={f.consolidateConfirmed} onChange={(e) => vm.setConsolidateConfirmed(e.target.checked)} />
                        <span>{t("authz.consolidate", {
                          count: vm.current.scripts.grants.length,
                          summary: [t("authz.riskUpTo", { level: t(`authz.risk.${f.risk}`) }),
                            scopeText(t, vm.scriptsScope.machines.length, vm.scriptsScope.groups.length),
                            f.days === 0 ? t("agents.until", { date: fmtDate(vm.current.scripts.until) }) : t("agents.days", { count: f.days })].join(" · "),
                        })}</span>
                      </label>
                    )}
                  </div>
                )}
              </>
            )}
          </fieldset>

          <fieldset className="space-y-3 rounded-md border border-border p-3" disabled={busy}>
            <legend className="px-1 text-sm font-medium">{t("authz.commands")}</legend>
            <label className={`flex items-center gap-2 text-sm ${commandsLocked ? "cursor-not-allowed opacity-60" : "cursor-pointer"}`}>
              <input type="checkbox" checked={f.commandsEnabled} disabled={commandsLocked}
                onChange={(e) => vm.setCommandsEnabled(e.target.checked)}
                aria-describedby={commandsReason ? "authz-commands-reason" : undefined} />
              {t("authz.commandsToggle")}
            </label>
            {commandsReason && <p id="authz-commands-reason" className="text-xs text-muted-foreground">{commandsReason}</p>}
            {f.commandsEnabled && (
              <>
                <p className="text-xs text-muted-foreground">{t("direct.warning")}</p>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input type="checkbox" checked={f.commandsAllMachines} onChange={(e) => vm.setCommandsAllMachines(e.target.checked)} />
                  {t("authz.commandsAllMachines")}
                </label>
                {!f.commandsAllMachines && vm.scope.coveredMachineIds.size === 0 && (
                  <p className="text-xs text-muted-foreground">{t("direct.noMachines")}</p>
                )}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor="authz-hours">{t("direct.duration")}</Label>
                    <Select id="authz-hours" value={String(f.hours)} onChange={(e) => vm.setHours(Number(e.target.value) as DirectDuration)} className="max-md:text-base">
                      {DIRECT_DURATIONS.map((h) => <option key={h} value={h}>{h === 0 ? t("direct.indefinite") : t("direct.hours", { count: h })}</option>)}
                    </Select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="authz-purpose">{t("direct.optionalPurpose")}</Label>
                    <Select id="authz-purpose" value={f.purpose} onChange={(e) => vm.setPurpose(e.target.value as DirectPurpose | "")} className="max-md:text-base">
                      <option value="">{t("direct.unspecified")}</option>
                      {DIRECT_PURPOSES.map((p) => <option key={p} value={p}>{t(`direct.purposes.${p}`)}</option>)}
                    </Select>
                  </div>
                </div>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input type="checkbox" checked={f.elevation} onChange={(e) => vm.setElevation(e.target.checked)} />{t("direct.allowElevation")}
                </label>
                <div className="space-y-1">
                  <Label htmlFor="authz-reason">{t("direct.pauseReason")}</Label>
                  <Textarea id="authz-reason" rows={2} maxLength={2000} value={f.reason}
                    onChange={(e) => vm.setReason(e.target.value)} className="resize-none max-md:text-base" />
                </div>
                <p className="text-xs text-muted-foreground">{t("direct.applyNextCommand")}</p>
              </>
            )}
          </fieldset>
        </>
      )}
    </SidePanel>
  );
}

export function AgentAuthorizationsCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useAgentAuthorizationViewModel();
  const pause = vm.pause;
  const fmtDate = (v: string) => new Intl.DateTimeFormat(i18n.language, { dateStyle: "short" }).format(new Date(v));
  const fmtDateTime = (v: string) => new Date(v).toLocaleString(i18n.language);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" /> {t("authz.title")}
          </CardTitle>
          <p className="mt-1 max-w-3xl text-xs text-muted-foreground">{t("authz.subtitle")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" onClick={vm.openAdd} disabled={vm.loadError !== null || vm.status === "loading"} className="cursor-pointer gap-1.5">
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> {t("authz.add")}
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={pause.paused ? () => void pause.resume() : pause.askPause}
            disabled={!pause.control || pause.resumePending} className="cursor-pointer gap-1.5">
            {pause.resumePending ? <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" /> : pause.paused ? <Play className="h-4 w-4" aria-hidden="true" /> : <Pause className="h-4 w-4" aria-hidden="true" />}
            {pause.paused ? t("direct.resume") : t("direct.pause")}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className={pause.paused ? "rounded-md border border-amber-500/50 px-3 py-2 text-sm" : "text-xs text-muted-foreground"}>
          {pause.paused && <p className="break-words font-medium">{t("direct.pausedState", { who: pause.control?.paused_by ?? "?", when: pause.control?.paused_at ? fmtDateTime(pause.control.paused_at) : "?" })}</p>}
          {pause.paused && pause.control?.reason && <p className="mt-1 break-words text-xs">{pause.control.reason}</p>}
          <p className={pause.paused ? "mt-1 text-xs text-muted-foreground" : undefined}>{t("direct.pauseScope")}</p>
        </div>
        {pause.error && !pause.confirmingPause && (
          <div role="alert" className="text-xs text-destructive">
            {pause.error}<Button type="button" variant="ghost" size="sm" onClick={pause.retry}>{t("direct.retry")}</Button>
          </div>
        )}
        {vm.loadError && (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs">
            {t("authz.loadError", { message: vm.loadError })}
          </p>
        )}
        {vm.status === "loading" && (
          <div className="flex min-h-16 items-center justify-center"><Loader2 className="h-5 w-5 motion-safe:animate-spin" aria-label={t("maintenance.loading")} /></div>
        )}
        {vm.status !== "loading" && !vm.loadError && vm.rows.length === 0 && <p className="text-sm text-muted-foreground">{t("authz.empty")}</p>}
        {vm.rows.length > 0 && (
          <ul className="divide-y divide-border rounded-md border border-border">
            {vm.rows.map((row) => {
              const scriptsReason = ineligible(t, row.scriptsReason);
              const commandsReason = ineligible(t, row.commandsReason);
              return (
                <li key={row.id} className="min-w-0 space-y-2 px-3 py-3" data-testid={`authz-row-${row.id}`}>
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Bot className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                    <span className="min-w-0 break-words font-medium">{row.name}</span>
                    {row.runtimeType && <Badge variant="secondary">{row.runtimeType}</Badge>}
                    <div className="ml-auto flex flex-wrap gap-1">
                      <Button type="button" variant="outline" size="sm" onClick={() => vm.openEdit(row.id)} disabled={vm.loadError !== null} className="cursor-pointer gap-1.5">
                        <Settings2 className="h-3.5 w-3.5" aria-hidden="true" /> {t("authz.edit", { name: row.name })}
                      </Button>
                      <Button type="button" variant="ghost" size="sm" onClick={() => vm.askRemove(row)} disabled={vm.loadError !== null}
                        aria-label={t("authz.remove", { name: row.name })} title={t("authz.remove", { name: row.name })}
                        className="cursor-pointer text-destructive hover:text-destructive">
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </div>
                  </div>
                  <RowPermissions row={row} t={t} fmtDate={fmtDate} fmtDateTime={fmtDateTime} />
                  {(scriptsReason || commandsReason) && (
                    <div className="space-y-0.5 text-xs text-muted-foreground">
                      {scriptsReason && <p>{t("authz.scripts")}: {scriptsReason}</p>}
                      {commandsReason && <p>{t("authz.commands")}: {commandsReason}</p>}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {vm.saved && (
          <p role="status" className="text-xs text-muted-foreground">
            {t("authz.saved", { name: vm.saved.name })}
            {vm.saved.direct && ` ${vm.saved.direct.running_commands > 0
              ? t("direct.closedRunning", { count: vm.saved.direct.running_commands })
              : t("direct.closedIdle")}`}
          </p>
        )}
        {vm.removed && (
          <p role="status" className="text-xs text-muted-foreground">
            {t("authz.removed", { name: vm.removed.name })}
            {vm.removed.direct && ` ${vm.removed.direct.running_commands > 0
              ? t("direct.closedRunning", { count: vm.removed.direct.running_commands })
              : t("direct.closedIdle")}`}
          </p>
        )}
      </CardContent>

      {vm.editing && <AgentPanel vm={vm} />}

      <ConfirmDialog open={vm.sensitive !== null} title={t("direct.confirmTitle", { name: vm.agent?.name ?? "" })}
        description={vm.sensitive?.all ? t("direct.allSensitive") : t("direct.selectedSensitive", { machines: vm.sensitive?.machines.join(", ") })}
        confirmLabel={t("direct.confirm")} variant="default" icon="warning" loading={vm.status === "submitting"} dismissDisabled={vm.status === "submitting"}
        onConfirm={() => void vm.confirmSensitive()} onCancel={vm.cancelSensitive} />
      <ConfirmDialog open={vm.confirmingHermesCommands} title={t("authz.hermesCommandsTitle", { name: vm.agent?.name ?? "" })}
        description={t("authz.hermesCommandsText")} confirmLabel={t("authz.hermesCommandsConfirm")} variant="default" icon="warning"
        onConfirm={vm.confirmHermesCommands} onCancel={vm.cancelHermesCommands} />
      <ConfirmDialog open={vm.removing !== null} title={t("authz.removeTitle", { name: vm.removing?.name ?? "" })}
        description={t("authz.removeText")} confirmLabel={t("direct.removeConfirm")} loading={vm.removePending} dismissDisabled={vm.removePending}
        error={vm.removing ? vm.removeError ?? undefined : undefined}
        onConfirm={() => void vm.confirmRemove()} onCancel={vm.cancelRemove} />
      <ConfirmDialog open={pause.confirmingPause} title={t("direct.pauseTitle")} description={t("direct.pauseText")} confirmLabel={t("direct.pause")}
        variant="default" icon="warning" loading={pause.pausePending} dismissDisabled={pause.pausePending} error={pause.confirmingPause ? pause.error : undefined}
        onConfirm={() => void pause.confirmPause()} onCancel={pause.cancelPause}>
        <Label htmlFor="authz-pause-reason">{t("direct.pauseReason")}</Label>
        <Textarea className="resize-none max-md:text-base" id="authz-pause-reason" rows={2} value={pause.pauseReason} onChange={(e) => pause.setPauseReason(e.target.value)} />
      </ConfirmDialog>
    </Card>
  );
}
