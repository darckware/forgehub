import { useTranslation } from "react-i18next";
import { Plug } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { McpServerManager } from "@/components/mcp/McpServerManager";
import { useAgentMcpServers, type Agent } from "@/hooks/useAgent";

/**
 * The MCP servers this agent's runtime loads, on the agent's own page.
 *
 * The backend answers 400 for an agent whose runtime cannot load MCP servers
 * at all (registered with no runtime_type) — that is shown as an explanation,
 * not as a failed card, since it is a property of the agent rather than a
 * fault. The same panel is reused on the /mcp page for the whole roster.
 */
export function AgentMcpServersCard({ agent }: { agent: Agent }) {
  const { t } = useTranslation("agent");
  const { data, isLoading, isError, error } = useAgentMcpServers(agent.id);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Plug className="h-5 w-5" />
          {t("mcp.title")}
        </CardTitle>
        <CardDescription>{t("mcp.description")}</CardDescription>
      </CardHeader>
      <CardContent>
        <McpServerManager
          agentId={agent.id}
          data={data}
          isLoading={isLoading}
          errorMessage={isError ? (error as Error)?.message : undefined}
        />
      </CardContent>
    </Card>
  );
}
