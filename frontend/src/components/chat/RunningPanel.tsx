import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Activity, AlertCircle, Bot, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleSlash, Loader2, Send } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { useAgents } from "@/hooks/useAgent";
import { useDemands } from "@/hooks/useDemands";
import type { ChatSubagent, SubagentStatus, SubagentStep } from "@/lib/chatSubagents";
import { cn } from "@/lib/utils";

/**
 * "Em execução" -- the agents working for this conversation right now
 * (2026-09-26, Marcelo: "preciso visualizar as tarefas dos subagentes caso eu
 * queira trocar o display na tela. Tem que aparecer as listas dos agentes em
 * execução", for both kinds he asked for):
 *   - Claude Code subagents launched inside a turn (see lib/chatSubagents.ts),
 *   - delegations sent through Messages mid-conversation (the demand numbers
 *     the trail already knows from send_agent_message).
 * Picking one swaps the panel's body to that agent's own steps and output;
 * "Principal" swaps back. Finished ones stay listed (collapsed) so their
 * output can still be read after the turn ends.
 *
 * Steps and the delegation card are rendered by the caller (ChatPane owns
 * QueueStepsList/SubagentStatusCard) -- passing them in avoids a circular
 * import with ChatPane.
 */

type Selection = { kind: "subagent"; id: string } | { kind: "delegation"; number: number } | null;

const TERMINAL_DISPATCH = new Set(["completed", "failed"]);

function StatusIcon({ status }: { status: SubagentStatus | "dispatched" | null | undefined }) {
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-600" />;
  if (status === "failed") return <AlertCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />;
  if (status === "stopped") return <CircleSlash className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
  return <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />;
}

