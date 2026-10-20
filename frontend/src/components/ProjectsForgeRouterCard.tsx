import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, FolderOpen, Loader2, RefreshCw, XCircle } from "lucide-react";
import claudeIcon from "@lobehub/icons-static-png/dark/claude-color.png";
import codexIcon from "@lobehub/icons-static-png/dark/codex-color.png";
import antigravityIcon from "@lobehub/icons-static-png/dark/antigravity-color.png";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProjects } from "@/hooks/useProject";
import { useForgeRouterServiceKey } from "@/hooks/useAgent";
import { useAppConfig } from "@/hooks/useAppConfig";
import {
  useForgeRouterGlobalAudit,
  useProjectForgeRouterConfig,
  useToggleProjectForgeRouter,
} from "@/hooks/useProjectForgeRouter";

// ---------------------------------------------------------------------------
// Per-project row
// ---------------------------------------------------------------------------

interface ProjectForgeRouterRowProps {
  projectId: string;
  projectName: string;
  projectPath: string | null | undefined;
  /** Settings -> ForgeRouter virtual models -> "Default agent for project
   * API keys" -- the name of a service-kind ai_router.agents entry (e.g.
   * "Hindsight"), empty = none set. Passed down from the card so every
   * row shares the one useAppConfig() fetch instead of each row
   * re-requesting it. */
  defaultServiceName: string;
}

type ToolKey = "claude" | "codex" | "antigravity";

const TOOL_LABELS: Record<ToolKey, string> = {
  claude: "Claude",
  codex: "Codex",
  antigravity: "Antigravity",
};

function ToolBadge({
  icon,
  label,
  enabled,
  loading,
  disabled = false,
  onClick,
}: {
  icon: string;
  label: string;
  enabled: boolean;
  loading: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  const { t } = useTranslation("dashboard");
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading || disabled}
      className="flex items-center gap-1 rounded px-0.5 transition-opacity hover:opacity-70 disabled:cursor-not-allowed disabled:opacity-50"
      title={
        disabled
          ? t("projectsForgeRouter.setWorkingDirFirst")
          : t(enabled ? "projectsForgeRouter.toolConfigured" : "projectsForgeRouter.toolNotConfigured", { tool: label })
      }
    >
      <img src={icon} alt="" className="h-4 w-4 rounded" />
      {loading ? (
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
      ) : enabled ? (
        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
      ) : (
        <XCircle className="h-3 w-3 text-muted-foreground/40" />
      )}
    </button>
  );
}

