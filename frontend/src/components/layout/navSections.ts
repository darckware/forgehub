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

// `labelKey` is an i18next key into common.json's "nav" tree (e.g.
// "nav.dashboard"), not display text -- Sidebar.tsx and CommandPalette.tsx
// (the two consumers) call t(entry.labelKey) at render time so the menu
// reacts live to a language switch. This module stays plain data (no hook
// access), so translation happens at the point of consumption, not here.
export interface NavLinkEntry {
  type: "link";
  to: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
  module?: string; // if set, check can_view; undefined = always visible
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
      // AI news digests archived by report-generating crons (e.g.
      // ai-news-noon), see news.py -- filesystem-only, no DB table.
      { type: "link", to: "/news", labelKey: "nav.news", icon: Newspaper },
      // Inbox de demandas de agentes ("como um e-mail"), conversível em
      // Task/Doc/Artefato/Knowledge Base (core/conversions.py).
      { type: "link", to: "/demands", labelKey: "nav.inbox", icon: Inbox, module: "demands" },
      // Área de criação: markdown editável em /root/docs, cruzado com
      // produtos/projetos/tasks (doc_links, fase 3).
      { type: "link", to: "/docs", labelKey: "nav.docs", icon: BookOpen, module: "docs" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.planning",
    entries: [
      { type: "link", to: "/conception", labelKey: "nav.conception", icon: Lightbulb, module: "product" },
      { type: "link", to: "/system-map", labelKey: "nav.systemMap", icon: Share2, module: "product" },
      { type: "link", to: "/project-scope", labelKey: "nav.projectScope", icon: ClipboardList, module: "projects" },
      { type: "link", to: "/product", labelKey: "nav.products", icon: Package, module: "product" },
      { type: "link", to: "/projects", labelKey: "nav.projects", icon: FolderKanban, module: "projects" },
      { type: "link", to: "/pipeline", labelKey: "nav.pipelines", icon: GitBranch, module: "pipeline" },
      { type: "link", to: "/pipeline-templates", labelKey: "nav.templates", icon: GitBranch, module: "pipeline" },
      { type: "link", to: "/backlog", labelKey: "nav.planningItem", icon: ClipboardList, module: "backlog" },
      { type: "link", to: "/tasks", labelKey: "nav.execution", icon: CheckSquare, module: "tasks" },
      { type: "link", to: "/artifact", labelKey: "nav.artifacts", icon: FileBox, module: "artifacts" },
      { type: "link", to: "/governance", labelKey: "nav.governance", icon: Gavel, module: "governance" },
      { type: "link", to: "/governance/policies", labelKey: "nav.policies", icon: ShieldCheck, module: "governance" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.agentsAi",
    entries: [
      { type: "link", to: "/agents", labelKey: "nav.agents", icon: Bot, module: "agents" },
      { type: "link", to: "/tools", labelKey: "nav.agentTools", icon: Wrench, module: "agents" },
      { type: "link", to: "/prompt-commands", labelKey: "nav.chatCommands", icon: Command, module: "agents" },
      { type: "link", to: "/skills", labelKey: "nav.skills", icon: Sparkles, module: "agents" },
      { type: "link", to: "/crons", labelKey: "nav.crons", icon: Clock, module: "crons" },
      { type: "link", to: "/foundation", labelKey: "nav.foundation", icon: Landmark, module: "foundation" },
      { type: "link", to: "/forgerouter", labelKey: "nav.forgerouter", icon: Route, module: "forgerouter" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.integrations",
    entries: [
      { type: "link", to: "/kanboard", labelKey: "nav.kanboard", icon: Kanban, module: "kanboard" },
      { type: "link", to: "/obsidian", labelKey: "nav.knowledgeBase", icon: Gem, module: "obsidian" },
    ],
  },
  {
    type: "section",
    labelKey: "nav.section.operations",
    entries: [
      { type: "link", to: "/system-control", labelKey: "nav.systemControl", icon: GitBranch, module: "system_control" },
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
