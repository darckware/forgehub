# Shared layouts

ForgeHub uses a persistent sidebar shell rather than a separate global top header or footer. The files below are the complete shared shell, navigation, overlay, identity, and breadcrumb implementations.

## `frontend/src/components/layout/AppLayout.tsx`

Application shell that mounts the persistent sidebar, route outlet, responsive page gutters/full-bleed behavior, session synchronization, and assistant drawer.

```tsx
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
```

## `frontend/src/components/layout/Sidebar.tsx`

Persistent desktop sidebar and mobile off-canvas navigation, including grouped links, unread Messages badge, search trigger, account controls, and collapse behavior.

```tsx
import React, { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { motion } from "framer-motion";
import {
  ChevronDown,
  ChevronRight,
  Search,
  PanelLeftClose,
  PanelLeftOpen,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { UserSettingsMenu } from "@/components/layout/UserSettingsMenu";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { NAV_SECTIONS, type NavGroupEntry, type NavLinkEntry } from "@/components/layout/navSections";
import { Logo, LogoMark } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/authStore";
import { usePermission } from "@/hooks/usePermission";
import { computeInboxTotalCount, useDemands } from "@/hooks/useDemands";

const COLLAPSE_STORAGE_KEY = "forgehub-sidebar-collapsed";
const GROUP_COLLAPSE_STORAGE_KEY = "forgehub-sidebar-group-collapsed";

function navLinkClasses(isActive: boolean, collapsed: boolean) {
  return cn(
    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
    collapsed && "justify-center px-2",
    isActive
      ? "bg-accent text-accent-foreground"
      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
  );
}

function PermissionGate({ module, children }: { module?: string; children: React.ReactNode }) {
  const perm = usePermission(module ?? "__always__");
  if (module && !perm.can_view) return null;
  return <>{children}</>;
}

/** Hamburger (≡) morphing into an X -- `open` is the sidebar/menu's own
 * open state, not the icon's: three lines mean "click to open", the X
 * means "click to close" (standard convention). */
function AnimatedMenuIcon({ open }: { open: boolean }) {
  return (
    <div className="relative h-4 w-4">
      <motion.span
        className="absolute inset-x-0 h-0.5 rounded-full bg-current"
        animate={open ? { top: "7px", rotate: 45 } : { top: "3px", rotate: 0 }}
        transition={{ duration: 0.2, ease: "easeInOut" }}
      />
      <motion.span
        className="absolute inset-x-0 top-[7px] h-0.5 rounded-full bg-current"
        animate={open ? { opacity: 0 } : { opacity: 1 }}
        transition={{ duration: 0.15 }}
      />
      <motion.span
        className="absolute inset-x-0 h-0.5 rounded-full bg-current"
        animate={open ? { top: "7px", rotate: -45 } : { top: "11px", rotate: 0 }}
        transition={{ duration: 0.2, ease: "easeInOut" }}
      />
    </div>
  );
}

// Below this width there's no room for a permanently-visible sidebar (icon
// rail or otherwise) -- phones and small tablets get an off-canvas overlay
// instead, same pattern as the workspace chat panels' mobile treatment.
const MOBILE_BREAKPOINT = 768;

export function Sidebar() {
  const { t } = useTranslation("common");
  const location = useLocation();
  const { user } = useAuthStore();
  // Badge on the "Messages" nav link -- same count/query the Messages
  // page's own header badge uses (react-query dedupes the request
  // regardless of which page is mounted, so this doesn't add a second poll
  // while /demands is open), both reading computeInboxTotalCount so this
  // always agrees with the Incoming tree's own root badge (2026-07-28,
  // Marcelo: "os todas tem que obedecer o total do grupo de entrada...
  // tem que haver sync").
  const { data: demandsForBadge } = useDemands();
  const unreadDemandsCount = computeInboxTotalCount(demandsForBadge ?? []);
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1"
  );
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem(GROUP_COLLAPSE_STORAGE_KEY) ?? "{}");
    } catch {
      return {};
    }
  });
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < MOBILE_BREAKPOINT);
  // Mobile's overlay open/closed state is separate from the desktop
  // icon-rail/expanded preference (`collapsed`) -- there's no icon-rail
  // state on mobile, it's either fully hidden or fully shown as an overlay.
  const [mobileOpen, setMobileOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(COLLAPSE_STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  useEffect(() => {
    localStorage.setItem(GROUP_COLLAPSE_STORAGE_KEY, JSON.stringify(collapsedGroups));
  }, [collapsedGroups]);

  useEffect(() => {
    function onResize() {
      setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Tapping a nav link closes the mobile overlay (desktop push-layout is
  // unaffected -- `collapsed` doesn't change on navigation).
  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const effectiveCollapsed = isMobile ? false : collapsed;

  function toggleSidebar() {
    if (isMobile) {
      setMobileOpen((v) => !v);
    } else {
      setCollapsed((c) => !c);
    }
  }

  const toggleGroup = (key: string) =>
    setCollapsedGroups((prev) => ({ ...prev, [key]: !prev[key] }));

  const renderLink = (entry: NavLinkEntry) => {
    // Only "Messages" carries a badge today -- generalize (a `badgeCount`
    // field on NavLinkEntry) if a second nav item ever needs one.
    const badgeCount = entry.to === "/demands" ? unreadDemandsCount : 0;
    const badgeText = badgeCount > 9 ? "9+" : String(badgeCount);
    return (
      <PermissionGate key={entry.to} module={entry.module}>
        <NavLink
          to={entry.to}
          end={entry.to === "/"}
          title={effectiveCollapsed ? t(entry.labelKey) : undefined}
          className={({ isActive }) => navLinkClasses(isActive, effectiveCollapsed)}
        >
          <span className="relative shrink-0">
            <entry.icon className="h-4 w-4" />
            {effectiveCollapsed && badgeCount > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-destructive text-[8px] font-bold text-destructive-foreground">
                {badgeText}
              </span>
            )}
          </span>
          {!effectiveCollapsed && (
            <span className="flex flex-1 items-center justify-between gap-2">
              {t(entry.labelKey)}
              {badgeCount > 0 && (
                <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
                  {badgeText}
                </span>
              )}
            </span>
          )}
        </NavLink>
      </PermissionGate>
    );
  };

  const renderGroup = (entry: NavGroupEntry) => {
    const visibleItems = entry.items; // PermissionGate handles hiding inside
    if (visibleItems.length === 0) return null;

    if (effectiveCollapsed) {
      return visibleItems.map((item) => (
        <PermissionGate key={item.to} module={item.module}>
          <NavLink
            to={item.to}
            title={t(item.labelKey)}
            className={({ isActive }) => navLinkClasses(isActive, effectiveCollapsed)}
          >
            <item.icon className="h-4 w-4 shrink-0" />
          </NavLink>
        </PermissionGate>
      ));
    }

    const GroupIcon = entry.icon;
    const isGroupActive = entry.items.some((item) => location.pathname.startsWith(item.to));
    const isGroupCollapsed = collapsedGroups[entry.labelKey] ?? false;

    return (
      <div key={entry.labelKey}>
        <button
          type="button"
          onClick={() => toggleGroup(entry.labelKey)}
          className={cn(
            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
            isGroupActive
              ? "text-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          )}
        >
          <GroupIcon className="h-4 w-4 shrink-0" />
          <span className="flex-1 text-left">{t(entry.labelKey)}</span>
          {isGroupCollapsed ? (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          )}
        </button>
        {!isGroupCollapsed && (
          <div className="ml-3 space-y-1 border-l border-border pl-2 pt-1">
            {entry.items.map((item) => (
              <PermissionGate key={item.to} module={item.module}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) => navLinkClasses(isActive, false)}
                >
                  <item.icon className="h-4 w-4 shrink-0" />
                  {t(item.labelKey)}
                </NavLink>
              </PermissionGate>
            ))}
          </div>
        )}
      </div>
    );
  };

  const renderEntry = (entry: NavLinkEntry | NavGroupEntry): React.ReactNode => {
    if (entry.type === "link") return renderLink(entry);
    return renderGroup(entry);
  };

  return (
    <>
      {/* Mobile: floating trigger, always visible, opens the overlay. */}
      {isMobile && !mobileOpen && (
        <Button
          variant="outline"
          size="icon"
          className="fixed left-3 top-3 z-40 h-9 w-9 shadow-md"
          aria-label={t("sidebar.openMenu")}
          title={t("sidebar.openMenu")}
          onClick={toggleSidebar}
        >
          <AnimatedMenuIcon open={false} />
        </Button>
      )}

      {/* Backdrop -- mobile overlay only, dismiss on tap outside. */}
      {isMobile && mobileOpen && (
        <div className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm" onClick={() => setMobileOpen(false)} />
      )}

      <aside
        className={cn(
          "flex h-screen flex-col border-r border-border bg-card transition-[width] duration-200",
          isMobile
            ? cn(
                "fixed inset-y-0 left-0 z-40 w-64 transition-transform duration-200",
                mobileOpen ? "translate-x-0" : "-translate-x-full"
              )
            : effectiveCollapsed
            ? "w-16"
            : "w-60"
        )}
      >
        <div
          className={cn(
            "flex h-16 items-center border-b border-border",
            effectiveCollapsed ? "justify-center px-2" : "justify-between px-6"
          )}
        >
          {effectiveCollapsed && !isMobile ? (
            // Icon-rail mode: the logo itself is the expand trigger -- hover
            // (or click) swaps the mark for the expand icon, same affordance
            // as the collapse button in expanded mode below.
            <button
              type="button"
              onClick={toggleSidebar}
              aria-label={t("sidebar.expandSidebar")}
              className="group relative flex h-10 w-10 items-center justify-center rounded-md hover:bg-accent"
            >
              <LogoMark className="h-8 w-8 shrink-0 transition-opacity group-hover:opacity-0" />
              <PanelLeftOpen className="absolute h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100" />
              <span className="pointer-events-none absolute left-full top-1/2 z-20 ml-2 -translate-y-1/2 whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs font-medium text-background opacity-0 shadow-md transition-opacity group-hover:opacity-100">
                {t("sidebar.expandSidebar")}
              </span>
            </button>
          ) : (
            <Logo iconOnly={effectiveCollapsed} />
          )}
          {!effectiveCollapsed && !isMobile && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("sidebar.collapseSidebar")}
              title={t("sidebar.collapseSidebar")}
              onClick={toggleSidebar}
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            title={t("sidebar.searchHint")}
            className={cn(
              "flex w-full items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
              effectiveCollapsed && "justify-center px-2"
            )}
          >
            <Search className="h-4 w-4 shrink-0" />
            {!effectiveCollapsed && (
              <>
                <span className="flex-1 text-left">{t("sidebar.search")}</span>
                <kbd className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px]">
                  {navigator.platform.toLowerCase().includes("mac") ? "⌘K" : "Ctrl K"}
                </kbd>
              </>
            )}
          </button>
          {NAV_SECTIONS.map((section) => {
            // Icon-rail mode ignores section collapse -- there's no label to
            // click there, so items always render as bare icons.
            const isSectionCollapsed = !effectiveCollapsed && (collapsedGroups[section.labelKey] ?? false);
            return (
              <div key={section.labelKey}>
                {!effectiveCollapsed && (
                  <button
                    type="button"
                    onClick={() => toggleGroup(section.labelKey)}
                    className="flex w-full items-center justify-between px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60 hover:text-muted-foreground"
                  >
                    <span>{t(section.labelKey)}</span>
                    {isSectionCollapsed ? (
                      <ChevronRight className="h-3 w-3 shrink-0" />
                    ) : (
                      <ChevronDown className="h-3 w-3 shrink-0" />
                    )}
                  </button>
                )}
                {!isSectionCollapsed && (
                  <div className="space-y-1">
                    {section.entries
                      // hiddenInSidebar routes are reached from inside another
                      // page; they stay in NAV_SECTIONS only so the command
                      // palette can still find them.
                      .filter((entry) => !(entry.type === "link" && entry.hiddenInSidebar))
                      .map((entry, i) => (
                        <React.Fragment key={i}>
                          {renderEntry(entry as NavLinkEntry | NavGroupEntry)}
                        </React.Fragment>
                      ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="space-y-1 border-t border-border p-3">
          {user && !effectiveCollapsed && (
            <div className="flex items-center gap-1 rounded-md px-3 py-2 mb-1">
              <UserSettingsMenu
                collapsed={false}
                stretch={false}
                avatarTrigger
                avatarUrl={user.avatar_data_url}
                usernameInitial={user.username[0]}
              />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{user.username}</p>
                {user.is_admin ? (
                  <p className="flex items-center gap-0.5 text-[10px] text-amber-600">
                    <ShieldCheck className="h-2.5 w-2.5" /> {t("sidebar.admin")}
                  </p>
                ) : null}
              </div>
              <NotificationBell collapsed={false} stretch={false} />
            </div>
          )}
          {/* Icon-rail mode has no user row to embed the gear/bell into --
              keep them as their own standalone buttons there. */}
          {effectiveCollapsed && (
            <>
              <UserSettingsMenu collapsed avatarUrl={user?.avatar_data_url} usernameInitial={user?.username?.[0]} />
              <NotificationBell collapsed />
            </>
          )}
        </div>
      </aside>

      <CommandPalette sections={NAV_SECTIONS} open={paletteOpen} onOpenChange={setPaletteOpen} />
    </>
  );
}
```

