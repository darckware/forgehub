import { useEffect, useMemo, useState } from "react";
import {
  Eye,
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-react";
import {
  DocumentBrowser,
  filterDocumentTree,
  type DocumentViewMode,
} from "@/components/DocumentBrowser";
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
import { Markdown } from "@/components/Markdown";
import { DocTree } from "@/components/DocTree";
import { GraphView } from "@/components/GraphView";
import { MindMapView } from "@/components/MindMapView";
import {
  useDeleteFoundationDoc,
  useFoundationDoc,
  useFoundationGraph,
  useFoundationTree,
  useUpdateFoundationDoc,
} from "@/hooks/useFoundationDocs";
import {
  useCreateFoundationScript,
  useDeleteFoundationScript,
  useFoundationScriptContent,
  useFoundationScriptRegistry,
  useSyncFoundationScripts,
  useUpdateFoundationScript,
  type FoundationScript,
} from "@/hooks/useFoundationScriptRegistry";

function DocumentationCard() {
  const { data: tree, isLoading: treeLoading, isError: treeError } = useFoundationTree();
  const [docSearch, setDocSearch] = useState("");
  const filteredTree = useMemo(() => {
    if (!tree) return tree;
    return filterDocumentTree(tree, docSearch);
  }, [tree, docSearch]);
  const [selectedPath, setSelectedPath] = useState<string | undefined>();
  const { data: doc, isLoading: docLoading } = useFoundationDoc(selectedPath);
  const updateDoc = useUpdateFoundationDoc();
  const deleteDoc = useDeleteFoundationDoc();

  const [viewMode, setViewMode] = useState<DocumentViewMode>("note");
  const { data: graph, isLoading: graphLoading } = useFoundationGraph();

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setIsEditing(false);
  }, [selectedPath]);

  function handleStartEdit() {
    setDraft(doc?.content ?? "");
    setIsEditing(true);
  }

  function handleSave() {
    if (!selectedPath) return;
    updateDoc.mutate(
      { path: selectedPath, content: draft },
      { onSuccess: () => setIsEditing(false) }
    );
  }

  function handleSelectFromGraph(path: string) {
    setSelectedPath(path);
    setViewMode("note");
  }

  function handleDelete() {
    if (!selectedPath) return;
    if (!window.confirm(`Delete "${selectedPath}"? This removes the document file permanently.`)) return;
    deleteDoc.mutate(selectedPath, {
      onSuccess: () => setSelectedPath(undefined),
    });
  }

  return (
    <DocumentBrowser
      title="Documentation"
      searchValue={docSearch}
      onSearchChange={setDocSearch}
      searchPlaceholder="Search docs by name or path…"
      viewMode={viewMode}
      onViewModeChange={setViewMode}
      mindMapDisabled={!selectedPath}
      actions={viewMode === "note" && selectedPath && (
        !isEditing ? (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleStartEdit} disabled={!doc}>
              <Pencil className="mr-2 h-3.5 w-3.5" />
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDelete}
              disabled={!doc || deleteDoc.isPending}
              className="text-destructive hover:text-destructive"
            >
              {deleteDoc.isPending ? (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-3.5 w-3.5" />
              )}
              Delete
            </Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={updateDoc.isPending}>
              <X className="mr-2 h-3.5 w-3.5" />
              Cancel
            </Button>
            <Button size="sm" onClick={handleSave} disabled={updateDoc.isPending}>
              {updateDoc.isPending ? (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="mr-2 h-3.5 w-3.5" />
              )}
              Save
            </Button>
          </div>
        )
      )}
      tree={
        <>
          {treeLoading && (
            <div className="flex items-center gap-2 p-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading Foundation…
            </div>
          )}
          {treeError && <p className="p-2 text-sm text-destructive">Failed to load Foundation docs.</p>}
          {filteredTree && (
            <DocTree
              nodes={filteredTree}
              selectedPath={selectedPath}
              onSelectFile={setSelectedPath}
              getAssistantDragPayload={(node) =>
                node.type === "dir"
                  ? {
                      source: "host-folder",
                      path: `/root/.hermes/foundation/${node.path}`,
                      name: node.name,
                    }
                  : {
                      source: "foundation-docs",
                      path: node.path,
                      name: node.name.endsWith(".md") ? node.name : `${node.name}.md`,
                    }
              }
            />
          )}
          {tree && tree.length === 0 && (
            <p className="p-2 text-sm italic text-muted-foreground">No markdown docs found.</p>
          )}
          {tree && tree.length > 0 && filteredTree && filteredTree.length === 0 && (
            <p className="p-2 text-sm italic text-muted-foreground">No docs match this search.</p>
          )}
        </>
      }
    >
      {viewMode === "note" && (
        <div className="flex-1 overflow-y-auto p-4">
          {!selectedPath && (
            <p className="text-sm italic text-muted-foreground">Select a document to read the Hermes rules.</p>
          )}
          {selectedPath && docLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading document…
            </div>
          )}
          {updateDoc.isError && (
            <p className="mb-3 text-sm text-destructive">Failed to save: {(updateDoc.error as Error)?.message}</p>
          )}
          {deleteDoc.isError && (
            <p className="mb-3 text-sm text-destructive">Failed to delete: {(deleteDoc.error as Error)?.message}</p>
          )}
          {doc && isEditing && (
            <Textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              className="h-full min-h-[50vh] resize-none font-mono text-sm"
            />
          )}
          {doc && !isEditing && <Markdown content={doc.content} className="text-sm" />}
        </div>
      )}

      {viewMode === "graph" && (
        <div className="flex-1 overflow-hidden">
          {graphLoading && (
            <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Building graph…
            </div>
          )}
          {graph && <GraphView graph={graph} onSelectNode={handleSelectFromGraph} />}
        </div>
      )}

      {viewMode === "mindmap" && (
        <div className="flex-1 overflow-hidden">
          {!doc && <p className="p-6 text-sm italic text-muted-foreground">Select a document first.</p>}
          {doc && <MindMapView markdown={doc.content} />}
        </div>
      )}
    </DocumentBrowser>
  );
}

