import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Demand } from "@/hooks/useDemands";
import { Badge } from "@/components/ui/badge";
import { operatorDestination, visibleMessageLabels } from "@/lib/messageLabels";

export function MessageOperatorLink({ demand }: { demand: Demand }) {
  const { t } = useTranslation("demands");
  const destination = operatorDestination(demand);
  return destination ? <Link className="block w-fit max-w-full break-words text-xs text-primary underline hover:text-primary/80 focus-visible:outline focus-visible:outline-2" to={destination}>
    {t(`messageLabels.destinations.${demand.operator_decision === "question" ? "answers" : demand.operator_destination}`)}
  </Link> : null;
}

export function MessageLabels({ demand, detail = false }: { demand: Demand; detail?: boolean }) {
  const { t, i18n } = useTranslation("demands");
  const labels = visibleMessageLabels(demand.message_labels);
  if (!labels.length && !detail) return null;
  const until = demand.execution_wait_until ? new Date(demand.execution_wait_until) : null;
  return <div className="min-w-0 space-y-1.5">
    {labels.length > 0 && <div className="flex flex-wrap gap-1" data-message-labels="true">
      {labels.map(label => <Badge key={label} className="max-w-full whitespace-normal break-words text-left text-[10px]" variant={["authorization_pending", "decision_pending", "uncertain_execution", "needs_correction"].includes(label) ? "warning" : "outline"}>{t(`messageLabels.items.${label}.label`)}</Badge>)}
    </div>}
    {detail && <>
      {demand.classification_summary && <p className="break-words text-sm text-muted-foreground">{demand.classification_summary}</p>}
      {until && Number.isFinite(until.getTime()) && <p className="text-xs text-muted-foreground">{t("messageLabels.waitUntil", { date: new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }).format(until) })}</p>}
      <MessageOperatorLink demand={demand} />
    </>}
  </div>;
}
