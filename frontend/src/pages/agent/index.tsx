import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AlertCircle, Bot, Download, KeyRound, Loader2, RefreshCw, Send, Wrench } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AgentEcosystemHierarchy } from "@/components/AgentEcosystemHierarchy";
import { useAgents, useSyncForgeRouterKeys, useSyncHermesAgents, useSkills } from "@/hooks/useAgent";
import { cn } from "@/lib/utils";

/**
 * The Agents page is the org chart, full stop.
 *
 * It used to carry a second surface below the chart: a filter bar plus a
 * roster table repeating every agent with its own View/Delete actions. Once
 * each chart card grew the agent's runtime, profile directory, profile files,
 * Telegram health, skills, sub-agents, crons and scripts, that table was
 * showing strictly less than the card directly above it — so it was removed
 * (2026-07-26) and its two real capabilities moved onto the card itself:
 * View, Delete, and delete-a-sub-agent. Retired agents, which the table used
 * to preserve for audit, now have their own section in the chart.
 */

/** Path the Hermes Foundation sync reads its canonical agent contracts from
 *  (backend/app/core/hermes_sync.py's CANONICAL_AGENTS_DOC_ROOT). Shown next
 *  to the sync button so it is obvious the roster comes from the Foundation,
 *  not from something ForgeHub invents. */
const FOUNDATION_AGENTS_ROOT = "/root/.hermes/foundation/agents";

