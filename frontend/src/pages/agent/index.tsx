import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Bot, CornerDownRight, Loader2, RefreshCw, Send, Trash2 } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { AgentEcosystemHierarchy } from "@/components/AgentEcosystemHierarchy";
import {
  useAgents,
  useDeleteAgent,
  useDeleteSubAgent,
  useSyncHermesAgents,
  useSkills,
  type Agent,
  type SubAgent,
} from "@/hooks/useAgent";

type AgentRow =
  | { kind: "agent"; agent: Agent }
  | { kind: "sub-agent"; agent: Agent; subAgent: SubAgent };

function toRows(agents: Agent[]): AgentRow[] {
  return agents.flatMap((agent) => [
    { kind: "agent" as const, agent },
    ...(agent.sub_agents ?? []).map((subAgent) => ({
      kind: "sub-agent" as const,
      agent,
      subAgent,
    })),
  ]);
}

// Layer/tier label as shown in the table column (minus the Telegram flag,
// which is orthogonal to where the agent sits in the hierarchy).
function layerTierLabel(agent: Agent): string | null {
  if (!agent.layer) return null;
  return `${agent.layer}${agent.runtime_tier ? ` · Tier ${agent.runtime_tier}` : ""}`;
}

const TYPE_VARIANT: Record<
  string,
  "default" | "secondary" | "success" | "warning" | "outline" | "destructive"
> = {
  executor: "secondary",
  coordinator: "default",
  hybrid: "outline",
};

