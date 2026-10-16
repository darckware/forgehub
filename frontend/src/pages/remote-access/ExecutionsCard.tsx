/** Execution log (decision 7, 2026-10-16: logs per agent): every run with who
 * asked -- a person, a schedule or an agent -- filterable by agent, person
 * and origin. Each row opens the execution screen. */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Bot, CalendarClock, CornerDownRight, ListChecks, User } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAgents } from "@/hooks/useAgent";
import { useHostExecutions, type ExecTrigger, type ExecutionLogFilters } from "@/hooks/useHostExecutions";
import { VerdictBadge } from "./VerdictBadge";

const ORIGIN_ICON = { manual: User, schedule: CalendarClock, agent: Bot } as const;

export function ExecutionsCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const [filters, setFilters] = useState<ExecutionLogFilters>({});
  const { data, isLoading, isError } = useHostExecutions(50, filters);
  const { data: agents } = useAgents();
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });
  const people = useMemo(() => [...new Set((data ?? []).map((e) => e.requested_by))].sort(), [data]);

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ListChecks className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> {t("executions.title")}
        </CardTitle>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Select aria-label={t("executions.filterAgent")} value={filters.agent_id ?? ""} onChange={(e) => setFilters((f) => ({ ...f, agent_id: e.target.value || undefined }))} className="max-md:text-base">
            <option value="">{t("executions.allAgents")}</option>
            {(agents ?? []).map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </Select>
          <Select aria-label={t("executions.filterPerson")} value={filters.requested_by ?? ""} onChange={(e) => setFilters((f) => ({ ...f, requested_by: e.target.value || undefined }))} className="max-md:text-base">
            <option value="">{t("executions.allPeople")}</option>
            {people.map((p) => <option key={p} value={p}>{p}</option>)}
          </Select>
          <Select aria-label={t("executions.filterOrigin")} value={filters.trigger ?? ""} onChange={(e) => setFilters((f) => ({ ...f, trigger: (e.target.value || undefined) as ExecTrigger | undefined }))} className="max-md:text-base">
            <option value="">{t("executions.allOrigins")}</option>
            <option value="manual">{t("executions.origins.manual")}</option>
            <option value="schedule">{t("executions.origins.schedule")}</option>
            <option value="agent">{t("executions.origins.agent")}</option>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="py-6 text-center text-sm text-muted-foreground" role="status">{t("loading")}</p>
        ) : isError ? (
          <p className="py-6 text-center text-sm text-destructive" role="alert">{t("executions.loadFailed")}</p>
        ) : !data?.length ? (
          <p className="py-6 text-center text-sm text-muted-foreground">{t("executions.empty")}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("executions.when")}</TableHead>
                <TableHead>{t("executions.origin")}</TableHead>
                <TableHead>{t("executions.command")}</TableHead>
                <TableHead>{t("executions.targets")}</TableHead>
                <TableHead>{t("executions.results")}</TableHead>
                <TableHead>{t("executions.verdict")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => {
                const Icon = ORIGIN_ICON[e.trigger] ?? User;
                return (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap text-xs">{fmt.format(new Date(e.started_at))}</TableCell>
                    <TableCell className="text-xs">
                      <span className="flex items-center gap-1.5">
                        <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-label={t(`executions.origins.${e.trigger}`)} />
                        <span>{e.agent_name ?? e.requested_by}</span>
                      </span>
                    </TableCell>
                    <TableCell className="max-w-xs">
                      <Link to={`/remote-access/executions/${e.id}`} className="flex items-start gap-1 text-xs hover:underline">
                        {e.parent_execution_id && <CornerDownRight className="mt-0.5 h-3 w-3 shrink-0" aria-label={t("executions.followUp")} />}
                        {e.script_name ? (
                          <span className="font-medium">{e.script_name} <span className="text-muted-foreground">v{e.script_version}</span></span>
                        ) : (
                          <span className="line-clamp-2 break-all font-mono">{e.command}</span>
                        )}
                      </Link>
                    </TableCell>
                    <TableCell className="text-xs">{e.target_summary ?? "—"}</TableCell>
                    <TableCell className="whitespace-nowrap text-xs">
                      {t("executions.countsLine", { ok: e.counts.succeeded, failed: e.counts.failed, skipped: e.counts.skipped, total: e.counts.total })}
                    </TableCell>
                    <TableCell><VerdictBadge verdict={e.verdict} /></TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
