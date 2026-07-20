import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Download,
  Eye,
  FileEdit,
  FilePlus,
  FolderPlus,
  Loader2,
  Palette,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  DocumentBrowser,
  filterDocumentTree,
  type DocumentViewMode,
} from "@/components/DocumentBrowser";
import { PathPrompt } from "@/components/PathPrompt";
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
import { WhiteboardModal, type WhiteboardSaveResult } from "@/components/whiteboard/WhiteboardModal";
import type { ExcalidrawInitialDataState } from "@excalidraw/excalidraw/types";
import {
  downloadFoundationFile,
  useCreateFoundationFolder,
  useDeleteFoundationPath,
  useFoundationDoc,
  useFoundationGraph,
  useFoundationTree,
  useRenameFoundationPath,
  useUpdateFoundationDoc,
  useUploadFoundationFile,
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

// Whiteboard exports land in an "assets" folder at the Foundation root,
// same convention as the Docs/Knowledge Base pages.
const WHITEBOARD_ASSETS_FOLDER = "assets";

function DocumentationCard() {
  const { t } = useTranslation("foundation");
  const { data: tree, isLoading: treeLoading, isError: treeError } = useFoundationTree();
  const [docSearch, setDocSearch] = useState("");
  const filteredTree = useMemo(() => {
    if (!tree) return tree;
    return filterDocumentTree(tree, docSearch);
  }, [tree, docSearch]);
  const [selectedPath, setSelectedPath] = useState<string | undefined>();
  const { data: doc, isLoading: docLoading } = useFoundationDoc(selectedPath);
  const updateDoc = useUpdateFoundationDoc();
  const deletePath = useDeleteFoundationPath();
  const createFolder = useCreateFoundationFolder();
  const renamePath = useRenameFoundationPath();
  const uploadFile = useUploadFoundationFile();
  const uploadRef = useRef<HTMLInputElement>(null);

  // Explicit "pasta de trabalho": click a folder in the tree (or use the
  // reset link) to choose where "Novo documento"/"Nova pasta"/"Enviar"
  // and the tree's own inline create actions land. "" is the root.
  const [workingDir, setWorkingDir] = useState("");

  const [viewMode, setViewMode] = useState<DocumentViewMode>("note");
  const { data: graph, isLoading: graphLoading } = useFoundationGraph();

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [prompt, setPrompt] = useState<"new-doc" | "new-folder" | "rename" | null>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Whiteboard: undefined = closed; object (possibly {}) = open.
  const [whiteboardData, setWhiteboardData] = useState<ExcalidrawInitialDataState | undefined>();
  const [whiteboardNote, setWhiteboardNote] = useState<string | null>(null);

  useEffect(() => {
    setIsEditing(false);
  }, [selectedPath]);
  useEffect(() => setWhiteboardNote(null), [selectedPath]);

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
    setDeleting(selectedPath);
  }

  function handleDeletePath(path: string) {
    setDeleting(path);
  }

  function handleCreateDoc(path: string) {
    const finalPath = path.toLowerCase().endsWith(".md") ? path : `${path}.md`;
    updateDoc.mutate(
      { path: finalPath, content: `# ${finalPath.split("/").pop()?.replace(/\.md$/i, "")}\n\n` },
      {
        onSuccess: () => {
          setPrompt(null);
          setSelectedPath(finalPath);
          setViewMode("note");
        },
      }
    );
  }

  function handleCreateFileIn(folder: string) {
    setWorkingDir(folder);
    setPrompt("new-doc");
  }

  function handleCreateFolderIn(folder: string) {
    setWorkingDir(folder);
    setPrompt("new-folder");
  }

  function handleRenamePath(path: string) {
    setRenameTarget(path);
    setPrompt("rename");
  }

  function handleDownload() {
    if (selectedPath) downloadFoundationFile(selectedPath);
  }

  function handleUpload(files: FileList | null) {
    if (!files?.length) return;
    for (const f of Array.from(files)) {
      uploadFile.mutate({ folder: workingDir, file: f });
    }
  }

  function handleOpenNewWhiteboard() {
    setWhiteboardData({});
  }

  // Drag-and-drop move: a move is a rename to the same basename under the
  // destination folder (see foundation_docs.py's /rename guard against
  // folder-into-itself moves).
  function handleMove(sourcePath: string, destFolderPath: string) {
    const basename = sourcePath.split("/").pop() ?? sourcePath;
    const newPath = destFolderPath ? `${destFolderPath}/${basename}` : basename;
    if (newPath === sourcePath) return;
    renamePath.mutate({ path: sourcePath, newPath }, {
      onSuccess: () => {
        if (selectedPath === sourcePath) setSelectedPath(newPath);
        if (workingDir === sourcePath) setWorkingDir(newPath);
      },
    });
  }

  async function handleWhiteboardSave(result: WhiteboardSaveResult) {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const base = `whiteboard-${stamp}`;
    const pngFile = new File([result.pngBlob], `${base}.png`, { type: "image/png" });
    const sceneFile = new File([result.sceneJson], `${base}.excalidraw`, {
      type: "application/json",
    });
    await Promise.all([
      uploadFile.mutateAsync({ folder: WHITEBOARD_ASSETS_FOLDER, file: pngFile }),
      uploadFile.mutateAsync({ folder: WHITEBOARD_ASSETS_FOLDER, file: sceneFile }),
    ]);
    const imageRef = `![whiteboard](${WHITEBOARD_ASSETS_FOLDER}/${base}.png)`;
    if (selectedPath && doc) {
      setDraft(`${draft || doc.content}\n\n${imageRef}\n`);
      setIsEditing(true);
      setWhiteboardNote(null);
    } else {
      setWhiteboardNote(t("docs.drawingSaved", { path: `${WHITEBOARD_ASSETS_FOLDER}/${base}.png` }));
    }
    setWhiteboardData(undefined);
  }

  return (
    <>
      <ConfirmDialog
        open={deleting !== null}
        title={t("docs.deleteTitle", { path: deleting ?? "" })}
        description={t("docs.deleteDescription")}
        loading={deletePath.isPending}
        onConfirm={() => {
          if (deleting)
            deletePath.mutate(deleting, {
              onSuccess: () => {
                if (selectedPath?.startsWith(deleting)) setSelectedPath(undefined);
                if (workingDir === deleting || workingDir.startsWith(`${deleting}/`)) setWorkingDir("");
                setDeleting(null);
              },
            });
        }}
        onCancel={() => setDeleting(null)}
      />
      <input
        ref={uploadRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          handleUpload(e.target.files);
          e.target.value = "";
        }}
      />
      {whiteboardData !== undefined && (
        <WhiteboardModal
          initialData={whiteboardData}
          onClose={() => setWhiteboardData(undefined)}
          onSave={handleWhiteboardSave}
        />
      )}
      {prompt === "new-doc" && (
        <PathPrompt
          label={t("docs.newFilePathLabel")}
          initial={workingDir ? `${workingDir}/` : ""}
          pending={updateDoc.isPending}
          confirmLabel={t("docs.pathPrompt.ok")}
          cancelLabel={t("docs.pathPrompt.cancel")}
          onConfirm={handleCreateDoc}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "new-folder" && (
        <PathPrompt
          label={t("docs.newFolderPathLabel")}
          initial={workingDir ? `${workingDir}/` : ""}
          pending={createFolder.isPending}
          confirmLabel={t("docs.pathPrompt.ok")}
          cancelLabel={t("docs.pathPrompt.cancel")}
          onConfirm={(p) => createFolder.mutate(p, { onSuccess: () => setPrompt(null) })}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "rename" && renameTarget && (
        <PathPrompt
          label={t("docs.renamePathLabel", { path: renameTarget })}
          initial={renameTarget}
          pending={renamePath.isPending}
          confirmLabel={t("docs.pathPrompt.ok")}
          cancelLabel={t("docs.pathPrompt.cancel")}
          onConfirm={(p) =>
            renamePath.mutate(
              { path: renameTarget, newPath: p },
              {
                onSuccess: () => {
                  setPrompt(null);
                  if (renameTarget === selectedPath) setSelectedPath(p);
                  if (renameTarget === workingDir) setWorkingDir(p);
                  setRenameTarget(null);
                },
              }
            )
          }
          onCancel={() => {
            setPrompt(null);
            setRenameTarget(null);
          }}
        />
      )}
      {whiteboardNote && (
        <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {whiteboardNote}
        </p>
      )}
      <DocumentBrowser
        title={t("docs.title")}
        titleSuffix={
          <span className="flex items-center gap-1 text-sm font-normal text-muted-foreground">
            {t("docs.foundationLabel")} <code className="text-foreground">~/.hermes/foundation</code>
          </span>
        }
        path={workingDir ? `/${workingDir}` : "/"}
        onResetPath={() => setWorkingDir("")}
        searchValue={docSearch}
        onSearchChange={setDocSearch}
        searchPlaceholder={t("docs.searchPlaceholder")}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        mindMapDisabled={!selectedPath}
        actions={
          <>
            <Button
              variant="outline"
              size="icon"
              title={t("docs.newDocument")}
              aria-label={t("docs.newDocument")}
              onClick={() => setPrompt("new-doc")}
            >
              <FilePlus className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              title={t("docs.newFolder")}
              aria-label={t("docs.newFolder")}
              onClick={() => setPrompt("new-folder")}
            >
              <FolderPlus className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={!selectedPath}
              title={selectedPath ? t("docs.download", { path: selectedPath }) : t("docs.selectToDownload")}
              aria-label={t("docs.downloadButton")}
              onClick={handleDownload}
            >
              <Download className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={uploadFile.isPending}
              title={t("docs.uploadTo", { folder: workingDir || t("docs.theRoot") })}
              aria-label={t("docs.upload")}
              onClick={() => uploadRef.current?.click()}
            >
              {uploadFile.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            </Button>
            <Button
              variant="outline"
              size="icon"
              title={t("docs.drawAndInsert")}
              aria-label={t("docs.whiteboard")}
              onClick={handleOpenNewWhiteboard}
            >
              <Palette className="h-4 w-4" />
            </Button>
          </>
        }
        tree={
          <>
            {treeLoading && (
              <div className="flex items-center gap-2 p-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("docs.loadingFoundation")}
              </div>
            )}
            {treeError && <p className="p-2 text-sm text-destructive">{t("docs.failedToLoad")}</p>}
            {filteredTree && (
              <DocTree
                nodes={filteredTree}
                selectedPath={selectedPath}
                onSelectFile={setSelectedPath}
                workingDir={workingDir}
                onSelectFolder={setWorkingDir}
                actions={{
                  onCreateFile: handleCreateFileIn,
                  onCreateFolder: handleCreateFolderIn,
                  onRename: handleRenamePath,
                  onDelete: handleDeletePath,
                }}
                onMove={handleMove}
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
              <p className="p-2 text-sm italic text-muted-foreground">{t("docs.noMarkdownDocs")}</p>
            )}
            {tree && tree.length > 0 && filteredTree && filteredTree.length === 0 && (
              <p className="p-2 text-sm italic text-muted-foreground">{t("docs.noDocsMatchSearch")}</p>
            )}
          </>
        }
      >
        {viewMode === "note" && !selectedPath && (
          <p className="m-auto text-sm italic text-muted-foreground">{t("docs.selectDocument")}</p>
        )}
        {viewMode === "note" && selectedPath && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <code className="truncate text-xs text-muted-foreground">{selectedPath}</code>
              <div className="flex flex-wrap items-center gap-0.5">
                {!isEditing && (
                  <Button
                    variant="outline"
                    size="icon"
                    title={t("docs.edit")}
                    aria-label={t("docs.edit")}
                    onClick={handleStartEdit}
                    disabled={!doc}
                  >
                    <FileEdit className="h-4 w-4" />
                  </Button>
                )}
                {isEditing && (
                  <>
                    <Button
                      variant="outline"
                      size="icon"
                      title={t("docs.cancel")}
                      aria-label={t("docs.cancel")}
                      onClick={() => setIsEditing(false)}
                      disabled={updateDoc.isPending}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                    <Button
                      size="icon"
                      title={t("docs.save")}
                      aria-label={t("docs.save")}
                      onClick={handleSave}
                      disabled={updateDoc.isPending}
                    >
                      {updateDoc.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Save className="h-4 w-4" />
                      )}
                    </Button>
                  </>
                )}
                <Button
                  variant="outline"
                  size="icon"
                  title={t("docs.renameMove")}
                  aria-label={t("docs.rename")}
                  onClick={() => handleRenamePath(selectedPath)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  title={t("docs.delete")}
                  aria-label={t("docs.delete")}
                  className="text-destructive"
                  onClick={handleDelete}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {docLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("docs.loadingDocument")}
              </div>
            )}
            {updateDoc.isError && (
              <p className="text-sm text-destructive">{t("docs.failedToSave", { message: (updateDoc.error as Error)?.message })}</p>
            )}
            {deletePath.isError && (
              <p className="text-sm text-destructive">{t("docs.failedToDelete", { message: (deletePath.error as Error)?.message })}</p>
            )}
            {renamePath.isError && (
              <p className="text-sm text-destructive">{t("docs.failedToRename", { message: (renamePath.error as Error)?.message })}</p>
            )}
            {doc && isEditing && (
              <Textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="h-full min-h-[50vh] resize-none font-mono text-sm"
              />
            )}
            {doc && !isEditing && <Markdown content={doc.content} className="text-sm" />}
          </>
        )}

        {viewMode === "graph" && (
          <div className="h-full overflow-hidden">
            {graphLoading && (
              <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("docs.buildingGraph")}
              </div>
            )}
            {graph && <GraphView graph={graph} onSelectNode={handleSelectFromGraph} />}
          </div>
        )}

        {viewMode === "mindmap" && (
          <div className="h-full overflow-hidden">
            {!doc && <p className="p-6 text-sm italic text-muted-foreground">{t("docs.selectDocumentFirst")}</p>}
            {doc && <MindMapView markdown={doc.content} />}
          </div>
        )}
      </DocumentBrowser>
    </>
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
  const { t } = useTranslation("foundation");
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
      setError(t("scriptForm.enterFilename"));
      return;
    }
    const opts = {
      onSuccess: onClose,
      onError: (e: Error) => setError(e.message || t("scriptForm.couldNotSave")),
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
          <h2 className="text-base font-semibold">{initial ? t("scriptForm.editScript") : t("scriptForm.addScript")}</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>{t("scriptForm.scriptName")}</Label>
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
            <Label>{t("scriptForm.path")}</Label>
            <Input
              value={draft.path}
              onChange={(e) => setDraft((d) => ({ ...d, path: e.target.value }))}
              placeholder="/root/.hermes/profiles/athos/scripts/telegram_audio_transcriber.py"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label>{t("scriptForm.docReference")}</Label>
            <Input
              value={draft.doc_path}
              onChange={(e) => setDraft((d) => ({ ...d, doc_path: e.target.value }))}
              placeholder="integrations/telegram.md"
              className="font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <Label>{t("scriptForm.whatItDoes")}</Label>
            <Textarea
              value={draft.description}
              onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              placeholder="Transcribes Telegram voice notes before handing them to the agent"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              {t("scriptForm.cancel")}
            </Button>
            <Button onClick={handleSave} disabled={pending}>
              {pending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {initial ? t("scriptForm.save") : t("scriptForm.add")}
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
  const { t } = useTranslation("foundation");
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
              <Loader2 className="h-4 w-4 animate-spin" /> {t("scriptFile.loadingFile")}
            </div>
          ) : isError ? (
            <p className="text-sm text-destructive">{(error as Error)?.message ?? t("scriptFile.couldNotReadFile")}</p>
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
  const { t } = useTranslation("foundation");
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
            {t("scriptsCard.title")}
            <span className="text-sm font-normal text-muted-foreground">{t("scriptsCard.registeredCount", { count: scripts.length })}</span>
          </h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button variant="outline" size="sm" className="gap-1.5" onClick={() => sync.mutate()} disabled={sync.isPending}>
              {sync.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {t("scriptsCard.sync")}
            </Button>
            <Button size="sm" className="gap-1.5" onClick={() => setFormScript("new")}>
              <Plus className="h-4 w-4" />
              {t("scriptsCard.addScript")}
            </Button>
          </div>
        </div>

        <p className="text-sm text-muted-foreground">
          {t("scriptsCard.description")}
        </p>

        {sync.isSuccess && (
          <p className="text-xs text-muted-foreground">
            {t("scriptsCard.syncResult", {
              scannedDocs: sync.data.scanned_docs,
              added: sync.data.added,
              alreadyRegistered: sync.data.already_registered,
            })}
          </p>
        )}
        {sync.isError && <p className="text-xs text-destructive">{t("scriptsCard.syncFailed", { message: (sync.error as Error)?.message })}</p>}

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("scriptsCard.searchPlaceholder")}
              className="w-72 pl-8"
            />
          </div>
          <Select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} className="w-48">
            <option value="">{t("scriptsCard.allSources")}</option>
            <option value="manual">{t("scriptsCard.manual")}</option>
            <option value="sync">{t("scriptsCard.syncSource")}</option>
          </Select>
        </div>

        <div className="overflow-x-auto rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("scriptsCard.tableScript")}</TableHead>
                <TableHead>{t("scriptsCard.tableSource")}</TableHead>
                <TableHead>{t("scriptsCard.tablePath")}</TableHead>
                <TableHead className="w-32 text-right">{t("scriptsCard.tableActions")}</TableHead>
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
                        {t("scriptsCard.docPrefix")} {s.doc_path}
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
                        title={t("scriptsCard.viewFile")}
                        disabled={!s.path}
                        onClick={() => setFileScript(s)}
                      >
                        <Eye className="h-4 w-4" />
                      </Button>
                      <Button size="icon" variant="ghost" title={t("scriptsCard.editRegistration")} onClick={() => setFormScript(s)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        title={t("scriptsCard.removeFromRegistry")}
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
                      ? t("scriptsCard.loadingScripts")
                      : isError
                        ? t("scriptsCard.failedToLoad", { message: (error as Error)?.message })
                        : scripts.length === 0
                          ? t("scriptsCard.noScriptsRegistered")
                          : t("scriptsCard.noScriptsMatchSearch")}
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
        title={t("scriptsCard.removeScriptTitle")}
        description={t("scriptsCard.removeScriptDescription", { name: deleting?.name ?? "" })}
        confirmLabel={t("scriptsCard.remove")}
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
    <div className="flex h-full min-h-0 flex-1 flex-col gap-6 overflow-y-auto p-6">
      <DocumentationCard />
      <ScriptsCard />
    </div>
  );
}
