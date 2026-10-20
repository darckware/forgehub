import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { Demand } from "@/hooks/useDemands";
import { Button } from "@/components/ui/button";

export function DemandContextPanel({ demand, demands, projectName, onOpen }: {
  demand: Demand; demands: Demand[]; projectName?: string; onOpen: (item: Demand) => void;
}) {
  const { t } = useTranslation("demands");
  const sources = demands.filter(item => item.consolidated_into_id === demand.id);
  const summary = demands.find(item => item.id === demand.consolidated_into_id);
  if (!demand.context_area && !projectName && !demand.requires_approval && !sources.length && !summary) return null;
  return <div className="mt-3 space-y-2 rounded-md border bg-muted/30 p-3 text-sm">
    {(projectName || demand.context_area) && <p className="font-medium">{projectName ?? demand.context_area}</p>}
    {demand.requires_approval && <p>{t(`workflow.${demand.approval_status ?? "pending"}`)}{" "}
      <Link className="text-primary underline" to={`/personal?tab=agent-work&workSearch=${encodeURIComponent(`#${demand.number}`)}`}>{t("workflow.deliberate")}</Link>
    </p>}
    {summary && <Button variant="outline" size="sm" onClick={() => onOpen(summary)}>{t("workflow.openSummary", { number: summary.number })}</Button>}
    {sources.length > 0 && <details><summary className="cursor-pointer">{t("workflow.sourceCount", { count: sources.length })}</summary>
      <ul className="mt-2 space-y-1">{sources.map(item => <li key={item.id}><button type="button" className="text-left text-primary underline focus-visible:outline" onClick={() => onOpen(item)}>#{item.number} · {item.subject}</button>
        {item.dispatch_error?.includes("uncertain") && <span className="ml-2 text-muted-foreground">{t("workflow.uncertain")}</span>}</li>)}</ul>
    </details>}
  </div>;
}