export default function AgentPage() {
  const { data: agents, isLoading, isError, error } = useAgents();
  const { data: skills = [] } = useSkills();
  const syncHermes = useSyncHermesAgents();
  const deleteAgent = useDeleteAgent();
  const deleteSubAgent = useDeleteSubAgent();
  const [typeFilter, setTypeFilter] = useState("");
  const [layerFilter, setLayerFilter] = useState("");
  const [deleting, setDeleting] = useState<AgentRow | null>(null);

  const typeOptions = [...new Set((agents ?? []).map((a) => a.agent_type))].sort();
  const layerOptions = [
    ...new Set((agents ?? []).flatMap((a) => (layerTierLabel(a) ? [layerTierLabel(a) as string] : []))),
  ].sort();

  // Filters apply to top-level agents; a matching agent keeps its sub-agent
  // rows, since those only make sense under their parent.
  const filteredAgents = (agents ?? []).filter(
    (a) =>
      (!typeFilter || a.agent_type === typeFilter) &&
      (!layerFilter || layerTierLabel(a) === layerFilter)
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Agents</h1>
          <p className="text-muted-foreground">
            Executors and coordinators registered for task assignment, with their sub-agents,
            skills, cost rates, and capacities.
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            title="Sync agents, sub-agents and skills from Hermes Foundation"
            onClick={() => syncHermes.mutate()}
            disabled={syncHermes.isPending}
          >
            {syncHermes.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Sync
          </Button>
          <AssistantToggleButton />
        </div>
      </div>

      {syncHermes.isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-4 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Hermes sync failed: {(syncHermes.error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {syncHermes.isSuccess && syncHermes.data && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Send className="h-4 w-4" />
              Hermes Foundation sync result
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-4 text-sm text-muted-foreground">
            <span>
              Agents: <strong className="text-foreground">{syncHermes.data.agents.created}</strong>{" "}
              created, <strong className="text-foreground">{syncHermes.data.agents.updated}</strong>{" "}
              updated
            </span>
            <span>
              Sub-agents:{" "}
              <strong className="text-foreground">{syncHermes.data.sub_agents.created}</strong>{" "}
              created,{" "}
              <strong className="text-foreground">{syncHermes.data.sub_agents.updated}</strong>{" "}
              updated
            </span>
            <span>
              Skills: <strong className="text-foreground">{syncHermes.data.skills.created}</strong>{" "}
              created, <strong className="text-foreground">{syncHermes.data.skills.updated}</strong>{" "}
              updated
            </span>
            <span>
              Skill grants:{" "}
              <strong className="text-foreground">{syncHermes.data.agent_skills.created}</strong>{" "}
              created
            </span>
            {syncHermes.data.warnings.length > 0 && (
              <span className="text-destructive">{syncHermes.data.warnings.join("; ")}</span>
            )}
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && agents && <AgentEcosystemHierarchy agents={agents} skills={skills} />}

      {!isLoading && !isError && agents && agents.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="w-48"
            aria-label="Filter by type"
          >
            <option value="">All types</option>
            {typeOptions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
          <Select
            value={layerFilter}
            onChange={(e) => setLayerFilter(e.target.value)}
            className="w-56"
            aria-label="Filter by layer / tier"
          >
            <option value="">All layers / tiers</option>
            {layerOptions.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </Select>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          Loading agents…
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>Failed to load agents: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && agents && agents.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Bot className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">No agents yet</p>
              <p className="text-sm text-muted-foreground">
                Sync the Hermes Foundation roster above to register agents.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && agents && agents.length > 0 && filteredAgents.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No agents match the selected filters.
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && filteredAgents.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Layer / Tier</TableHead>
                  <TableHead>Sub-agents</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {toRows(filteredAgents).map((row) =>
                  row.kind === "agent" ? (
                    <TableRow key={row.agent.id}>
                      <TableCell>
                        <Link
                          to={`/agents/${row.agent.id}`}
                          className="font-medium hover:underline"
                        >
                          {row.agent.name}
                        </Link>
                        {row.agent.profile_slug && (
                          <p className="text-xs text-muted-foreground">`{row.agent.profile_slug}`</p>
                        )}
                        {!row.agent.profile_slug && row.agent.description && (
                          <p className="max-w-xs truncate text-xs text-muted-foreground">
                            {row.agent.description}
                          </p>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={TYPE_VARIANT[row.agent.agent_type] ?? "outline"}>
                          {row.agent.agent_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {row.agent.layer ? (
                          <span>
                            {row.agent.layer}
                            {row.agent.runtime_tier ? ` · Tier ${row.agent.runtime_tier}` : ""}
                            {row.agent.telegram_required ? " · Telegram" : ""}
                          </span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {row.agent.sub_agents?.length ?? 0}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Link
                            to={`/agents/${row.agent.id}`}
                            className={buttonVariants({ variant: "outline", size: "sm" })}
                          >
                            View
                          </Link>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="text-destructive"
                            title="Delete agent"
                            onClick={() => setDeleting(row)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    <TableRow key={row.subAgent.id} className="bg-muted/40">
                      <TableCell>
                        <div className="flex items-center gap-2 pl-6">
                          <CornerDownRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                          <span className="text-sm">{row.subAgent.name}</span>
                        </div>
                        {row.subAgent.description && (
                          <p className="max-w-xs truncate pl-9 text-xs text-muted-foreground">
                            {row.subAgent.description}
                          </p>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="text-xs">
                          sub-agent
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">—</TableCell>
                      <TableCell className="text-sm text-muted-foreground">—</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Link
                            to={`/agents/${row.agent.id}`}
                            className={buttonVariants({ variant: "ghost", size: "sm" })}
                          >
                            View parent
                          </Link>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="text-destructive"
                            title="Delete sub-agent"
                            onClick={() => setDeleting(row)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={deleting !== null}
        title={
          deleting?.kind === "sub-agent"
            ? `Delete sub-agent "${deleting.subAgent.name}"`
            : `Delete agent "${deleting?.agent.name ?? ""}"`
        }
        description={
          deleting?.kind === "sub-agent"
            ? "Removes this sub-agent's registration. This action cannot be undone."
            : "Removes the agent, its sub-agents and skill grants. This action cannot be undone."
        }
        confirmLabel="Delete"
        loading={deleteAgent.isPending || deleteSubAgent.isPending}
        onConfirm={() => {
          if (!deleting) return;
          if (deleting.kind === "sub-agent") {
            deleteSubAgent.mutate(
              { agentId: deleting.agent.id, subAgentId: deleting.subAgent.id },
              { onSuccess: () => setDeleting(null) }
            );
          } else {
            deleteAgent.mutate(deleting.agent.id, { onSuccess: () => setDeleting(null) });
          }
        }}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
