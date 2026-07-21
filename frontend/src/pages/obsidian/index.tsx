import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Download,
  FileEdit,
  FilePlus,
  FolderPlus,
  Gem,
  Loader2,
  Maximize2,
  Minimize2,
  Palette,
  Pencil,
  Save,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import {
  DocumentWorkspace,
  type DocumentViewMode,
} from "@/components/DocumentWorkspace";
import { filterDocumentTree } from "@/components/DocumentBrowser";
import { CopyButton } from "@/components/CopyButton";
import { DocTree } from "@/components/DocTree";
import { GraphView } from "@/components/GraphView";
import { Markdown } from "@/components/Markdown";
import { MindMapView } from "@/components/MindMapView";
import { PathPrompt } from "@/components/PathPrompt";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Textarea } from "@/components/ui/textarea";
import { WhiteboardModal, type WhiteboardSaveResult } from "@/components/whiteboard/WhiteboardModal";
import type { ExcalidrawInitialDataState } from "@excalidraw/excalidraw/types";
import { useElementFullscreen } from "@/hooks/useElementFullscreen";
import { cn } from "@/lib/utils";
import {
  downloadVaultFile,
  useCreateVaultFolder,
  useDeleteVaultPath,
  useRenameVaultPath,
  useUpdateVaultNote,
  useUploadVaultFile,
  useVaultGraph,
  useVaultNote,
  useVaultTree,
} from "@/hooks/useVault";

// Whiteboard exports land in an "assets" folder at the vault root, same
// convention as the Docs page (see docs/index.tsx's WHITEBOARD_ASSETS_FOLDER).
const WHITEBOARD_ASSETS_FOLDER = "assets";

