import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Demand } from "@/hooks/useDemands";
import { Badge } from "@/components/ui/badge";
import { operatorDestination, operatorDestinationLabel, visibleMessageLabels } from "@/lib/messageLabels";

export function MessageOperatorLink({ demand }: { demand: Demand }) {
  const { t } = useTranslation("demands");
  const destination = operatorDestination(demand);
  const label = operatorDestinationLabel(demand);
  return destination ? <Link className="block w-fit max-w-full break-words text-xs text-primary underline hover:text-primary/80 focus-visible:outline focus-visible:outline-2" to={destination}>
    {label ? t(`messageLabels.destinations.${label}`) : null}
  </Link> : null;
}

export function MessageLabels({ demand, detail = false, executorName }: { demand: Demand; detail?: boolean; executorName?: string }) {
  const { t, i18n } = useTranslation("demands");
  const quotaWait = demand.dispatch_status === "waiting_quota" || demand.execution_wait_reason === "quota";
  const labels = visibleMessageLabels(quotaWait ? [...(demand.message_labels ?? []), "quota_unavailable"] : demand.message_labels);
  if (!labels.length && !detail) return null;
  const reset = demand.quota_reset_at ?? demand.execution_wait_until;
  const until = reset ? new Date(reset) : null;
  const date = until && Number.isFinite(until.getTime()) ? new Intl.DateTimeFormat(i18n.language, { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(until) : null;
  return <div className="min-w-0 space-y-1.5">
    {labels.length > 0 && <div className="flex flex-wrap gap-1" data-message-labels="true">
      {labels.map(label => <Badge key={label} className="max-w-full whitespace-normal break-words text-left text-[10px]" variant={["authorization_pending", "decision_pending", "uncertain_execution", "needs_correction"].includes(label) ? "warning" : "outline"}>{t(`messageLabels.items.${label}.label`)}</Badge>)}
    </div>}
    {quotaWait && executorName && <p className="break-words text-xs text-muted-foreground">{t("messageLabels.quotaExecutor", { agent: executorName })}</p>}
    {quotaWait && <p className="break-words text-xs text-muted-foreground">{date ? t("messageLabels.quotaReset", { date }) : t("messageLabels.quotaResetUnknown")}</p>}
    {detail && <>
      {demand.classification_summary && <p className="break-words text-sm text-muted-foreground">{demand.classification_summary}</p>}
      {!quotaWait && until && Number.isFinite(until.getTime()) && <p className="text-xs text-muted-foreground">{t("messageLabels.waitUntil", { date: new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(until) })}</p>}
      <MessageOperatorLink demand={demand} />
    </>}
  </div>;
}