## `frontend/src/components/layout/navSections.ts`

Canonical typed navigation map used by both the sidebar and command palette.

```ts
import {
  Activity,
  Bell,
  BookOpen,
  Bot,
  Brain,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  Code2,
  Command,
  Database,
  FolderKanban,
  Gauge,
  Gem,
  GitBranch,
  Landmark,
  Layout,
  LayoutDashboard,
  LayoutList,
  LayoutPanelLeft,
  Lightbulb,
  Boxes,
  Mail,
  Newspaper,
  Plug,
  Server,
  Share2,
  ShieldCheck,
  Sparkles,
  Users,
  Wrench,
  Network,
} from "lucide-react";

export interface NavLinkEntry {
  type: "link";
  to: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string;
  hiddenInSidebar?: boolean;
}

export interface NavGroupEntry {
  type: "group";
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
  items: (Omit<NavLinkEntry, "type"> & { module?: string })[];
}

export interface NavSectionEntry {
  type: "section";
  labelKey: string;
  entries: (NavLinkEntry | NavGroupEntry)[];
}

export const NAV_SECTIONS: NavSectionEntry[] = [
  {
    type: "section",
    labelKey: "nav.section.general",
    entries: [
      { type: "link", to: "/", labelKey: "nav.dashboard", icon: LayoutDashboard },
      { type: "link", to: "/workspace", labelKey: "nav.workspace", icon: LayoutPanelLeft },
      { type: "link", to: "/notifications", labelKey: "nav.notifications", icon: Bell },
      { type: "link", to: "/news", labelKey: "nav.news", icon: Newspaper },
      { type: "link", to: "/demands", labelKey: "nav.inbox", icon: Mail, module: "demands" },
      { type: "link", to: "/docs", labelKey: "nav.docs", icon: BookOpen, module: "docs" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.factory2",
    entries: [
      // Cockpit first -- it's the overview/entry point across every phase
      // below, not a phase itself. The rest follows the pipeline order:
      // 1 Conception, 2 Screens/Business Rules, 2.1 Database Modeling,
      // 3 Projects/Planning/Tasks, 4 Governance, 5 Version Closure.
      { type: "link", to: "/cockpit", labelKey: "nav.cockpit", icon: Gauge, module: "product" },
      { type: "link", to: "/conception", labelKey: "nav.conception", icon: Lightbulb, module: "product" },
      { type: "link", to: "/screen-inspector", labelKey: "nav.screenInspector", icon: Layout, module: "product" },
      { type: "link", to: "/concept-erd", labelKey: "nav.conceptDatabaseDiagram", icon: Share2, module: "database" },
      { type: "link", to: "/projects", labelKey: "nav.projectCenter", icon: FolderKanban, module: "projects" },
      { type: "link", to: "/governance", labelKey: "nav.governance", icon: ShieldCheck, module: "governance" },
      { type: "link", to: "/version-closure", labelKey: "nav.versionClosure", icon: CheckCircle2, module: "product" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.agentsAi",
    entries: [
      { type: "link", to: "/agents", labelKey: "nav.agents", icon: Bot, module: "agents" },
      // Agent Tools is reached from the button in the Agents page header, not
      // from the sidebar (2026-07-26) -- the tools registry is scoped to the
      // agent roster rather than being a peer destination of it, and its page
      // carries a back link to /agents. Still listed here so Cmd/Ctrl+K finds
      // it; only the sidebar hides it.
      {
        type: "link",
        to: "/tools",
        labelKey: "nav.agentTools",
        icon: Wrench,
        module: "agents",
        hiddenInSidebar: true,
      },
      // MCP servers are agent configuration, not a tool registry: the same
      // server is installed per agent, in each runtime's own config file, so
      // the roster-wide view belongs next to Agents rather than under Tools.
      { type: "link", to: "/mcp", labelKey: "nav.mcp", icon: Plug, module: "agents" },
      { type: "link", to: "/prompt-commands", labelKey: "nav.chatCommands", icon: Command, module: "agents" },
      { type: "link", to: "/prompt-techniques", labelKey: "nav.promptTechniques", icon: Sparkles, module: "agents" },
      { type: "link", to: "/skills", labelKey: "nav.skills", icon: Sparkles, module: "agents" },
      { type: "link", to: "/crons", labelKey: "nav.crons", icon: Clock, module: "crons" },
      { type: "link", to: "/systems-hub", labelKey: "nav.systemsHub", icon: Boxes, module: "agents" },
      { type: "link", to: "/foundation", labelKey: "nav.foundation", icon: Landmark, module: "foundation" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.integrations",
    entries: [
      { type: "link", to: "/obsidian", labelKey: "nav.knowledgeBase", icon: Gem, module: "obsidian" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.operations",
    entries: [
      { type: "link", to: "/system-control", labelKey: "nav.systemControl", icon: GitBranch, module: "system_control" },
      // Live board over the same data the Messages page's overview tab
      // aggregates -- gated on the same "demands" module rather than a new
      // one, since it's a different view of identical rows/permissions.
      { type: "link", to: "/agent-activity", labelKey: "nav.agentActivity", icon: Activity, module: "demands" },
      { type: "link", to: "/hindsight", labelKey: "nav.hindsight", icon: Brain, module: "foundation" },
      // Ecosystem checkpoints (audit_checks) -- admins always see it; grant
      // the "auditor" module in Access Profiles for non-admin visibility.
      { type: "link", to: "/auditor", labelKey: "nav.auditor", icon: ClipboardCheck, module: "auditor" },
      { type: "link", to: "/deploy", labelKey: "nav.deployControl", icon: Server, module: "deploy" },
      { type: "link", to: "/servers", labelKey: "nav.servers", icon: Network, module: "servers" },
      {
        type: "group",
        labelKey: "nav.database",
        icon: Database,
        items: [
          { to: "/database/schema", labelKey: "nav.databaseSchema", icon: LayoutList, module: "database" },
          { to: "/database/diagram", labelKey: "nav.databaseDiagram", icon: Share2, module: "database" },
          { to: "/database/query", labelKey: "nav.databaseQuery", icon: Code2, module: "database" },
        ],
      },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.administration",
    entries: [
      { type: "link", to: "/users", labelKey: "nav.users", icon: Users, module: "users" },
      { type: "link", to: "/profiles", labelKey: "nav.accessProfiles", icon: ShieldCheck, module: "profiles" },
    ],
  },
];
```

