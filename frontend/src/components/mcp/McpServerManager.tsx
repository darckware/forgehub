import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Loader2, Plug, Plus, Power, PowerOff, Save, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import {
  useDeleteAgentMcpServer,
  useUpsertAgentMcpServer,
  type AgentMcpServer,
  type AgentMcpServers,
} from "@/hooks/useAgent";

/**
 * Read/edit one agent's MCP servers, shared by the agent page card and the
 * MCP page's per-agent panel.
 *
 * It edits the runtime's own config file (see backend core/agent_mcp.py), so
 * every state here is a real file state, not a ForgeHub record: `config_path`
 * is always visible for that reason. Enable/disable is only offered for
 * runtimes whose format has a flag for it — for Claude Code and agy, removing
 * the server is the only way to turn it off, and a toggle that silently did a
 * delete would be a trap.
 *
 * Args and env are edited as plain text (one per line, `KEY=VALUE`) rather
 * than as row widgets: these are copied from a runtime's docs or another
 * agent far more often than they are typed field by field.
 */

interface DraftState {
  name: string;
  transport: "stdio" | "http";
  command: string;
  argsText: string;
  envText: string;
  url: string;
  enabled: boolean;
}

const EMPTY_DRAFT: DraftState = {
  name: "",
  transport: "stdio",
  command: "",
  argsText: "",
  envText: "",
  url: "",
  enabled: true,
};

