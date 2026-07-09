import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Eye,
  Loader2,
  MessageSquare,
  Pencil,
  RefreshCw,
  Save,
  Search,
  Settings2,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAgents } from "@/hooks/useAgent";
import {
  AGENT_TOOL_STATUSES,
  useCreateTool,
  useDeleteTool,
  useSaveToolContent,
  useScanTools,
  useToolCategories,
  useToolContent,
  useTools,
  useUpdateTool,
  type AgentTool,
  type AgentToolStatus,
  type ToolCreateInput,
} from "@/hooks/useTools";
import { useChatHandoffStore } from "@/store/chatHandoff";

/** Draft seeded into the responsible agent's workspace chat composer —
 * leads with the file path so the agent has the maintenance context. */
function buildMaintenanceMessage(tool: AgentTool): string {
  return [
    `Maintenance for tool "${tool.name}" (category: ${tool.category}).`,
    `File: ${tool.file_path}`,
    `Registered functionality: ${tool.description}`,
    "",
    "Review the file above and help me maintain this tool.",
  ].join("\n");
}

function ToolFormModal({
  initial,
  onClose,
}: {
  initial: AgentTool | null;
  onClose: () => void;
}) {
  const { data: agents } = useAgents();
  const { data: categories } = useToolCategories();
  const createTool = useCreateTool();
  const updateTool = useUpdateTool();
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<ToolCreateInput>(
    initial
      ? {
          agent_id: initial.agent_id,
          name: initial.name,
          description: initial.description,
          file_path: initial.file_path,
          category: initial.category,
          status: initial.status,
        }
      : { agent_id: "", name: "", description: "", file_path: "", category: "", status: "active" }
  );
  const pending = createTool.isPending || updateTool.isPending;

  function handleSave() {
    setError(null);
    if (!form.agent_id || !form.name.trim() || !form.description.trim() || !form.file_path.trim()) {
      setError("Responsible agent, name, file path and description are required.");
      return;
    }
    const payload: ToolCreateInput = {
      agent_id: form.agent_id,
      name: form.name.trim(),
      description: form.description.trim(),
      file_path: form.file_path.trim(),
      category: form.category.trim() || "general",
      status: form.status,
    };
    const opts = {
      onSuccess: onClose,
      onError: (e: Error) => setError(e.message || "Could not save."),
    };
    if (initial) updateTool.mutate({ id: initial.id, data: payload }, opts);
    else createTool.mutate(payload, opts);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{initial ? "Edit tool" : "Register tool"}</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Responsible agent</Label>
              <Select
                value={form.agent_id}
                onChange={(e) => setForm((f) => ({ ...f, agent_id: e.target.value }))}
              >
                <option value="">Select an agent…</option>
                {(agents ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Tool name</Label>
              <Input
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="net-scanner"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Category</Label>
              <Input
                value={form.category}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                placeholder="network, monitoring, reporting…"
                list="tool-categories"
              />
              <datalist id="tool-categories">
                {(categories ?? []).map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </div>
            <div className="space-y-1">
              <Label>Status</Label>
              <Select
                value={form.status}
                onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as AgentToolStatus }))}
              >
                {AGENT_TOOL_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label>File path</Label>
            <Input
              value={form.file_path}
              onChange={(e) => setForm((f) => ({ ...f, file_path: e.target.value }))}
              placeholder="/root/.hermes/profiles/aegis/tools/net_scanner.py"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label>What it does</Label>
            <Textarea
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Scans the local network and reports open ports"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={pending}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {initial ? "Save" : "Register"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** View/edit the tool's file content (read via GET /tools/{id}/content,
 * saved via PUT — the backend remaps the stored host path to its container
 * mounts). */
function ToolFileModal({
  tool,
  startEditing,
  onClose,
}: {
  tool: AgentTool;
  startEditing: boolean;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useToolContent(tool.id);
  const saveMut = useSaveToolContent();
  const [editing, setEditing] = useState(startEditing);
  const [draft, setDraft] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const content = draft ?? data?.content ?? "";

  const handleSave = () => {
    setSaveError(null);
    saveMut.mutate(
      { id: tool.id, content },
      {
        onSuccess: () => {
          setDraft(null);
          setEditing(false);
        },
        onError: (e) => setSaveError(e.message || "Could not save file."),
      }
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 flex w-full max-w-4xl flex-col rounded-xl border border-border bg-card shadow-2xl" style={{ maxHeight: "85vh" }}>
        <div className="h-1 w-full rounded-t-xl bg-blue-500" />
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-border">
          <div className="min-w-0">
            <p className="font-semibold text-sm truncate">{tool.name}</p>
            <code className="text-[11px] text-muted-foreground font-mono truncate block">{tool.file_path}</code>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {!editing && data?.exists && (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
              </Button>
            )}
            {editing && (
              <Button size="sm" onClick={handleSave} disabled={saveMut.isPending}>
                {saveMut.isPending ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
                Save
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="flex-1 min-h-0 overflow-auto p-4" style={{ minHeight: "300px" }}>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading file...
            </div>
          ) : isError ? (
            <p className="text-sm text-destructive">{(error as Error)?.message ?? "Could not read file."}</p>
          ) : !data?.exists ? (
            <p className="text-sm text-muted-foreground italic">File not found on disk.</p>
          ) : editing ? (
            <Textarea
              value={content}
              onChange={(e) => setDraft(e.target.value)}
              spellCheck={false}
              className="h-full min-h-[50vh] font-mono text-xs resize-none"
            />
          ) : (
            <pre className="text-xs font-mono whitespace-pre-wrap break-all text-foreground/90">{content}</pre>
          )}
          {saveError && <p className="mt-2 text-sm text-destructive">{saveError}</p>}
        </div>
      </div>
    </div>
  );
}

/** Registry of tools built by agents: file location, functionality,
 * category and the responsible agent. The chat action hands the tool off
 * to the responsible agent's chat in the Workspace (composer pre-filled
 * with the file path) for maintenance. */
export default function ToolsPage() {
  const [agentFilter, setAgentFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [search, setSearch] = useState("");
  const [formTool, setFormTool] = useState<AgentTool | null | "new">(null);
  const [fileModal, setFileModal] = useState<{ tool: AgentTool; editing: boolean } | null>(null);
  const [deleting, setDeleting] = useState<AgentTool | null>(null);

  const { data: agents } = useAgents();
  const { data: categories } = useToolCategories();
  const filter = useMemo(
    () => ({
      agentId: agentFilter || undefined,
      category: categoryFilter || undefined,
      q: search.trim() || undefined,
    }),
    [agentFilter, categoryFilter, search]
  );
  const { data: tools, isLoading } = useTools(filter);
  const deleteTool = useDeleteTool();
  const scanTools = useScanTools();
  const [scanSummary, setScanSummary] = useState<string | null>(null);
  const setDraft = useChatHandoffStore((s) => s.setDraft);
  const navigate = useNavigate();

  function handleScan() {
    setScanSummary(null);
    scanTools.mutate(undefined, {
      onSuccess: (r) =>
        setScanSummary(`Scan: ${r.scanned} files found, ${r.created} registered, ${r.skipped} already known.`),
      onError: (e) => setScanSummary(e.message || "Scan failed."),
    });
  }

  function openMaintenanceChat(tool: AgentTool) {
    setDraft(buildMaintenanceMessage(tool), tool.agent_id);
    navigate("/workspace");
  }

  return (
    <div className="flex min-h-0 flex-1 w-full flex-col gap-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <Wrench className="h-5 w-5" /> Agent Tools
          {tools && <span className="text-sm font-normal text-muted-foreground">{tools.length} registered</span>}
        </h1>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          disabled={scanTools.isPending}
          title="Scan every profile's scripts dir and register new tools; unowned files go to Athos"
          onClick={handleScan}
        >
          {scanTools.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Sync
        </Button>
      </div>

      {scanSummary && <p className="text-xs text-muted-foreground">{scanSummary}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name, description or path…"
            className="w-72 pl-8"
          />
        </div>
        <Select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className="w-48">
          <option value="">All agents</option>
          {(agents ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
        <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="w-48">
          <option value="">All categories</option>
          {(categories ?? []).map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      </div>

      {isLoading && (
        <div className="flex justify-center py-12">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      )}

      {!isLoading && (tools ?? []).length === 0 && (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            No tools registered yet. Use “Register tool” to record a tool an agent has built.
          </CardContent>
        </Card>
      )}

      {(tools ?? []).length > 0 && (
        <Card className="flex-1 min-h-0 overflow-hidden">
          <CardContent className="h-full overflow-auto p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tool</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead className="sticky right-0 w-48 bg-card text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(tools ?? []).map((tool) => (
                  <TableRow key={tool.id}>
                    <TableCell>
                      <p className="font-medium">{tool.name}</p>
                      <p className="max-w-sm truncate text-xs text-muted-foreground" title={tool.description}>
                        {tool.description}
                      </p>
                    </TableCell>
                    <TableCell>{tool.agent_name ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{tool.category}</Badge>
                    </TableCell>
                    <TableCell>
                      <code className="block max-w-xs truncate font-mono text-xs" title={tool.file_path}>
                        {tool.file_path}
                      </code>
                    </TableCell>
                    <TableCell className="sticky right-0 bg-card text-right">
                      <div className="flex justify-end gap-0.5">
                        <Button
                          size="icon"
                          variant="ghost"
                          title={`Open maintenance chat with ${tool.agent_name ?? "the responsible agent"}`}
                          onClick={() => openMaintenanceChat(tool)}
                        >
                          <MessageSquare className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          title="View file"
                          onClick={() => setFileModal({ tool, editing: false })}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          title="Edit file"
                          onClick={() => setFileModal({ tool, editing: true })}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          title="Edit registration"
                          onClick={() => setFormTool(tool)}
                        >
                          <Settings2 className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          title="Delete file and registration"
                          className="text-destructive"
                          onClick={() => setDeleting(tool)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {formTool !== null && (
        <ToolFormModal initial={formTool === "new" ? null : formTool} onClose={() => setFormTool(null)} />
      )}

      {fileModal && (
        <ToolFileModal
          key={`${fileModal.tool.id}-${fileModal.editing}`}
          tool={fileModal.tool}
          startEditing={fileModal.editing}
          onClose={() => setFileModal(null)}
        />
      )}

      <ConfirmDialog
        open={deleting !== null}
        title={`Delete "${deleting?.name ?? ""}"`}
        description={`Removes the registration and deletes the file ${deleting?.file_path ?? ""} from disk. This action cannot be undone.`}
        confirmLabel="Delete"
        loading={deleteTool.isPending}
        onConfirm={() => {
          if (deleting)
            deleteTool.mutate(
              { id: deleting.id, deleteFile: true },
              { onSuccess: () => setDeleting(null) }
            );
        }}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
