import type React from "react";
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
  Brain,
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
  BookOpen,
  Inbox,
  ClipboardCheck,
  Users,
  ShieldCheck,
  Sparkles,
  Wrench,
  Command,
  Newspaper,
  Lightbulb,
} from "lucide-react";

export interface NavLinkEntry {
  type: "link";
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string; // if set, check can_view; undefined = always visible
}

export interface NavGroupEntry {
  type: "group";
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  items: (Omit<NavLinkEntry, "type"> & { module?: string })[];
}

export interface NavSectionEntry {
  type: "section";
  label: string;
  entries: (NavLinkEntry | NavGroupEntry)[];
}

export const NAV_SECTIONS: NavSectionEntry[] = [
  {
    type: "section",
    label: "General",
    entries: [
      { type: "link", to: "/", label: "Dashboard", icon: LayoutDashboard },
      { type: "link", to: "/workspace", label: "Workspace", icon: LayoutPanelLeft },
      { type: "link", to: "/notifications", label: "Notifications", icon: Bell },
      // AI news digests archived by report-generating crons (e.g.
      // ai-news-noon), see news.py -- filesystem-only, no DB table.
      { type: "link", to: "/news", label: "News", icon: Newspaper },
      // Inbox de demandas de agentes ("como um e-mail"), conversível em
      // Task/Doc/Artefato/Knowledge Base (core/conversions.py).
      { type: "link", to: "/demands", label: "Inbox", icon: Inbox, module: "demands" },
      // Área de criação: markdown editável em /root/docs, cruzado com
      // produtos/projetos/tasks (doc_links, fase 3).
      { type: "link", to: "/docs", label: "Docs", icon: BookOpen, module: "docs" },
    ],
  },
  {
    type: "section",
    label: "Planning",
    entries: [
      { type: "link", to: "/conception", label: "Conception", icon: Lightbulb, module: "product" },
      { type: "link", to: "/system-map", label: "System Map", icon: Share2, module: "product" },
      { type: "link", to: "/project-scope", label: "Project Scope", icon: ClipboardList, module: "projects" },
      { type: "link", to: "/product", label: "Products", icon: Package, module: "product" },
      { type: "link", to: "/projects", label: "Projects", icon: FolderKanban, module: "projects" },
      { type: "link", to: "/pipeline", label: "Pipelines", icon: GitBranch, module: "pipeline" },
      { type: "link", to: "/pipeline-templates", label: "Templates", icon: GitBranch, module: "pipeline" },
      { type: "link", to: "/backlog", label: "Planning", icon: ClipboardList, module: "backlog" },
      { type: "link", to: "/tasks", label: "Execution", icon: CheckSquare, module: "tasks" },
      { type: "link", to: "/artifact", label: "Artifacts", icon: FileBox, module: "artifacts" },
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
      { type: "link", to: "/prompt-commands", label: "Chat Commands", icon: Command, module: "agents" },
      { type: "link", to: "/skills", label: "Skills", icon: Sparkles, module: "agents" },
      { type: "link", to: "/crons", label: "Crons", icon: Clock, module: "crons" },
      { type: "link", to: "/foundation", label: "Foundation", icon: Landmark, module: "foundation" },
      { type: "link", to: "/forgerouter", label: "ForgeRouter", icon: Route, module: "forgerouter" },
    ],
  },
  {
    type: "section",
    label: "Integrations",
    entries: [
      { type: "link", to: "/kanboard", label: "Kanboard", icon: Kanban, module: "kanboard" },
      { type: "link", to: "/obsidian", label: "Knowledge Base", icon: Gem, module: "obsidian" },
    ],
  },
  {
    type: "section",
    label: "Operations",
    entries: [
      { type: "link", to: "/system-control", label: "System Control", icon: GitBranch, module: "system_control" },
      { type: "link", to: "/hindsight", label: "Hindsight", icon: Brain, module: "foundation" },
      // Ecosystem checkpoints (audit_checks) -- admins always see it; grant
      // the "auditor" module in Access Profiles for non-admin visibility.
      { type: "link", to: "/auditor", label: "Auditor", icon: ClipboardCheck, module: "auditor" },
      { type: "link", to: "/deploy", label: "Deploy Control", icon: Server, module: "deploy" },
      { type: "link", to: "/servers", label: "Servers", icon: Network, module: "servers" },
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
