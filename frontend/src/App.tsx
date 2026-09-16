import { Navigate, Routes, Route, useLocation } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { RequireAdmin } from "@/components/auth/RequireAdmin";
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
import ClientsPage from "@/pages/clients";
import NexoAgentsPage from "@/pages/nexo-agents";
import NewClientPage from "@/pages/clients/new";
import ClientDetailPage from "@/pages/clients/[id]";
import IrregularitiesPage from "@/pages/irregularities";
import DatabaseLayout from "@/pages/database/DatabaseLayout";
import DatabaseSchemaPage from "@/pages/database/SchemaPage";
import DatabaseDiagramPage from "@/pages/database/DiagramPage";
import DatabaseQueryPage from "@/pages/database/QueryPage";
import UsersPage from "@/pages/users";
import ProfilesPage from "@/pages/profiles";
import PipelineTemplatesPage from "@/pages/pipeline-templates";
import NotificationsPage from "@/pages/notifications";
import SettingsPage from "@/pages/settings";
import ConceptionPage from "@/pages/conception";
import SystemMapPage from "@/pages/system-map";
import ProjectScopePage from "@/pages/project-scope";
import CockpitPage from "@/pages/cockpit";
import VpnPage from "@/pages/vpn";

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
        <Route path="clients" element={<ClientsPage />} />
        <Route path="nexo-agents" element={<RequireAdmin><NexoAgentsPage /></RequireAdmin>} />
        <Route path="clients/new" element={<NewClientPage />} />
        <Route path="clients/:id" element={<ClientDetailPage />} />
        <Route path="irregularities" element={<IrregularitiesPage />} />
        <Route path="vpn" element={<RequireAdmin><VpnPage /></RequireAdmin>} />
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
