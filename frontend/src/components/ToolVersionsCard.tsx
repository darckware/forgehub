import { BellOff, BellRing, ChevronDown, ChevronRight, Feather, Loader2, RefreshCw, X } from "lucide-react";
import hermesIcon from "@lobehub/icons-static-png/light/hermesagent.png";
import claudeIcon from "@lobehub/icons-static-png/dark/claude-color.png";
import codexIcon from "@lobehub/icons-static-png/dark/codex-color.png";
import antigravityIcon from "@lobehub/icons-static-png/dark/antigravity-color.png";
import opencodeIcon from "@lobehub/icons-static-png/light/opencode.png";
import piIcon from "@/assets/icons/pi.svg";
import kanboardIcon from "@/assets/icons/kanboard.svg";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type MonitoredTool,
  useCheckToolVersions,
  useRunToolUpdate,
  useSetToolSyncSetting,
  useToolSyncSetting,
  useToolVersions,
} from "@/hooks/useToolVersions";
import { useToolUpdateStore } from "@/store/toolUpdate";

// pi's mark is a plain white glyph with no built-in background, so it needs
// a dark backing square to read against this card's light background --
// unlike the other PNGs below, which are already self-contained color icons.
const TOOL_META: Record<MonitoredTool, { label: string; icon?: string; iconBg?: string }> = {
  hermes: { label: "Hermes", icon: hermesIcon },
  claude: { label: "Claude Code", icon: claudeIcon },
  codex: { label: "Codex", icon: codexIcon },
  antigravity: { label: "Antigravity", icon: antigravityIcon },
  pi: { label: "PI", icon: piIcon, iconBg: "bg-black" },
  opencode: { label: "Opencode", icon: opencodeIcon },
  kanboard: { label: "Kanboard", icon: kanboardIcon },
};

const TOOL_ORDER: MonitoredTool[] = ["hermes", "claude", "codex", "antigravity", "pi", "opencode", "kanboard"];


export function ToolVersionsCard() {
  const { data: versions, isLoading } = useToolVersions();
  const { data: syncSetting } = useToolSyncSetting();
  const checkVersions = useCheckToolVersions();
  const setSyncSetting = useSetToolSyncSetting();
  const runToolUpdate = useRunToolUpdate();
  const {
    updatingTools,
    expandedTool,
    updateOutputs,
    setExpandedTool,
    dismissUpdate,
    clearUpdateDetails,
  } = useToolUpdateStore();

  const syncEnabled = syncSetting?.enabled ?? true;

  const handleUpdate = (tool: MonitoredTool) => {
    void runToolUpdate(tool);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-3">
        <CardTitle>Tool Versions</CardTitle>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            title="Check now"
            aria-label="Check versions now"
            onClick={() => {
              clearUpdateDetails();
              checkVersions.mutate();
            }}
            disabled={checkVersions.isPending}
          >
            {checkVersions.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            title={syncEnabled ? "Disable automatic sync" : "Enable automatic sync"}
            aria-label="Toggle automatic version sync"
            onClick={() => setSyncSetting.mutate(!syncEnabled)}
            disabled={setSyncSetting.isPending}
          >
            {syncEnabled ? (
              <BellRing className="h-4 w-4 text-emerald-600" />
            ) : (
              <BellOff className="h-4 w-4 text-muted-foreground" />
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        {checkVersions.isError && (
          <p className="px-2 pb-1 text-xs text-destructive">
            Failed to reach the host bridge — is forgehub-chat-bridge running?
          </p>
        )}
        {isLoading && (
          <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading...
          </div>
        )}
        {!isLoading &&
          TOOL_ORDER.map((tool) => {
            const meta = TOOL_META[tool];
            const version = versions?.find((v) => v.tool === tool);
            const isExpanded = expandedTool === tool;
            const updateOut = updateOutputs[tool] ?? null;
            const isUpdating = updatingTools.has(tool);
            const errorText = version?.last_error;
            return (
              <div key={tool} className="rounded-md">
                <div className="flex items-center justify-between gap-3 px-2 py-1.5 hover:bg-accent/50">
                  <div className="flex items-center gap-3">
                    {meta.icon ? (
                      meta.iconBg ? (
                        <span className={`flex h-6 w-6 items-center justify-center rounded ${meta.iconBg}`}>
                          <img src={meta.icon} alt="" className="h-4 w-4" />
                        </span>
                      ) : (
                        <img src={meta.icon} alt="" className="h-6 w-6 rounded" />
                      )
                    ) : (
                      <Feather className="h-6 w-6 text-muted-foreground" />
                    )}
                    <div>
                      <div className="text-sm font-medium">{meta.label}</div>
                      <div className="text-xs text-muted-foreground">
                        {version?.installed_version ?? (errorText ? "Error" : "Unknown")}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {version?.update_available ? (
                      <Badge variant="warning">{version.latest_version ?? "Update available"}</Badge>
                    ) : version?.installed_version ? (
                      <Badge variant="success">Up to date</Badge>
                    ) : errorText ? (
                      <button
                        className="flex items-center gap-1 rounded"
                        onClick={() => setExpandedTool(isExpanded ? null : tool)}
                      >
                        <Badge variant="destructive" className="gap-1">
                          {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                          Check failed
                        </Badge>
                      </button>
                    ) : (
                      <Badge variant="outline">Not checked</Badge>
                    )}
                    {version?.update_available && (
                      <Button
                        id={`tool-update-${tool}`}
                        data-testid={`tool-update-${tool}`}
                        size="sm"
                        variant="outline"
                        aria-label={`Update ${meta.label}`}
                        onClick={() => handleUpdate(tool)}
                        disabled={isUpdating}
                      >
                        {isUpdating ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          "Update"
                        )}
                      </Button>
                    )}
                </div>
              </div>

              {/* Inline error / update output panel */}
              {isExpanded && (errorText || updateOut) && (
                <div className="mx-2 mb-2 max-h-64 overflow-y-auto rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                      Details
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0"
                      title="Close and clear details"
                      aria-label={`Close and clear ${meta.label} details`}
                      onClick={() => dismissUpdate(tool)}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                  {updateOut && (
                    <>
                      {updateOut.output && (
                        <pre className="whitespace-pre-wrap break-words text-[11px] text-foreground/80 font-mono">
                          {updateOut.output.trim()}
                        </pre>
                      )}
                      {updateOut.error && (
                        <p className="mt-1 text-[11px] text-destructive font-mono">{updateOut.error}</p>
                      )}
                    </>
                  )}
                  {!updateOut && errorText && (
                    <pre className="whitespace-pre-wrap break-words text-[11px] text-destructive font-mono">
                      {errorText}
                    </pre>
                  )}
                </div>
              )}
            </div>
            );
          })}
      </CardContent>
    </Card>
  );
}
