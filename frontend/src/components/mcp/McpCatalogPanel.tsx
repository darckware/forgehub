import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Globe2,
  Link2,
  Loader2,
  Plug,
  Plus,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useAgents } from "@/hooks/useAgent";
import { useProjects } from "@/hooks/useProject";
import {
  useAssignMcpCatalogServer,
  useCreateMcpCatalogServer,
  useDeleteMcpCatalogServer,
  useMcpCatalogAssignments,
  useMcpCatalogServers,
  useUnassignMcpCatalogServer,
  useUpdateMcpCatalogServer,
  type McpCatalogServer,
  type McpCatalogServerInput,
} from "@/hooks/useMcpCatalog";

/**
 * Register an MCP server once, assign it to any number of agents/projects
 * from here -- the catalog layer described in the plan's Fase 1. Does not
 * replace `/mcp` (per-agent direct editor) or a project's own MCP card
 * (per-project direct editor); this is the "cadastra uma vez" front end
 * for the same underlying write engines.
 */

interface DraftState {
  name: string;
  description: string;
  transport: "stdio" | "http";
  command: string;
  argsText: string;
  envText: string;
  url: string;
  applyToAllAgents: boolean;
}

const EMPTY_DRAFT: DraftState = {
  name: "",
  description: "",
  transport: "stdio",
  command: "",
  argsText: "",
  envText: "",
  url: "",
  applyToAllAgents: false,
};

