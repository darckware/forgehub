/** Remote Access › Machines: which agents may maintain machines (2026-10-19).
 * Granting creates a governance delegation for remote_access.execute per
 * agent; without one, every agent request is refused (deny by default).
 * State: useAuthorizedAgentsViewModel. */
import { useTranslation } from "react-i18next";
import { Bot, Loader2, Plus, ShieldCheck, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { RISK_LEVELS, type RiskLevel } from "@/hooks/useAgentMaintenance";
import { useAuthorizedAgentsViewModel, VALIDITY_DAYS } from "@/hooks/useAuthorizedAgentsViewModel";

export function AuthorizedAgentsCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const vm = useAuthorizedAgentsViewModel();
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short" });

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
        <div className="fixed inset-0 z-50 flex justify-center overflow-y-auto p-4" role="dialog" aria-modal="true" aria-labelledby="grant-title">
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={vm.status === "submitting" ? undefined : vm.closeGrant} />
          <div className="relative z-10 my-auto w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <h2 id="grant-title" className="text-base font-semibold">{t("agents.grantTitle")}</h2>
              <button type="button" onClick={vm.closeGrant} aria-label={t("cancel")} className="cursor-pointer text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <div className="space-y-4 px-6 py-4">
              <fieldset className="space-y-1">
                <legend className="text-sm font-medium">{t("agents.pickAgents")}</legend>
                {vm.grantable.length === 0 && <p className="text-xs text-muted-foreground">{t("agents.noneToGrant")}</p>}
                <ul className="max-h-56 space-y-1 overflow-y-auto">
                  {vm.grantable.map((a) => (
                    <li key={a.id}>
                      <label className="flex cursor-pointer items-center gap-2 text-sm">
                        <input type="checkbox" checked={vm.chosen.has(a.id)} onChange={() => vm.toggleAgent(a.id)} />
                        {a.name}
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
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
            </div>
            <div className="flex justify-end gap-2 border-t border-border px-6 py-4">
              <Button type="button" variant="outline" size="sm" onClick={vm.closeGrant} disabled={vm.status === "submitting"} className="cursor-pointer">{t("cancel")}</Button>
              <Button type="button" size="sm" onClick={() => void vm.grant()} disabled={!vm.canGrant} className="cursor-pointer gap-1.5">
                {vm.status === "submitting" && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                {t("agents.grantConfirm", { count: vm.chosen.size })}
              </Button>
            </div>
          </div>
        </div>
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
