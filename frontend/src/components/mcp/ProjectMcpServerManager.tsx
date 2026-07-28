import { useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Loader2, Plug, Plus, Save, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  useDeleteProjectMcpServer,
  useProjectMcpServersLive,
  useUpsertProjectMcpServer,
  type ProjectMcpServer,
} from "@/hooks/useProjectMcp";

/**
 * Read/edit one project's MCP servers -- the project-scoped sibling of
 * McpServerManager.tsx (per-agent), deliberately NOT sharing code with it
 * (see the plan's Fase 2.4: touching the agent-scoped component risks
 * regressing /mcp's existing behavior, which is off limits here).
 *
 * Claude Code only today, and no enable/disable toggle at all -- `.mcp.json`
 * has no such field (same as the per-agent Claude Code format), so "off" is
 * always removal, enforced server-side.
 */

interface DraftState {
  name: string;
  transport: "stdio" | "http";
  command: string;
  argsText: string;
  envText: string;
  url: string;
}

const EMPTY_DRAFT: DraftState = { name: "", transport: "stdio", command: "", argsText: "", envText: "", url: "" };

function toDraft(server: ProjectMcpServer): DraftState {
  return {
    name: server.name,
    transport: server.url ? "http" : "stdio",
    command: server.command ?? "",
    argsText: (server.args ?? []).join("\n"),
    envText: Object.entries(server.env ?? {})
      .map(([key, value]) => `${key}=${value}`)
      .join("\n"),
    url: server.url ?? "",
  };
}

function parseEnv(text: string): Record<string, string> {
  const env: Record<string, string> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const separator = trimmed.indexOf("=");
    if (separator <= 0) continue;
    env[trimmed.slice(0, separator).trim()] = trimmed.slice(separator + 1).trim();
  }
  return env;
}

