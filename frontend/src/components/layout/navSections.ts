import {
  Activity,
  AlertTriangle,
  Bell,
  BookOpen,
  Bot,
  Brain,
  Building2,
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
  ShieldEllipsis,
} from "lucide-react";

export interface NavLinkEntry {
  type: "link";
  to: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string;
  hiddenInSidebar?: boolean;
  adminOnly?: boolean;
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

export function isNavEntryVisible(entry: { adminOnly?: boolean }, isAdmin: boolean): boolean {
  return !entry.adminOnly || isAdmin;
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
      // Monitoramento da Software Factory:
      // 0. Cockpit de Execução
      // Pipeline Sequencial da Software Factory (1 a 6):
      // 1. Concepção & Contexto
      // 2. Telas & Regras de Negócio
      // 3. Banco de Dados & ERD
      // 4. Central de Projetos & Backlog
      // 5. Gate de Governança
      // 6. Fechamento de Versão
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
      { type: "link", to: "/clients", labelKey: "nav.clients", icon: Building2, module: "clients" },
      { type: "link", to: "/irregularities", labelKey: "nav.irregularities", icon: AlertTriangle, module: "clients" },
      { type: "link", to: "/vpn", labelKey: "nav.vpn", icon: ShieldEllipsis, module: "vpn", adminOnly: true },
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
