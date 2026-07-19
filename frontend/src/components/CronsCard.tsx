import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowUpRight, Clock, Loader2, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { type CronJob, useFoundationCrons } from "@/hooks/useFoundationCrons";
import { usePermission } from "@/hooks/usePermission";

function healthBadge(job: CronJob, t: (key: string) => string) {
  switch (job.health) {
    case "ok":
      return <Badge variant="success">{t("crons.health.working")}</Badge>;
    case "error":
      return <Badge variant="destructive">{t("crons.health.error")}</Badge>;
    case "overdue":
      return <Badge variant="warning">{t("crons.health.notRunning")}</Badge>;
    case "never_ran":
      return <Badge variant="outline">{t("crons.health.neverRan")}</Badge>;
    default:
      return <Badge variant="outline">{t("crons.health.off")}</Badge>;
  }
}

/** Dashboard card: read-only overview of the `hermes cron` jobs -- which
 * are running and which are off. Clicking any row (or the header arrow)
 * goes to the /crons page, where the actual controls live. */
export function CronsCard() {
  const { t } = useTranslation("dashboard");
  const perm = usePermission("crons");
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch, isRefetching } = useFoundationCrons();
  const jobs = data?.jobs;
  const storeErrors = data?.store_errors ?? [];

  if (!perm.can_view) return null;

  // Problems first (error/overdue), then working, then the rest.
  const healthRank: Record<CronJob["health"], number> = {
    error: 0,
    overdue: 1,
    never_ran: 2,
    ok: 3,
    off: 4,
  };
  const sorted = [...(jobs ?? [])].sort(
    (a, b) => healthRank[a.health] - healthRank[b.health] || a.name.localeCompare(b.name)
  );
  const workingCount = sorted.filter((j) => j.health === "ok").length;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-muted-foreground" />
          {t("crons.title")}
          {jobs && (
            <span className="text-xs font-normal text-muted-foreground">
              {t("crons.workingCount", { working: workingCount, total: jobs.length })}
            </span>
          )}
        </CardTitle>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            title={t("crons.refresh")}
            aria-label={t("crons.refreshAria")}
            onClick={() => refetch()}
            disabled={isRefetching}
          >
            {isRefetching ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            title={t("crons.openCrons")}
            aria-label={t("crons.openCronsAria")}
            onClick={() => navigate("/crons")}
          >
            <ArrowUpRight className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="max-h-72 space-y-1 overflow-y-auto">
        {isLoading && (
          <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t("crons.loading")}
          </div>
        )}
        {isError && (
          <p className="px-2 pb-1 text-xs text-destructive">{t("crons.loadError")}</p>
        )}
        {storeErrors.length > 0 && (
          <p className="px-2 pb-1 text-xs text-destructive">
            {t("crons.corruptedStore", { profiles: storeErrors.map((se) => se.profile).join(", ") })}
          </p>
        )}
        {!isLoading && !isError && sorted.length === 0 && (
          <p className="py-4 text-sm text-muted-foreground">{t("crons.empty")}</p>
        )}
        {sorted.map((job) => (
          <button
            key={job.id}
            type="button"
            onClick={() => navigate("/crons")}
            title={job.description ?? job.name}
            className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left hover:bg-accent/50"
          >
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{job.name}</div>
              <div className="truncate text-xs text-muted-foreground">
                {job.profile}
                {job.schedule_display ? ` · ${job.schedule_display}` : ""}
              </div>
            </div>
            <div className="flex shrink-0 items-center">{healthBadge(job, t)}</div>
          </button>
        ))}
      </CardContent>
    </Card>
  );
}
