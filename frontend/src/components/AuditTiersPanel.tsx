import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Loader2, PlayCircle } from "lucide-react";
import i18n from "@/i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuditTiersViewModel } from "@/hooks/useAuditTiersViewModel";

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString(i18n.resolvedLanguage ?? i18n.language);
}

/** One card per frequency tier: its checks, its Operação 24x7 routine, the
 * last complete scheduled batch and the next occurrence. */
export function AuditTiersPanel() {
  const { t } = useTranslation("auditor");
  const vm = useAuditTiersViewModel();
  if (vm.status !== "ready" || vm.tiers.length === 0) return null;
  return (
    <section aria-label={t("auditor.tiers.title")} className="rounded-md border bg-card p-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("auditor.tiers.title")}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {vm.scheduleSource === "routines" ? t("auditor.tiers.sourceRoutines") : t("auditor.tiers.sourceCron")}
          </p>
        </div>
        <Link className="text-sm text-primary underline-offset-2 hover:underline" to="/operations">
          {t("auditor.tiers.openOperations")}
        </Link>
      </div>
      {vm.runError && <p role="alert" className="mt-2 text-sm text-destructive">{t("auditor.runFailed")}: {vm.runError}</p>}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {vm.tiers.map((tier) => (
          <div key={tier.frequency} className="rounded-md border border-border/70 p-3 text-xs">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold">{t(`auditor.frequency.${tier.frequency}`)}</h3>
                <p className="text-muted-foreground">{t("auditor.tiers.checks", { count: tier.enabled_checks })}</p>
              </div>
              <Badge variant={!tier.routine_id ? "outline" : tier.routine_enabled ? "success" : "warning"}>
                {!tier.routine_id
                  ? t("auditor.tiers.noRoutine")
                  : tier.routine_enabled
                    ? t("auditor.tiers.routineOn")
                    : t("auditor.tiers.routinePaused")}
              </Badge>
            </div>
            <dl className="mt-2 space-y-1 text-muted-foreground">
              <div className="flex flex-wrap justify-between gap-x-2">
                <dt>{t("auditor.tiers.lastComplete")}</dt>
                <dd className={tier.overdue ? "font-medium text-destructive" : undefined}>
                  {formatTimestamp(tier.last_complete_run_at)}
                  {tier.overdue && ` · ${t("auditor.tiers.overdue")}`}
                </dd>
              </div>
              <div className="flex flex-wrap justify-between gap-x-2">
                <dt>{t("auditor.tiers.nextDue")}</dt>
                <dd>{formatTimestamp(tier.next_due_at)}</dd>
              </div>
              {tier.schedule && (
                <div className="flex flex-wrap justify-between gap-x-2">
                  <dt>{t("auditor.schedule")}</dt>
                  <dd><code>{tier.schedule}</code></dd>
                </div>
              )}
            </dl>
            <Button
              size="sm"
              variant="outline"
              className="mt-3 w-full gap-1.5 max-md:h-auto max-md:whitespace-normal"
              aria-label={t("auditor.tiers.runTier", { tier: t(`auditor.frequency.${tier.frequency}`) })}
              disabled={vm.runningTier !== null || tier.enabled_checks === 0}
              onClick={() => vm.runTier(tier.frequency)}
            >
              {vm.runningTier === tier.frequency ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              {t("auditor.tiers.runNow")}
            </Button>
          </div>
        ))}
      </div>
    </section>
  );
}
