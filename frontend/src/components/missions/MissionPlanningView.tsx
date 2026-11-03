import { useState } from "react";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { PlanningView } from "@/hooks/useMissions";
import type { MissionExecutionsViewModel } from "@/hooks/useMissionExecutionsViewModel";
import { cn } from "@/lib/utils";

/** §4.1: the P1-P8 stepper, what the current stage waits for, the
 * consolidation table and the decisions pending for Marcelo. */
export function MissionPlanningView({ planning, vm }: { planning: PlanningView; vm: MissionExecutionsViewModel }) {
  const { t } = useTranslation("missions");
  const currentIndex = Math.max(0, planning.stages.indexOf(planning.current ?? ""));
  const [shown, setShown] = useState(currentIndex);
  return (
    <section data-testid="planning-view" className="space-y-4 rounded-lg border bg-card p-4">
      <h2 className="text-sm font-semibold">{t("planning.title")}</h2>
      <ol className="flex flex-wrap gap-1 max-md:hidden">
        {planning.stages.map((stage, index) => (
          <li key={stage} className={cn("flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs",
            index < currentIndex && "border-emerald-500/40 text-emerald-700 dark:text-emerald-300",
            index === currentIndex && "border-primary bg-primary/10 font-semibold",
            index > currentIndex && "text-muted-foreground")}
            aria-current={index === currentIndex ? "step" : undefined}>
            {index < currentIndex && <Check className="h-3 w-3" />}
            {t(`planning.stages.${stage}`, stage)}
          </li>
        ))}
      </ol>
      <div className="flex items-center justify-between gap-2 md:hidden">
        <Button size="sm" variant="ghost" disabled={shown === 0} onClick={() => setShown(shown - 1)} aria-label={t("planning.prev")}>
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <span className={cn("text-sm", shown === currentIndex && "font-semibold")}>
          {t(`planning.stages.${planning.stages[shown]}`, planning.stages[shown])}
        </span>
        <Button size="sm" variant="ghost" disabled={shown >= planning.stages.length - 1} onClick={() => setShown(shown + 1)} aria-label={t("planning.next")}>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      <div className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("planning.waitingFor")}</h3>
        {planning.status !== "ok" ? <p className="text-xs text-amber-700">{t("board.unavailable")}</p>
          : planning.unmet.length === 0 ? <p className="text-xs text-muted-foreground">{t("planning.nothingMissing")}</p> : (
            <ul className="space-y-0.5 text-xs">
              {planning.unmet.map((u, index) => <li key={`${u.code}-${index}`} className="break-words"><b>{u.code}</b> {u.message}</li>)}
            </ul>
          )}
        {planning.not_evaluated.length > 0 && (
          <p className="text-xs text-muted-foreground">{t("planning.notEvaluated")}: {planning.not_evaluated.map((n) => n.code).join(", ")}</p>
        )}
      </div>

      {planning.layers.length > 0 && (
        <div className="space-y-1">
          <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("planning.layers")}</h3>
          <div className="flex flex-wrap gap-1">
            {planning.layers.map((layer) => (
              <span key={layer.layer} className={cn("rounded border px-1.5 text-xs",
                layer.reviewed ? "border-emerald-500/40" : "border-amber-500/60")}>
                {layer.layer}: {layer.waived ? t("planning.waived") : layer.reviewed ? t("planning.reviewed") : t("planning.missing")}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("planning.consolidation")}</h3>
        {planning.items.length === 0 ? <p className="text-xs text-muted-foreground">{t("planning.noItems")}</p> : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("planning.item")}</TableHead>
                <TableHead>{t("planning.origin")}</TableHead>
                <TableHead>{t("planning.disposition")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {planning.items.map((item) => (
                <TableRow key={item.item_id}>
                  <TableCell className="min-w-[12rem] text-xs">{item.text}</TableCell>
                  <TableCell className="text-xs">{item.origin}</TableCell>
                  <TableCell className="text-xs">{item.decision ?? item.disposition ?? "—"}{item.reason ? ` — ${item.reason}` : ""}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      <div className="space-y-1">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t("planning.pendingDecisions")}</h3>
        {planning.pending_decisions.length === 0 ? <p className="text-xs text-muted-foreground">{t("planning.noDecisions")}</p> : (
          <ul className="space-y-2">
            {planning.pending_decisions.map((item) => (
              <li key={item.item_id} className="flex flex-col gap-2 rounded border p-2 text-xs sm:flex-row sm:items-center sm:justify-between">
                <span className="break-words">{item.text}</span>
                <Button size="sm" variant="outline" disabled={!item.can_decide || vm.status === "submitting"}
                  title={item.blocked_reason ? t("actions.blockedTitle", { reason: item.blocked_reason }) : undefined}
                  className="max-md:h-auto max-md:whitespace-normal"
                  onClick={() => vm.openAction("decide_item", { itemId: item.item_id })}>
                  {t("actions.decide_item")}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