## `frontend/src/components/layout/NotificationBell.tsx`

Shared notification indicator and popover used in the sidebar footer.

```tsx
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bell } from "lucide-react";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";
import { cn } from "@/lib/utils";
import { useClickOutside } from "@/hooks/useClickOutside";
import {
  useMarkNotificationsRead,
  useNotifications,
  type AppNotification,
} from "@/hooks/useNotifications";
import { Button } from "@/components/ui/button";

export function formatRelativeTime(iso: string): string {
  const t = i18n.getFixedT(null, "common", "notificationBell");
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return t("justNow");
  if (minutes < 60) return t("minutesAgo", { count: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 24) return t("hoursAgo", { count: hours });
  const days = Math.round(hours / 24);
  return t("daysAgo", { count: days });
}

const SEVERITY_DOT: Record<AppNotification["severity"], string> = {
  error: "bg-destructive",
  warning: "bg-amber-500",
  success: "bg-emerald-500",
  info: "bg-sky-500",
};

/** Bell icon + dropdown over the persistent notification record
 * (GET /api/v1/notifications -- one row per cron run, ingested server-side).
 * Read state is stored in the DB (read_at): opening the dropdown marks
 * everything as read. Full history + cleanup live on /notifications. */
export function NotificationBell({
  collapsed,
  stretch = true,
}: {
  collapsed: boolean;
  /** Mirrors UserSettingsMenu's `stretch`: false renders a compact,
   * intrinsic-size icon button meant to sit inline next to it (the
   * expanded user row) instead of the full-width standalone rail row. */
  stretch?: boolean;
}) {
  const { t } = useTranslation("common", { keyPrefix: "notificationBell" });
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);
  const { data } = useNotifications();
  const markRead = useMarkNotificationsRead();

  const notifications = data?.notifications ?? [];
  const unreadCount = data?.unread_count ?? 0;

  function handleToggle() {
    setOpen((v) => {
      const next = !v;
      if (next && unreadCount > 0) markRead.mutate({ all: true });
      return next;
    });
  }

  return (
    <div className={cn("relative", stretch && "w-full")} ref={containerRef}>
      <Button
        variant="ghost"
        size={collapsed || !stretch ? "icon" : "default"}
        className={cn("relative text-muted-foreground", stretch && "w-full", !collapsed && stretch && "justify-start gap-3")}
        aria-label={t("title")}
        title={t("title")}
        onClick={handleToggle}
      >
        <Bell className="h-4 w-4 shrink-0" />
        {!collapsed && stretch && t("title")}
        {unreadCount > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-destructive-foreground">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </Button>
      {open && (
        <div
          className="absolute bottom-0 left-full z-20 ml-1 flex max-h-80 w-72 flex-col rounded-md border border-border bg-card py-1 shadow-md"
        >
          <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
            {t("title")}
          </p>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {notifications.length === 0 && (
              <p className="px-3 py-3 text-xs italic text-muted-foreground">{t("empty")}</p>
            )}
            {notifications.slice(0, 20).map((n) => (
              <div key={n.id} className="border-t border-border px-3 py-2 first:border-t-0">
                <p className="flex items-center gap-1.5 text-xs font-medium">
                  <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", SEVERITY_DOT[n.severity])} />
                  <span className="truncate">{n.title}</span>
                </p>
                <p className="text-[10px] text-muted-foreground">
                  {n.profile ?? n.source} · {formatRelativeTime(n.occurred_at)}
                </p>
                {(n.message ?? n.summary) && (
                  <p className="mt-1 line-clamp-3 whitespace-pre-wrap break-words rounded bg-muted/50 px-1.5 py-1 font-mono text-[10px] text-muted-foreground">
                    {n.message ?? n.summary}
                  </p>
                )}
              </div>
            ))}
          </div>
          <Link
            to="/notifications"
            onClick={() => setOpen(false)}
            className="border-t border-border px-3 py-2 text-center text-xs font-medium text-primary hover:underline"
          >
            {t("viewAll")}
          </Link>
        </div>
      )}
    </div>
  );
}
```

