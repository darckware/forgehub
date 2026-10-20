# Route Map

## Router

- Framework: React 18 with React Router (`react-router-dom`).
- Router style: config-based route tree declared in `frontend/src/App.tsx`.
- Authentication: `/login` is public; every other route is wrapped by `RequireAuth` and redirects unauthenticated users to `/login` while preserving `location.pathname` in route state.
- Primary layout: authenticated routes render inside `frontend/src/components/layout/AppLayout.tsx`.
- Nested database layout: `/database`, `/database/schema`, `/database/diagram`, and `/database/query` additionally render inside `frontend/src/pages/database/DatabaseLayout.tsx`.

## Route Inventory

| URL path | Component file | Layout |
| --- | --- | --- |
| `/login` | `frontend/src/pages/auth/LoginPage.tsx` | None (public) |
| `/` | `frontend/src/pages/Dashboard.tsx` | `AppLayout` |
| `/workspace` | `frontend/src/pages/workspace/index.tsx` | `AppLayout` (full bleed) |
| `/notifications` | `frontend/src/pages/notifications/index.tsx` | `AppLayout` (full bleed) |
| `/news` | `frontend/src/pages/news/index.tsx` | `AppLayout` |
| `/conception` | `frontend/src/pages/conception/index.tsx` | `AppLayout` |
| `/system-map` | `frontend/src/pages/system-map/index.tsx` | `AppLayout` |
| `/project-scope` | `frontend/src/pages/project-scope/index.tsx` | `AppLayout` |
| `/product` | `frontend/src/pages/product/index.tsx` | `AppLayout` |
| `/product/:id` | `frontend/src/pages/product/ProductDetail.tsx` | `AppLayout` |
| `/projects` | `frontend/src/pages/project/index.tsx` | `AppLayout` |
| `/projects/:id` | `frontend/src/pages/project/[id].tsx` | `AppLayout` |
| `/pipeline` | `frontend/src/pages/pipeline/index.tsx` | `AppLayout` |
| `/pipeline/:id` | `frontend/src/pages/pipeline/[id].tsx` | `AppLayout` |
| `/pipeline-templates` | `frontend/src/pages/pipeline-templates/index.tsx` | `AppLayout` |
| `/backlog` | `frontend/src/pages/backlog/index.tsx` | `AppLayout` |
| `/backlog/:id` | `frontend/src/pages/backlog/[id].tsx` | `AppLayout` |
| `/tasks` | `frontend/src/pages/task/index.tsx` | `AppLayout` |
| `/tasks/:id` | `frontend/src/pages/task/[id].tsx` | `AppLayout` |
| `/agents` | `frontend/src/pages/agent/index.tsx` | `AppLayout` |
| `/agents/:id` | `frontend/src/pages/agent/[id].tsx` | `AppLayout` |
| `/tools` | `frontend/src/pages/tools/index.tsx` | `AppLayout` (full bleed) |
| `/mcp` | `frontend/src/pages/mcp/index.tsx` | `AppLayout` |
| `/systems-hub` | `frontend/src/pages/systems-hub/index.tsx` | `AppLayout` |
| `/prompt-commands` | `frontend/src/pages/prompt-commands/index.tsx` | `AppLayout` |
| `/prompt-techniques` | `frontend/src/pages/prompt-techniques/index.tsx` | `AppLayout` |
| `/skills` | `frontend/src/pages/skills/index.tsx` | `AppLayout` (full bleed) |
| `/artifact` | `frontend/src/pages/artifact/index.tsx` | `AppLayout` |
| `/artifact/:id` | `frontend/src/pages/artifact/[id].tsx` | `AppLayout` |
| `/governance` | `frontend/src/pages/governance/index.tsx` | `AppLayout` |
| `/governance/:id` | `frontend/src/pages/governance/[id].tsx` | `AppLayout` |
| `/governance/policies` | `frontend/src/pages/governance/PoliciesPage.tsx` | `AppLayout` |
| `/forgerouter` | `frontend/src/pages/forgerouter/index.tsx` | `AppLayout` |
| `/obsidian` | `frontend/src/pages/obsidian/index.tsx` | `AppLayout` (full bleed) |
| `/hindsight` | `frontend/src/pages/hindsight/index.tsx` | `AppLayout` |
| `/foundation` | `frontend/src/pages/foundation/index.tsx` | `AppLayout` (full bleed) |
| `/crons` | `frontend/src/pages/crons/index.tsx` | `AppLayout` |
| `/system-control` | `frontend/src/pages/system-control/index.tsx` | `AppLayout` |
| `/settings` | `frontend/src/pages/settings/index.tsx` | `AppLayout` |
| `/auditor` | `frontend/src/pages/auditor/index.tsx` | `AppLayout` (full bleed) |
| `/demands` | `frontend/src/pages/demands/index.tsx` | `AppLayout` (full bleed) |
| `/agent-activity` | `frontend/src/pages/agent-activity/index.tsx` | `AppLayout` |
| `/docs` | `frontend/src/pages/docs/index.tsx` | `AppLayout` (full bleed) |
| `/deploy` | `frontend/src/pages/deploy/index.tsx` | `AppLayout` |
| `/servers` | `frontend/src/pages/servers/index.tsx` | `AppLayout` |
| `/users` | `frontend/src/pages/users/index.tsx` | `AppLayout` |
| `/profiles` | `frontend/src/pages/profiles/index.tsx` | `AppLayout` |
| `/screen-inspector` | `frontend/src/pages/screen-inspector/index.tsx` | `AppLayout` |
| `/concept-erd` | `frontend/src/pages/concept-erd/index.tsx` | `AppLayout` |
| `/screen-rules` | `frontend/src/pages/screen-inspector/index.tsx` | `AppLayout` |
| `/version-closure` | `frontend/src/pages/version-closure/index.tsx` | `AppLayout` |
| `/cockpit` | `frontend/src/pages/cockpit/index.tsx` | `AppLayout` |
| `/database` | `frontend/src/pages/database/SchemaPage.tsx` | `AppLayout` → `DatabaseLayout` |
| `/database/schema` | `frontend/src/pages/database/SchemaPage.tsx` | `AppLayout` → `DatabaseLayout` |
| `/database/diagram` | `frontend/src/pages/database/DiagramPage.tsx` | `AppLayout` → `DatabaseLayout` |
| `/database/query` | `frontend/src/pages/database/QueryPage.tsx` | `AppLayout` → `DatabaseLayout` |

