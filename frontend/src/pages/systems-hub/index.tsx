import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Boxes, FolderKanban, SquareTerminal, TestTube2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BackgroundTestsPanel } from "@/components/BackgroundTestsPanel";
import { McpCatalogPanel } from "@/components/mcp/McpCatalogPanel";
import { ProjectMcpServerManager } from "@/components/mcp/ProjectMcpServerManager";
import { useProjects } from "@/hooks/useProject";
import { useProjectMcpServers } from "@/hooks/useProjectMcp";

/**
 * Systems Hub -- distinct from `/mcp` (per-agent MCP editor, under
 * "Agents & AI"): this page is scoped to *systems* (Project/Product), not
 * agents. Three tabs per the plan: catalog (Fase 1), per-project MCP
 * servers (Fase 2), background app testing (Fase 3).
 */
export default function SystemsHubPage() {
  const { t } = useTranslation("systemsHub");
  const navigate = useNavigate();
  const { data: projects } = useProjects();
  const [tab, setTab] = useState("catalog");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");
  const selectedProject = projects?.find((p) => p.id === selectedProjectId);
  const { data: projectMcpServers, isLoading: projectMcpLoading } = useProjectMcpServers(
    selectedProjectId || undefined,
  );

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="catalog" className="gap-2">
            <Boxes className="h-4 w-4" />
            {t("tabs.catalog")}
          </TabsTrigger>
          <TabsTrigger value="project-mcp" className="gap-2">
            <FolderKanban className="h-4 w-4" />
            {t("tabs.projectMcp")}
          </TabsTrigger>
          <TabsTrigger value="background-tests" className="gap-2">
            <TestTube2 className="h-4 w-4" />
            {t("tabs.backgroundTests")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="catalog" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("catalog.title")}</CardTitle>
              <CardDescription>{t("catalog.description")}</CardDescription>
            </CardHeader>
            <CardContent>
              <McpCatalogPanel />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="project-mcp" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("projectMcp.title")}</CardTitle>
              <CardDescription>{t("projectMcp.description")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <select
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  className="flex h-9 w-full max-w-sm rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
                >
                  <option value="">{t("projectMcp.pickProject")}</option>
                  {(projects ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                {selectedProject?.working_directory_path && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0 gap-1.5"
                    onClick={() =>
                      navigate("/workspace", {
                        state: {
                          openTerminal: { label: selectedProject.name, cwd: selectedProject.working_directory_path },
                        },
                      })
                    }
                  >
                    <SquareTerminal className="h-4 w-4" />
                    {t("projectMcp.openTerminalHere")}
                  </Button>
                )}
              </div>

              {selectedProjectId && (
                <ProjectMcpServerManager
                  projectId={selectedProjectId}
                  servers={projectMcpServers}
                  isLoading={projectMcpLoading}
                  workingDirectoryPath={selectedProject?.working_directory_path ?? null}
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="background-tests" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("backgroundTests.title")}</CardTitle>
              <CardDescription>{t("backgroundTests.description")}</CardDescription>
            </CardHeader>
            <CardContent>
              <BackgroundTestsPanel />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
