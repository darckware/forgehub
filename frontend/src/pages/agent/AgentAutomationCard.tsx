import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Clock, FileCode2, Loader2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useFoundationCrons } from "@/hooks/useFoundationCrons";
import { useFoundationAllScripts } from "@/hooks/useFoundationScripts";
import type { Agent } from "@/hooks/useAgent";

/**
 * The scheduled work an agent actually performs: its `hermes cron` jobs and
 * the scripts in its own profile directory.
 *
 * Both are per-profile on disk (`<profile>/cron/jobs.json` and
 * `<profile>/scripts/`), so they key off `profile_slug`, not agent id — and
 * an agent without a Hermes profile simply has neither.
 */

const CRON_HEALTH_VARIANT: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  ok: "success",
  error: "destructive",
  overdue: "destructive",
  never_ran: "warning",
  off: "outline",
};

const SCRIPT_STATUS_VARIANT: Record<string, "success" | "warning" | "destructive"> = {
  ok: "success",
  broken: "destructive",
  unused: "warning",
};

export function AgentAutomationCard({ agent }: { agent: Agent }) {
  const { t } = useTranslation("agent");
  const { data: cronData, isLoading: cronsLoading } = useFoundationCrons();
  const { data: scriptData, isLoading: scriptsLoading } = useFoundationAllScripts();

  const slug = agent.profile_slug;
  const crons = slug ? (cronData?.jobs ?? []).filter((job) => job.profile === slug) : [];
  const scripts = slug ? (scriptData ?? []).filter((script) => script.location === slug) : [];
  // A jobs.json that failed to parse does not just hide this profile's jobs —
  // its scheduler has stopped running them entirely. Never swallow it.
  const storeError = slug
    ? (cronData?.store_errors ?? []).find((entry) => entry.profile === slug)
    : undefined;

  const isLoading = cronsLoading || scriptsLoading;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <Clock className="h-5 w-5" />
          {t("automation.title")}
        </CardTitle>
        <CardDescription>{t("automation.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {isLoading && (
          <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t("automation.loading")}
          </p>
        )}

        {!isLoading && !slug && (
          <p className="text-sm italic text-muted-foreground">{t("automation.noProfile")}</p>
        )}

        {storeError && (
          <div className="rounded-md border border-destructive/50 bg-destructive/5 p-3 text-sm">
            <p className="font-medium text-destructive">{t("automation.storeErrorTitle")}</p>
            <p className="text-muted-foreground">
              {storeError.store} — {storeError.error}
            </p>
          </div>
        )}

        {!isLoading && slug && (
          <>
            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <Clock className="h-4 w-4" />
                {t("automation.cronsTitle")}
                <Badge variant="outline">{crons.length}</Badge>
                <Link to="/crons" className="text-xs font-normal text-muted-foreground hover:underline">
                  {t("automation.manageCrons")}
                </Link>
              </h3>
              {crons.length === 0 ? (
                <p className="text-sm italic text-muted-foreground">{t("automation.noCrons")}</p>
              ) : (
                <div className="max-h-72 overflow-y-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("automation.cronColumns.name")}</TableHead>
                        <TableHead>{t("automation.cronColumns.schedule")}</TableHead>
                        <TableHead>{t("automation.cronColumns.script")}</TableHead>
                        <TableHead>{t("automation.cronColumns.health")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {crons.map((job) => (
                        <TableRow key={job.id}>
                          <TableCell className="font-medium">
                            {job.name}
                            {job.description && (
                              <p className="max-w-md truncate text-xs text-muted-foreground">
                                {job.description}
                              </p>
                            )}
                          </TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {job.schedule_display ?? "—"}
                          </TableCell>
                          <TableCell>
                            <code className="text-xs text-muted-foreground">
                              {job.script ?? "—"}
                            </code>
                          </TableCell>
                          <TableCell>
                            <Badge variant={CRON_HEALTH_VARIANT[job.health] ?? "outline"}>
                              {t(`hierarchy.cronHealth.${job.health}`)}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </section>

            <section>
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
                <FileCode2 className="h-4 w-4" />
                {t("automation.scriptsTitle")}
                <Badge variant="outline">{scripts.length}</Badge>
              </h3>
              {scripts.length === 0 ? (
                <p className="text-sm italic text-muted-foreground">{t("automation.noScripts")}</p>
              ) : (
                <div className="max-h-72 overflow-y-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>{t("automation.scriptColumns.name")}</TableHead>
                        <TableHead>{t("automation.scriptColumns.description")}</TableHead>
                        <TableHead>{t("automation.scriptColumns.status")}</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {scripts.map((script) => (
                        <TableRow key={`${script.location}/${script.name}`}>
                          <TableCell>
                            <code className="text-xs font-medium">{script.name}</code>
                            <p className="max-w-md truncate text-[11px] text-muted-foreground">
                              {script.path}
                            </p>
                          </TableCell>
                          <TableCell className="max-w-md truncate text-xs text-muted-foreground">
                            {script.description ?? "—"}
                          </TableCell>
                          <TableCell>
                            <Badge variant={SCRIPT_STATUS_VARIANT[script.status] ?? "outline"}>
                              {t(`hierarchy.scriptStatus.${script.status}`)}
                            </Badge>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}