type ScriptDraft = { name: string; path: string; description: string; doc_path: string };
const EMPTY_SCRIPT_DRAFT: ScriptDraft = { name: "", path: "", description: "", doc_path: "" };

/** Create/edit modal -- name is only editable on create since it's the
 * registry's unique key (sync matches on it). */
function ScriptFormModal({
  initial,
  onClose,
}: {
  initial: FoundationScript | null;
  onClose: () => void;
}) {
  const createScript = useCreateFoundationScript();
  const updateScript = useUpdateFoundationScript();
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<ScriptDraft>(
    initial
      ? {
          name: initial.name,
          path: initial.path ?? "",
          description: initial.description ?? "",
          doc_path: initial.doc_path ?? "",
        }
      : EMPTY_SCRIPT_DRAFT
  );
  const pending = createScript.isPending || updateScript.isPending;

  function handleSave() {
    setError(null);
    if (!initial && !draft.name.trim()) {
      setError("Enter a script filename, e.g. telegram_audio_transcriber.py");
      return;
    }
    const opts = {
      onSuccess: onClose,
      onError: (e: Error) => setError(e.message || "Could not save."),
    };
    if (initial) {
      updateScript.mutate(
        {
          id: initial.id,
          payload: {
            path: draft.path.trim() || null,
            description: draft.description.trim() || null,
            doc_path: draft.doc_path.trim() || null,
          },
        },
        opts
      );
    } else {
      createScript.mutate(
        {
          name: draft.name.trim(),
          path: draft.path.trim() || null,
          description: draft.description.trim() || null,
        },
        opts
      );
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{initial ? "Edit script" : "Add script"}</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Script name</Label>
            <Input
              value={draft.name}
              onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
              placeholder="telegram_audio_transcriber.py"
              className="font-mono text-xs"
              disabled={Boolean(initial)}
              autoFocus={!initial}
            />
          </div>
          <div className="space-y-1">
            <Label>Path</Label>
            <Input
              value={draft.path}
              onChange={(e) => setDraft((d) => ({ ...d, path: e.target.value }))}
              placeholder="/root/.hermes/profiles/athos/scripts/telegram_audio_transcriber.py"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label>Doc reference</Label>
            <Input
              value={draft.doc_path}
              onChange={(e) => setDraft((d) => ({ ...d, doc_path: e.target.value }))}
              placeholder="integrations/telegram.md"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label>What it does</Label>
            <Textarea
              value={draft.description}
              onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              placeholder="Transcribes Telegram voice notes before handing them to the agent"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={pending}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {initial ? "Save" : "Add"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Read-only file viewer -- reads via GET .../content, which resolves the
 * row's stored `path` on disk (same idea as the Agent Tools file modal, but
 * view-only here: editing a script's source is Agent Tools/Crons' job, not
 * this registry's). */
function ScriptFileModal({ script, onClose }: { script: FoundationScript; onClose: () => void }) {
  const { data, isLoading, isError, error } = useFoundationScriptContent(script.id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div
        className="relative z-10 flex w-full max-w-4xl flex-col rounded-xl border border-border bg-card shadow-2xl"
        style={{ maxHeight: "85vh" }}
      >
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{script.name}</p>
            <code className="block truncate font-mono text-[11px] text-muted-foreground">{script.path}</code>
          </div>
          <Button size="sm" variant="ghost" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        <div className="min-h-[300px] flex-1 overflow-auto p-4">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading file...
            </div>
          ) : isError ? (
            <p className="text-sm text-destructive">{(error as Error)?.message ?? "Could not read file."}</p>
          ) : (
            <pre className="whitespace-pre-wrap break-all font-mono text-xs text-foreground/90">
              {data?.content}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

function ScriptsCard() {
  const { data: scripts = [], isLoading, isError, error } = useFoundationScriptRegistry();
  const deleteScript = useDeleteFoundationScript();
  const sync = useSyncFoundationScripts();

  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [formScript, setFormScript] = useState<FoundationScript | null | "new">(null);
  const [fileScript, setFileScript] = useState<FoundationScript | null>(null);
  const [deleting, setDeleting] = useState<FoundationScript | null>(null);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return scripts.filter((s) => {
      if (sourceFilter && s.source !== sourceFilter) return false;
      if (!q) return true;
      return [s.name, s.description, s.doc_path, s.path].some((v) => v?.toLowerCase().includes(q));
    });
  }, [scripts, search, sourceFilter]);

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-base font-semibold">
            Scripts
            <span className="text-sm font-normal text-muted-foreground">{scripts.length} registered</span>
          </h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => sync.mutate()} disabled={sync.isPending}>
              {sync.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Sync
            </Button>
            <Button size="sm" className="gap-1.5" onClick={() => setFormScript("new")}>
              <Plus className="h-4 w-4" />
              Add script
            </Button>
          </div>
        </div>

        <p className="text-sm text-muted-foreground">
          Scripts that implement something the Foundation docs describe (e.g. a Telegram voice-message transcriber
          named in an integrations doc). "Sync" scans every Foundation doc for script filenames and registers new
          ones it finds; add or remove rows by hand at any time.
        </p>

        {sync.isSuccess && (
          <p className="text-xs text-muted-foreground">
            Scanned {sync.data.scanned_docs} doc(s): added {sync.data.added} new script(s),{" "}
            {sync.data.already_registered} already registered.
          </p>
        )}
        {sync.isError && <p className="text-xs text-destructive">Sync failed: {(sync.error as Error)?.message}</p>}

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search name, description, doc or path…"
              className="w-72 pl-8"
            />
          </div>
          <Select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} className="w-48">
            <option value="">All sources</option>
            <option value="manual">Manual</option>
            <option value="sync">Sync</option>
          </Select>
        </div>

        <div className="overflow-x-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Script</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Path</TableHead>
                <TableHead className="w-32 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <p className="font-medium">{s.name}</p>
                    {s.description && (
                      <p className="max-w-sm truncate text-xs text-muted-foreground" title={s.description}>
                        {s.description}
                      </p>
                    )}
                    {s.doc_path && (
                      <p
                        className="max-w-sm truncate text-[11px] text-muted-foreground/70"
                        title={s.doc_path}
                      >
                        doc: {s.doc_path}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant={s.source === "sync" ? "secondary" : "outline"}>{s.source}</Badge>
                  </TableCell>
                  <TableCell>
                    <code className="block max-w-xs truncate font-mono text-xs" title={s.path ?? undefined}>
                      {s.path ?? "—"}
                    </code>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-0.5">
                      <Button
                        size="icon"
                        variant="ghost"
                        title="View file"
                        disabled={!s.path}
                        onClick={() => setFileScript(s)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="ghost" title="Edit registration" onClick={() => setFormScript(s)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        title="Remove from registry"
                        className="text-destructive"
                        onClick={() => setDeleting(s)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                    {isLoading
                      ? "Loading scripts…"
                      : isError
                        ? `Failed to load: ${(error as Error)?.message}`
                        : scripts.length === 0
                          ? "No scripts registered yet -- add one or run Sync."
                          : "No scripts match this search."}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>

      {formScript !== null && (
        <ScriptFormModal initial={formScript === "new" ? null : formScript} onClose={() => setFormScript(null)} />
      )}

      {fileScript && <ScriptFileModal script={fileScript} onClose={() => setFileScript(null)} />}

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Remove script"
        description={`Remove "${deleting?.name ?? ""}" from the Foundation Scripts registry? This only removes the registry entry, not the script file itself.`}
        confirmLabel="Remove"
        onCancel={() => setDeleting(null)}
        onConfirm={() => {
          if (!deleting) return;
          deleteScript.mutate(deleting.id, { onSuccess: () => setDeleting(null) });
        }}
        loading={deleteScript.isPending}
      />
    </Card>
  );
}

export default function FoundationPage() {
  return (
    <div className="space-y-6">
      <DocumentationCard />
      <ScriptsCard />
    </div>
  );
}