## `frontend/src/components/layout/UserSettingsMenu.tsx`

Shared account/settings dropdown and its account and password dialogs, used from the sidebar.

```tsx
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Camera, Check, KeyRound, Laptop, LogOut, Loader2, Moon, Settings, Settings2, Sun, User as UserIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { useClickOutside } from "@/hooks/useClickOutside";
import { useTheme } from "@/lib/theme";
import type { UiLanguage } from "@/i18n";
import { useAuthStore } from "@/store/authStore";
import { useUpdateMe, useChangeMyPassword, useClearQueryCacheOnLogout } from "@/hooks/useAuth";
import { Button } from "@/components/ui/button";

const THEME_OPTIONS = [
  { value: "light" as const, labelKey: "themeLight", icon: Sun },
  { value: "dark" as const, labelKey: "themeDark", icon: Moon },
  { value: "system" as const, labelKey: "themeSystem", icon: Laptop },
];

const LANGUAGE_OPTIONS: { value: UiLanguage; labelKey: string }[] = [
  { value: "pt-BR", labelKey: "languagePt" },
  { value: "en", labelKey: "languageEn" },
  { value: "es", labelKey: "languageEs" },
];

/** Backdrop + centered panel, same pattern as components/ui/confirm-dialog.tsx. */
function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-2xl">
        <h2 className="mb-4 text-base font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}

function AccountModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("common");
  const user = useAuthStore((s) => s.user);
  const updateMe = useUpdateMe();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [avatarPreview, setAvatarPreview] = useState<string | null>(user?.avatar_data_url ?? null);
  // Staged like fullName/email above -- previously this field applied
  // (i18n.changeLanguage) and persisted (mutate) directly in its onChange,
  // bypassing Cancel entirely (picking a language then hitting Cancel still
  // left you on the new language). Now it only takes effect on Save, same
  // as every other field in this modal.
  const [uiLanguage, setUiLanguage] = useState<UiLanguage>((user?.ui_language as UiLanguage) ?? "pt-BR");
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handlePickPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setAvatarPreview(reader.result as string);
    reader.readAsDataURL(file);
  }

  function handleSave() {
    updateMe.mutate(
      {
        full_name: fullName.trim() || undefined,
        email: email.trim() || undefined,
        avatar_data_url: avatarPreview,
        ui_language: uiLanguage,
      },
      { onSuccess: onClose }
    );
    // No explicit i18n.changeLanguage here -- useUpdateMe's onSuccess writes
    // the fresh user (including ui_language) into authStore, and
    // useSyncUiLanguage (mounted once in AppLayout) reactively applies it
    // app-wide the moment that store value changes.
  }

  return (
    <ModalShell title={t("userMenu.account")} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex justify-center">
          <button
            type="button"
            className="group relative h-16 w-16 shrink-0 overflow-hidden rounded-full bg-accent"
            onClick={() => fileInputRef.current?.click()}
            aria-label={t("userMenu.changeUserPhoto")}
            title={t("userMenu.changePhoto")}
          >
            {avatarPreview ? (
              <img src={avatarPreview} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-lg font-bold uppercase text-accent-foreground">
                {user?.username?.[0]}
              </div>
            )}
            <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 transition-opacity group-hover:opacity-100">
              <Camera className="h-5 w-5 text-white" />
            </div>
          </button>
          <input ref={fileInputRef} type="file" accept="image/*" className="hidden" onChange={handlePickPhoto} />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.username")}</label>
          <p className="text-sm">{user?.username}</p>
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.fullName")}</label>
          <input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.email")}</label>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.language")}</label>
          <select
            value={uiLanguage}
            onChange={(e) => setUiLanguage(e.target.value as UiLanguage)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          >
            {LANGUAGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(`userMenu.${opt.labelKey}`)}
              </option>
            ))}
          </select>
        </div>
        {updateMe.isError && (
          <p className="text-xs text-destructive">{t("userMenu.saveError")}</p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t("userMenu.cancel")}
          </Button>
          <Button size="sm" onClick={handleSave} disabled={updateMe.isPending}>
            {updateMe.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {t("userMenu.save")}
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("common");
  const changePassword = useChangeMyPassword();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  function handleSave() {
    setLocalError(null);
    if (newPassword.length < 8) {
      setLocalError(t("userMenu.passwordTooShort"));
      return;
    }
    if (newPassword !== confirmPassword) {
      setLocalError(t("userMenu.passwordsDoNotMatch"));
      return;
    }
    changePassword.mutate(
      { current_password: currentPassword, new_password: newPassword },
      { onSuccess: onClose }
    );
  }

  return (
    <ModalShell title={t("userMenu.changePassword")} onClose={onClose}>
      <div className="space-y-4">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.currentPassword")}</label>
          <input
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.newPassword")}</label>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">{t("userMenu.confirmNewPassword")}</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="h-9 w-full rounded-md border border-border bg-transparent px-3 text-sm outline-none focus:border-primary"
          />
        </div>
        {(localError || changePassword.isError) && (
          <p className="text-xs text-destructive">
            {localError ?? t("userMenu.currentPasswordIncorrect")}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={onClose}>
            {t("userMenu.cancel")}
          </Button>
          <Button size="sm" onClick={handleSave} disabled={changePassword.isPending}>
            {changePassword.isPending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            {t("userMenu.save")}
          </Button>
        </div>
      </div>
    </ModalShell>
  );
}

/** Gear icon + dropdown (Account / Change password / Theme / Log out) --
 * replaces the standalone ThemeToggle and the standalone "Log out" button
 * that used to sit in the sidebar header/footer, folding all
 * account-adjacent actions into this single settings menu instead.
 * Language lives inside the Account modal (a persisted profile field, same
 * PATCH /users/me as name/email), not here -- this quick dropdown is for
 * per-device/session toggles (Theme) and navigation, not profile edits.
 *
 * `collapsed` controls icon-only vs icon+label. `stretch` controls whether
 * the trigger fills its container's width (the standalone rail-mode
 * button) or sits at its own intrinsic size (embedded inline next to the
 * username, right-aligned via the parent's flex row). */
export function UserSettingsMenu({
  collapsed,
  stretch = true,
  avatarUrl,
  usernameInitial,
  avatarTrigger = false,
}: {
  collapsed: boolean;
  stretch?: boolean;
  /** Rail-mode (collapsed && stretch) or avatarTrigger: shows the user's
   * photo (or initial) as the trigger instead of the gear icon. */
  avatarUrl?: string | null;
  usernameInitial?: string;
  /** Forces the avatar-photo trigger even outside rail mode -- used
   * inline in the expanded user row, where the avatar itself opens the
   * Account/Password/Theme dropdown instead of a separate gear button. */
  avatarTrigger?: boolean;
}) {
  const { t } = useTranslation("common");
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState<"account" | "password" | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clearAuth);
  const clearQueryCache = useClearQueryCacheOnLogout();

  function handleLogout() {
    setOpen(false);
    clearQueryCache();
    clearAuth();
    navigate("/login", { replace: true });
  }

  const railMode = collapsed && stretch;
  const showAvatar = railMode || avatarTrigger;

  return (
    <>
      <div className={cn("relative", stretch && "w-full")} ref={containerRef}>
        <Button
          variant="ghost"
          size={collapsed || avatarTrigger ? "icon" : "default"}
          className={cn(
            "text-muted-foreground",
            stretch && "w-full",
            !collapsed && !avatarTrigger && "justify-start gap-3",
            avatarTrigger && "h-7 w-7 rounded-full p-0"
          )}
          aria-label={t("userMenu.settings")}
          title={t("userMenu.settings")}
          onClick={() => setOpen((v) => !v)}
        >
          {showAvatar ? (
            <span
              className={cn(
                "flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-accent font-bold uppercase text-accent-foreground",
                avatarTrigger ? "h-7 w-7 text-xs" : "h-6 w-6 text-[11px]"
              )}
            >
              {avatarUrl ? (
                <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
              ) : (
                usernameInitial
              )}
            </span>
          ) : (
            <Settings className="h-4 w-4 shrink-0" />
          )}
          {!collapsed && !avatarTrigger && t("userMenu.settings")}
        </Button>
        {open && (
          <div
            className="absolute bottom-0 left-full z-20 ml-1 w-48 overflow-hidden rounded-md border border-border bg-card py-1 shadow-md"
          >
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {t("userMenu.account")}
            </p>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                setModal("account");
                setOpen(false);
              }}
            >
              <UserIcon className="h-3.5 w-3.5" />
              {t("userMenu.account")}
            </button>
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                setModal("password");
                setOpen(false);
              }}
            >
              <KeyRound className="h-3.5 w-3.5" />
              {t("userMenu.changePassword")}
            </button>
            {user?.is_admin && (
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                onClick={() => {
                  setOpen(false);
                  navigate("/settings");
                }}
              >
                <Settings2 className="h-3.5 w-3.5" />
                {t("userMenu.systemSettings")}
              </button>
            )}
            <div className="my-1 border-t border-border" />
            <p className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {t("userMenu.theme")}
            </p>
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                onClick={() => setTheme(opt.value)}
              >
                <opt.icon className="h-3.5 w-3.5" />
                <span className="flex-1">{t(`userMenu.${opt.labelKey}`)}</span>
                {theme === opt.value && <Check className="h-3.5 w-3.5" />}
              </button>
            ))}
            <div className="my-1 border-t border-border" />
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              onClick={handleLogout}
            >
              <LogOut className="h-3.5 w-3.5" />
              {t("userMenu.logout")}
            </button>
          </div>
        )}
      </div>
      {modal === "account" && <AccountModal onClose={() => setModal(null)} />}
      {modal === "password" && <ChangePasswordModal onClose={() => setModal(null)} />}
    </>
  );
}
```

