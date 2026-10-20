import { Archive, BookOpen, CalendarClock } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { HindsightStatus } from "@/hooks/useHindsight";

export function HindsightRetentionCard({ retention }: { retention: HindsightStatus["retention"] }) {
  const { t, i18n } = useTranslation("hindsight");
  return (
    <Card>
      <CardContent className="space-y-4 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-md border border-border bg-muted p-2">
              <Archive className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-base font-semibold">{t("retention.title")}</h2>
              <p className="text-sm text-muted-foreground">{t("retention.description")}</p>
            </div>
          </div>
          <Link to="/obsidian" className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-primary hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            <BookOpen className="h-4 w-4" aria-hidden="true" />
            {t("retention.openKnowledgeBase")}
          </Link>
        </div>

        <div className="grid gap-3 text-sm sm:grid-cols-3">
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("retention.reviewStage")}</p>
            <p className="mt-1 font-semibold">{t("retention.afterDays", { days: retention?.review_days ?? 90 })}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t("retention.reviewDetail")}</p>
          </div>
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("retention.compactStage")}</p>
            <p className="mt-1 font-semibold">{t("retention.afterDays", { days: retention?.compact_days ?? 180 })}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t("retention.compactDetail")}</p>
          </div>
          <div className="rounded-md border border-border bg-muted/30 p-3">
            <p className="text-xs font-medium uppercase text-muted-foreground">{t("retention.recoveryStage")}</p>
            <p className="mt-1 font-semibold">{t("retention.forDays", { days: retention?.recovery_days ?? 60 })}</p>
            <p className="mt-1 text-xs text-muted-foreground">{t("retention.recoveryDetail")}</p>
          </div>
        </div>

        {retention ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3 text-xs text-muted-foreground" role="status">
            <span>{t("retention.reviewCount", { count: retention.review_count })}</span>
            <span>{t("retention.eligibleCount", { count: retention.eligible_count })}</span>
            <span>{t("retention.protectedCount", { count: retention.protected_count })}</span>
            <span>{t("retention.compactedCount", { count: retention.compacted_count })}</span>
            <span>{t("retention.discontinuedCount", { count: retention.discontinued_topics_count ?? 0 })}</span>
            {retention.error_count > 0 && <Badge variant="destructive">{t("retention.errorCount", { count: retention.error_count })}</Badge>}
            <span className="ml-auto inline-flex items-center gap-1">
              <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
              {t("retention.checkedAt", { date: new Date(retention.checked_at).toLocaleString(i18n.language) })}
            </span>
          </div>
        ) : (
          <p className="border-t border-border pt-3 text-sm text-muted-foreground" role="status">
            {t("retention.awaitingReport")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