## Key Route Summaries

### `/agent-activity`

Live operational visualization of agent work. It derives an activity view model from Messages/demands and ForgeRouter telemetry, renders the agent stage, and opens a task-history dialog for selected agents.

### `/demands`

The Messages operational workspace. It presents incoming/outgoing demand trees, status and dispatch controls, message composition, execution-wave visibility, and task context in a full-bleed control-panel layout.

### `/agents`

Agent roster and directory. It provides searchable/sortable agent records, avatars, expandable detail, role/runtime metadata, and navigation to individual profiles.

### `/agents/:id`

Detailed agent profile and configuration surface, including identity/profile files, automation, MCP assignment, API/runtime details, and agent-specific controls.

### `/workspace`

Full-bleed interactive work environment combining agent chat/channel interfaces, terminal, browser/application panes, project working-directory selection, and persisted workspace layout state.

### `/projects`

Project portfolio management surface with project creation/editing and navigation into project detail, planning, automation, files, ForgeRouter configuration, and related entities.

### `/governance`

Approval queue and governance control surface. It lists approval requests, exposes decision state, and links to request details and policy management.

### `/notifications`

Full-bleed operational notification history with severity/read-state handling and cleanup controls; it is the expanded destination for the persistent sidebar notification bell.

### `/forgerouter`

ForgeRouter gateway operations page for provider/model routing, connectivity status, and telemetry relevant to the ecosystem's single LLM gateway.

### `/cockpit`

High-level operational cockpit that composes system and execution information into a monitoring-oriented mission-control view.

## Full Router Configuration

Source: `frontend/src/App.tsx`

