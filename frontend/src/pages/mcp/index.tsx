import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plug,
  RefreshCw,
  Server,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { McpServerManager } from "@/components/mcp/McpServerManager";
import {
  useAgentsMcpOverview,
  useSyncAgentRuntimes,
  type AgentMcpOverviewItem,
} from "@/hooks/useAgent";

/**
 * Ecosystem-wide MCP control: which agent loads which MCP server, and the
 * editor for each one.
 *
 * The coverage matrix is the reason this page exists rather than only the
 * per-agent card: the operational question is "which agents still lack this
 * server", which is unanswerable one agent page at a time across thirteen
 * agents. Each row expands into the same editor the agent page embeds, so
 * closing a gap does not mean navigating away.
 *
 * Every cell reflects a real runtime config file, not a ForgeHub record —
 * an agent whose runtime cannot load MCP servers at all is listed as
 * unsupported instead of being hidden.
 */

function CoverageCell({ agent, server }: { agent: AgentMcpOverviewItem; server: string }) {
  const { t } = useTranslation("agent");
  const match = agent.servers.find((s) => s.name === server);
  if (!match) {
    return <span className="text-muted-foreground/40">—</span>;
  }
  return match.enabled ? (
    <Badge variant="success" className="font-normal">
      {t("mcp.page.present")}
    </Badge>
  ) : (
    <Badge variant="outline" className="font-normal">
      {t("mcp.disabled")}
    </Badge>
  );
}

function AgentPanel({ agent }: { agent: AgentMcpOverviewItem }) {
  const { t } = useTranslation("agent");
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full flex-wrap items-center justify-between gap-3 p-3 text-left hover:bg-muted/40"
      >
        <span className="flex min-w-0 items-center gap-2">
          {open ? (
            <ChevronDown className="h-4 w-4 shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0" />
          )}
          <span className="font-medium">{agent.agent_name}</span>
          <Badge variant="outline" className="font-mono text-[10px]">
            {agent.runtime_type ?? t("mcp.page.noRuntime")}
          </Badge>
          {!agent.supported && (
            <Badge variant="outline" className="font-normal">
              {t("mcp.page.unsupported")}
            </Badge>
          )}
          {agent.error && <AlertTriangle className="h-4 w-4 text-destructive" />}
        </span>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          {agent.supported && t("mcp.page.serverCount", { count: agent.servers.length })}
        </span>
      </button>

      {open && (
        <div className="border-t p-3">
          {agent.supported ? (
            <>
              <McpServerManager agentId={agent.agent_id} data={agent} />
              <div className="mt-3 text-right">
                <Link
                  to={`/agents/${agent.agent_id}`}
                  className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                >
                  {t("mcp.page.openAgent")}
                </Link>
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{t("mcp.page.unsupportedHelp")}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function McpPage() {
  const { t } = useTranslation("agent");
  const { data, isLoading, isError, error, isFetching, refetch } = useAgentsMcpOverview();
  // The real sync: reads each runtime off the host instead of the Foundation
  // docs, which is what left an installed agent showing as "no runtime".
  const sync = useSyncAgentRuntimes();

  const agents = useMemo(() => data?.agents ?? [], [data]);
  const supported = useMemo(() => agents.filter((a) => a.supported), [agents]);
  const serverNames = useMemo(() => {
    const names = new Set<string>();
    for (const agent of agents) for (const server of agent.servers) names.add(server.name);
    return [...names].sort();
  }, [agents]);

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-bold">
            <Plug className="h-7 w-7" />
            {t("mcp.page.title")}
          </h1>
          <p className="mt-1 text-muted-foreground">{t("mcp.page.subtitle")}</p>
        </div>
        {/* Reconciles every agent's runtime against the host and re-reads the
            MCP configs. Both halves of this screen are keyed by the roster, so
            without this a stale one shows agents that no longer exist -- and an
            agent whose runtime was never registered shows as unsupported even
            with its MCP config sitting on disk. */}
        <Button
          variant="outline"
          title={t("mcp.page.syncTooltip")}
          onClick={() => sync.mutate(undefined, { onSettled: () => void refetch() })}
          disabled={sync.isPending || isFetching}
        >
          {sync.isPending || isFetching ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          {t("mcp.page.sync")}
        </Button>
      </div>

      {sync.isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-4 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("list.syncError", { message: (sync.error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {sync.isSuccess && sync.data && (
        <Card>
          <CardContent className="space-y-2 py-4 text-sm">
            <p>
              {t("mcp.page.syncResult", {
                checked: sync.data.checked,
                updated: sync.data.updated,
              })}
            </p>
            {sync.data.agents
              .filter((a) => a.applied)
              .map((a) => (
                <p key={a.agent_id} className="text-muted-foreground">
                  • {a.agent_name} → <code>{a.runtime_type}</code> ({a.evidence})
                </p>
              ))}
            {sync.data.agents
              .flatMap((a) => a.issues.map((issue) => ({ id: a.agent_id + issue, a, issue })))
              .map(({ id, a, issue }) => (
                <p key={id} className="flex items-start gap-2 text-amber-500">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    <strong>{a.agent_name}</strong>: {issue}
                  </span>
                </p>
              ))}
            {sync.data.unregistered_profiles.length > 0 && (
              <p className="text-muted-foreground">
                {t("mcp.page.unregisteredProfiles", {
                  profiles: sync.data.unregistered_profiles.join(", "),
                })}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("mcp.loading")}
        </div>
      )}

      {isError && (
        <p className="text-sm text-destructive">
          {t("mcp.page.loadError", { message: (error as Error)?.message })}
        </p>
      )}

      {!isLoading && !isError && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Server className="h-5 w-5" />
                {t("mcp.page.coverageTitle")}
              </CardTitle>
              <CardDescription>{t("mcp.page.coverageDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              {serverNames.length === 0 ? (
                <p className="rounded-md border border-dashed p-6 text-center text-sm italic text-muted-foreground">
                  {t("mcp.page.noServers")}
                </p>
              ) : (
                // Thirteen agents -- the matrix scrolls sideways inside the
                // card rather than making the page scroll.
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="sticky left-0 bg-card">
                          {t("mcp.page.serverColumn")}
                        </TableHead>
                        {supported.map((agent) => (
                          <TableHead key={agent.agent_id} className="whitespace-nowrap text-center">
                            {agent.agent_name}
                          </TableHead>
                        ))}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {serverNames.map((server) => (
                        <TableRow key={server}>
                          <TableCell className="sticky left-0 bg-card font-mono text-xs font-medium">
                            {server}
                          </TableCell>
                          {supported.map((agent) => (
                            <TableCell key={agent.agent_id} className="text-center">
                              <CoverageCell agent={agent} server={server} />
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">{t("mcp.page.byAgentTitle")}</CardTitle>
              <CardDescription>{t("mcp.page.byAgentDescription")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {agents.map((agent) => (
                <AgentPanel key={agent.agent_id} agent={agent} />
              ))}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
