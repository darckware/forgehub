import { Fragment, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronRight } from "lucide-react";
import { AgentAvatar } from "@/components/AgentAvatar";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { isExternalRuntime, type Agent } from "@/hooks/useAgent";
import { cn } from "@/lib/utils";


export type AgentSortKey = "name" | "function" | "organization" | "runtime" | "status" | "inventory";
export type SortDirection = "asc" | "desc";

function functionText(agent: Agent): string {
  return agent.mission || agent.description || `${agent.agent_type} agent`;
}

function organizationText(agent: Agent): string {
  return [agent.department, agent.sector].filter(Boolean).join(" · ");
}

function sortValue(agent: Agent, key: AgentSortKey): string | number {
  switch (key) {
    case "name": return agent.name;
    case "function": return functionText(agent);
    case "organization": return organizationText(agent);
    case "runtime": return [agent.runtime_type, agent.runtime_tier].filter(Boolean).join(" ");
    case "status": return agent.status;
    case "inventory": return agent.sub_agents.length;
  }
}

export function sortAgents(agents: Agent[], key: AgentSortKey, direction: SortDirection): Agent[] {
  const multiplier = direction === "asc" ? 1 : -1;
  return [...agents].sort((left, right) => {
    const a = sortValue(left, key);
    const b = sortValue(right, key);
    const compared = typeof a === "number" && typeof b === "number"
      ? a - b
      : String(a).localeCompare(String(b), "pt-BR", { sensitivity: "base" });
    return compared * multiplier || left.name.localeCompare(right.name, "pt-BR") * multiplier;
  });
}

const STATUS_VARIANT: Record<string, "success" | "warning" | "outline"> = {
  active: "success",
  inactive: "warning",
  retired: "outline",
};

function SortableHead({
  sortKey,
  activeKey,
  direction,
  onSort,
  children,
  className,
}: {
  sortKey: AgentSortKey;
  activeKey: AgentSortKey;
  direction: SortDirection;
  onSort: (key: AgentSortKey) => void;
  children: ReactNode;
  className?: string;
}) {
  const active = sortKey === activeKey;
  const Icon = active ? (direction === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <TableHead
      aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}
      className={className}
    >
      <button
        type="button"
        className="group -ml-2 inline-flex h-9 cursor-pointer items-center gap-1 rounded-md px-2 text-left transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => onSort(sortKey)}
      >
        {children}
        <Icon className={cn("h-3.5 w-3.5", active ? "text-foreground" : "opacity-45 group-hover:opacity-80")} />
      </button>
    </TableHead>
  );
}

export function AgentRosterTable({
  agents,
  sortKey,
  sortDirection,
  expandedAgentId,
  onSort,
  onToggle,
  renderDetails,
  approvedSkillCount = () => 0,
}: {
  agents: Agent[];
  sortKey: AgentSortKey;
  sortDirection: SortDirection;
  expandedAgentId: string | null;
  onSort: (key: AgentSortKey) => void;
  onToggle: (agentId: string) => void;
  renderDetails: (agent: Agent) => ReactNode;
  approvedSkillCount?: (agentId: string) => number;
}) {
  const { t } = useTranslation("agent");
  const sortedAgents = sortAgents(agents, sortKey, sortDirection);

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <SortableHead sortKey="name" activeKey={sortKey} direction={sortDirection} onSort={onSort}>
            {t("roster.columns.agent")}
          </SortableHead>
          <SortableHead sortKey="function" activeKey={sortKey} direction={sortDirection} onSort={onSort} className="min-w-64">
            {t("roster.columns.function")}
          </SortableHead>
          <SortableHead sortKey="organization" activeKey={sortKey} direction={sortDirection} onSort={onSort}>
            {t("roster.columns.organization")}
          </SortableHead>
          <SortableHead sortKey="runtime" activeKey={sortKey} direction={sortDirection} onSort={onSort}>
            {t("roster.columns.runtime")}
          </SortableHead>
          <SortableHead sortKey="status" activeKey={sortKey} direction={sortDirection} onSort={onSort}>
            {t("roster.columns.status")}
          </SortableHead>
          <SortableHead sortKey="inventory" activeKey={sortKey} direction={sortDirection} onSort={onSort} className="text-right">
            {t("roster.columns.inventory")}
          </SortableHead>
          <TableHead className="w-12"><span className="sr-only">{t("roster.columns.details")}</span></TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sortedAgents.map((agent) => {
          const expanded = expandedAgentId === agent.id;
          const detailId = `agent-detail-${agent.id}`;
          return (
            <Fragment key={agent.id}>
              <TableRow
                className={cn(
                  "group cursor-pointer",
                  expanded && "border-b-0 bg-muted/50",
                  !agent.is_active && "opacity-70",
                )}
                onClick={() => onToggle(agent.id)}
              >
                <TableCell>
                  <button
                    type="button"
                    className="flex min-w-44 cursor-pointer items-center gap-3 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    aria-expanded={expanded}
                    aria-controls={detailId}
                    aria-label={t(expanded ? "roster.collapseAgent" : "roster.expandAgent", { name: agent.name })}
                    onClick={(event) => {
                      event.stopPropagation();
                      onToggle(agent.id);
                    }}
                  >
                    <AgentAvatar name={agent.name} avatarDataUrl={agent.avatar_data_url} size="sm" />
                    <span className="min-w-0">
                      <span className="block truncate font-semibold text-foreground">{agent.name}</span>
                      {agent.profile_slug && <code className="block truncate text-[11px] text-muted-foreground">{agent.profile_slug}</code>}
                    </span>
                  </button>
                </TableCell>
                <TableCell className="max-w-sm"><span className="line-clamp-2 text-muted-foreground">{functionText(agent)}</span></TableCell>
                <TableCell className="max-w-56 text-xs text-muted-foreground">{organizationText(agent) || t("roster.notDefined")}</TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1">
                    {agent.runtime_type && (
                      <Badge variant={isExternalRuntime(agent.runtime_type) ? "warning" : "secondary"}>
                        {t(`runtimes.${agent.runtime_type}`)}
                      </Badge>
                    )}
                    {agent.runtime_tier && <Badge variant="outline">{t("detail.tierBadge", { tier: agent.runtime_tier })}</Badge>}
                  </div>
                </TableCell>
                <TableCell><Badge variant={STATUS_VARIANT[agent.status] ?? "outline"}>{t(`roster.status.${agent.status}`)}</Badge></TableCell>
                <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                  {t("roster.inventory", { skills: approvedSkillCount(agent.id), workers: agent.sub_agents.length })}
                </TableCell>
                <TableCell className="text-right">
                  {expanded ? <ChevronDown className="ml-auto h-4 w-4 text-primary" /> : <ChevronRight className="ml-auto h-4 w-4 text-muted-foreground group-hover:text-foreground" />}
                </TableCell>
              </TableRow>
              {expanded && (
                <TableRow className="border-b bg-muted/20 hover:bg-muted/20">
                  <TableCell id={detailId} colSpan={7} className="border-l-2 border-l-primary/50 p-5">
                    {renderDetails(agent)}
                  </TableCell>
                </TableRow>
              )}
            </Fragment>
          );
        })}
      </TableBody>
    </Table>
  );
}