```tsx
import { Navigate, Routes, Route, useLocation } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { useAuthStore } from "@/store/authStore";
import LoginPage from "@/pages/auth/LoginPage";
import Dashboard from "@/pages/Dashboard";
import WorkspacePage from "@/pages/workspace";
import ProductPage from "@/pages/product";
import ProductDetail from "@/pages/product/ProductDetail";
import ProjectPage from "@/pages/project";
import ProjectDetailPage from "@/pages/project/[id]";
import PipelinePage from "@/pages/pipeline";
import PipelineDetailPage from "@/pages/pipeline/[id]";
import BacklogPage from "@/pages/backlog";
import PlanningItemDetailPage from "@/pages/backlog/[id]";
import TaskPage from "@/pages/task";
import TaskDetailPage from "@/pages/task/[id]";
import AgentPage from "@/pages/agent";
import AgentDetailPage from "@/pages/agent/[id]";
import ToolsPage from "@/pages/tools";
import McpPage from "@/pages/mcp";
import SystemsHubPage from "@/pages/systems-hub";
import PromptCommandsPage from "@/pages/prompt-commands";
import PromptTechniquesPage from "@/pages/prompt-techniques";
import SkillsPage from "@/pages/skills";
import AuditorPage from "@/pages/auditor";
import DemandsPage from "@/pages/demands";
import AgentActivityPage from "@/pages/agent-activity";
import DocsPage from "@/pages/docs";
import ArtifactPage from "@/pages/artifact";
import ArtifactDetailPage from "@/pages/artifact/[id]";
import GovernancePage from "@/pages/governance";
import ApprovalDetailPage from "@/pages/governance/[id]";
import PoliciesPage from "@/pages/governance/PoliciesPage";
import ForgeRouterPage from "@/pages/forgerouter";
import ObsidianPage from "@/pages/obsidian";
import HindsightPage from "@/pages/hindsight";
import FoundationPage from "@/pages/foundation";
import CronsPage from "@/pages/crons";
import SystemControlPage from "@/pages/system-control";
import DeployPage from "@/pages/deploy";
import ServersPage from "@/pages/servers";
import DatabaseLayout from "@/pages/database/DatabaseLayout";
import DatabaseSchemaPage from "@/pages/database/SchemaPage";
import DatabaseDiagramPage from "@/pages/database/DiagramPage";
import DatabaseQueryPage from "@/pages/database/QueryPage";
import UsersPage from "@/pages/users";
import ProfilesPage from "@/pages/profiles";
import PipelineTemplatesPage from "@/pages/pipeline-templates";
import NotificationsPage from "@/pages/notifications";
import NewsPage from "@/pages/news";
import SettingsPage from "@/pages/settings";
import ConceptionPage from "@/pages/conception";
import SystemMapPage from "@/pages/system-map";
import ProjectScopePage from "@/pages/project-scope";
import CockpitPage from "@/pages/cockpit";

import ScreenInspectorPage from "@/pages/screen-inspector";
import ConceptErdViewerPage from "@/pages/concept-erd";
import VersionClosurePage from "@/pages/version-closure";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const location = useLocation();
  if (!token) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="workspace" element={<WorkspacePage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route path="news" element={<NewsPage />} />
        <Route path="conception" element={<ConceptionPage />} />
        <Route path="system-map" element={<SystemMapPage />} />
        <Route path="project-scope" element={<ProjectScopePage />} />
        <Route path="product" element={<ProductPage />} />
        <Route path="product/:id" element={<ProductDetail />} />
        <Route path="projects" element={<ProjectPage />} />
        <Route path="projects/:id" element={<ProjectDetailPage />} />
        <Route path="pipeline" element={<PipelinePage />} />
        <Route path="pipeline/:id" element={<PipelineDetailPage />} />
        <Route path="pipeline-templates" element={<PipelineTemplatesPage />} />
        <Route path="backlog" element={<BacklogPage />} />
        <Route path="backlog/:id" element={<PlanningItemDetailPage />} />
        <Route path="tasks" element={<TaskPage />} />
        <Route path="tasks/:id" element={<TaskDetailPage />} />
        <Route path="agents" element={<AgentPage />} />
        <Route path="agents/:id" element={<AgentDetailPage />} />
        <Route path="tools" element={<ToolsPage />} />
        <Route path="mcp" element={<McpPage />} />
        <Route path="systems-hub" element={<SystemsHubPage />} />
        <Route path="prompt-commands" element={<PromptCommandsPage />} />
        <Route path="prompt-techniques" element={<PromptTechniquesPage />} />
        <Route path="skills" element={<SkillsPage />} />
        <Route path="artifact" element={<ArtifactPage />} />
        <Route path="artifact/:id" element={<ArtifactDetailPage />} />
        <Route path="governance" element={<GovernancePage />} />
        <Route path="governance/:id" element={<ApprovalDetailPage />} />
        <Route path="governance/policies" element={<PoliciesPage />} />
        <Route path="forgerouter" element={<ForgeRouterPage />} />
        <Route path="obsidian" element={<ObsidianPage />} />
        <Route path="hindsight" element={<HindsightPage />} />
        <Route path="foundation" element={<FoundationPage />} />
        <Route path="crons" element={<CronsPage />} />
        <Route path="system-control" element={<SystemControlPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="auditor" element={<AuditorPage />} />
        <Route path="demands" element={<DemandsPage />} />
        <Route path="agent-activity" element={<AgentActivityPage />} />
        <Route path="docs" element={<DocsPage />} />
        <Route path="deploy" element={<DeployPage />} />
        <Route path="servers" element={<ServersPage />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="profiles" element={<ProfilesPage />} />
        
        <Route path="screen-inspector" element={<ScreenInspectorPage />} />
        <Route path="concept-erd" element={<ConceptErdViewerPage />} />
        <Route path="screen-rules" element={<ScreenInspectorPage />} />
        <Route path="version-closure" element={<VersionClosurePage />} />
        <Route path="cockpit" element={<CockpitPage />} />
        <Route path="database" element={<DatabaseLayout />}>
          <Route index element={<DatabaseSchemaPage />} />
          <Route path="schema" element={<DatabaseSchemaPage />} />
          <Route path="diagram" element={<DatabaseDiagramPage />} />
          <Route path="query" element={<DatabaseQueryPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
```
