import * as React from "react";
import { cn } from "@/lib/utils";

interface TabsContextValue {
  value: string;
  setValue: (value: string) => void;
}

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabsContext(component: string) {
  const ctx = React.useContext(TabsContext);
  if (!ctx) throw new Error(`${component} must be used within <Tabs>`);
  return ctx;
}

interface TabsProps {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
}

function Tabs({ value, onValueChange, children, className }: TabsProps) {
  return (
    <TabsContext.Provider value={{ value, setValue: onValueChange }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

function TabsList({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      role="tablist"
      // max-md: a phone scrolls the tab row sideways instead of wrapping
      // each label onto 3-4 lines (docs/architecture/MOBILE_RESPONSIVE_PLAN.md, P4).
      // max-md:inline-flex also overrides callers' `grid grid-cols-N`, whose
      // minmax(0,1fr) columns can't grow and made the labels overlap.
      className={cn("inline-flex items-center gap-1 rounded-md bg-muted p-1 max-md:max-w-full max-md:overflow-x-auto", className, "max-md:inline-flex")}
    >
      {children}
    </div>
  );
}

function TabsTrigger({
  value,
  children,
  className,
  title,
}: {
  value: string;
  children: React.ReactNode;
  className?: string;
  /** Tooltip -- lets an icon-only trigger (no visible label) still expose
   * its name on hover/to assistive tech. */
  title?: string;
}) {
  const ctx = useTabsContext("TabsTrigger");
  const isActive = ctx.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={isActive}
      aria-label={title}
      title={title}
      onClick={() => ctx.setValue(value)}
      className={cn(
        "rounded-sm px-3 py-1.5 text-sm font-medium transition-colors max-md:shrink-0 max-md:whitespace-nowrap",
        isActive
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {children}
    </button>
  );
}

function TabsContent({
  value,
  children,
  className,
}: {
  value: string;
  children: React.ReactNode;
  className?: string;
}) {
  const ctx = useTabsContext("TabsContent");
  if (ctx.value !== value) return null;
  return (
    <div role="tabpanel" className={className}>
      {children}
    </div>
  );
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
