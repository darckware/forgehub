import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAgentAccessViewModel } from "@/hooks/useAgentAccessViewModel";
import { useAuthStore } from "@/store/authStore";

function when(value: string | null, locale: string) {
  return value ? new Date(value).toLocaleString(locale) : "—";
}

export function AgentAccessCard() {
  const { t, i18n } = useTranslation("settings");
  const admin = useAuthStore((s) => s.user?.is_admin);
  const vm = useAgentAccessViewModel();
  if (!admin) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("agentAccess.title")}</CardTitle>
        <CardDescription>{t("agentAccess.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {vm.status === "loading" && <Loader2 className="h-5 w-5 animate-spin" aria-label={t("agentAccess.loading")} />}
        {vm.status === "error" && (
          <p role="alert" className="text-sm text-destructive">
            {t("agentAccess.loadError")}
          </p>
        )}
        {vm.toggleFailed && (
          <p role="alert" className="text-sm text-destructive">
            {t("agentAccess.toggleError")}
          </p>
        )}
        {vm.endFailed && (
          <p role="alert" className="text-sm text-destructive">
            {t("agentAccess.endError")}
          </p>
        )}
        {vm.status === "ready" && (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("agentAccess.agent")}</TableHead>
                  <TableHead>{t("agentAccess.credential")}</TableHead>
                  <TableHead>{t("agentAccess.lastSession")}</TableHead>
                  <TableHead>{t("agentAccess.openSessions")}</TableHead>
                  <TableHead>{t("agentAccess.status")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {vm.agents.map((agent) => (
                  <TableRow key={agent.id}>
                    <TableCell className="font-medium">{agent.name}</TableCell>
                    <TableCell>{t(agent.has_credential ? "agentAccess.hasCredential" : "agentAccess.noCredential")}</TableCell>
                    <TableCell>{when(agent.last_session_at, i18n.language)}</TableCell>
                    <TableCell>{agent.open_sessions}</TableCell>
                    <TableCell>
                      <Badge variant={agent.enabled ? "default" : "secondary"}>
                        {t(agent.enabled ? "agentAccess.enabled" : "agentAccess.disabled")}
                      </Badge>
                    </TableCell>
                    <TableCell className="space-x-2 whitespace-nowrap text-right">
                      {agent.open_sessions > 0 && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={vm.endingId === agent.id}
                          onClick={() => vm.endSessions(agent)}
                        >
                          {vm.endingId === agent.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                          {t("agentAccess.endSessions")}
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={vm.togglingId === agent.id}
                        onClick={() => vm.toggle(agent)}
                      >
                        {vm.togglingId === agent.id && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                        {t(agent.enabled ? "agentAccess.block" : "agentAccess.allow")}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <div className="space-y-3">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <h3 className="font-semibold">{t("agentAccess.auditTitle")}</h3>
                <Select
                  aria-label={t("agentAccess.filter")}
                  value={vm.agentFilter}
                  onChange={(event) => vm.setAgentFilter(event.target.value)}
                  className="sm:w-56"
                >
                  <option value="">{t("agentAccess.allAgents")}</option>
                  {vm.agents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.name}
                    </option>
                  ))}
                </Select>
              </div>
              {vm.events.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("agentAccess.noEvents")}</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("agentAccess.when")}</TableHead>
                      <TableHead>{t("agentAccess.agent")}</TableHead>
                      <TableHead>{t("agentAccess.event")}</TableHead>
                      <TableHead>{t("agentAccess.target")}</TableHead>
                      <TableHead>{t("agentAccess.origin")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {vm.events.map((row) => (
                      <TableRow key={row.id}>
                        <TableCell className="whitespace-nowrap">{when(row.occurred_at, i18n.language)}</TableCell>
                        <TableCell>{row.agent}</TableCell>
                        <TableCell>{t(`agentAccess.events.${row.event}`, { defaultValue: row.event })}</TableCell>
                        <TableCell className="break-all">{row.details.path ?? row.details.reason ?? "—"}</TableCell>
                        <TableCell title={row.details.user_agent}>{row.details.ip_address ?? "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
