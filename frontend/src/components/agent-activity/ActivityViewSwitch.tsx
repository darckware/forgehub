import { History, Rows3 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export type ActivityOperationalView = "flow" | "history";
export const ACTIVITY_VIEW_STORAGE_KEY = "forgehub:agent-activity:view:v1";

export function readActivityView(): ActivityOperationalView {
  const saved = window.localStorage.getItem(ACTIVITY_VIEW_STORAGE_KEY);
  return saved === "history" ? "history" : "flow";
}

export function ActivityViewSwitch({
  value,
  onChange,
}: {
  value: ActivityOperationalView;
  onChange: (value: ActivityOperationalView) => void;
}) {
  const { t } = useTranslation("agentActivity");
  const options = [
    { value: "flow" as const, icon: Rows3 },
    { value: "history" as const, icon: History },
  ];

  const select = (next: ActivityOperationalView) => {
    window.localStorage.setItem(ACTIVITY_VIEW_STORAGE_KEY, next);
    onChange(next);
  };

  return (
    <div role="tablist" aria-label={t("views.label")} className="inline-flex rounded-md border border-border bg-card p-0.5">
      {options.map((option) => {
        const Icon = option.icon;
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => select(option.value)}
            className={cn(
              "inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded px-3 text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:bg-muted",
              selected && "bg-muted text-foreground shadow-sm",
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            {t(`views.${option.value}`)}
          </button>
        );
      })}
    </div>
  );
}
