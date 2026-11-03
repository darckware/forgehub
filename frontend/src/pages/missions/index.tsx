import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDuration } from "@/components/missions/missionFormat";
import { useMissions, type MissionFilters } from "@/hooks/useMissions";
import { cn } from "@/lib/utils";

const STATES = ["active", "verifying", "awaiting_acceptance", "ready", "planning", "paused", "draft", "completed", "cancelled"];

/** /missions — every mission the viewer may read (§8), active first, then
 * by priority (lower = more urgent) and deadline. */
export default function MissionsPage() {
  const { t } = useTranslation("missions");
  const [filters, setFilters] = useState<MissionFilters>({ states: [], q: "", hasConflicts: false, hasUncertain: false });
  const query = useMissions(filters);
  const items = query.data?.items ?? [];
  const toggleState = (state: string) => setFilters((f) => ({
    ...f, states: f.states.includes(state) ? f.states.filter((s) => s !== state) : [...f.states, state],
  }));

  return (
    <div className="space-y-4">
      <PageHeader title={t("list.title")} description={t("list.description")} />
      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <Input aria-label={t("list.search")} placeholder={t("list.search")} value={filters.q}
          onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} className="sm:max-w-xs max-md:text-base" />
        <div className="flex flex-wrap gap-1">
          {STATES.map((state) => (
            <button key={state} type="button" onClick={() => toggleState(state)} aria-pressed={filters.states.includes(state)}
              className={cn("rounded-full border px-2 py-0.5 text-xs", filters.states.includes(state) && "border-primary bg-primary/10")}>
              {t(`state.${state}`)}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1 text-xs">
          <input type="checkbox" checked={filters.hasConflicts} onChange={(e) => setFilters((f) => ({ ...f, hasConflicts: e.target.checked }))} />
          {t("list.withConflicts")}
        </label>
        <label className="flex items-center gap-1 text-xs">
          <input type="checkbox" checked={filters.hasUncertain} onChange={(e) => setFilters((f) => ({ ...f, hasUncertain: e.target.checked }))} />
          {t("list.withUncertain")}
        </label>
      </div>

      {query.isLoading ? (
        <div className="space-y-2" data-testid="missions-loading" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => <div key={i} className="h-10 animate-pulse rounded bg-muted" />)}
        </div>
      ) : query.isError ? (
        <div role="alert" className="space-y-2 rounded-lg border p-4 text-sm">
          <p>{t("list.error")}</p>
          <Button size="sm" variant="outline" onClick={() => void query.refetch()}>{t("board.retry")}</Button>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground" data-testid="missions-empty">
          <p>{t("list.empty")}</p>
          <p className="text-xs">{t("list.emptyHint")}</p>
        </div>
      ) : (
        <>
          <div className="max-md:hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  {(["priority", "name", "state", "orchestrator", "progress", "running", "queued", "awaitingReview", "uncertain", "conflicts", "deadline", "lastDecision"] as const)
                    .map((col) => <TableHead key={col}>{t(`list.columns.${col}`)}</TableHead>)}
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((m) => (
                  <TableRow key={m.project_id}>
                    <TableCell className="font-mono text-xs">{m.priority}</TableCell>
                    <TableCell><Link className="font-medium text-primary hover:underline" to={`/missions/${m.project_id}`}>{m.name}</Link></TableCell>
                    <TableCell><Badge variant="outline">{t(`state.${m.state}`, m.state)}</Badge></TableCell>
                    <TableCell className="text-xs">{m.orchestrator.name}</TableCell>
                    <TableCell className="text-xs">{m.progress.done_proven}/{m.progress.total}</TableCell>
                    <TableCell className="text-xs">{m.running}</TableCell>
                    <TableCell className="text-xs">{m.queued}</TableCell>
                    <TableCell className="text-xs">{m.awaiting_review}</TableCell>
                    <TableCell className={cn("text-xs", m.uncertain && "font-semibold text-red-600")}>{m.uncertain}</TableCell>
                    <TableCell className={cn("text-xs", m.conflicts && "font-semibold text-red-600")}>{m.conflicts}{m.warnings ? ` (+${m.warnings})` : ""}</TableCell>
                    <TableCell className="text-xs">{m.deadline_at ? formatDuration(m.remaining_seconds) : "—"}</TableCell>
                    <TableCell className="text-xs">{m.last_decision ? `${m.last_decision.event_type} · ${m.last_decision.actor ?? ""}` : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="space-y-2 md:hidden">
            {items.map((m) => (
              <Link key={m.project_id} to={`/missions/${m.project_id}`} className="block space-y-1 rounded-lg border bg-card p-3 text-sm">
                <div className="flex items-start justify-between gap-2">
                  <span className="break-words font-medium">{m.name}</span>
                  <Badge variant="outline" className="shrink-0">{t(`state.${m.state}`, m.state)}</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  P{m.priority} · {m.orchestrator.name} · {m.progress.done_proven}/{m.progress.total} · {t("list.columns.running")} {m.running}
                  {m.conflicts ? ` · ${t("list.columns.conflicts")} ${m.conflicts}` : ""}
                </p>
              </Link>
            ))}
          </div>
        </>
      )}

      {(query.data?.contested_agents.length ?? 0) > 0 && (
        <section className="space-y-1 rounded-lg border p-3 text-sm" data-testid="contested-agents">
          <h2 className="text-xs font-semibold uppercase text-muted-foreground">{t("list.contested")}</h2>
          <ul className="space-y-1 text-xs">
            {query.data!.contested_agents.map((agent) => (
              <li key={agent.agent_id} className="break-words">
                <b>{agent.name}</b>: {agent.missions.map((m) => `${m.name} (P${m.priority})`).join(", ")} —{" "}
                {t("list.contestedWinner", { name: agent.missions.find((m) => m.project_id === agent.winner_project_id)?.name })}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
