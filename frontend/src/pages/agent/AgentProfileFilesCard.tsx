import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Eye, FolderTree, Loader2, Pencil, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Markdown } from "@/components/Markdown";
import {
  useAgentProfileFile,
  useAgentProfileFiles,
  useUpdateAgentProfileFile,
  type Agent,
  type AgentProfileFileInfo,
} from "@/hooks/useAgent";

/**
 * One tab per profile Markdown file, inside the agent's own card.
 *
 * Each tab has two modes: a rendered read view (this is the primary use —
 * these files are prose describing what the agent is, not config to be
 * squinted at as raw text) and an editor. The tab strip scrolls horizontally
 * rather than wrapping: the set runs up to 11 files (SOUL/IDENTITY/USER/
 * TOOLS/AGENTS/FOUNDATION_LINK/HEARTBEAT/MEMORY/CONTINUITY + the runtime
 * extra + the optional <PROFILE>_SUBAGENTS.md) and a wrapping strip turns
 * into an unreadable pile of chips.
 */

/** Translation key per filename, under "profileFiles.roles". Filenames are
 *  literal and never translated; only the explanation is. */
const ROLE_KEYS: Record<string, string> = {
  "SOUL.md": "soul",
  "IDENTITY.md": "identity",
  "USER.md": "user",
  "TOOLS.md": "tools",
  "AGENTS.md": "agents",
  "CLAUDE.md": "claude",
  "FOUNDATION_LINK.md": "foundationLink",
  "HEARTBEAT.md": "heartbeat",
  "MEMORY.md": "memory",
  "CONTINUITY.md": "continuity",
};

function roleKeyFor(filename: string): string {
  return ROLE_KEYS[filename] ?? (filename.endsWith("_SUBAGENTS.md") ? "subagents" : "generic");
}

/** Files ForgeHub never expects to exist up front: CONTINUITY.md is written
 *  by the agent's memory adapter on first run, and <PROFILE>_SUBAGENTS.md
 *  only exists for agents that actually orchestrate sub-agents. Their absence
 *  is normal and must not be flagged as a gap. */
function isOptional(filename: string): boolean {
  return filename === "CONTINUITY.md" || filename.endsWith("_SUBAGENTS.md");
}

/** Tab label: the filename without its .md suffix, which is the same on every
 *  tab and just costs horizontal room. */
function tabLabel(filename: string): string {
  return filename.replace(/\.md$/, "");
}

function formatBytes(size: number | null | undefined): string {
  if (size === null || size === undefined) return "—";
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} kB`;
}

function FilePanel({ agentId, file }: { agentId: string; file: AgentProfileFileInfo }) {
  const { t } = useTranslation("agent");
  const { data, isLoading, isError, error } = useAgentProfileFile(agentId, file.filename);
  const updateFile = useUpdateAgentProfileFile(agentId, file.filename);
  const [draft, setDraft] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  // Switching tabs must not carry the previous file's unsaved buffer or its
  // edit mode over.
  useEffect(() => {
    setDraft(null);
    setEditing(false);
  }, [file.filename, agentId]);

  const savedContent = data?.content ?? "";
  const content = draft ?? savedContent;
  const isDirty = draft !== null && draft !== savedContent;

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t("profileFiles.loading", { filename: file.filename })}
      </div>
    );
  }

  if (isError) {
    return (
      <p className="py-4 text-sm text-destructive">
        {t("profileFiles.loadError", {
          filename: file.filename,
          message: (error as Error)?.message,
        })}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-medium">{file.filename}</span>
            {!file.exists && (
              <Badge variant={isOptional(file.filename) ? "outline" : "warning"}>
                {t("profileFiles.notCreated")}
              </Badge>
            )}
            {file.exists && (
              <span className="text-[11px] text-muted-foreground">{formatBytes(file.size)}</span>
            )}
          </div>
          <p className="mt-1 max-w-2xl text-xs text-muted-foreground">
            {t(`profileFiles.roles.${roleKeyFor(file.filename)}`)}
          </p>
          <code className="mt-1 block truncate text-[11px] text-muted-foreground">
            {file.path}
          </code>
        </div>
        <Button variant="outline" size="sm" onClick={() => setEditing((v) => !v)}>
          {editing ? <Eye className="mr-2 h-4 w-4" /> : <Pencil className="mr-2 h-4 w-4" />}
          {editing ? t("profileFiles.viewMode") : t("profileFiles.editMode")}
        </Button>
      </div>

      {editing ? (
        <Textarea
          value={content}
          onChange={(e) => setDraft(e.target.value)}
          className="h-[28rem] resize-y overflow-y-auto font-mono text-xs leading-relaxed"
          placeholder={`# ${file.filename}`}
          spellCheck={false}
        />
      ) : content ? (
        // Rendered read view owns its vertical scrollbar so a long SOUL.md
        // scrolls inside the card instead of stretching the page.
        <div className="h-[28rem] overflow-y-auto rounded-md border bg-muted/20 p-4">
          <Markdown content={content} className="text-sm" />
        </div>
      ) : (
        <div className="flex h-[28rem] items-center justify-center rounded-md border border-dashed text-sm italic text-muted-foreground">
          {t("profileFiles.emptyFile")}
        </div>
      )}

      {editing && (
        <div className="flex flex-wrap items-center justify-end gap-3">
          {updateFile.isError && (
            <p className="text-sm text-destructive">
              {t("profileFiles.saveError", { message: (updateFile.error as Error)?.message })}
            </p>
          )}
          {updateFile.isSuccess && !isDirty && (
            <p className="text-sm text-muted-foreground">{t("profileFiles.saved")}</p>
          )}
          <Button
            size="sm"
            disabled={!isDirty || updateFile.isPending}
            onClick={() => updateFile.mutate(content, { onSuccess: () => setDraft(null) })}
          >
            {updateFile.isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            {t("profileFiles.saveButton")}
          </Button>
        </div>
      )}
    </div>
  );
}

