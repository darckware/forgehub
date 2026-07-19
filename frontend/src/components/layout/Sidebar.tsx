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

  const renderLink = (entry: NavLinkEntry) => (
    <PermissionGate key={entry.to} module={entry.module}>
      <NavLink
        to={entry.to}
        end={entry.to === "/"}
        title={effectiveCollapsed ? t(entry.labelKey) : undefined}
        className={({ isActive }) => navLinkClasses(isActive, effectiveCollapsed)}
      >
        <entry.icon className="h-4 w-4 shrink-0" />
        {!effectiveCollapsed && t(entry.labelKey)}
      </NavLink>
    </PermissionGate>
  );

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
                    {section.entries.map((entry, i) => (
                      <React.Fragment key={i}>{renderEntry(entry as NavLinkEntry | NavGroupEntry)}</React.Fragment>
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
