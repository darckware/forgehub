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
  Gauge,
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
  Mail,
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
  /** Keep the route out of the sidebar while leaving it in the command
   * palette. For pages reached from inside another page rather than from the
   * nav -- dropping the entry entirely would also drop it from Cmd/Ctrl+K,
   * which is a search surface, not a menu. */
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
      // AI news digests archived by report-generating crons (e.g.
      // ai-news-noon), see news.py -- filesystem-only, no DB table.
      { type: "link", to: "/news", labelKey: "nav.news", icon: Newspaper },
      // Mensagens: canal de demandas de agentes ("como um e-mail"),
      // conversível em Task/Doc/Knowledge Base (core/conversions.py). Rotulado
      // "Mensagens" desde 2026-07-26 -- a rota /demands e o domínio `demand`
      // mantêm o nome antigo para não quebrar links e integrações existentes.
      { type: "link", to: "/demands", labelKey: "nav.inbox", icon: Mail, module: "demands" },
      // Área de criação: markdown editável em /root/docs, cruzado com
      // produtos/projetos/tasks (doc_links, fase 3).
      { type: "link", to: "/docs", labelKey: "nav.docs", icon: BookOpen, module: "docs" },
    ],
  },
  // Fábrica de Software -- EM REPLANEJAMENTO (2026-07-27).
  //
  // A versão anterior desta seção organizava o ciclo de desenvolvimento em
  // cinco fases numeradas, derivadas de um documento externo ao repositório.
  // Ela foi desfeita porque divergia da arquitetura canônica do projeto
  // (docs/architecture/PLANNING_DELIVERY_ARCHITECTURE.md), que descreve três
  // macrofluxos movidos por três autorizações -- Concept Approval, Delivery
  // Authorization e Release Approval -- com telas ancoradas em Product/Project
  // e um Cockpit especificado em docs/modules/06_COCKPIT_AND_INTEGRATIONS.md.
  // Três dos cinco rótulos também prometiam telas que não existem: o mapa do
  // sistema não é um designer de telas navegável, e o backlog não é um editor
  // de stored procedures.
  //
  // Enquanto o novo conceito é desenhado, a seção **não expõe nenhum item no
  // menu** (decisão do Marcelo, 2026-07-27). As entradas continuam aqui com
  // `hiddenInSidebar: true`: as rotas seguem no ar e alcançáveis pelo
  // Cmd/Ctrl+K, que é superfície de busca e não menu -- apagá-las daqui seria
  // remover as telas, não esvaziar o menu. O Sidebar omite o cabeçalho de uma
  // seção sem itens visíveis, então a seção inteira desaparece da navegação
  // enquanto estiver assim.
  //
  // Não acrescente aqui uma nova organização de fases/etapas sem uma spec
  // aprovada em docs/modules/ -- ver o Definition Gate em docs/README.md.
  {
    type: "section",
    labelKey: "nav.section.factory",
    entries: [
      { type: "link", to: "/product", labelKey: "nav.products", icon: Package, module: "product", hiddenInSidebar: true },
      { type: "link", to: "/projects", labelKey: "nav.projects", icon: FolderKanban, module: "projects", hiddenInSidebar: true },
      { type: "link", to: "/conception", labelKey: "nav.conception", icon: Lightbulb, module: "product", hiddenInSidebar: true },
      { type: "link", to: "/system-map", labelKey: "nav.systemMap", icon: Share2, module: "product", hiddenInSidebar: true },
      { type: "link", to: "/backlog", labelKey: "nav.backlog", icon: Code2, module: "backlog", hiddenInSidebar: true },
      { type: "link", to: "/tasks", labelKey: "nav.tasks", icon: CheckSquare, module: "tasks", hiddenInSidebar: true },
      { type: "link", to: "/governance", labelKey: "nav.governance", icon: ShieldCheck, module: "governance", hiddenInSidebar: true },
      // As entradas abaixo já estavam fora do menu antes desta decisão.
      // Artefatos saiu da navegação por decisão do Marcelo (2026-07-26): o
      // detalhamento passa a ser feito em arquivos .md (Docs e o step de
      // Documentação da Concepção). A rota e o domínio `artifact` continuam no
      // backend por causa das FKs existentes.
      // /cockpit continua roteável pelo mesmo motivo: a tela e o endpoint
      // `factory` seguem no ar, mas fora do menu até o módulo 06 ser
      // especificado e decidir o que aproveitar.
      {
        type: "link",
        to: "/cockpit",
        labelKey: "nav.cockpit",
        icon: Gauge,
        module: "product",
        hiddenInSidebar: true,
      },
      {
        type: "link",
        to: "/project-scope",
        labelKey: "nav.projectScope",
        icon: ClipboardList,
        module: "projects",
        hiddenInSidebar: true,
      },
      {
        type: "link",
        to: "/pipeline",
        labelKey: "nav.pipelines",
        icon: GitBranch,
        module: "pipeline",
        hiddenInSidebar: true,
      },
      {
        type: "link",
        to: "/pipeline-templates",
        labelKey: "nav.templates",
        icon: GitBranch,
        module: "pipeline",
        hiddenInSidebar: true,
      },
      {
        type: "link",
        to: "/governance/policies",
        labelKey: "nav.policies",
        icon: Gavel,
        module: "governance",
        hiddenInSidebar: true,
      },
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
      // Kanboard saiu do menu por decisão do Marcelo (2026-07-26): o controle
      // de tarefas passa a ser nativo do ForgeHub. A rota continua registrada
      // e alcançável pelo Cmd/Ctrl+K enquanto a integração não é desligada de
      // fato -- o board externo ainda é escrito por outros agentes do
      // ecossistema (ver CLAUDE.md), então arrancar o cliente/sync e as
      // colunas kanboard_* é uma remoção à parte, não um efeito colateral
      // desta reorganização de menu.
      {
        type: "link",
        to: "/kanboard",
        labelKey: "nav.kanboard",
        icon: Kanban,
        module: "kanboard",
        hiddenInSidebar: true,
      },
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
