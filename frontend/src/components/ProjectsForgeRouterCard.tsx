import { useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, FolderOpen, Loader2, RefreshCw, XCircle } from "lucide-react";
import claudeIcon from "@lobehub/icons-static-png/dark/claude-color.png";
import codexIcon from "@lobehub/icons-static-png/dark/codex-color.png";
import antigravityIcon from "@lobehub/icons-static-png/dark/antigravity-color.png";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useProjects } from "@/hooks/useProject";
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
}

function ToolBadge({
  icon,
  label,
  enabled,
  loading,
}: {
  icon: string;
  label: string;
  enabled: boolean;
  loading: boolean;
}) {
  return (
    <div className="flex items-center gap-1" title={`${label}: ${enabled ? "configured" : "not configured"}`}>
      <img src={icon} alt="" className="h-4 w-4 rounded" />
      {loading ? (
        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
      ) : enabled ? (
        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
      ) : (
        <XCircle className="h-3 w-3 text-muted-foreground/40" />
      )}
    </div>
  );
}

function ProjectForgeRouterRow({ projectId, projectName, projectPath }: ProjectForgeRouterRowProps) {
  const { data: config, isLoading } = useProjectForgeRouterConfig(projectId);
  const toggle = useToggleProjectForgeRouter(projectId);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);

  const isEnabled = Boolean(config?.claude_enabled || config?.codex_enabled || config?.antigravity_enabled);
  const hasPath = Boolean(projectPath);

  const handleToggle = async (newEnabled: boolean) => {
    if (newEnabled && !apiKeyInput) {
      setShowApiKey(true);
      return;
    }
    await toggle.mutateAsync({
      enabled: newEnabled,
      api_key: apiKeyInput,
      claude: true,
      codex: true,
      antigravity: false,
    });
    if (!newEnabled) {
      setApiKeyInput("");
      setShowApiKey(false);
    }
  };

  const handleConfirmEnable = async () => {
    await toggle.mutateAsync({
      enabled: true,
      api_key: apiKeyInput,
      claude: true,
      codex: true,
      antigravity: false,
    });
    setShowApiKey(false);
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
            <span className="text-xs text-amber-500">No working directory set</span>
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
            />
            <ToolBadge
              icon={codexIcon}
              label="Codex"
              enabled={config?.codex_enabled ?? false}
              loading={toggle.isPending}
            />
            <ToolBadge
              icon={antigravityIcon}
              label="Antigravity"
              enabled={config?.antigravity_enabled ?? false}
              loading={toggle.isPending}
            />
          </div>
        )}

        {/* ForgeRouter master toggle */}
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={isEnabled ? "default" : "outline"}
            className="h-7 min-w-[72px] text-xs"
            disabled={!hasPath || toggle.isPending || isLoading}
            onClick={() => void handleToggle(!isEnabled)}
            title={!hasPath ? "Set working_directory_path on the project first" : undefined}
          >
            {toggle.isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : isEnabled ? (
              "Active"
            ) : (
              "Enable"
            )}
          </Button>
          {isEnabled && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-muted-foreground"
              disabled={toggle.isPending}
              onClick={() => void handleToggle(false)}
            >
              Disable
            </Button>
          )}
        </div>
      </div>

      {/* API key prompt */}
      {showApiKey && (
        <div className="border-t border-border/50 px-3 py-2 bg-muted/30">
          <p className="mb-2 text-xs text-muted-foreground">
            Enter the ForgeRouter agent API key for this project (leave blank if ForgeRouter has no auth):
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              value={apiKeyInput}
              onChange={(e) => setApiKeyInput(e.target.value)}
              placeholder="API key (optional)"
              className="h-7 flex-1 rounded border border-border bg-background px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-ring"
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleConfirmEnable();
                if (e.key === "Escape") setShowApiKey(false);
              }}
              autoFocus
            />
            <Button size="sm" className="h-7 text-xs" onClick={() => void handleConfirmEnable()} disabled={toggle.isPending}>
              {toggle.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Enable"}
            </Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowApiKey(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Last configured timestamp */}
      {configuredAt && (
        <div className="border-t border-border/30 px-3 py-1 text-[10px] text-muted-foreground/60">
          Last configured: {configuredAt}
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
  const { data: audit, isLoading, refetch } = useForgeRouterGlobalAudit();
  const [expanded, setExpanded] = useState(false);

  if (isLoading || !audit || audit.clean) return null;

  return (
    <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
        <span className="flex-1 text-xs text-amber-700 dark:text-amber-400">
          {audit.findings.length} global ForgeRouter config(s) detected — these should be per-project.
        </span>
        <button
          className="text-xs text-amber-600 underline"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Hide" : "Details"}
        </button>
        <button onClick={() => void refetch()} title="Re-audit">
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
  const { data: projects, isLoading } = useProjects();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <div>
          <CardTitle>Projects</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            ForgeRouter is configured per project inside each project's directory.
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={() => setCollapsed((v) => !v)}
          title={collapsed ? "Expand" : "Collapse"}
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
              Loading projects...
            </div>
          )}

          {!isLoading && (!projects || projects.length === 0) && (
            <p className="py-3 text-center text-sm text-muted-foreground">
              No projects registered yet.
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
                />
              ))}
          </div>

          {/* Legend */}
          {!isLoading && projects && projects.length > 0 && (
            <p className="pt-1 text-[10px] text-muted-foreground/60">
              Toggle enables ForgeRouter for Claude Code (.claude/settings.local.json) and Codex (.codex/config.toml)
              inside the project directory. Antigravity requires manual env sourcing (.forgerouter/antigravity.env).
            </p>
          )}
        </CardContent>
      )}
    </Card>
  );
}
