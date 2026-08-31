import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  ChevronUp,
  FileCode2,
  Globe,
  Loader2,
  RefreshCw,
  Server,
  Zap,
} from "lucide-react";
import claudeIcon from "@lobehub/icons-static-png/dark/claude-color.png";
import codexIcon from "@lobehub/icons-static-png/dark/codex-color.png";
import antigravityIcon from "@lobehub/icons-static-png/dark/antigravity-color.png";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type CliForgeRouterTool,
  useCliForgeRouterStatus,
  useToggleCliForgeRouter,
} from "@/hooks/useCliForgeRouter";
import { cn } from "@/lib/utils";

interface ToolConfig {
  key: CliForgeRouterTool;
  label: string;
  icon: string;
  protocol: string;
  configFile: string;
}

const TOOLS: ToolConfig[] = [
  {
    key: "claude",
    label: "Claude Code",
    icon: claudeIcon,
    protocol: "Anthropic Messages Protocol",
    configFile: "~/.claude/settings.json",
  },
  {
    key: "codex",
    label: "OpenAI Codex",
    icon: codexIcon,
    protocol: "Responses Protocol",
    configFile: "~/.codex/config.toml",
  },
  {
    key: "antigravity",
    label: "Antigravity",
    icon: antigravityIcon,
    protocol: "OpenAI Compatible Protocol",
    configFile: "~/.antigravity/settings.json",
  },
];

export function CliForgeRouterCard() {
  const { t } = useTranslation("dashboard");
  const { data: status, isLoading, isError, refetch, isRefetching } = useCliForgeRouterStatus();
  const toggleMutation = useToggleCliForgeRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [activeTool, setActiveTool] = useState<CliForgeRouterTool | null>(null);

  const handleToggle = async (tool: CliForgeRouterTool, nextState: boolean) => {
    setActiveTool(tool);
    try {
      await toggleMutation.mutateAsync({ tool, enabled: nextState });
    } finally {
      setActiveTool(null);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <Server className="h-4 w-4 text-primary" />
            {t("cliForgeRouter.title")}
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            {t("cliForgeRouter.description")}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            title={t("cliForgeRouter.refresh")}
            aria-label={t("cliForgeRouter.refresh")}
            onClick={() => void refetch()}
            disabled={isRefetching || isLoading}
          >
            {isRefetching ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? t("projectsForgeRouter.expand") : t("projectsForgeRouter.collapse")}
          >
            {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
          </Button>
        </div>
      </CardHeader>

      {!collapsed && (
        <CardContent className="space-y-4">
          {/* Target Gateway Info Banner */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3.5 py-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </span>
              <span className="font-medium text-foreground">
                {t("cliForgeRouter.targetGateway")}:
              </span>
              <code className="font-mono font-semibold text-primary">
                http://localhost:2100
              </code>
            </div>
            <div className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <Zap className="h-3 w-3 text-amber-500 shrink-0" />
              <span>{t("cliForgeRouter.gatewayUrl")}</span>
            </div>
          </div>

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <span>{t("cliForgeRouter.loading")}</span>
            </div>
          )}

          {/* Error state */}
          {isError && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              {t("cliForgeRouter.loadError")}
            </div>
          )}

          {/* Tools Grid */}
          {!isLoading && status && (
            <div className="grid gap-3 sm:grid-cols-3">
              {TOOLS.map((tool) => {
                const isEnabled = status[tool.key];
                const isPending = toggleMutation.isPending && activeTool === tool.key;

                return (
                  <div
                    key={tool.key}
                    className={cn(
                      "flex flex-col justify-between rounded-lg border p-3.5 transition-all",
                      isEnabled
                        ? "border-emerald-500/30 bg-emerald-500/[0.03] shadow-sm"
                        : "border-border/60 bg-card/50"
                    )}
                  >
                    <div>
                      {/* Tool header: Icon, Name & Status Switch */}
                      <div className="flex items-center justify-between gap-2 pb-2">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <img
                            src={tool.icon}
                            alt=""
                            className="h-6 w-6 rounded-md shrink-0 object-contain shadow-xs"
                          />
                          <div className="min-w-0">
                            <h4 className="text-sm font-semibold truncate text-foreground">
                              {t(`cliForgeRouter.tools.${tool.key}.title`, { defaultValue: tool.label })}
                            </h4>
                          </div>
                        </div>

                        {/* Switch toggle button */}
                        <button
                          type="button"
                          role="switch"
                          aria-checked={isEnabled}
                          disabled={isPending}
                          onClick={() => void handleToggle(tool.key, !isEnabled)}
                          className={cn(
                            "relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
                            isEnabled ? "bg-emerald-500" : "bg-muted-foreground/30"
                          )}
                          title={isEnabled ? t("cliForgeRouter.active") : t("cliForgeRouter.off")}
                        >
                          <span
                            className={cn(
                              "pointer-events-none inline-flex h-5 w-5 transform rounded-full bg-background shadow-md ring-0 transition duration-200 ease-in-out items-center justify-center",
                              isEnabled ? "translate-x-5" : "translate-x-0"
                            )}
                          >
                            {isPending ? (
                              <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                            ) : null}
                          </span>
                        </button>
                      </div>

                      {/* Tool description & details */}
                      <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                        {t(`cliForgeRouter.tools.${tool.key}.description`)}
                      </p>
                    </div>

                    <div className="mt-3.5 pt-2.5 border-t border-border/40 space-y-1.5">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="flex items-center gap-1 text-muted-foreground">
                          <Globe className="h-3 w-3 shrink-0" />
                          <span>{t("cliForgeRouter.protocol")}:</span>
                        </span>
                        <span className="font-mono text-muted-foreground truncate max-w-[130px]" title={tool.protocol}>
                          {tool.protocol.split(" ")[0]}
                        </span>
                      </div>

                      <div className="flex items-center justify-between text-[11px]">
                        <span className="flex items-center gap-1 text-muted-foreground">
                          <FileCode2 className="h-3 w-3 shrink-0" />
                          <span>{t("cliForgeRouter.configLocation")}:</span>
                        </span>
                        <code className="font-mono text-[10px] text-muted-foreground/80 truncate max-w-[130px]" title={tool.configFile}>
                          {tool.configFile}
                        </code>
                      </div>

                      <div className="flex items-center justify-between pt-1">
                        <span className="text-[11px] text-muted-foreground">Status:</span>
                        {isEnabled ? (
                          <Badge variant="success" className="h-5 px-1.5 text-[10px]">
                            {t("cliForgeRouter.active")}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="h-5 px-1.5 text-[10px] text-muted-foreground">
                            {t("cliForgeRouter.off")}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Mutation error notification */}
          {toggleMutation.isError && (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {String(toggleMutation.error)}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
