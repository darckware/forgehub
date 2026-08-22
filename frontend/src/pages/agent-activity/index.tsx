import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ListChecks } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AgentActivityLegend, AgentActivityStage } from "@/components/AgentActivityStage";
import { AgentActivityTasksDialog } from "@/components/AgentActivityTasksDialog";
import { useAgentActivityViewModel } from "@/hooks/useAgentActivityViewModel";

/** Live "data center floor" view of real agent-to-agent traffic: every
 * animation on the board (packets flying, working glow, speech bubbles) is
 * seeded straight from ForgeHub Messages (`useDemands`, already polling
 * every 3s while something is in flight) -- see
 * useAgentActivityViewModel's own docstring. The "Tarefas em execução"
 * button opens a plain list of the same underlying rows for anyone who
 * wants to read subjects/results as text instead of watching the board. */
export default function AgentActivityPage() {
  const { t } = useTranslation("agentActivity");
  const { nodes, packets, tasks, runningCount, anyRunning, isEmpty } = useAgentActivityViewModel();
  const [showTasks, setShowTasks] = useState(false);

  return (
    <div className="space-y-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button variant="outline" className="gap-2" onClick={() => setShowTasks(true)}>
          <ListChecks className="h-4 w-4" />
          {t("openTasks")}
          {runningCount > 0 && (
            <Badge variant="warning" className="ml-1">
              {runningCount}
            </Badge>
          )}
        </Button>
      </div>

      {isEmpty ? (
        <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border/60 text-sm text-muted-foreground">
          {t("emptyState")}
        </div>
      ) : (
        <AgentActivityStage nodes={nodes} packets={packets} anyRunning={anyRunning} />
      )}

      <AgentActivityLegend />

      {showTasks && <AgentActivityTasksDialog tasks={tasks} onClose={() => setShowTasks(false)} />}
    </div>
  );
}