function toDraft(server: McpCatalogServer): DraftState {
  return {
    name: server.name,
    description: server.description ?? "",
    transport: server.url ? "http" : "stdio",
    command: server.command ?? "",
    argsText: (server.args ?? []).join("\n"),
    envText: Object.entries(server.env ?? {})
      .map(([key, value]) => `${key}=${value}`)
      .join("\n"),
    url: server.url ?? "",
    applyToAllAgents: server.apply_to_all_agents,
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

function draftToInput(draft: DraftState): McpCatalogServerInput {
  return {
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    transport: draft.transport,
    command: draft.transport === "stdio" ? draft.command.trim() : null,
    args: draft.transport === "stdio" ? parseArgs(draft.argsText) : [],
    env: parseEnv(draft.envText),
    url: draft.transport === "http" ? draft.url.trim() : null,
    apply_to_all_agents: draft.applyToAllAgents,
  };
}

function CatalogServerForm({
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
  const nameInvalid = draft.name.trim() !== "" && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(draft.name.trim());
  const canSave =
    draft.name.trim() !== "" &&
    !nameInvalid &&
    (draft.transport === "http" ? draft.url.trim() !== "" : draft.command.trim() !== "");

  return (
    <div className="space-y-3 rounded-md border bg-muted/20 p-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="catalog-name">{t("mcp.form.name")}</Label>
          <Input
            id="catalog-name"
            value={draft.name}
            disabled={!isNew}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="notion"
            className="font-mono text-sm"
          />
          {nameInvalid && <p className="text-xs text-destructive">{t("mcp.form.nameInvalid")}</p>}
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="catalog-transport">{t("mcp.form.transport")}</Label>
          <select
            id="catalog-transport"
            value={draft.transport}
            onChange={(e) => setDraft({ ...draft, transport: e.target.value as "stdio" | "http" })}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
          >
            <option value="stdio">{t("mcp.form.transportStdio")}</option>
            <option value="http">{t("mcp.form.transportHttp")}</option>
          </select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="catalog-description">{t("mcp.catalog.form.description")}</Label>
        <Input
          id="catalog-description"
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          placeholder={t("mcp.catalog.form.descriptionPlaceholder")}
        />
      </div>

      {draft.transport === "stdio" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="catalog-command">{t("mcp.form.command")}</Label>
            <Input
              id="catalog-command"
              value={draft.command}
              onChange={(e) => setDraft({ ...draft, command: e.target.value })}
              placeholder="npx"
              className="font-mono text-sm"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="catalog-args">{t("mcp.form.args")}</Label>
            <Textarea
              id="catalog-args"
              value={draft.argsText}
              onChange={(e) => setDraft({ ...draft, argsText: e.target.value })}
              placeholder={"-y\n@notionhq/notion-mcp-server"}
              className="h-20 resize-y font-mono text-xs"
              spellCheck={false}
            />
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          <Label htmlFor="catalog-url">{t("mcp.form.url")}</Label>
          <Input
            id="catalog-url"
            value={draft.url}
            onChange={(e) => setDraft({ ...draft, url: e.target.value })}
            placeholder="https://mcp.example.com/mcp"
            className="font-mono text-sm"
          />
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="catalog-env">{t("mcp.form.env")}</Label>
        <Textarea
          id="catalog-env"
          value={draft.envText}
          onChange={(e) => setDraft({ ...draft, envText: e.target.value })}
          placeholder={"NOTION_API_KEY=..."}
          className="h-20 resize-y font-mono text-xs"
          spellCheck={false}
        />
        <p className="text-xs text-muted-foreground">{t("mcp.form.envHint")}</p>
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={draft.applyToAllAgents}
          onChange={(e) => setDraft({ ...draft, applyToAllAgents: e.target.checked })}
          className="mt-0.5 h-4 w-4 rounded border-input"
        />
        <span>
          <span className="font-medium">{t("mcp.catalog.form.applyToAll")}</span>
          <br />
          <span className="text-xs text-muted-foreground">{t("mcp.catalog.form.applyToAllHint")}</span>
        </span>
      </label>

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

function AssignmentsPanel({ server }: { server: McpCatalogServer }) {
  const { t } = useTranslation("agent");
  const { data: assignments } = useMcpCatalogAssignments(server.id);
  const { data: agents } = useAgents();
  const { data: projects } = useProjects();
  const assign = useAssignMcpCatalogServer(server.id);
  const unassign = useUnassignMcpCatalogServer(server.id);
  const [pickerType, setPickerType] = useState<"agent" | "project">("agent");
  const [pickerId, setPickerId] = useState("");

  const assignedAgentIds = new Set(
    (assignments ?? []).filter((a) => a.target_type === "agent").map((a) => a.target_id),
  );
  const assignedProjectIds = new Set(
    (assignments ?? []).filter((a) => a.target_type === "project").map((a) => a.target_id),
  );

  const agentName = (id: string) => agents?.find((a) => a.id === id)?.name ?? id;
  const projectName = (id: string) => projects?.find((p) => p.id === id)?.name ?? id;

  return (
    <div className="space-y-3 border-t px-4 py-3">
      {server.apply_to_all_agents && (
        <div className="flex items-start gap-2 rounded-md border border-blue-500/30 bg-blue-500/10 p-2 text-xs">
          <Globe2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-blue-600" />
          <span>{t("mcp.catalog.globalNotice")}</span>
        </div>
      )}

      <ul className="space-y-1.5">
        {(assignments ?? []).map((a) => (
          <li key={a.id} className="flex items-center justify-between gap-2 rounded-md border p-2 text-sm">
            <div className="flex min-w-0 items-center gap-2">
              {a.target_type === "agent" ? (
                <Badge variant="outline">{t("mcp.catalog.targetAgent")}</Badge>
              ) : (
                <Badge variant="outline">{t("mcp.catalog.targetProject")}</Badge>
              )}
              <span className="truncate font-medium">
                {a.target_type === "agent" ? agentName(a.target_id) : projectName(a.target_id)}
              </span>
              {a.last_sync_error ? (
                <span title={a.last_sync_error}>
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-destructive" />
                </span>
              ) : a.last_synced_at ? (
                <Badge variant="success">{t("mcp.catalog.synced")}</Badge>
              ) : null}
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="shrink-0 text-destructive"
              onClick={() => unassign.mutate(a.id)}
              disabled={unassign.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </li>
        ))}
        {(assignments ?? []).length === 0 && (
          <p className="text-xs italic text-muted-foreground">{t("mcp.catalog.noAssignments")}</p>
        )}
      </ul>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={pickerType}
          onChange={(e) => {
            setPickerType(e.target.value as "agent" | "project");
            setPickerId("");
          }}
          className="flex h-8 rounded-md border border-input bg-background px-2 text-xs shadow-sm"
        >
          <option value="agent">{t("mcp.catalog.targetAgent")}</option>
          <option value="project">{t("mcp.catalog.targetProject")}</option>
        </select>
        <select
          value={pickerId}
          onChange={(e) => setPickerId(e.target.value)}
          className="flex h-8 min-w-[10rem] flex-1 rounded-md border border-input bg-background px-2 text-xs shadow-sm"
        >
          <option value="">{t("mcp.catalog.pickTarget")}</option>
          {pickerType === "agent"
            ? (agents ?? [])
                .filter((a) => !assignedAgentIds.has(a.id))
                .map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))
            : (projects ?? [])
                .filter((p) => !assignedProjectIds.has(p.id))
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
        </select>
        <Button
          size="sm"
          variant="outline"
          disabled={!pickerId || assign.isPending}
          onClick={() => {
            assign.mutate({ targetType: pickerType, targetId: pickerId }, { onSuccess: () => setPickerId("") });
          }}
        >
          {assign.isPending ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Plus className="mr-2 h-3.5 w-3.5" />}
          {t("mcp.catalog.assignButton")}
        </Button>
      </div>
    </div>
  );
}

/** One catalog server's row -- owns its own edit-mode state and its own
 * `useUpdateMcpCatalogServer(server.id)` call. Kept as a real component
 * (not a helper function called from inside `.map()`) specifically so that
 * hook call is legal: each row is a distinct component instance, so calling
 * the same hook with a different id per instance is fine, whereas calling
 * a hook-wrapping function conditionally/repeatedly inside a parent's
 * render (the previous shape here) violates the Rules of Hooks for real,
 * not just as a lint nit -- React would throw "Rendered more hooks than
 * during the previous render" the moment more than one row was mounted. */
function CatalogServerRow({
  server,
  expanded,
  onToggleExpand,
  onRequestRemove,
}: {
  server: McpCatalogServer;
  expanded: boolean;
  onToggleExpand: () => void;
  onRequestRemove: () => void;
}) {
  const { t } = useTranslation("agent");
  const update = useUpdateMcpCatalogServer(server.id);
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<DraftState>(() => toDraft(server));

  if (isEditing) {
    return (
      <li>
        <CatalogServerForm
          draft={draft}
          setDraft={setDraft}
          isNew={false}
          isPending={update.isPending}
          errorMessage={update.isError ? (update.error as Error)?.message : undefined}
          onSave={() =>
            update.mutate(draftToInput(draft), { onSuccess: () => setIsEditing(false) })
          }
          onCancel={() => setIsEditing(false)}
        />
      </li>
    );
  }

  return (
    <li className="rounded-md border">
      <div className="flex flex-wrap items-start justify-between gap-3 p-3">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-start gap-2 text-left"
          onClick={onToggleExpand}
        >
          {expanded ? (
            <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              {server.url ? (
                <Link2 className="h-4 w-4 text-muted-foreground" />
              ) : (
                <Plug className="h-4 w-4 text-muted-foreground" />
              )}
              <span className="font-mono text-sm font-medium">{server.name}</span>
              {server.is_builtin && <Badge variant="outline">{t("mcp.catalog.builtinBadge")}</Badge>}
              {server.apply_to_all_agents && (
                <Badge variant="outline" className="gap-1">
                  <Globe2 className="h-3 w-3" />
                  {t("mcp.catalog.globalBadge")}
                </Badge>
              )}
            </div>
            {server.description && <p className="text-xs text-muted-foreground">{server.description}</p>}
            <code className="block truncate text-[11px] text-muted-foreground">
              {server.url ?? [server.command, ...(server.args ?? [])].join(" ")}
            </code>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDraft(toDraft(server));
              setIsEditing(true);
            }}
          >
            {t("mcp.editAction")}
          </Button>
          <Button variant="ghost" size="sm" className="text-destructive" onClick={onRequestRemove}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      {expanded && <AssignmentsPanel server={server} />}
    </li>
  );
}

export function McpCatalogPanel() {
  const { t } = useTranslation("agent");
  const { data: servers, isLoading } = useMcpCatalogServers();
  const create = useCreateMcpCatalogServer();
  const [creating, setCreating] = useState(false);
  const [newDraft, setNewDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pendingRemoval, setPendingRemoval] = useState<McpCatalogServer | null>(null);
  const [search, setSearch] = useState("");
  const removeServer = useDeleteMcpCatalogServer();

  const filtered = (servers ?? []).filter((s) => {
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return s.name.toLowerCase().includes(q) || (s.description ?? "").toLowerCase().includes(q);
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="relative min-w-[16rem] flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("mcp.catalog.searchPlaceholder")}
            className="pl-8"
          />
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            setNewDraft(EMPTY_DRAFT);
            setCreating(true);
          }}
          disabled={creating}
        >
          <Plus className="mr-2 h-4 w-4" />
          {t("mcp.catalog.newServer")}
        </Button>
      </div>

      {creating && (
        <CatalogServerForm
          draft={newDraft}
          setDraft={setNewDraft}
          isNew
          isPending={create.isPending}
          errorMessage={create.isError ? (create.error as Error)?.message : undefined}
          onSave={() => create.mutate(draftToInput(newDraft), { onSuccess: () => setCreating(false) })}
          onCancel={() => setCreating(false)}
        />
      )}

      {isLoading && (
        <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {t("mcp.loading")}
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <p className="rounded-md border border-dashed p-6 text-center text-sm italic text-muted-foreground">
          {t("mcp.catalog.empty")}
        </p>
      )}

      <ul className="space-y-2">
        {filtered.map((server) => (
          <CatalogServerRow
            key={server.id}
            server={server}
            expanded={expanded === server.id}
            onToggleExpand={() => setExpanded(expanded === server.id ? null : server.id)}
            onRequestRemove={() => setPendingRemoval(server)}
          />
        ))}
      </ul>

      <ConfirmDialog
        open={pendingRemoval !== null}
        title={t("mcp.catalog.removeTitle")}
        description={t("mcp.catalog.removeDescription", { name: pendingRemoval?.name ?? "" })}
        loading={removeServer.isPending}
        onConfirm={() => {
          if (!pendingRemoval) return;
          removeServer.mutate(pendingRemoval.id, { onSuccess: () => setPendingRemoval(null) });
        }}
        onCancel={() => setPendingRemoval(null)}
      />
    </div>
  );
}
