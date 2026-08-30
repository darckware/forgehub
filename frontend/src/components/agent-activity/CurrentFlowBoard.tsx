import { Activity, AlertTriangle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ActivityFlowItem, ActivityFlowStage } from "@/hooks/useAgentActivity";
import { cn } from "@/lib/utils";

export const FLOW_STAGE_ORDER: ActivityFlowStage[] = [
  "incoming",
  "planning",
  "queued",
  "executing",
  "verifying",
  "completed",
  "attention",
  "archived",
];

export function CurrentFlowBoard({ items }: { items: ActivityFlowItem[] }) {
  const { t, i18n } = useTranslation("agentActivity");

  return (
    <section aria-labelledby="current-flow-title" className="overflow-hidden rounded-lg border border-border bg-card lg:col-span-2">
      <div className="flex min-h-10 items-center gap-2 border-b border-border px-3 py-2">
        <Activity className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <h2 id="current-flow-title" className="text-xs font-medium">{t("flow.title")}</h2>
        <span className="font-mono text-[9px] text-muted-foreground">{t("flow.subtitle")}</span>
      </div>

      {items.length === 0 ? (
        <p className="px-4 py-8 text-center text-xs text-muted-foreground">{t("flow.empty")}</p>
      ) : (
        <div className="overflow-x-auto p-3">
          <div className="flex min-w-max gap-2">
            {FLOW_STAGE_ORDER.map((stage) => {
              const stageItems = items
                .filter((item) => item.stage === stage)
                .sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at) || left.key.localeCompare(right.key));
              return (
                <section
                  key={stage}
                  role="group"
                  aria-label={t(`flow.stage.${stage}`)}
                  className={cn(
                    "w-60 shrink-0 rounded-md border border-border bg-background/45",
                    stage === "attention" && "border-destructive/35 bg-destructive/5",
                  )}
                >
                  <div className="flex min-h-9 items-center justify-between gap-2 border-b border-border px-2.5">
                    <h3 className="text-[11px] font-medium">{t(`flow.stage.${stage}`)}</h3>
                    <span className="rounded border border-border px-1.5 font-mono text-[9px] text-muted-foreground">{stageItems.length}</span>
                  </div>
                  {stageItems.length === 0 ? (
                    <p className="px-2.5 py-5 text-center text-[10px] text-muted-foreground">{t("flow.stageEmpty")}</p>
                  ) : (
                    <ol className="space-y-2 p-2">
                      {stageItems.map((item) => (
                        <li key={item.key}>
                          <a
                            href={item.canonical_path}
                            aria-label={`${item.title}, ${item.source_status}`}
                            className="block cursor-pointer rounded-md border border-border bg-card px-2.5 py-2 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-muted"
                          >
                            <span className="flex items-start justify-between gap-2">
                              <span className="line-clamp-2 text-[11px] font-medium">{item.title}</span>
                              {stage === "attention" && <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-destructive" aria-hidden="true" />}
                            </span>
                            <span className="mt-1.5 block truncate font-mono text-[9px] text-muted-foreground">
                              {item.source_type} · {item.source_status}
                            </span>
                            <span className="mt-1 block font-mono text-[9px] text-muted-foreground">
                              {new Intl.DateTimeFormat(i18n.language, { hour: "2-digit", minute: "2-digit" }).format(new Date(item.updated_at))}
                            </span>
                          </a>
                        </li>
                      ))}
                    </ol>
                  )}
                </section>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