## `frontend/src/components/layout/CommandPalette.tsx`

Global keyboard-driven route search overlay opened from the sidebar.

```tsx
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/store/authStore";
import type { NavGroupEntry, NavSectionEntry } from "@/components/layout/navSections";

interface FlatEntry {
  to: string;
  label: string;
  section: string;
  module?: string;
  icon: React.ComponentType<{ className?: string }>;
}

// Translates at flatten-time (not render-time) so search matching runs
// against the same text the user sees, in whichever language is active.
function flattenSections(sections: NavSectionEntry[], t: (key: string) => string): FlatEntry[] {
  const out: FlatEntry[] = [];
  for (const section of sections) {
    const sectionLabel = t(section.labelKey);
    for (const entry of section.entries) {
      if (entry.type === "link") {
        out.push({ to: entry.to, label: t(entry.labelKey), section: sectionLabel, module: entry.module, icon: entry.icon });
      } else {
        const groupLabel = t(entry.labelKey);
        for (const item of (entry as NavGroupEntry).items) {
          out.push({
            to: item.to,
            label: `${groupLabel} / ${t(item.labelKey)}`,
            section: sectionLabel,
            module: item.module,
            icon: item.icon,
          });
        }
      }
    }
  }
  return out;
}

/** Cmd/Ctrl+K quick navigation, filtered to whatever the signed-in user can
 * actually view -- reuses the same permission map the sidebar reads, not a
 * per-item hook call (avoids conditional hooks over a mapped list). */
export function CommandPalette({
  sections,
  open,
  onOpenChange,
}: {
  sections: NavSectionEntry[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation("common");
  const setOpen = onOpenChange;
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const permissions = useAuthStore((s) => s.permissions);

  const canView = React.useCallback(
    (module: string | undefined) => {
      if (!module) return true;
      if (!user) return false;
      if (user.is_admin) return true;
      return permissions[module]?.can_view ?? false;
    },
    [user, permissions]
  );

  const allEntries = React.useMemo(() => flattenSections(sections, t), [sections, t]);

  const visibleEntries = React.useMemo(() => {
    const withPerm = allEntries.filter((entry) => canView(entry.module));
    if (!query.trim()) return withPerm;
    const q = query.trim().toLowerCase();
    return withPerm.filter(
      (entry) => entry.label.toLowerCase().includes(q) || entry.section.toLowerCase().includes(q)
    );
  }, [allEntries, canView, query]);

  React.useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isK = e.key.toLowerCase() === "k";
      if ((e.metaKey || e.ctrlKey) && isK) {
        e.preventDefault();
        setOpen(!open);
        return;
      }
      if (!open) return;
      if (e.key === "Escape") {
        e.preventDefault();
        setOpen(false);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, visibleEntries.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const target = visibleEntries[activeIndex];
        if (target) {
          navigate(target.to);
          setOpen(false);
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, visibleEntries, activeIndex, navigate]);

  React.useEffect(() => {
    if (open) {
      setQuery("");
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4 sm:pt-[15vh]"
      role="dialog"
      aria-modal="true"
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div className="relative z-10 flex max-h-full w-full max-w-lg flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl animate-in fade-in-0 zoom-in-95 duration-150">
        <div className="flex shrink-0 items-center gap-2 border-b border-border px-4">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("commandPalette.placeholder")}
            className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label={t("commandPalette.close")}
            title={t("commandPalette.close")}
            className="flex shrink-0 items-center gap-1 rounded-md border border-border px-2 py-1 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <X className="h-3 w-3" />
            {t("commandPalette.close")}
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {visibleEntries.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t("commandPalette.noResults")}</p>
          )}
          {visibleEntries.map((entry, i) => (
            <button
              key={entry.to}
              type="button"
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => {
                navigate(entry.to);
                setOpen(false);
              }}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm",
                i === activeIndex ? "bg-accent text-accent-foreground" : "text-foreground"
              )}
            >
              <entry.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="flex-1 truncate">{entry.label}</span>
              <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground/60">
                {entry.section}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

## `frontend/src/components/Logo.tsx`

Shared ForgeHub full logo and compact logo mark rendered in the navigation shell.

```tsx
import { cn } from "@/lib/utils";