function ProjectForgeRouterRow({ projectId, projectName, projectPath, defaultServiceName }: ProjectForgeRouterRowProps) {
  const { t } = useTranslation("dashboard");
  const { data: config, isLoading } = useProjectForgeRouterConfig(projectId);
  const toggle = useToggleProjectForgeRouter(projectId);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [pendingTool, setPendingTool] = useState<ToolKey | null>(null);
  // Fetched only while the prompt is actually open (name is undefined
  // otherwise, which disables the query) -- this is an admin-only secret
  // (GET /agents/forgerouter-services/{name}), so it's only pulled when
  // there's an actual use for it, not proactively for every project row.
  const { data: defaultService } = useForgeRouterServiceKey(showApiKey ? defaultServiceName || undefined : undefined);
  // Pre-fills the prompt with the default service's key the moment it
  // opens and the fetch resolves -- still fully editable/clearable per
  // project+tool before confirming (2026-07-29, Marcelo: "para não
  // precisar preencher a api do agente do forgerouter").
  useEffect(() => {
    if (showApiKey && defaultService?.api_key) {
      setApiKeyInput((current) => current || defaultService.api_key);
    }
    // pendingTool is in the deps (not just showApiKey) so switching directly
    // from one tool's prompt to another's (without closing it first) also
    // re-triggers the prefill, since `showApiKey` itself never flips false->
    // true in that case.
  }, [showApiKey, pendingTool, defaultService?.api_key]);

  const isEnabled = Boolean(config?.claude_enabled || config?.codex_enabled || config?.antigravity_enabled);
  const hasPath = Boolean(projectPath);

  const currentState = (): Record<ToolKey, boolean> => ({
    claude: config?.claude_enabled ?? false,
    codex: config?.codex_enabled ?? false,
    antigravity: config?.antigravity_enabled ?? false,
  });

  const currentApiKey = (tool: ToolKey): string | null => ({
    claude: config?.claude_api_key ?? null,
    codex: config?.codex_api_key ?? null,
    antigravity: config?.antigravity_api_key ?? null,
  })[tool];

  // Each icon toggles only its own tool and carries only that tool's own
  // key — Claude/Codex/Antigravity are separate products with separate
  // credentials, so a key typed for one must never be applied to another.
  const applyToggle = async (tool: ToolKey, nextValue: boolean, apiKey: string) => {
    const desired = { ...currentState(), [tool]: nextValue };
    await toggle.mutateAsync({
      enabled: desired.claude || desired.codex || desired.antigravity,
      [`${tool}_api_key`]: apiKey,
      ...desired,
    });
  };

  const handleToolClick = async (tool: ToolKey) => {
    if (!hasPath) return;
    const nextValue = !currentState()[tool];
    if (nextValue && !currentApiKey(tool)) {
      // Fresh prompt for this specific tool -- never carry over a key
      // typed (or left over from a cancelled prompt) for a different tool.
      setApiKeyInput("");
      setPendingTool(tool);
      setShowApiKey(true);
      return;
    }
    await applyToggle(tool, nextValue, "");
  };

  const handleCancelApiKey = () => {
    setApiKeyInput("");
    setShowApiKey(false);
    setPendingTool(null);
  };

  const handleDisableAll = async () => {
    await toggle.mutateAsync({ enabled: false, claude: false, codex: false, antigravity: false });
    setApiKeyInput("");
    setShowApiKey(false);
    setPendingTool(null);
  };

  const handleConfirmEnable = async () => {
    if (!pendingTool) {
      setShowApiKey(false);
      return;
    }
    await applyToggle(pendingTool, true, apiKeyInput);
    setApiKeyInput("");
    setShowApiKey(false);
    setPendingTool(null);
  };

  const configuredAt = config?.configured_at
    ? new Date(config.configured_at).toLocaleString()
    : null;

  return (
    <div className="rounded-md border border-border/50 bg-card/30">
      <div className="flex items-center gap-3 px-3 py-2.5">
        {/* Project name + path */}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{projectName}</div>
          {projectPath ? (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <FolderOpen className="h-3 w-3 shrink-0" />
              <span className="truncate font-mono">{projectPath}</span>
            </div>
          ) : (
            <span className="text-xs text-amber-500">{t("projectsForgeRouter.noWorkingDir")}</span>
          )}
        </div>

        {/* Tool status icons */}
        {isLoading ? (
          <div className="flex gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <ToolBadge
              icon={claudeIcon}
              label="Claude"
              enabled={config?.claude_enabled ?? false}
              loading={toggle.isPending}
              disabled={!hasPath}
              onClick={() => void handleToolClick("claude")}
            />
            <ToolBadge
              icon={codexIcon}
              label="Codex"
              enabled={config?.codex_enabled ?? false}
              loading={toggle.isPending}
              disabled={!hasPath}
              onClick={() => void handleToolClick("codex")}
            />
            <ToolBadge
              icon={antigravityIcon}
              label="Antigravity"
              enabled={config?.antigravity_enabled ?? false}
              loading={toggle.isPending}
              disabled={!hasPath}
              onClick={() => void handleToolClick("antigravity")}
            />
          </div>
        )}

        {/* Status + disable-all — picking which CLI to enable happens on the icons above */}
        <div className="flex items-center gap-2">
          <span
            className={`h-7 min-w-[72px] rounded border px-2 text-center text-xs leading-7 ${
              isEnabled ? "border-emerald-500/40 text-emerald-500" : "border-border/50 text-muted-foreground"
            }`}
            title={!hasPath ? t("projectsForgeRouter.setWorkingDirFirst") : undefined}
          >
            {isEnabled ? t("projectsForgeRouter.active") : t("projectsForgeRouter.off")}
          </span>
          {isEnabled && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-muted-foreground"
              disabled={toggle.isPending || !hasPath}
              onClick={() => void handleDisableAll()}
            >
              {t("projectsForgeRouter.disableAll")}
            </Button>
          )}
        </div>
      </div>

      {/* API key prompt */}
      {showApiKey && (
        <div className="border-t border-border/50 px-3 py-2 bg-muted/30">
          <p className="mb-2 text-xs text-muted-foreground">
            {t("projectsForgeRouter.apiKeyPrompt", { tool: pendingTool ? TOOL_LABELS[pendingTool] : "" })}
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder={t("projectsForgeRouter.apiKeyPlaceholder")}
              className="h-7 flex-1 rounded border border-border bg-background px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleConfirmEnable();
                if (e.key === "Escape") handleCancelApiKey();
              }}
              autoFocus
            />
            <Button size="sm" className="h-7 text-xs" onClick={() => void handleConfirmEnable()} disabled={toggle.isPending}>
              {toggle.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : t("projectsForgeRouter.enable")}
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={handleCancelApiKey}>
              {t("projectsForgeRouter.cancel")}
            </Button>
          </div>
        </div>
      )}

      {/* Last configured timestamp */}
      {configuredAt && (
        <div className="border-t border-border/30 px-3 py-1 text-[10px] text-muted-foreground/60">
          {t("projectsForgeRouter.lastConfigured", { timestamp: configuredAt })}
        </div>
      )}

      {/* Error state */}
      {toggle.isError && (
        <div className="border-t border-destructive/30 px-3 py-1 text-[11px] text-destructive">
          {String(toggle.error)}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Global audit banner
// ---------------------------------------------------------------------------

function GlobalAuditBanner() {
  const { t } = useTranslation("dashboard");
  const { data: audit, isLoading, refetch } = useForgeRouterGlobalAudit();
  const [expanded, setExpanded] = useState(false);

  if (isLoading || !audit || audit.clean) return null;

  return (
    <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
        <span className="flex-1 text-xs text-amber-700 dark:text-amber-400">
          {t("projectsForgeRouter.globalConfigsDetected", { count: audit.findings.length })}
        </span>
        <button
          className="text-xs text-amber-600 underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? t("projectsForgeRouter.hide") : t("projectsForgeRouter.details")}
        </button>
        <button onClick={() => void refetch()} title={t("projectsForgeRouter.reAudit")}>
          <RefreshCw className="h-3 w-3 text-muted-foreground" />
        </button>
      </div>
      {expanded && (
        <ul className="mt-2 space-y-1">
          {audit.findings.map((f, i) => (
            <li key={i} className="font-mono text-[11px] text-amber-600 dark:text-amber-400">
              [{f.tool}] {f.path} — {f.detail}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main card
// ---------------------------------------------------------------------------

export function ProjectsForgeRouterCard() {
  const { t } = useTranslation("dashboard");
  const { data: projects, isLoading } = useProjects();
  const { data: appConfig } = useAppConfig();
  const defaultServiceName = appConfig?.default_forgerouter_service_name ?? "";
  const [collapsed, setCollapsed] = useState(false);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle>{t("projectsForgeRouter.title")}</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t("projectsForgeRouter.description")}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setCollapsed((v) => !v)}
          title={collapsed ? t("projectsForgeRouter.expand") : t("projectsForgeRouter.collapse")}
        >
          {collapsed ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
        </Button>
      </CardHeader>

      {!collapsed && (
        <CardContent className="space-y-2">
          <GlobalAuditBanner />

          {isLoading && (
            <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("projectsForgeRouter.loadingProjects")}
            </div>
          )}

          {!isLoading && (!projects || projects.length === 0) && (
            <p className="py-3 text-center text-sm text-muted-foreground">
              {t("projectsForgeRouter.noProjects")}
            </p>
          )}

          <div className="max-h-80 overflow-y-auto pr-1">
            {!isLoading &&
              projects?.map((project) => (
                <ProjectForgeRouterRow
                  key={project.id}
                  projectId={project.id}
                  projectName={project.name}
                  projectPath={project.working_directory_path}
                  defaultServiceName={defaultServiceName}
                />
              ))}
          </div>

          {/* Legend */}
          {!isLoading && projects && projects.length > 0 && (
            <p className="pt-1 text-[10px] text-muted-foreground/60">
              {t("projectsForgeRouter.legend")}
            </p>
          )}
        </CardContent>
      )}
    </Card>
  );
}
