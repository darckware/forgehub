/** Remote Access › Machines: which agents may maintain machines (2026-10-19).
 * Granting creates a governance delegation for remote_access.execute per
 * agent; without one, every agent request is refused (deny by default).
 * The grant form opens as a right-hand panel (2026-11-11) and only enables
 * agents and machines that can use the access. State:
 * useAuthorizedAgentsViewModel. */
import { useTranslation } from "react-i18next";
import { Bot, Loader2, Plus, Search, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { SidePanel } from "@/components/ui/side-panel";
import { RISK_LEVELS, type RiskLevel } from "@/hooks/useAgentMaintenance";
import { useAuthorizedAgentsViewModel, VALIDITY_DAYS, type GrantMachineHint } from "@/hooks/useAuthorizedAgentsViewModel";
import { STATUS_BADGE, statusKey } from "./machineStatus";

/** The note beside a machine in the grant panel, and its tooltip. */
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

export function AuthorizedAgentsCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useAuthorizedAgentsViewModel();
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short" });
  const busy = vm.status === "submitting";
  // "3 agentes · 12 máquinas · 1 grupo · risco até médio · 1 dia": what will be sent.
  const summary = [
    t("agents.summary.agents", { count: vm.summary.agents }),
    t("agents.summary.machines", { count: vm.summary.machines }),
    vm.summary.groups > 0 ? t("agents.summary.groups", { count: vm.summary.groups }) : null,
    t("agents.summary.risk", { level: t(`agents.summary.riskLevel.${vm.summary.risk}`) }),
    t("agents.days", { count: vm.summary.days }),
  ].filter(Boolean).join(" · ");

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" /> {t("agents.title")}
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">{t("agents.subtitle")}</p>
        </div>
        <Button type="button" size="sm" onClick={vm.openGrant} className="cursor-pointer gap-1.5">
          <Plus className="h-3.5 w-3.5" aria-hidden="true" /> {t("agents.grant")}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {vm.status === "loading" && <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-label={t("maintenance.loading")} />}
        {vm.status !== "loading" && vm.authorized.length === 0 && <p className="text-sm text-muted-foreground">{t("agents.empty")}</p>}
        {vm.authorized.length > 0 && (
          <ul className="divide-y divide-border rounded-md border border-border">
            {vm.authorized.map((entry) => {
              const until = entry.delegations.map((d) => d.expires_at).sort().at(-1)!;
              return (
                <li key={entry.agent.id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                  <Bot className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  <span className="font-medium">{entry.agent.name}</span>
                  <Badge variant={entry.maxRisk === "high" ? "destructive" : entry.maxRisk === "medium" ? "warning" : "secondary"}>
                    {t(`agents.risks.${entry.maxRisk}`, { defaultValue: entry.maxRisk })}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{t("agents.until", { date: fmt.format(new Date(until)) })}</span>
                  <Button type="button" size="sm" variant="ghost" onClick={() => vm.askRevoke(entry)}
                    className="ml-auto cursor-pointer text-destructive hover:text-destructive">
                    {t("agents.revoke")}
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        {vm.error && !vm.revoking && !vm.grantOpen && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
      </CardContent>

      {vm.grantOpen && (
        <SidePanel
          onClose={vm.closeGrant}
          busy={busy}
          titleId="grant-title"
          title={t("agents.grantTitle")}
          description={t("agents.grantHelp")}
          closeLabel={t("cancel")}
          footer={
            <>
              <p className="mr-auto w-full text-xs text-muted-foreground sm:w-auto" aria-live="polite" data-testid="grant-summary">
                {summary}
              </p>
              <Button type="button" variant="outline" size="sm" onClick={vm.closeGrant} disabled={busy} className="cursor-pointer">{t("cancel")}</Button>
              <Button type="button" size="sm" onClick={() => void vm.grant()} disabled={!vm.canGrant} className="cursor-pointer gap-1.5">
                {busy && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                {t("agents.grantConfirm", { count: vm.summary.agents })}
              </Button>
            </>
          }
        >
          {vm.pruned && (
            <p role="status" className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs">
              {t("agents.pruned", { agents: vm.pruned.agents, machines: vm.pruned.machines })}
            </p>
          )}
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">{t("agents.pickAgents")}</legend>
            {vm.agentRows.length === 0 && <p className="text-xs text-muted-foreground">{t("agents.noneToGrant")}</p>}
            {vm.agentRows.length > 0 && vm.eligibilityPending && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden="true" /> {t("agents.eligibilityPending")}
              </p>
            )}
            <ul className="space-y-1">
              {vm.agentRows.map(({ agent, unsupportedReason, selectable }) => {
                const reasonId = `grant-agent-reason-${agent.id}`;
                return (
                  <li key={agent.id} className={selectable ? undefined : "opacity-60"}>
                    <label className={`flex items-center gap-2 text-sm ${selectable ? "cursor-pointer" : "cursor-not-allowed"}`}>
                      <input type="checkbox" checked={vm.chosen.has(agent.id)} disabled={!selectable} onChange={() => vm.toggleAgent(agent.id)}
                        aria-describedby={selectable ? undefined : reasonId} />
                      {agent.name}
                    </label>
                    {!selectable && (
                      <p id={reasonId} className="pl-6 text-xs text-muted-foreground">
                        {t(`direct.unsupported.${unsupportedReason}`, { defaultValue: t("agents.ineligibleUnknown") })}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
          </fieldset>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">{t("agents.pickMachines")}</legend>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input type="search" value={vm.machineQuery} onChange={(e) => vm.setMachineQuery(e.target.value)}
                placeholder={t("agents.searchMachines")} aria-label={t("agents.searchMachines")} className="pl-8 max-md:text-base" />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              {vm.readinessPending ? (
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <Loader2 className="h-3 w-3 motion-safe:animate-spin" aria-hidden="true" /> {t("agents.readinessPending")}
                </span>
              ) : <span />}
              {vm.machines.some((m) => m.selectable) && (
                <button type="button" onClick={vm.toggleAllVisible} className="cursor-pointer text-primary hover:underline">
                  {t(vm.allVisibleSelected ? "agents.clearVisible" : "agents.selectAllVisible")}
                </button>
              )}
            </div>
            {vm.machineCount > 0 && vm.machines.length === 0 && <p className="text-xs text-muted-foreground">{t("agents.noMachinesMatch")}</p>}
            <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-md border border-border empty:hidden">
              {vm.machines.map((m) => {
                const hintId = `grant-machine-hint-${m.id}`;
                const status = m.readiness?.status ?? "unknown";
                return (
                  <li key={m.id} className={`flex flex-wrap items-center gap-x-2 gap-y-1 px-3 py-1.5 ${m.selectable ? "" : "opacity-60"}`}>
                    <label className={`flex min-w-0 items-center gap-2 text-sm ${m.selectable ? "cursor-pointer" : "cursor-not-allowed"}`}>
                      <input type="checkbox" checked={vm.selectedMachines.has(m.id)} disabled={!m.selectable} onChange={() => vm.toggleMachine(m.id)}
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
          </fieldset>

          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">{t("agents.pickGroups")}</legend>
            <div className="space-y-1">
              {vm.groups.map((g) => (
                <label key={g.id} className="flex cursor-pointer items-center gap-2 py-1 text-sm">
                  <input type="checkbox" checked={vm.selectedGroups.has(g.id)} onChange={() => vm.toggleGroup(g.id)} />{g.name}
                </label>
              ))}
            </div>
          </fieldset>
          <p className="text-xs text-muted-foreground">{t("agents.scopeRequired")}</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="grant-risk">{t("agents.maxRisk")}</Label>
              <Select id="grant-risk" value={vm.risk} onChange={(e) => vm.setRisk(e.target.value as RiskLevel)} className="max-md:text-base">
                {RISK_LEVELS.map((r) => <option key={r} value={r}>{t(`agents.risks.${r}`)}</option>)}
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="grant-days">{t("agents.validity")}</Label>
              <Select id="grant-days" value={String(vm.days)} onChange={(e) => vm.setDays(Number(e.target.value))} className="max-md:text-base">
                {VALIDITY_DAYS.map((d) => <option key={d} value={d}>{t("agents.days", { count: d })}</option>)}
              </Select>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{t(`agents.riskHelp.${vm.risk}`)}</p>
          {vm.error && <p role="alert" className="text-xs text-destructive">{vm.error}</p>}
        </SidePanel>
      )}

      <ConfirmDialog
        open={vm.revoking !== null}
        title={t("agents.revokeTitle", { name: vm.revoking?.agent.name ?? "" })}
        description={t("agents.revokeText")}
        confirmLabel={t("agents.revoke")}
        loading={vm.revokePending}
        error={vm.revoking ? vm.error ?? undefined : undefined}
        onConfirm={() => void vm.confirmRevoke()}
        onCancel={vm.cancelRevoke}
      />
    </Card>
  );
}