function parseArgs(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function ProjectServerForm({
  draft,
  setDraft,
  isNew,
  isPending,
  errorMessage,
  onSave,
  onCancel,
}: {
  draft: DraftState;
  setDraft: (draft: DraftState) => void;
  isNew: boolean;
  isPending: boolean;
  errorMessage?: string;
  onSave: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation("agent");
  const nameInvalid = isNew && draft.name.trim() !== "" && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(draft.name.trim());
  const canSave =
    draft.name.trim() !== "" &&
    !nameInvalid &&
    (draft.transport === "http" ? draft.url.trim() !== "" : draft.command.trim() !== "");

  return (
    <div className="space-y-3 rounded-md border bg-muted/20 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="project-mcp-name">{t("mcp.form.name")}</Label>
          <Input
            id="project-mcp-name"
            value={draft.name}
            disabled={!isNew}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="playwright"
            className="font-mono text-sm"
          />
          {nameInvalid && <p className="text-xs text-destructive">{t("mcp.form.nameInvalid")}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="project-mcp-transport">{t("mcp.form.transport")}</Label>
          <select
            id="project-mcp-transport"
            value={draft.transport}
            onChange={(e) => setDraft({ ...draft, transport: e.target.value as "stdio" | "http" })}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
          >
            <option value="stdio">{t("mcp.form.transportStdio")}</option>
            <option value="http">{t("mcp.form.transportHttp")}</option>
          </select>
        </div>
      </div>

      {draft.transport === "stdio" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="project-mcp-command">{t("mcp.form.command")}</Label>
            <Input
              id="project-mcp-command"
              value={draft.command}
              onChange={(e) => setDraft({ ...draft, command: e.target.value })}
              placeholder="npx"
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-mcp-args">{t("mcp.form.args")}</Label>
            <Textarea
              id="project-mcp-args"
              value={draft.argsText}
              onChange={(e) => setDraft({ ...draft, argsText: e.target.value })}
              placeholder={"-y\n@playwright/mcp@latest"}
              className="h-20 resize-y font-mono text-xs"
              spellCheck={false}
            />
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="project-mcp-url">{t("mcp.form.url")}</Label>
          <Input
            id="project-mcp-url"
            value={draft.url}
            onChange={(e) => setDraft({ ...draft, url: e.target.value })}
            placeholder="https://mcp.example.com/mcp"
            className="font-mono text-sm"
          />
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="project-mcp-env">{t("mcp.form.env")}</Label>
        <Textarea
          id="project-mcp-env"
          value={draft.envText}
          onChange={(e) => setDraft({ ...draft, envText: e.target.value })}
          placeholder={"API_KEY=..."}
          className="h-20 resize-y font-mono text-xs"
          spellCheck={false}
        />
        <p className="text-xs text-muted-foreground">{t("mcp.form.envHint")}</p>
      </div>

      {errorMessage && <p className="text-sm text-destructive">{errorMessage}</p>}

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          <X className="mr-2 h-4 w-4" />
          {t("mcp.form.cancel")}
        </Button>
        <Button size="sm" disabled={!canSave || isPending} onClick={onSave}>
          {isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
          {t("mcp.form.save")}
        </Button>
      </div>
    </div>
  );
}

export function ProjectMcpServerManager({
  projectId,
  servers,
  isLoading,
  workingDirectoryPath,
}: {
  projectId: string;
  servers: ProjectMcpServer[] | undefined;
  isLoading?: boolean;
  workingDirectoryPath: string | null;
}) {
  const { t } = useTranslation("agent");
  const upsert = useUpsertProjectMcpServer(projectId);
  const remove = useDeleteProjectMcpServer(projectId);
  const live = useProjectMcpServersLive(projectId);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [pendingRemoval, setPendingRemoval] = useState<string | null>(null);

  const rows = servers ?? [];

  function startCreate() {
    setDraft(EMPTY_DRAFT);
    setEditing("__new__");
  }

  function startEdit(server: ProjectMcpServer) {
    setDraft(toDraft(server));
    setEditing(server.name);
  }

  function save() {
    const name = draft.name.trim();
    upsert.mutate(
      {
        name,
        command: draft.transport === "stdio" ? draft.command.trim() : null,
        args: draft.transport === "stdio" ? parseArgs(draft.argsText) : [],
        env: parseEnv(draft.envText),
        url: draft.transport === "http" ? draft.url.trim() : null,
      },
      { onSuccess: () => setEditing(null) },
    );
  }

  if (!workingDirectoryPath) {
    return (
      <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
        <p>{t("mcp.projectNoWorkingDir")}</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t("mcp.loading")}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <code className="block truncate text-[11px] text-muted-foreground">
            {live.data?.config_path ?? `${workingDirectoryPath}/.mcp.json`}
            {live.data && !live.data.config_exists && ` — ${t("mcp.configMissing")}`}
          </code>
          <p className="text-[11px] text-muted-foreground">{t("mcp.noToggleHint")}</p>
        </div>
        <Button size="sm" variant="outline" onClick={startCreate} disabled={editing === "__new__"}>
          <Plus className="mr-2 h-4 w-4" />
          {t("mcp.addServer")}
        </Button>
      </div>

      {editing === "__new__" && (
        <ProjectServerForm
          draft={draft}
          setDraft={setDraft}
          isNew
          isPending={upsert.isPending}
          errorMessage={upsert.isError ? (upsert.error as Error)?.message : undefined}
          onSave={save}
          onCancel={() => setEditing(null)}
        />
      )}

      {rows.length === 0 && editing !== "__new__" && (
        <p className="rounded-md border border-dashed p-6 text-center text-sm italic text-muted-foreground">
          {t("mcp.emptyProject")}
        </p>
      )}

      <ul className="space-y-2">
        {rows.map((server) =>
          editing === server.name ? (
            <li key={server.name}>
              <ProjectServerForm
                draft={draft}
                setDraft={setDraft}
                isNew={false}
                isPending={upsert.isPending}
                errorMessage={upsert.isError ? (upsert.error as Error)?.message : undefined}
                onSave={save}
                onCancel={() => setEditing(null)}
              />
            </li>
          ) : (
            <li
              key={server.name}
              className="flex flex-wrap items-start justify-between gap-3 rounded-md border p-3"
            >
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Plug className="h-4 w-4 text-muted-foreground" />
                  <span className="font-mono text-sm font-medium">{server.name}</span>
                  {server.url && <Badge variant="outline">HTTP</Badge>}
                </div>
                <code className="block truncate text-[11px] text-muted-foreground">
                  {server.url ?? [server.command, ...(server.args ?? [])].join(" ")}
                </code>
                {Object.keys(server.env ?? {}).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {Object.keys(server.env).map((key) => (
                      <Badge key={key} variant="outline" className="font-mono text-[10px]">
                        {key}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Button variant="ghost" size="sm" onClick={() => startEdit(server)}>
                  {t("mcp.editAction")}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive"
                  onClick={() => setPendingRemoval(server.name)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          ),
        )}
      </ul>

      <ConfirmDialog
        open={pendingRemoval !== null}
        title={t("mcp.removeTitle")}
        description={t("mcp.removeDescription", {
          name: pendingRemoval ?? "",
          path: live.data?.config_path ?? `${workingDirectoryPath}/.mcp.json`,
        })}
        loading={remove.isPending}
        onConfirm={() => {
          if (!pendingRemoval) return;
          remove.mutate({ name: pendingRemoval }, { onSuccess: () => setPendingRemoval(null) });
        }}
        onCancel={() => setPendingRemoval(null)}
      />
    </div>
  );
}