export function AgentProfileFilesCard({ agent }: { agent: Agent }) {
  const { t } = useTranslation("agent");
  const { data, isLoading, isError, error } = useAgentProfileFiles(agent.id);
  const [activeFile, setActiveFile] = useState<string | null>(null);

  const files = data?.files ?? [];
  const selected = files.find((f) => f.filename === activeFile)?.filename ?? files[0]?.filename;
  const missingRequired = files.filter((f) => !f.exists && !isOptional(f.filename));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-xl">
          <FolderTree className="h-5 w-5" />
          {t("profileFiles.title")}
        </CardTitle>
        <CardDescription>
          {t("profileFiles.description")}{" "}
          {data?.home_path && <code className="text-xs">{data.home_path}</code>}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t("profileFiles.loadingList")}
          </div>
        )}

        {isError && (
          <p className="py-4 text-sm text-destructive">
            {t("profileFiles.listError", { message: (error as Error)?.message })}
          </p>
        )}

        {!isLoading && !isError && data && !data.home_resolved && (
          <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
            <div>
              <p className="font-medium">{t("profileFiles.homeUnreachableTitle")}</p>
              <p className="text-muted-foreground">
                {t("profileFiles.homeUnreachableBody", {
                  path: data.home_path ?? t("profileFiles.noHomeRegistered"),
                })}
              </p>
            </div>
          </div>
        )}

        {!isLoading && !isError && data?.home_resolved && selected && (
          <Tabs value={selected} onValueChange={setActiveFile}>
            {/* Horizontal scroll instead of wrapping — up to 11 tabs. */}
            <div className="-mx-1 overflow-x-auto px-1 pb-1">
              <TabsList className="flex w-max">
                {files.map((file) => (
                  <TabsTrigger
                    key={file.filename}
                    value={file.filename}
                    title={file.path}
                    className="whitespace-nowrap font-mono text-xs"
                  >
                    {tabLabel(file.filename)}
                    {!file.exists && (
                      <span
                        className={
                          isOptional(file.filename)
                            ? "ml-1 text-muted-foreground/60"
                            : "ml-1 text-amber-500"
                        }
                      >
                        •
                      </span>
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>
            </div>

            {missingRequired.length > 0 && (
              <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                {t("profileFiles.missingSummary", { count: missingRequired.length })}
                {missingRequired.map((f) => (
                  <Badge key={f.filename} variant="outline" className="font-mono text-[11px]">
                    {f.filename}
                  </Badge>
                ))}
              </p>
            )}

            {files.map((file) => (
              <TabsContent key={file.filename} value={file.filename} className="mt-4">
                <FilePanel agentId={agent.id} file={file} />
              </TabsContent>
            ))}
          </Tabs>
        )}
      </CardContent>
    </Card>
  );
}
