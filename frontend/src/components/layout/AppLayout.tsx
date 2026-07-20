import { Outlet, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Sidebar } from "@/components/layout/Sidebar";
import { useSessionKeepAlive, useSyncUiLanguage } from "@/hooks/useAuth";
import { AssistantDrawer } from "@/components/chat/AssistantDrawer";

export function AppLayout() {
  // Keeps an actively-used session's JWT sliding forward so it never
  // expires out from under the user mid-work -- see useSessionKeepAlive's
  // own docstring for why this is needed at all.
  useSessionKeepAlive();
  // Applies the logged-in user's saved UI language on load/login -- see
  // useSyncUiLanguage's own docstring.
  useSyncUiLanguage();

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
    pathname.startsWith("/obsidian") ||
    pathname.startsWith("/foundation") ||
    pathname.startsWith("/demands");

  return (
    <div className="flex min-h-screen w-full bg-background">
      <Sidebar />
      {/* h-screen (not min-h-screen like the outer row): both <main>'s
          overflow-y-auto and AssistantDrawer's h-full need a definite
          ancestor height to actually contain their own scrolling instead
          of growing the page. */}
      <div className="flex h-screen min-w-0 flex-1">
        <main
          className={cn(
            "min-w-0 flex-1 overflow-hidden",
            // Extra top clearance below md: the sidebar's mobile hamburger
            // trigger is `fixed top-3 left-3` and would otherwise sit on
            // top of page titles/toolbars that start right at the p-8
            // corner.
            isFullBleed ? "flex flex-col pt-14 md:pt-0" : "overflow-y-auto p-4 pt-16 md:p-8"
          )}
        >
          <Outlet />
        </main>
        {/* Not a global floating trigger anymore -- each page that wants
            the assistant renders its own toggle button (icon + "Assistant"
            label) inline in its toolbar, next to its other buttons, and
            calls useAssistantStore's setOpen itself (see pages/docs,
            pages/demands). This div still needs to be here so opening the
            drawer shrinks <main> instead of covering it. */}
        <AssistantDrawer />
      </div>
    </div>
  );
}
