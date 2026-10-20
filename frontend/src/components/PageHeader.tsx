import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The title/description/actions row every list page starts with
 * (2026-09-26, docs/architecture/MOBILE_RESPONSIVE_PLAN.md, pattern P1).
 *
 * ~65 pages each hand-rolled this as one `flex justify-between` row. On a
 * phone that row can't fit: the action buttons ran off the right edge, or
 * the description got squeezed into a column a couple of words wide. Here
 * the row only forms from `sm` up; below it the actions drop under the text
 * and wrap, so every button stays reachable.
 *
 * Desktop is meant to look exactly like the hand-rolled headers it replaces:
 * `titleClassName` exists so a page whose title was a different size keeps
 * it when migrated.
 */
export function PageHeader({
  title,
  description,
  icon,
  actions,
  className,
  titleClassName,
  align = "start",
}: {
  title: ReactNode;
  description?: ReactNode;
  /** Rendered before the title, e.g. a lucide icon. */
  icon?: ReactNode;
  /** Buttons/filters on the right (desktop) or below (phone). */
  actions?: ReactNode;
  className?: string;
  titleClassName?: string;
  /** Vertical alignment of text vs actions on the desktop row -- match the
   * header being replaced ("center" for the ones that were `items-center`). */
  align?: "start" | "center";
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:justify-between",
        align === "center" ? "sm:items-center" : "sm:items-start",
        className
      )}
    >
      <div className="min-w-0 space-y-1">
        <h1 className={cn("flex items-center gap-2 text-2xl font-bold tracking-tight md:text-3xl", titleClassName)}>
          {icon}
          <span className="min-w-0">{title}</span>
        </h1>
        {description && <div className="text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">{actions}</div>}
    </div>
  );
}
