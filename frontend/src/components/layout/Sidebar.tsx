import React, { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Bell,
  LayoutDashboard,
  LayoutPanelLeft,
  Package,
  FolderKanban,
  GitBranch,
  ClipboardList,
  CheckSquare,
  Bot,
  FileBox,
  Gavel,
  Gem,
  Kanban,
  Landmark,
  Route,
  Clock,
  Server,
  Network,
  Database,
  LayoutList,
  Share2,
  Code2,
  ChevronDown,
  BookOpen,
  ChevronRight,
  ClipboardCheck,
  Users,
  ShieldCheck,
  Sparkles,
  Wrench,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { UserSettingsMenu } from "@/components/layout/UserSettingsMenu";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/authStore";
import { usePermission } from "@/hooks/usePermission";

const COLLAPSE_STORAGE_KEY = "forgehub-sidebar-collapsed";
const GROUP_COLLAPSE_STORAGE_KEY = "forgehub-sidebar-group-collapsed";

interface NavLinkEntry {
  type: "link";
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string; // if set, check can_view; undefined = always visible
}

interface NavGroupEntry {
  type: "group";
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  items: (Omit<NavLinkEntry, "type"> & { module?: string })[];
}

interface NavSectionEntry {
  type: "section";
  label: string;
  entries: (NavLinkEntry | NavGroupEntry)[];
}


const NAV_SECTIONS: NavSectionEntry[] = [
  {
    type: "section",
    label: "General",
    entries: [
      { type: "link", to: "/", label: "Dashboard", icon: LayoutDashboard },
      { type: "link", to: "/workspace", label: "Workspace", icon: LayoutPanelLeft },
      { type: "link", to: "/notifications", label: "Notifications", icon: Bell },
    ],
  },
  {
    type: "section",
    label: "Planning",
    entries: [
      { type: "link", to: "/product", label: "Products", icon: Package, module: "product" },
      { type: "link", to: "/projects", label: "Projects", icon: FolderKanban, module: "projects" },
      { type: "link", to: "/pipeline", label: "Pipelines", icon: GitBranch, module: "pipeline" },
      { type: "link", to: "/pipeline-templates", label: "Templates", icon: GitBranch, module: "pipeline" },
      { type: "link", to: "/backlog", label: "Planning", icon: ClipboardList, module: "backlog" },
      { type: "link", to: "/tasks", label: "Execution", icon: CheckSquare, module: "tasks" },
      { type: "link", to: "/artifact", label: "Artifacts", icon: FileBox, module: "artifacts" },
      // Área de criação: markdown editável em /root/docs, cruzado com
      // produtos/projetos/tasks (doc_links, fase 3).
      { type: "link", to: "/docs", label: "Docs", icon: BookOpen, module: "docs" },
      { type: "link", to: "/governance", label: "Governance", icon: Gavel, module: "governance" },
      { type: "link", to: "/governance/policies", label: "Policies", icon: ShieldCheck, module: "governance" },
    ],
  },
  {
    type: "section",
    label: "Agents & AI",
    entries: [
      { type: "link", to: "/agents", label: "Agents", icon: Bot, module: "agents" },
      { type: "link", to: "/tools", label: "Agent Tools", icon: Wrench, module: "agents" },
      { type: "link", to: "/skills", label: "Skills", icon: Sparkles, module: "agents" },
      { type: "link", to: "/foundation", label: "Foundation", icon: Landmark, module: "foundation" },
      { type: "link", to: "/forgerouter", label: "ForgeRouter", icon: Route, module: "forgerouter" },
    ],
  },
  {
    type: "section",
    label: "Tools",
    entries: [
      { type: "link", to: "/kanboard", label: "Kanboard", icon: Kanban, module: "kanboard" },
      { type: "link", to: "/obsidian", label: "Knowledge Base", icon: Gem, module: "obsidian" },
      {
        type: "group",
        label: "Database",
        icon: Database,
        items: [
          { to: "/database/schema", label: "Schema", icon: LayoutList, module: "database" },
          { to: "/database/diagram", label: "Diagram", icon: Share2, module: "database" },
          { to: "/database/query", label: "Query", icon: Code2, module: "database" },
        ],
      },
      { type: "link", to: "/crons", label: "Crons", icon: Clock, module: "crons" },
      // Ecosystem checkpoints (audit_checks) -- admins always see it; grant
      // the "auditor" module in Access Profiles for non-admin visibility.
      { type: "link", to: "/auditor", label: "Auditor", icon: ClipboardCheck, module: "auditor" },
      { type: "link", to: "/deploy", label: "Deploy Control", icon: Server, module: "deploy" },
      { type: "link", to: "/servers", label: "Servers", icon: Network, module: "servers" },
    ],
  },
  {
    type: "section",
    label: "Administration",
    entries: [
      { type: "link", to: "/users", label: "Users", icon: Users, module: "users" },
      { type: "link", to: "/profiles", label: "Access Profiles", icon: ShieldCheck, module: "profiles" },
    ],
  },
];

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
  const location = useLocation();
  const navigate = useNavigate();
  const { user, clearAuth } = useAuthStore();
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

  const handleLogout = () => {
    clearAuth();
    navigate("/login", { replace: true });
  };

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

  const toggleGroup = (label: string) =>
    setCollapsedGroups((prev) => ({ ...prev, [label]: !prev[label] }));

  const renderLink = (entry: NavLinkEntry) => (
    <PermissionGate key={entry.to} module={entry.module}>
      <NavLink
        to={entry.to}
        end={entry.to === "/"}
        title={effectiveCollapsed ? entry.label : undefined}
        className={({ isActive }) => navLinkClasses(isActive, effectiveCollapsed)}
      >
        <entry.icon className="h-4 w-4 shrink-0" />
        {!effectiveCollapsed && entry.label}
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
            title={item.label}
            className={({ isActive }) => navLinkClasses(isActive, effectiveCollapsed)}
          >
            <item.icon className="h-4 w-4 shrink-0" />
          </NavLink>
        </PermissionGate>
      ));
    }

    const GroupIcon = entry.icon;
    const isGroupActive = entry.items.some((item) => location.pathname.startsWith(item.to));
    const isGroupCollapsed = collapsedGroups[entry.label] ?? false;

    return (
      <div key={entry.label}>
        <button
          type="button"
          onClick={() => toggleGroup(entry.label)}
          className={cn(
            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
            isGroupActive
              ? "text-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          )}
        >
          <GroupIcon className="h-4 w-4 shrink-0" />
          <span className="flex-1 text-left">{entry.label}</span>
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
                  {item.label}
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
          aria-label="Abrir menu"
          title="Abrir menu"
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
          <Logo iconOnly={effectiveCollapsed} />
          {!effectiveCollapsed && !isMobile && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Recolher sidebar"
              title="Recolher sidebar"
              onClick={toggleSidebar}
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          )}
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-4">
          {effectiveCollapsed && !isMobile && (
            <Button
              variant="ghost"
              size="icon"
              className="w-full"
              aria-label="Expandir sidebar"
              title="Expandir sidebar"
              onClick={toggleSidebar}
            >
              <PanelLeftOpen className="h-4 w-4" />
            </Button>
          )}
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              {!effectiveCollapsed && (
                <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground/60">
                  {section.label}
                </p>
              )}
              <div className="space-y-1">
                {section.entries.map((entry, i) => (
                  <React.Fragment key={i}>{renderEntry(entry as NavLinkEntry | NavGroupEntry)}</React.Fragment>
                ))}
              </div>
            </div>
          ))}
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
                    <ShieldCheck className="h-2.5 w-2.5" /> Admin
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
          <Button
            variant="ghost"
            size={effectiveCollapsed ? "icon" : "default"}
            className={cn("w-full text-muted-foreground", !effectiveCollapsed && "justify-start gap-3")}
            aria-label="Log out"
            title="Log out"
            onClick={handleLogout}
          >
            <LogOut className="h-4 w-4 shrink-0" />
            {!effectiveCollapsed && "Log out"}
          </Button>
        </div>
      </aside>
    </>
  );
}
