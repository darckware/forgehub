import { useState } from "react";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { MissionConflict } from "@/hooks/useMissions";
import { cn } from "@/lib/utils";

/** Conflicts between executions (§5). On a phone it collapses to a count
 * chip that expands; an unknown check is its own warning, never "none". */
export function MissionConflictsBanner({ conflicts }: { conflicts: MissionConflict[] }) {
  const { t } = useTranslation("missions");
  const [open, setOpen] = useState(false);
  const blocking = conflicts.filter((c) => c.severity === "blocking");
  const warnings = conflicts.filter((c) => c.severity !== "blocking");
  if (conflicts.length === 0) {
    return <p className="text-xs text-muted-foreground" data-testid="conflicts-none">{t("conflicts.none")}</p>;
  }
  const summary = [
    blocking.length ? t("conflicts.title", { count: blocking.length }) : null,
    warnings.length ? t("conflicts.warnings", { count: warnings.length }) : null,
  ].filter(Boolean).join(" · ");
  return (
    <section
      data-testid="conflicts-banner"
      className={cn("rounded-lg border p-3 text-sm",
        blocking.length ? "border-red-500/40 bg-red-500/5" : "border-amber-500/40 bg-amber-500/5")}
    >
      <button
        type="button"
        className="flex w-full items-center gap-2 text-left font-medium md:pointer-events-none"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <AlertTriangle className={cn("h-4 w-4 shrink-0", blocking.length ? "text-red-600" : "text-amber-600")} />
        <span>{summary}</span>
        <span className="ml-auto md:hidden">{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</span>
      </button>
      <ul className={cn("mt-2 space-y-1", !open && "max-md:hidden")}>
        {conflicts.map((conflict) => (
          <li key={conflict.id} className="flex flex-wrap items-baseline gap-x-2 text-xs">
            <span className={cn("font-semibold", conflict.severity === "blocking" ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300")}>
              {conflict.id} · {t(`conflicts.kinds.${conflict.kind}`, conflict.kind)}
            </span>
            <span>{t("conflicts.tasks", { list: conflict.tasks.map((n) => `#${n}`).join(", ") })}</span>
            {conflict.target && <span className="break-all text-muted-foreground">{conflict.target}</span>}
            <span className="break-all text-muted-foreground">{conflict.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
