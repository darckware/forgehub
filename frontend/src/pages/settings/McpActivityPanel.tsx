import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AgentMcpAccessRow } from "@/hooks/useAgentMcpAccessViewModel";
import { useMcpActivityViewModel } from "@/hooks/useMcpActivityViewModel";

function when(value: string, locale: string) {
  return new Date(value).toLocaleString(locale);
}

/** Auditoria: ForgeHub MCP calls per agent and the requests that went to approval. */
export function McpActivityPanel({ agents, active }: { agents: AgentMcpAccessRow[]; active: boolean }) {
  const { t, i18n } = useTranslation("settings");
  const vm = useMcpActivityViewModel(active);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Select
          aria-label={t("mcpAccess.activity.agentFilter")}
          value={vm.agentId}
          onChange={(event) => vm.setAgentId(event.target.value)}
          className="sm:w-56"
        >
          <option value="">{t("mcpAccess.activity.allAgents")}</option>
          {agents.map((agent) => (
            <option key={agent.agent_id} value={agent.agent_id}>
              {agent.name}
            </option>
          ))}
        </Select>
        <Select
          aria-label={t("mcpAccess.activity.period")}
          value={String(vm.days)}
          onChange={(event) => vm.setDays(Number(event.target.value))}
          className="sm:w-40"
        >
          {[1, 7, 30].map((days) => (
            <option key={days} value={days}>
              {t("mcpAccess.activity.lastDays", { count: days })}
            </option>
          ))}
        </Select>
      </div>
      {vm.status === "loading" && <Loader2 className="h-5 w-5 animate-spin" aria-label={t("mcpAccess.loading")} />}
      {vm.status === "error" && (
        <p role="alert" className="text-sm text-destructive">
          {t("mcpAccess.activity.loadError")}
        </p>
      )}
      {vm.status === "ready" && (
        <>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">{t("mcpAccess.activity.approvals")}</h3>
            {vm.approvals.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("mcpAccess.activity.noApprovals")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>#</TableHead>
                    <TableHead>{t("mcpAccess.agent")}</TableHead>
                    <TableHead>{t("mcpAccess.activity.action")}</TableHead>
                    <TableHead>{t("mcpAccess.activity.status")}</TableHead>
                    <TableHead>{t("mcpAccess.activity.when")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {vm.approvals.map((item) => (
                    <TableRow key={item.number}>
                      <TableCell className="tabular-nums">#{item.number}</TableCell>
                      <TableCell>{item.agent}</TableCell>
                      <TableCell>{t(`mcpAccess.activity.actions.${item.action}`, { defaultValue: item.action })}</TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {item.dispatch_status ?? item.approval_status ?? "—"}
                        </Badge>
                      </TableCell>
                      <TableCell className="whitespace-nowrap">{when(item.created_at, i18n.language)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">{t("mcpAccess.activity.calls")}</h3>
            {vm.calls.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("mcpAccess.activity.noCalls")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("mcpAccess.activity.when")}</TableHead>
                    <TableHead>{t("mcpAccess.agent")}</TableHead>
                    <TableHead>{t("mcpAccess.activity.server")}</TableHead>
                    <TableHead>{t("mcpAccess.activity.tool")}</TableHead>
                    <TableHead>{t("mcpAccess.activity.status")}</TableHead>
                    <TableHead className="text-right">ms</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {vm.calls.map((call, index) => (
                    <TableRow key={`${call.occurred_at}-${index}`}>
                      <TableCell className="whitespace-nowrap">{when(call.occurred_at, i18n.language)}</TableCell>
                      <TableCell>{call.agent}</TableCell>
                      <TableCell className="font-mono text-xs">{call.server ?? "—"}</TableCell>
                      <TableCell className="font-mono text-xs">{call.tool}</TableCell>
                      <TableCell>
                        <Badge variant={call.status === "error" ? "destructive" : "outline"}>{call.status ?? "—"}</Badge>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{call.duration_ms ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            <p className="text-xs text-muted-foreground">{t("mcpAccess.activity.footnote")}</p>
          </section>
        </>
      )}
    </div>
  );
}