export function RunningPanel({
  subagents,
  delegationNumbers,
  renderSteps,
  renderDelegation,
}: {
  subagents: ChatSubagent[];
  /** Messages delegations made from this conversation, oldest first. */
  delegationNumbers: number[];
  renderSteps: (steps: SubagentStep[]) => ReactNode;
  renderDelegation: (demandNumber: number) => ReactNode;
}) {
  const { t } = useTranslation("chat");
  const { data: demands } = useDemands();
  const { data: agents } = useAgents();
  const [open, setOpen] = useState(true);
  const [showFinished, setShowFinished] = useState(false);
  const [selection, setSelection] = useState<Selection>(null);

  const delegations = useMemo(
    () =>
      delegationNumbers
        .map((number) => ({ number, demand: demands?.find((d) => d.number === number) }))
        .map(({ number, demand }) => ({
          number,
          demand,
          running: !demand || !TERMINAL_DISPATCH.has(demand.dispatch_status ?? ""),
          agentName: agents?.find((a) => a.id === demand?.target_agent_id)?.name ?? "?",
        })),
    [delegationNumbers, demands, agents]
  );

  const runningSubagents = subagents.filter((s) => s.status === "running");
  const finishedSubagents = subagents.filter((s) => s.status !== "running");
  const runningDelegations = delegations.filter((d) => d.running);
  const finishedDelegations = delegations.filter((d) => !d.running);
  const runningCount = runningSubagents.length + runningDelegations.length;
  const finishedCount = finishedSubagents.length + finishedDelegations.length;

  if (runningCount + finishedCount === 0) return null;

  const selectedSubagent = selection?.kind === "subagent" ? subagents.find((s) => s.id === selection.id) : undefined;
  const selectedDelegation = selection?.kind === "delegation" ? delegations.find((d) => d.number === selection.number) : undefined;

  const statusLabel = (status: SubagentStatus) => t(`running.status.${status}`);

  const subagentRow = (sub: ChatSubagent) => (
    <button
      key={sub.id}
      type="button"
      onClick={() => setSelection({ kind: "subagent", id: sub.id })}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent"
    >
      <StatusIcon status={sub.status} />
      <Bot className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{sub.description || t("running.subagentFallback")}</span>
        <span className="block truncate text-muted-foreground">
          {sub.subagentType || t("running.subagentFallback")}
          {sub.status === "running" && sub.lastTool ? ` · ${t("running.lastTool", { tool: sub.lastTool })}` : ""}
          {sub.status !== "running" ? ` · ${statusLabel(sub.status)}` : ""}
        </span>
      </span>
      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
    </button>
  );

  const delegationRow = (d: (typeof delegations)[number]) => (
    <button
      key={d.number}
      type="button"
      onClick={() => setSelection({ kind: "delegation", number: d.number })}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-accent"
    >
      <StatusIcon status={d.running ? "running" : d.demand?.dispatch_status === "failed" ? "failed" : "completed"} />
      <Send className="h-3.5 w-3.5 shrink-0 text-sky-500" />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">
          {t("running.delegation", { number: d.number, agent: d.agentName })}
        </span>
        {d.demand?.subject && <span className="block truncate text-muted-foreground">{d.demand.subject}</span>}
      </span>
      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
    </button>
  );

  return (
    <div className="mx-auto mb-2 w-full max-w-4xl rounded-lg border border-border bg-card text-card-foreground shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium"
      >
        <Activity className={cn("h-3.5 w-3.5", runningCount > 0 ? "text-primary" : "text-muted-foreground")} />
        {t("running.title")}
        <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums">{runningCount}</span>
        <span className="flex-1" />
        {open ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
      </button>

      {open && (
        <div className="max-h-[40vh] overflow-y-auto border-t border-border px-1.5 py-1.5">
          {selection && (selectedSubagent || selectedDelegation) ? (
            <div className="space-y-2 px-1.5 pb-1">
              <button
                type="button"
                onClick={() => setSelection(null)}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                <ChevronLeft className="h-3.5 w-3.5" /> {t("running.main")}
              </button>
              {selectedSubagent && (
                <>
                  <div className="flex items-start gap-2">
                    <StatusIcon status={selectedSubagent.status} />
                    <div className="min-w-0">
                      <p className="break-words text-sm font-medium">{selectedSubagent.description || t("running.subagentFallback")}</p>
                      <p className="text-xs text-muted-foreground">
                        {selectedSubagent.subagentType} · {statusLabel(selectedSubagent.status)}
                      </p>
                    </div>
                  </div>
                  {selectedSubagent.steps.length > 0 && <div className="space-y-1">{renderSteps(selectedSubagent.steps)}</div>}
                  {selectedSubagent.text ? (
                    <div className="rounded-md bg-muted/40 px-3 py-2 text-sm [overflow-wrap:anywhere]">
                      <Markdown content={selectedSubagent.text} />
                    </div>
                  ) : selectedSubagent.summary ? (
                    <p className="text-sm text-muted-foreground">{selectedSubagent.summary}</p>
                  ) : (
                    <p className="text-xs italic text-muted-foreground">{t("running.noOutput")}</p>
                  )}
                </>
              )}
              {selectedDelegation && (
                <>
                  {renderDelegation(selectedDelegation.number)}
                  {selectedDelegation.demand?.subject && (
                    <p className="break-words text-sm font-medium">{selectedDelegation.demand.subject}</p>
                  )}
                  {selectedDelegation.demand?.dispatch_result ? (
                    <div className="rounded-md bg-muted/40 px-3 py-2 text-sm [overflow-wrap:anywhere]">
                      <Markdown content={selectedDelegation.demand.dispatch_result} />
                    </div>
                  ) : (
                    <p className="text-xs italic text-muted-foreground">{t("running.noOutput")}</p>
                  )}
                </>
              )}
            </div>
          ) : (
            <>
              {runningCount === 0 && <p className="px-2 py-1 text-xs italic text-muted-foreground">{t("running.noneRunning")}</p>}
              {runningSubagents.map(subagentRow)}
              {runningDelegations.map(delegationRow)}
              {finishedCount > 0 && (
                <>
                  <button
                    type="button"
                    onClick={() => setShowFinished((v) => !v)}
                    className="mt-1 flex w-full items-center gap-1 px-2 py-1 text-left text-[11px] font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground"
                  >
                    {showFinished ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                    {t("running.finished", { count: finishedCount })}
                  </button>
                  {showFinished && (
                    <>
                      {finishedSubagents.map(subagentRow)}
                      {finishedDelegations.map(delegationRow)}
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
