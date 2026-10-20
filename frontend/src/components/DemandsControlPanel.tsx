import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Building2, Loader2, User, Users, Workflow } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { NO_AGENT_ID } from "@/components/AgentInboxTree";
import { useAgents } from "@/hooks/useAgent";
import { useProjects } from "@/hooks/useProject";
import type { Demand, DemandStatus } from "@/hooks/useDemands";

type Dimension = "project" | "agent" | "login";

interface Bucket {
  key: string;
  label: string;
  demands: Demand[];
}

const STATUS_DOT: Record<DemandStatus, string> = {
  new: "bg-primary",
  read: "bg-muted-foreground",
  converted: "bg-emerald-600",
  archived: "bg-muted-foreground/50",
};

function formatDate(value: string): string {
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString();
}

export function DemandsControlPanel({
  demands,
  onOpenDemand,
}: {
  demands: Demand[];
  /** Jumps back to the Mensagens tab with this item selected -- see
   * DemandsPage's openFromControl. */
  onOpenDemand: (demand: Demand) => void;
}) {
  const { t } = useTranslation("demands");
  const { data: agents, isLoading: agentsLoading } = useAgents();
  const { data: projects, isLoading: projectsLoading } = useProjects();
  const [dimension, setDimension] = useState<Dimension>("project");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const agentNames = useMemo(() => new Map((agents ?? []).map((a) => [a.id, a.name])), [agents]);
  const projectNames = useMemo(() => new Map((projects ?? []).map((p) => [p.id, p.name])), [projects]);

  const buckets = useMemo<Bucket[]>(() => {
    const map = new Map<string, Bucket>();
    function push(key: string, label: string, demand: Demand) {
      let bucket = map.get(key);
      if (!bucket) {
        bucket = { key, label, demands: [] };
        map.set(key, bucket);
      }
      bucket.demands.push(demand);
    }

    for (const d of demands) {
      if (dimension === "project") {
        const key = d.project_id ?? "__no_project__";
        const label = d.project_id ? projectNames.get(d.project_id) ?? d.project_id : t("control.noProject");
        push(key, label, d);
      } else if (dimension === "agent") {
        // One bucket per item -- prefer the addressee (this is who the
        // item is "about" from a work-queue point of view), falling back
        // to the sender, falling back to Sistema. Deliberately a single
        // bucket per demand (unlike the graph's from->to edges) so every
        // row in this control shows up in exactly one place.
        const agentId = d.target_agent_id ?? d.from_agent_id ?? null;
        const key = agentId ?? NO_AGENT_ID;
        const label = agentId ? agentNames.get(agentId) ?? agentId : t("systemLabel");
        push(key, label, d);
      } else {
        const key = d.from_agent_id ? "__agents__" : d.from_agent;
        const label = d.from_agent_id ? t("control.agentsBucket") : d.from_agent;
        push(key, label, d);
      }
    }
    return [...map.values()].sort((a, b) => b.demands.length - a.demands.length);
  }, [demands, dimension, agentNames, projectNames, t]);

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const isLoading = dimension === "project" ? projectsLoading : dimension === "agent" ? agentsLoading : false;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold">
            <Workflow className="h-4 w-4 text-muted-foreground" />
            {t("control.title")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("control.subtitle")}</p>
        </div>
        <div className="flex items-center gap-1 rounded-md bg-muted p-1">
          <Button
            size="sm"
            variant="ghost"
            className={cn("h-7 gap-1.5 px-2.5", dimension === "project" && "bg-background shadow-sm")}
            onClick={() => setDimension("project")}
          >
            <Building2 className="h-3.5 w-3.5" /> {t("control.dimension.project")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className={cn("h-7 gap-1.5 px-2.5", dimension === "agent" && "bg-background shadow-sm")}
            onClick={() => setDimension("agent")}
          >
            <Users className="h-3.5 w-3.5" /> {t("control.dimension.agent")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className={cn("h-7 gap-1.5 px-2.5", dimension === "login" && "bg-background shadow-sm")}
            onClick={() => setDimension("login")}
          >
            <User className="h-3.5 w-3.5" /> {t("control.dimension.login")}
          </Button>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> {t("control.loading")}
        </div>
      )}

      {!isLoading && buckets.length === 0 && (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-border/60 text-sm text-muted-foreground">
          {t("overview.emptyState")}
        </div>
      )}

      <div className="space-y-2">
        {buckets.map((bucket) => {
          const isOpen = expanded.has(bucket.key);
          return (
            <Card key={bucket.key}>
              <button
                type="button"
                onClick={() => toggle(bucket.key)}
                className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
              >
                <span className="font-medium">{bucket.label}</span>
                <Badge variant="secondary">{bucket.demands.length}</Badge>
              </button>
              {isOpen && (
                <CardContent className="pt-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-6" />
                        <TableHead>{t("control.table.subject")}</TableHead>
                        <TableHead>{t("control.table.from")}</TableHead>
                        <TableHead>{t("control.table.status")}</TableHead>
                        <TableHead>{t("control.table.date")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {[...bucket.demands]
                        .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                        .map((d) => (
                          <TableRow key={d.id} className="cursor-pointer" onClick={() => onOpenDemand(d)}>
                            <TableCell>
                              <span className={cn("block h-2 w-2 rounded-full", STATUS_DOT[d.status])} />
                            </TableCell>
                            <TableCell className="max-w-xs truncate">
                              <span className="text-muted-foreground">#{d.number}</span> {d.subject}
                            </TableCell>
                            <TableCell className="text-muted-foreground">{d.from_agent}</TableCell>
                            <TableCell className="text-muted-foreground">{d.status}</TableCell>
                            <TableCell className="text-muted-foreground">{formatDate(d.created_at)}</TableCell>
                          </TableRow>
                        ))}
                    </TableBody>
                  </Table>
                </CardContent>
              )}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