export default function ObsidianPage() {
  const { t } = useTranslation("knowledgeBase");
  const { data: tree, isLoading: treeLoading, isError: treeError } = useVaultTree();
  const [noteSearch, setNoteSearch] = useState("");
  const filteredTree = useMemo(
    () => (tree ? filterDocumentTree(tree, noteSearch) : tree),
    [tree, noteSearch]
  );
  const [selectedPath, setSelectedPath] = useState<string | undefined>();
  const { data: note, isLoading: noteLoading } = useVaultNote(selectedPath);
  const updateNote = useUpdateVaultNote();
  const deletePath = useDeleteVaultPath();
  const createFolder = useCreateVaultFolder();
  const renamePath = useRenameVaultPath();
  const uploadFile = useUploadVaultFile();
  const uploadRef = useRef<HTMLInputElement>(null);

  // Explicit "pasta de trabalho": click a folder in the tree (or use the
  // reset link) to choose where "Nova nota"/"Nova pasta"/the tree's own
  // inline create actions land. "" is the vault root.
  const [workingDir, setWorkingDir] = useState("");

  const [viewMode, setViewMode] = useState<DocumentViewMode>("note");
  const { data: graph, isLoading: graphLoading } = useVaultGraph();

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const { ref: fullscreenRef, isFullscreen, toggle: toggleFullscreen } = useElementFullscreen<HTMLDivElement>();
  const [prompt, setPrompt] = useState<"new-note" | "new-folder" | "rename" | null>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Whiteboard: undefined = closed; object (possibly {}) = open.
  const [whiteboardData, setWhiteboardData] = useState<ExcalidrawInitialDataState | undefined>();
  const [whiteboardNote, setWhiteboardNote] = useState<string | null>(null);

  useEffect(() => {
    setIsEditing(false);
  }, [selectedPath]);
  useEffect(() => setWhiteboardNote(null), [selectedPath]);

  function handleSelectFromGraph(path: string) {
    setSelectedPath(path);
    setViewMode("note");
  }

  function handleStartEdit() {
    setDraft(note?.content ?? "");
    setIsEditing(true);
  }

  function handleSave() {
    if (!selectedPath) return;
    updateNote.mutate(
      { path: selectedPath, content: draft },
      { onSuccess: () => setIsEditing(false) }
    );
  }

  function handleDelete() {
    if (!selectedPath) return;
    setDeleting(selectedPath);
  }

  function handleDeletePath(path: string) {
    setDeleting(path);
  }

  function handleCreateNote(path: string) {
    const finalPath = path.toLowerCase().endsWith(".md") ? path : `${path}.md`;
    updateNote.mutate(
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
    setPrompt("new-note");
  }

  function handleCreateFolderIn(folder: string) {
    setWorkingDir(folder);
    setPrompt("new-folder");
  }

  function handleRenamePath(path: string) {
    setRenameTarget(path);
    setPrompt("rename");
  }

  // Drag-and-drop move: a move is a rename to the same basename under the
  // destination folder (see vault.py's rename endpoint, same guard docs.py's
  // /rename uses against folder-into-itself moves).
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

  function handleDownload() {
    if (selectedPath) downloadVaultFile(selectedPath);
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
    if (selectedPath && note) {
      setDraft(`${draft || note.content}\n\n${imageRef}\n`);
      setIsEditing(true);
      setWhiteboardNote(null);
    } else {
      setWhiteboardNote(t("drawingSaved", { path: `${WHITEBOARD_ASSETS_FOLDER}/${base}.png` }));
    }
    setWhiteboardData(undefined);
  }

  return (
    <>
      <ConfirmDialog
        open={deleting !== null}
        title={t("deleteTitle", { path: deleting ?? "" })}
        description={t("deleteDescription")}
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
      {prompt === "new-note" && (
        <div className="px-6 pt-6">
          <PathPrompt
            label={t("newNotePathLabel")}
            initial={workingDir ? `${workingDir}/` : ""}
            pending={updateNote.isPending}
            confirmLabel={t("pathPrompt.ok")}
            cancelLabel={t("pathPrompt.cancel")}
            onConfirm={handleCreateNote}
            onCancel={() => setPrompt(null)}
          />
        </div>
      )}
      {prompt === "new-folder" && (
        <div className="px-6 pt-6">
          <PathPrompt
            label={t("newFolderPathLabel")}
            initial={workingDir ? `${workingDir}/` : ""}
            pending={createFolder.isPending}
            confirmLabel={t("pathPrompt.ok")}
            cancelLabel={t("pathPrompt.cancel")}
            onConfirm={(p) => createFolder.mutate(p, { onSuccess: () => setPrompt(null) })}
            onCancel={() => setPrompt(null)}
          />
        </div>
      )}
      {prompt === "rename" && renameTarget && (
        <div className="px-6 pt-6">
          <PathPrompt
            label={t("renamePathLabel", { path: renameTarget })}
            initial={renameTarget}
            pending={renamePath.isPending}
            confirmLabel={t("pathPrompt.ok")}
            cancelLabel={t("pathPrompt.cancel")}
            onConfirm={(p) =>
              renamePath.mutate(
                { path: renameTarget, newPath: p },
                {
                  onSuccess: () => {
                    setPrompt(null);
                    if (renameTarget === selectedPath) setSelectedPath(p);
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
        </div>
      )}
      {whiteboardNote && (
        <p className="mx-6 mt-6 rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {whiteboardNote}
        </p>
      )}
      <DocumentWorkspace
        title={t("title")}
        titleIcon={<Gem className="h-5 w-5" />}
        titleSuffix={
          <span className="flex items-center gap-1 text-sm font-normal text-muted-foreground">
            {t("vaultLabel")} <code className="text-foreground">~/.hermes/knowledge_base</code>
          </span>
        }
        path={workingDir ? `/${workingDir}` : "/"}
        onResetPath={() => setWorkingDir("")}
        searchValue={noteSearch}
        onSearchChange={setNoteSearch}
        searchPlaceholder={t("searchPlaceholder")}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        mindMapDisabled={!selectedPath}
        actions={
          <>
            <Button
              variant="outline"
              size="icon"
              title={t("newNote")}
              aria-label={t("newNote")}
              onClick={() => setPrompt("new-note")}
            >
              <FilePlus className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              title={t("newFolder")}
              aria-label={t("newFolder")}
              onClick={() => setPrompt("new-folder")}
            >
              <FolderPlus className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={!selectedPath}
              title={selectedPath ? t("download", { path: selectedPath }) : t("selectToDownload")}
              aria-label={t("downloadButton")}
              onClick={handleDownload}
            >
              <Download className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              disabled={uploadFile.isPending}
              title={t("uploadTo", { folder: workingDir || t("theRoot") })}
              aria-label={t("upload")}
              onClick={() => uploadRef.current?.click()}
            >
              {uploadFile.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            </Button>
            <Button
              variant="outline"
              size="icon"
              title={t("drawAndInsert")}
              aria-label={t("whiteboard")}
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
                {t("loadingVault")}
              </div>
            )}
            {treeError && <p className="p-2 text-sm text-destructive">{t("failedToLoadVault")}</p>}
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
                        path: `/root/.hermes/knowledge_base/${node.path}`,
                        name: node.name,
                      }
                    : {
                        source: "vault",
                        path: node.path,
                        name: node.name.endsWith(".md") ? node.name : `${node.name}.md`,
                      }
                }
              />
            )}
            {tree && tree.length === 0 && (
              <p className="p-2 text-sm italic text-muted-foreground">{t("noNotesFound")}</p>
            )}
            {tree && tree.length > 0 && filteredTree && filteredTree.length === 0 && (
              <p className="p-2 text-sm italic text-muted-foreground">{t("noNotesMatchSearch")}</p>
            )}
          </>
        }
      >
        {viewMode === "note" && !selectedPath && (
          <p className="m-auto text-sm italic text-muted-foreground">{t("selectNoteToRead")}</p>
        )}
        {viewMode === "note" && selectedPath && (
          <div
            ref={fullscreenRef}
            className={cn("flex flex-1 flex-col gap-2", isFullscreen && "overflow-y-auto bg-background p-6")}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <code className="truncate text-xs text-muted-foreground">{selectedPath}</code>
              <div className="flex flex-wrap items-center gap-0.5">
                {note && (
                  <CopyButton getText={() => (isEditing ? draft : note.content)} title={t("copyDocument")} />
                )}
                <Button
                  variant="outline"
                  size="icon"
                  title={isFullscreen ? t("exitFullscreen") : t("fullscreen")}
                  aria-label={isFullscreen ? t("exitFullscreen") : t("fullscreen")}
                  onClick={toggleFullscreen}
                >
                  {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                </Button>
                {!isEditing && (
                  <Button
                    variant="outline"
                    size="icon"
                    title={t("edit")}
                    aria-label={t("edit")}
                    onClick={handleStartEdit}
                    disabled={!note}
                  >
                    <FileEdit className="h-4 w-4" />
                  </Button>
                )}
                {isEditing && (
                  <>
                    <Button
                      variant="outline"
                      size="icon"
                      title={t("cancel")}
                      aria-label={t("cancel")}
                      onClick={() => setIsEditing(false)}
                      disabled={updateNote.isPending}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                    <Button
                      size="icon"
                      title={t("save")}
                      aria-label={t("save")}
                      onClick={handleSave}
                      disabled={updateNote.isPending}
                    >
                      {updateNote.isPending ? (
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
                  title={t("renameMove")}
                  aria-label={t("rename")}
                  onClick={() => handleRenamePath(selectedPath)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  title={t("delete")}
                  aria-label={t("delete")}
                  className="text-destructive"
                  onClick={handleDelete}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {noteLoading && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("loadingNote")}
              </div>
            )}
            {updateNote.isError && (
              <p className="text-sm text-destructive">{t("failedToSave", { message: (updateNote.error as Error)?.message })}</p>
            )}
            {deletePath.isError && (
              <p className="text-sm text-destructive">{t("failedToDelete", { message: (deletePath.error as Error)?.message })}</p>
            )}
            {renamePath.isError && (
              <p className="text-sm text-destructive">{t("failedToRename", { message: (renamePath.error as Error)?.message })}</p>
            )}
            {note && isEditing && (
              <Textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className="h-full min-h-[50vh] resize-none font-mono text-sm"
              />
            )}
            {note && !isEditing && <Markdown content={note.content} className="text-sm" />}
          </div>
        )}

        {viewMode === "graph" && (
          <div className="h-full overflow-hidden">
            {graphLoading && (
              <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {t("buildingGraph")}
              </div>
            )}
            {graph && <GraphView graph={graph} onSelectNode={handleSelectFromGraph} />}
          </div>
        )}

        {viewMode === "mindmap" && (
          <div className="h-full overflow-hidden">
            {!note && <p className="p-6 text-sm italic text-muted-foreground">{t("selectNoteFirst")}</p>}
            {note && <MindMapView markdown={note.content} />}
          </div>
        )}
      </DocumentWorkspace>
    </>
  );
}