function toDraft(server: AgentMcpServer): DraftState {
  return {
    name: server.name,
    transport: server.url ? "http" : "stdio",
    command: server.command ?? "",
    argsText: (server.args ?? []).join("\n"),
    envText: Object.entries(server.env ?? {})
      .map(([key, value]) => `${key}=${value}`)
      .join("\n"),
    url: server.url ?? "",
    enabled: server.enabled,
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

function ServerForm({
  draft,
  setDraft,
  supportsToggle,
  isNew,
  isPending,
  errorMessage,
  onSave,
  onCancel,
}: {
  draft: DraftState;
  setDraft: (draft: DraftState) => void;
  supportsToggle: boolean;
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
          <Label htmlFor="mcp-name">{t("mcp.form.name")}</Label>
          <Input
            id="mcp-name"
            value={draft.name}
            disabled={!isNew}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="forgehub"
            className="font-mono text-sm"
          />
          {nameInvalid && <p className="text-xs text-destructive">{t("mcp.form.nameInvalid")}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="mcp-transport">{t("mcp.form.transport")}</Label>
          <select
            id="mcp-transport"
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
            <Label htmlFor="mcp-command">{t("mcp.form.command")}</Label>
            <Input
              id="mcp-command"
              value={draft.command}
              onChange={(e) => setDraft({ ...draft, command: e.target.value })}
              placeholder="uv"
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="mcp-args">{t("mcp.form.args")}</Label>
            <Textarea
              id="mcp-args"
              value={draft.argsText}
              onChange={(e) => setDraft({ ...draft, argsText: e.target.value })}
              placeholder={"run\n/root/project/forgehub/host-bridge/forgehub_messages_mcp.py"}
              className="h-20 resize-none font-mono text-xs"
              spellCheck={false}
            />
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="mcp-url">{t("mcp.form.url")}</Label>
          <Input
            id="mcp-url"
            value={draft.url}
            onChange={(e) => setDraft({ ...draft, url: e.target.value })}
            placeholder="https://mcp.example.com/mcp"
            className="font-mono text-sm"
          />
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="mcp-env">{t("mcp.form.env")}</Label>
        <Textarea
          id="mcp-env"
          value={draft.envText}
          onChange={(e) => setDraft({ ...draft, envText: e.target.value })}
          placeholder={"FORGEHUB_API_URL=http://localhost:8000\nFORGEHUB_AGENT_SLUG=athos"}
          className="h-20 resize-none font-mono text-xs"
          spellCheck={false}
        />
        <p className="text-xs text-muted-foreground">{t("mcp.form.envHint")}</p>
      </div>

      {supportsToggle && (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={draft.enabled}
            onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
            className="h-4 w-4 rounded border-input"
          />
          {t("mcp.form.enabled")}
        </label>
      )}

      {errorMessage && <p className="text-sm text-destructive">{errorMessage}</p>}

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          <X className="mr-2 h-4 w-4" />
          {t("mcp.form.cancel")}
        </Button>
        <Button size="sm" disabled={!canSave || isPending} onClick={onSave}>
          {isPending ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Save className="mr-2 h-4 w-4" />
          )}
          {t("mcp.form.save")}
        </Button>
      </div>
    </div>
  );
}

export function McpServerManager({
  agentId,
  data,
  isLoading,
  errorMessage,
}: {
  agentId: string;
  data: AgentMcpServers | undefined;
  isLoading?: boolean;
  errorMessage?: string;
}) {
  const { t } = useTranslation("agent");
  const upsert = useUpsertAgentMcpServer(agentId);
  const remove = useDeleteAgentMcpServer(agentId);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [pendingRemoval, setPendingRemoval] = useState<string | null>(null);

  // Switching agents (the MCP page renders one panel per agent) must not carry
  // another agent's open form over.
  useEffect(() => {
    setEditing(null);
    setDraft(EMPTY_DRAFT);
  }, [agentId]);

  const servers = data?.servers ?? [];
  const supportsToggle = data?.supports_toggle ?? false;

  function startCreate() {
    setDraft(EMPTY_DRAFT);
    setEditing("__new__");
  }

  function startEdit(server: AgentMcpServer) {
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
        enabled: draft.enabled,
      },
      { onSuccess: () => setEditing(null) },
    );
  }

  function toggle(server: AgentMcpServer) {
    upsert.mutate({
      name: server.name,
      command: server.command ?? null,
      args: server.args ?? [],
      env: server.env ?? {},
      url: server.url ?? null,
      enabled: !server.enabled,
    });
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        {t("mcp.loading")}
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className="flex items-start gap-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
        <p>{errorMessage}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0 space-y-1">
          {data?.config_path && (
            <code className="block truncate text-[11px] text-muted-foreground">
              {data.config_path}
              {!data.config_exists && ` — ${t("mcp.configMissing")}`}
            </code>
          )}
          {!supportsToggle && servers.length > 0 && (
            <p className="text-[11px] text-muted-foreground">{t("mcp.noToggleHint")}</p>
          )}
        </div>
        <Button size="sm" variant="outline" onClick={startCreate} disabled={editing === "__new__"}>
          <Plus className="mr-2 h-4 w-4" />
          {t("mcp.addServer")}
        </Button>
      </div>

      {data?.error && (
        <div className="flex items-start gap-3 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div>
            <p className="font-medium">{t("mcp.parseErrorTitle")}</p>
            <p className="text-muted-foreground">{data.error}</p>
          </div>
        </div>
      )}

      {editing === "__new__" && (
        <ServerForm
          draft={draft}
          setDraft={setDraft}
          supportsToggle={supportsToggle}
          isNew
          isPending={upsert.isPending}
          errorMessage={upsert.isError ? (upsert.error as Error)?.message : undefined}
          onSave={save}
          onCancel={() => setEditing(null)}
        />
      )}

      {servers.length === 0 && editing !== "__new__" && (
        <p className="rounded-md border border-dashed p-6 text-center text-sm italic text-muted-foreground">
          {t("mcp.empty")}
        </p>
      )}

      <ul className="space-y-2">
        {servers.map((server) =>
          editing === server.name ? (
            <li key={server.name}>
              <ServerForm
                draft={draft}
                setDraft={setDraft}
                supportsToggle={supportsToggle}
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
                  {!server.enabled && <Badge variant="outline">{t("mcp.disabled")}</Badge>}
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
                {supportsToggle && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => toggle(server)}
                    disabled={upsert.isPending}
                    title={server.enabled ? t("mcp.disableAction") : t("mcp.enableAction")}
                  >
                    {server.enabled ? (
                      <PowerOff className="h-4 w-4" />
                    ) : (
                      <Power className="h-4 w-4" />
                    )}
                  </Button>
                )}
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
          path: data?.config_path ?? "",
        })}
        loading={remove.isPending}
        onConfirm={() => {
          if (!pendingRemoval) return;
          remove.mutate(pendingRemoval, { onSuccess: () => setPendingRemoval(null) });
        }}
        onCancel={() => setPendingRemoval(null)}
      />
    </div>
  );
}
