import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { type ActionMode, useAgentMcpAccessViewModel } from "@/hooks/useAgentMcpAccessViewModel";
import { useAuthStore } from "@/store/authStore";
import { McpActivityPanel } from "./McpActivityPanel";

/** Short column label: "forgehub_factory" -> "factory". */
function shortName(server: string) {
  return server.replace(/^forgehub_/, "");
}

/** Agentes e MCP do ForgeHub: one row per agent, one column per ForgeHub MCP server, plus how a
 * container restart and a direct database query run for that agent (MCP-005, MCP-023). Admin only. */
export function AgentMcpAccessCard() {
  const { t } = useTranslation("settings");
  const admin = useAuthStore((s) => s.user?.is_admin);
  const vm = useAgentMcpAccessViewModel();
  const [tab, setTab] = useState("access");
  if (!admin) return null;

  const modeSelect = (row: (typeof vm.rows)[number], field: "restart_mode" | "query_mode") => (
    <Select
      aria-label={t(`mcpAccess.${field}`) + " — " + row.name}
      value={vm.draftOf(row)[field]}
      onChange={(event) => vm.setMode(row, field, event.target.value as ActionMode)}
      className="min-w-[8.5rem]"
    >
      <option value="direct">{t("mcpAccess.mode.direct")}</option>
      <option value="approval">{t("mcpAccess.mode.approval")}</option>
    </Select>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("mcpAccess.title")}</CardTitle>
        <CardDescription>{t("mcpAccess.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {vm.status === "loading" && <Loader2 className="h-5 w-5 animate-spin" aria-label={t("mcpAccess.loading")} />}
        {vm.status === "error" && (
          <p role="alert" className="text-sm text-destructive">
            {t("mcpAccess.loadError")}
          </p>
        )}
        {vm.status === "ready" && (
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="access">{t("mcpAccess.tabs.access")}</TabsTrigger>
              <TabsTrigger value="activity">{t("mcpAccess.tabs.activity")}</TabsTrigger>
            </TabsList>
            <TabsContent value="access" className="space-y-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("mcpAccess.agent")}</TableHead>
                  <TableHead>{t("mcpAccess.function")}</TableHead>
                  <TableHead className="text-center" title={t("mcpAccess.coreHint")}>
                    {vm.coreServer}
                  </TableHead>
                  {vm.servers.map((server) => (
                    <TableHead key={server} className="text-center" title={server}>
                      {shortName(server)}
                    </TableHead>
                  ))}
                  <TableHead>{t("mcpAccess.restart_mode")}</TableHead>
                  <TableHead>{t("mcpAccess.query_mode")}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {vm.rows.map((row) => {
                  const draft = vm.draftOf(row);
                  const dirty = vm.isDirty(row);
                  const saving = vm.savingId === row.agent_id;
                  return (
                    <TableRow key={row.agent_id}>
                      <TableCell className="font-medium whitespace-nowrap">
                        {row.name}
                        {!row.saved && (
                          <Badge variant="outline" className="ml-2">
                            {t("mcpAccess.suggested")}
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                        {row.department || t("mcpAccess.noFunction")}
                      </TableCell>
                      <TableCell className="text-center">
                        <input
                          type="checkbox"
                          checked
                          disabled
                          aria-label={`${vm.coreServer} — ${row.name}`}
                          title={t("mcpAccess.coreHint")}
                        />
                      </TableCell>
                      {vm.servers.map((server) => {
                        const blocked = server === "forgehub_personal" && !row.personal_allowed;
                        return (
                          <TableCell key={server} className="text-center">
                            <input
                              type="checkbox"
                              className="h-4 w-4 cursor-pointer disabled:cursor-not-allowed"
                              checked={draft.servers.includes(server)}
                              disabled={blocked || saving}
                              title={blocked ? t("mcpAccess.personalHint") : server}
                              aria-label={`${server} — ${row.name}`}
                              onChange={() => vm.toggleServer(row, server)}
                            />
                          </TableCell>
                        );
                      })}
                      <TableCell>{modeSelect(row, "restart_mode")}</TableCell>
                      <TableCell>{modeSelect(row, "query_mode")}</TableCell>
                      <TableCell className="whitespace-nowrap">
                        <div className="flex flex-wrap gap-2">
                          <Button size="sm" disabled={!dirty || saving} onClick={() => vm.save(row)}>
                            {saving && <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />}
                            {t("mcpAccess.save")}
                          </Button>
                          <Button size="sm" variant="outline" disabled={saving} onClick={() => vm.applySuggestion(row)}>
                            {t("mcpAccess.suggest")}
                          </Button>
                          {dirty && row.saved && (
                            <Button size="sm" variant="ghost" disabled={saving} onClick={() => vm.discard(row)}>
                              {t("mcpAccess.discard")}
                            </Button>
                          )}
                        </div>
                        {vm.saveError?.agentId === row.agent_id && (
                          <p role="alert" className="mt-1 text-xs text-destructive">
                            {t("mcpAccess.saveError")}
                          </p>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <p className="text-xs text-muted-foreground">{t("mcpAccess.footnote")}</p>
            </TabsContent>
            <TabsContent value="activity">
              <McpActivityPanel agents={vm.rows} active={tab === "activity"} />
            </TabsContent>
          </Tabs>
        )}
      </CardContent>
    </Card>
  );
}
