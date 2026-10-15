/** Recent command executions on the Remote Access page, and the entry point
 * to run a new one. Each row opens the execution screen. */
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { CornerDownRight, ListChecks, TerminalSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useHostExecutions } from "@/hooks/useHostExecutions";
import { RunCommandDialog } from "./RunCommandDialog";
import { VerdictBadge } from "./VerdictBadge";

export function ExecutionsCard() {
  const { t, i18n } = useTranslation("remoteAccess");
  const navigate = useNavigate();
  const { data, isLoading, isError } = useHostExecutions();
  const [running, setRunning] = useState(false);
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" });

  return (
    <Card>
      <CardHeader className="flex flex-col gap-3 space-y-0 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="flex items-center gap-2 text-base">
          <ListChecks className="h-4 w-4 text-muted-foreground" aria-hidden="true" /> {t("executions.title")}
        </CardTitle>
        <Button type="button" size="sm" onClick={() => setRunning(true)} className="cursor-pointer gap-1.5">
          <TerminalSquare className="h-3.5 w-3.5" aria-hidden="true" /> {t("executions.run")}
        </Button>
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
                <TableHead>{t("executions.command")}</TableHead>
                <TableHead>{t("executions.targets")}</TableHead>
                <TableHead>{t("executions.results")}</TableHead>
                <TableHead>{t("executions.verdict")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="whitespace-nowrap text-xs">
                    {fmt.format(new Date(e.started_at))}
                    <p className="text-muted-foreground">{e.requested_by}</p>
                  </TableCell>
                  <TableCell className="max-w-xs">
                    <Link to={`/remote-access/executions/${e.id}`} className="flex items-start gap-1 font-mono text-xs hover:underline">
                      {e.parent_execution_id && <CornerDownRight className="mt-0.5 h-3 w-3 shrink-0" aria-label={t("executions.followUp")} />}
                      <span className="line-clamp-2 break-all">{e.command}</span>
                    </Link>
                  </TableCell>
                  <TableCell className="text-xs">{e.target_summary ?? "—"}</TableCell>
                  <TableCell className="whitespace-nowrap text-xs">
                    {t("executions.countsLine", { ok: e.counts.succeeded, failed: e.counts.failed, skipped: e.counts.skipped, total: e.counts.total })}
                  </TableCell>
                  <TableCell><VerdictBadge verdict={e.verdict} /></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
      {running && (
        <RunCommandDialog
          onClose={() => setRunning(false)}
          onStarted={(execution) => {
            setRunning(false);
            navigate(`/remote-access/executions/${execution.id}`);
          }}
        />
      )}
    </Card>
  );
}