/**
 * Brand mark: an anvil (the forge — building/executing the work) struck by
 * a spark (an AI agent actively at work on it). Deliberately fixed,
 * non-theme-dependent brand colors -- indigo anvil + amber spark -- so the
 * mark reads the same everywhere instead of just matching whatever text
 * color happens to surround it.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <polygon points="8,29 24,25 24,35" fill="#4f46e5" />
      <rect x="22" y="24" width="28" height="11" rx="1.5" fill="#4f46e5" />
      <rect x="29" y="35" width="10" height="9" fill="#4f46e5" />
      <polygon points="23,44 45,44 51,53 17,53" fill="#4f46e5" />
      <path
        d="M52 11 L54 16 L59 18 L54 20 L52 25 L50 20 L45 18 L50 16 Z"
        fill="#f59e0b"
      />
    </svg>
  );
}

interface LogoProps {
  className?: string;
  /** Render only the mark, no wordmark — used in collapsed layouts. */
  iconOnly?: boolean;
}

export function Logo({ className, iconOnly = false }: LogoProps) {
  return (
    <div className={cn("flex items-center gap-2 overflow-hidden", className)}>
      <LogoMark className="h-11 w-11 shrink-0" />
      {!iconOnly && (
        <span className="text-lg font-semibold tracking-tight whitespace-nowrap">
          ForgeHub
        </span>
      )}
    </div>
  );
}
```

## `frontend/src/components/ui/breadcrumb.tsx`

Reusable breadcrumb navigation primitive used by page headers.

```tsx
import * as React from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
  className?: string;
}

export function Breadcrumb({ items, className }: BreadcrumbProps) {
  return (
    <nav aria-label="Breadcrumb" className={cn("flex items-center gap-1 text-sm text-muted-foreground", className)}>
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50" />}
          {item.href ? (
            <Link to={item.href} className="hover:text-foreground transition-colors">
              {item.label}
            </Link>
          ) : (
            <span className="font-medium text-foreground">{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}
```