export default function AgentPage() {
  const { t } = useTranslation("agent");
  const { data: agents, isLoading, isError, error } = useAgents();
  const { data: skills = [] } = useSkills();
  const syncHermes = useSyncHermesAgents();
  const syncForgeRouterKeys = useSyncForgeRouterKeys();
  const [focusedAgentId, setFocusedAgentId] = useState("");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">{t("list.title")}</h1>
          <p className="text-muted-foreground">{t("list.subtitle")}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("list.foundationSource")} <code>{FOUNDATION_AGENTS_ROOT}</code>
          </p>
        </div>
        <div className="flex items-center gap-1.5">
          {/* Focus the chart on one agent. Built from the full roster, retired
              rows included, so filtering to an archived agent still works. */}
          <Select
            value={focusedAgentId}
            onChange={(e) => setFocusedAgentId(e.target.value)}
            className="w-56"
            aria-label={t("list.filterByAgent")}
          >
            <option value="">{t("list.allAgents")}</option>
            {[...(agents ?? [])]
              .sort((a, b) => a.name.localeCompare(b.name))
              .map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                  {agent.is_active ? "" : ` · ${t("list.retiredSuffix")}`}
                </option>
              ))}
          </Select>
          <Button
            variant="outline"
            title={t("list.syncTooltipDetailed", { path: FOUNDATION_AGENTS_ROOT })}
            onClick={() => syncHermes.mutate()}
            disabled={syncHermes.isPending}
          >
            {syncHermes.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            {t("list.syncFromFoundation")}
          </Button>
          <Button
            variant="outline"
            title={t("list.importForgeRouterKeysTooltip")}
            onClick={() => syncForgeRouterKeys.mutate()}
            disabled={syncForgeRouterKeys.isPending}
          >
            {syncForgeRouterKeys.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            {t("list.importForgeRouterKeys")}
          </Button>
          {/* Agent Tools moved off the sidebar and in here: the tools registry
              is scoped to this roster, not a peer destination of it. */}
          <Link
            to="/tools"
            className={buttonVariants({ variant: "outline" })}
            title={t("list.agentToolsTooltip")}
          >
            <Wrench className="mr-2 h-4 w-4" />
            {t("list.agentTools")}
          </Link>
        </div>
      </div>

      {syncHermes.isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-4 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("list.syncError", { message: (syncHermes.error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {syncHermes.isSuccess && syncHermes.data && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Send className="h-4 w-4" />
              {t("list.syncResultTitle")}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-4 text-sm text-muted-foreground">
            <span>
              {t("list.syncResult.agents")}{" "}
              <strong className="text-foreground">{syncHermes.data.agents.created}</strong>{" "}
              {t("list.syncResult.created")},{" "}
              <strong className="text-foreground">{syncHermes.data.agents.updated}</strong>{" "}
              {t("list.syncResult.updated")}
            </span>
            <span>
              {t("list.syncResult.subAgents")}{" "}
              <strong className="text-foreground">{syncHermes.data.sub_agents.created}</strong>{" "}
              {t("list.syncResult.created")},{" "}
              <strong className="text-foreground">{syncHermes.data.sub_agents.updated}</strong>{" "}
              {t("list.syncResult.updated")}
            </span>
            <span>
              {t("list.syncResult.skills")}{" "}
              <strong className="text-foreground">{syncHermes.data.skills.created}</strong>{" "}
              {t("list.syncResult.created")},{" "}
              <strong className="text-foreground">{syncHermes.data.skills.updated}</strong>{" "}
              {t("list.syncResult.updated")}
            </span>
            <span>
              {t("list.syncResult.skillGrants")}{" "}
              <strong className="text-foreground">{syncHermes.data.agent_skills.created}</strong>{" "}
              {t("list.syncResult.created")}
            </span>
            {syncHermes.data.warnings.length > 0 && (
              <span className="text-destructive">{syncHermes.data.warnings.join("; ")}</span>
            )}
          </CardContent>
        </Card>
      )}

      {syncForgeRouterKeys.isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-4 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("list.importForgeRouterKeysError", { message: (syncForgeRouterKeys.error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {syncForgeRouterKeys.isSuccess && syncForgeRouterKeys.data && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <KeyRound className="h-4 w-4" />
              {t("list.importForgeRouterKeysResultTitle")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Headline number is `matched` (keys ForgeHub actually pulled
                and confirmed against ForgeRouter this run), not `updated`
                (only the subset that needed a fresh DB write) -- `updated`
                alone reading "0" whenever everything was already in sync
                looked like the button did nothing, even though 13 keys
                were in fact checked and confirmed (2026-07-29, Marcelo:
                "a mensagem precisa conter o número de keys atualizadas ou
                importadas. Não pode aparecer 0" -- matched is the number
                that's genuinely never 0 on a working sync; `updated` stays
                visible below as the finer-grained stat). */}
            <p className={cn("text-sm font-medium", syncForgeRouterKeys.data.matched > 0 ? "text-emerald-500" : "text-destructive")}>
              {syncForgeRouterKeys.data.matched > 0
                ? t("list.importForgeRouterKeysResult.importedCount", { count: syncForgeRouterKeys.data.matched })
                : t("list.importForgeRouterKeysResult.noneMatched")}
            </p>
            <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
              <span>
                {t("list.importForgeRouterKeysResult.checked")}{" "}
                <strong className="text-foreground">{syncForgeRouterKeys.data.checked}</strong>
              </span>
              <span>
                {t("list.importForgeRouterKeysResult.matched")}{" "}
                <strong className="text-foreground">{syncForgeRouterKeys.data.matched}</strong>
              </span>
              <span>
                {t("list.importForgeRouterKeysResult.updated")}{" "}
                <strong className="text-foreground">{syncForgeRouterKeys.data.updated}</strong>
              </span>
              {syncForgeRouterKeys.data.unmatched_forgerouter_agents.length > 0 && (
                <span className="text-destructive">
                  {t("list.importForgeRouterKeysResult.unmatched")}{" "}
                  {syncForgeRouterKeys.data.unmatched_forgerouter_agents.join(", ")}
                </span>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {isLoading && (
        <div className="flex items-center justify-center gap-2 py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          {t("list.loading")}
        </div>
      )}

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("list.loadError", { message: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && agents && agents.length === 0 && (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
            <Bot className="h-10 w-10 text-muted-foreground" />
            <div>
              <p className="font-medium">{t("list.emptyTitle")}</p>
              <p className="text-sm text-muted-foreground">{t("list.emptyDescription")}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* The full roster goes in, retired rows included — the chart owns the
          active/inactive split and renders retired agents in their own
          section. */}
      {!isLoading && !isError && agents && agents.length > 0 && (
        <AgentEcosystemHierarchy
          agents={agents}
          skills={skills}
          focusedAgentId={focusedAgentId || null}
        />
      )}
    </div>
  );
}
