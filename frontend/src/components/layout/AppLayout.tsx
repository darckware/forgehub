import { Outlet, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Sidebar } from "@/components/layout/Sidebar";

export function AppLayout() {
  // The workspace (chat/terminal) page manages its own full-bleed layout
  // (the terminal card should fill the viewport, not sit inside the
  // standard page padding) -- every other page still gets the normal p-8
  // gutter.
  const pathname = useLocation().pathname;
  // Pages that manage their own full-bleed layout (terminal fills viewport,
  // database/diagram needs height-constrained flex columns, tools scrolls
  // inside its own grid, etc.)
  const isFullBleed =
    pathname.startsWith("/workspace") ||
    pathname.startsWith("/database") ||
    pathname.startsWith("/tools") ||
    pathname.startsWith("/skills") ||
    pathname.startsWith("/notifications") ||
    pathname.startsWith("/auditor") ||
    pathname.startsWith("/docs") ||
    pathname.startsWith("/demands");

  return (
    <div className="flex min-h-screen w-full bg-background">
      <Sidebar />
      <main
        className={cn(
          "flex-1 overflow-hidden",
          // h-screen, not min-h-screen growth: full-bleed pages rely on a
          // definite height so their inner flex-1/min-h-0 panes (tools
          // table, database diagram, terminal) get their own scrollbars
          // instead of growing past the viewport with no way to scroll.
          // Extra top clearance below md: the sidebar's mobile hamburger
          // trigger is `fixed top-3 left-3` and would otherwise sit on top
          // of page titles/toolbars that start right at the p-8 corner.
          isFullBleed ? "flex h-screen flex-col pt-14 md:pt-0" : "overflow-y-auto p-4 pt-16 md:p-8"
        )}
      >
        <Outlet />
      </main>
    </div>
  );
}
