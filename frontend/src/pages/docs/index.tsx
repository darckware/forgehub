import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowRightCircle,
  BookOpen,
  ChevronDown,
  Download,
  Eye,
  FileEdit,
  FilePlus,
  FoldVertical,
  Folder,
  FolderPlus,
  Loader2,
  Maximize2,
  Minimize2,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Save,
  Trash2,
  UnfoldVertical,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { PathPrompt } from "@/components/PathPrompt";
import { SearchFilterInput } from "@/components/SearchFilterInput";
import { DocTree, useExpandedTree, type DocTreeNode } from "@/components/DocTree";
import { filterDocumentTree } from "@/components/DocumentBrowser";
import { CopyButton } from "@/components/CopyButton";
import { GraphView } from "@/components/GraphView";
import { Markdown } from "@/components/Markdown";
import { MindMapView } from "@/components/MindMapView";
import { ViewModeToggle, type DocumentViewMode } from "@/components/ViewModeToggle";
import { ConvertMenu, convertResultMessage } from "@/components/ConvertMenu";
import { useConvertDoc } from "@/hooks/useDemands";
import { useAssistantContext } from "@/hooks/useAssistant";
import { useElementFullscreen } from "@/hooks/useElementFullscreen";
import { AssistantToggleButton } from "@/components/AssistantToggleButton";
import { WhiteboardModal, type WhiteboardSaveResult } from "@/components/whiteboard/WhiteboardModal";
import type { ExcalidrawInitialDataState } from "@excalidraw/excalidraw/types";
import { cn } from "@/lib/utils";
import {
  downloadDoc,
  useCreateDocArea,
  useCreateDocFolder,
  useDeleteDocArea,
  useDeleteDocPath,
  useDocAreas,
  useDocFile,
  useDocsGraph,
  useDocsTree,
  useRenameDocPath,
  useSaveDocFile,
  useUploadDocFile,
} from "@/hooks/useDocs";

const EDITABLE_RE = /\.(md|markdown|txt)$/i;
const SCENE_RE = /\.excalidraw$/i;
// Whiteboard exports always land here (see /root/docs/README.md's
// "assets/ — imagens (inclui exports da lousa)").
const WHITEBOARD_ASSETS_FOLDER = "assets";
// doc_links/convert (backend/app/api/routes/docs.py) are deliberately not
// area-aware -- they always resolve against the original /root/docs mount,
// so those panels only make sense while that area is the working one.
const DOCS_HOST_PATH = "/root/docs";

/** Switch between "creation areas" (any host folder) -- add/remove/select. */
function AreaSwitcher({
  areas,
  currentAreaId,
  onSelect,
}: {
  areas: { id: string; name: string; host_path: string }[];
  currentAreaId: string | null;
  onSelect: (areaId: string) => void;
}) {
  const { t } = useTranslation("docs");
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPath, setNewPath] = useState("/");
  const [deletingArea, setDeletingArea] = useState<string | null>(null);
  const createArea = useCreateDocArea();
  const deleteArea = useDeleteDocArea();
  const current = areas.find((a) => a.id === currentAreaId);

  function resetAddForm() {
    setAdding(false);
    setNewName("");
    setNewPath("/");
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="flex items-center gap-1 text-sm font-normal text-muted-foreground hover:text-foreground"
        onClick={() => setOpen((v) => !v)}
      >
        {t("areaSwitcher.creationArea")} <code className="text-foreground">{current?.host_path ?? "..."}</code>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <Card className="absolute left-0 top-full z-50 mt-1 w-96 shadow-xl">
            <CardContent className="max-h-80 overflow-y-auto p-2">
              <ConfirmDialog
                open={deletingArea !== null}
                title={t("areaSwitcher.removeAreaTitle")}
                description={t("areaSwitcher.removeAreaDescription")}
                loading={deleteArea.isPending}
                onConfirm={() => {
                  if (!deletingArea) return;
                  deleteArea.mutate(deletingArea, { onSuccess: () => setDeletingArea(null) });
                }}
                onCancel={() => setDeletingArea(null)}
              />
              {areas.map((area) => (
                <div
                  key={area.id}
                  className={
                    "group flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm " +
                    (area.id === currentAreaId
                      ? "bg-accent text-accent-foreground"
                      : "hover:bg-accent hover:text-accent-foreground")
                  }
                >
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 flex-col items-start text-left"
                    onClick={() => {
                      onSelect(area.id);
                      setOpen(false);
                    }}
                  >
                    <span className="font-medium">{area.name}</span>
                    <code className="truncate text-xs text-muted-foreground">{area.host_path}</code>
                  </button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 shrink-0 text-destructive opacity-0 group-hover:opacity-100"
                    disabled={areas.length <= 1}
                    title={areas.length <= 1 ? t("areaSwitcher.atLeastOneMustExist") : t("areaSwitcher.removeArea")}
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeletingArea(area.id);
                    }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}

              {adding ? (
                <div className="mt-1.5 flex flex-col gap-1.5 rounded-md border border-border bg-muted/30 p-2">
                  <Input
                    autoFocus
                    placeholder={t("areaSwitcher.namePlaceholder")}
                    value={newName}
                    className="h-8 text-xs"
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <Input
                    placeholder={t("areaSwitcher.pathPlaceholder")}
                    value={newPath}
                    className="h-8 font-mono text-xs"
                    onChange={(e) => setNewPath(e.target.value)}
                  />
                  {createArea.isError && (
                    <p className="text-xs text-destructive">{(createArea.error as Error)?.message}</p>
                  )}
                  <div className="flex justify-end gap-1.5">
                    <Button size="sm" variant="outline" onClick={resetAddForm}>
                      {t("areaSwitcher.cancel")}
                    </Button>
                    <Button
                      size="sm"
                      disabled={!newName.trim() || !newPath.trim() || createArea.isPending}
                      onClick={() =>
                        createArea.mutate(
                          { name: newName.trim(), host_path: newPath.trim() },
                          {
                            onSuccess: (created) => {
                              onSelect(created.id);
                              resetAddForm();
                              setOpen(false);
                            },
                          }
                        )
                      }
                    >
                      {createArea.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : t("areaSwitcher.add")}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button variant="ghost" size="sm" className="mt-1 w-full justify-start gap-1.5" onClick={() => setAdding(true)}>
                  <Plus className="h-3.5 w-3.5" /> {t("areaSwitcher.newArea")}
                </Button>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export default function DocsPage() {
  const { t } = useTranslation("docs");
  const { data: areas } = useDocAreas();
  const [areaId, setAreaId] = useState<string | null>(null);
  useEffect(() => {
    if (!areaId && areas?.length) setAreaId(areas[0].id);
  }, [areas, areaId]);
  const currentArea = areas?.find((a) => a.id === areaId);
  // doc_links/ConvertMenu only make sense against the original /root/docs
  // mount (see DOCS_HOST_PATH comment above).
  const isDocsArea = currentArea?.host_path === DOCS_HOST_PATH;

  const { data: tree, isLoading, isError, error } = useDocsTree(areaId);
  const [treeSearch, setTreeSearch] = useState("");
  const filteredTree = useMemo(
    () => (tree ? filterDocumentTree(tree as DocTreeNode[], treeSearch) : tree),
    [tree, treeSearch]
  );
  const { expandedPaths, toggle: toggleExpanded, allExpanded, toggleAll: toggleAllExpanded } =
    useExpandedTree(tree as DocTreeNode[] | undefined, areaId);
  const [viewMode, setViewMode] = useState<DocumentViewMode>("note");
  const { data: graph, isLoading: graphLoading } = useDocsGraph(areaId);
  const [searchParams] = useSearchParams();
  // Deep-link from EntityDocsCard (/docs?path=...) -- only seeds the
  // initial selection, so navigating the tree afterwards isn't fought.
  const [selectedPath, setSelectedPath] = useState<string | null>(() => searchParams.get("path"));
  const isEditable = selectedPath ? EDITABLE_RE.test(selectedPath) : false;
  const isScene = selectedPath ? SCENE_RE.test(selectedPath) : false;
  // .excalidraw is read as text too (backend allows it) so a saved scene
  // can be reopened for editing without a dedicated endpoint.
  const { data: file, isLoading: fileLoading, isError: fileError } = useDocFile(
    areaId,
    isEditable || isScene ? selectedPath : null
  );
  const saveFile = useSaveDocFile(areaId ?? "");
  const deletePath = useDeleteDocPath(areaId ?? "");
  const createFolder = useCreateDocFolder(areaId ?? "");
  const renamePath = useRenameDocPath(areaId ?? "");
  const uploadFile = useUploadDocFile(areaId ?? "");

  // null = viewing; string = editing draft. Cleared when switching files.
  const [draft, setDraft] = useState<string | null>(null);
  const [showConvert, setShowConvert] = useState(false);
  const [hideTree, setHideTree] = useState(false);
  const { ref: fullscreenRef, isFullscreen, toggle: toggleFullscreen } = useElementFullscreen<HTMLDivElement>();
  const [prompt, setPrompt] = useState<"new-file" | "new-folder" | "rename" | null>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  useAssistantContext({
    label: t("assistantContext.useCurrentDocument"),
    workingDir: currentArea?.host_path ?? "/root/docs",
    build: () => {
      if (!selectedPath || !currentArea) return null;
      const lines = [
        `I'm working in the "${currentArea.name}" area of ForgeHub Docs (files at ${currentArea.host_path}, on the host).`,
        `Current document: ${currentArea.host_path}/${selectedPath}`,
        "",
        "Help me create/edit this document. Write the result directly to the file (you have host access) and let me know when you save it.",
      ];
      const content = draft ?? file?.content;
      if (content) lines.push("", "Current content:", "```markdown", content, "```");
      return lines.join("\n");
    },
  });

  // Explicit "pasta de trabalho": click a folder in the tree (or use the
  // reset button) to choose where "Novo documento"/"Nova pasta"/"Upload"
  // and the tree's own inline create actions land. "" is the area's root.
  const [workingDir, setWorkingDir] = useState("");

  // Whiteboard: undefined = closed; object (possibly {}) = open, reopening
  // that scene when non-empty (see handleOpenWhiteboard).
  const [whiteboardData, setWhiteboardData] = useState<ExcalidrawInitialDataState | undefined>();
  const [whiteboardNote, setWhiteboardNote] = useState<string | null>(null);

  useEffect(() => setDraft(null), [selectedPath]);
  const convertDoc = useConvertDoc();
  const [convertMessage, setConvertMessage] = useState<string | null>(null);

  useEffect(() => setWhiteboardNote(null), [selectedPath]);
  useEffect(() => setConvertMessage(null), [selectedPath]);
  useEffect(() => setShowConvert(false), [selectedPath]);

  // Switching areas invalidates every bit of per-file/per-folder state --
  // each area is its own distinct working space (per-area selection/draft).
  function handleSelectArea(nextAreaId: string) {
    setAreaId(nextAreaId);
    setSelectedPath(null);
    setDraft(null);
    setWorkingDir("");
    setTreeSearch("");
    setViewMode("note");
    setWhiteboardData(undefined);
    setWhiteboardNote(null);
    setConvertMessage(null);
    setShowConvert(false);
    setPrompt(null);
    setRenameTarget(null);
    setDeleting(null);
  }

  const dirty = draft != null && draft !== (file?.content ?? "");

  function handleSave() {
    if (selectedPath == null || draft == null) return;
    saveFile.mutate({ path: selectedPath, content: draft }, { onSuccess: () => setDraft(null) });
  }

  function handleCreateFile(path: string) {
    const finalPath = EDITABLE_RE.test(path) ? path : `${path}.md`;
    saveFile.mutate(
      { path: finalPath, content: `# ${finalPath.split("/").pop()?.replace(/\.md$/i, "")}\n\n` },
      {
        onSuccess: () => {
          setPrompt(null);
          setSelectedPath(finalPath);
        },
      }
    );
  }

  function handleUpload(files: FileList | null) {
    if (!files?.length) return;
    for (const f of Array.from(files)) {
      uploadFile.mutate({ folder: workingDir, file: f });
    }
  }

  function handleDeletePath(path: string) {
    setDeleting(path);
  }

  function handleRenamePath(path: string) {
    setRenameTarget(path);
    setPrompt("rename");
  }

  function handleCreateFileIn(folder: string) {
    setWorkingDir(folder);
    setPrompt("new-file");
  }

  function handleCreateFolderIn(folder: string) {
    setWorkingDir(folder);
    setPrompt("new-folder");
  }

  // Drag-and-drop move: a move is a rename to the same basename under the
  // destination folder (see docs.py's rename_path guard against folder-
  // into-itself moves, which this relies on for that edge case).
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

  function handleSelectFromGraph(path: string) {
    setSelectedPath(path);
    setViewMode("note");
  }

  function handleOpenNewWhiteboard() {
    setWhiteboardData({});
  }

  function handleEditScene() {
    if (!file) return;
    try {
      const scene = JSON.parse(file.content);
      setWhiteboardData({ elements: scene.elements ?? [], appState: scene.appState, files: scene.files });
    } catch {
      setWhiteboardNote(t("page.couldNotReadSceneInvalidJson"));
    }
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
    if (selectedPath && isEditable) {
      const currentContent = draft ?? file?.content ?? "";
      setDraft(`${currentContent}\n\n${imageRef}\n`);
      setWhiteboardNote(null);
    } else {
      setWhiteboardNote(
        t("page.drawingSaved", { path: `${WHITEBOARD_ASSETS_FOLDER}/${base}.png` })
      );
    }
    setWhiteboardData(undefined);
  }

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col gap-4 p-6">
      <ConfirmDialog
        open={deleting !== null}
        title={t("page.deleteTitle", { path: deleting ?? "" })}
        description={t("page.deleteDescription")}
        loading={deletePath.isPending}
        onConfirm={() => {
          if (deleting)
            deletePath.mutate(deleting, {
              onSuccess: () => {
                if (selectedPath?.startsWith(deleting)) setSelectedPath(null);
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

      <div className="grid grid-cols-[280px_1fr] items-center gap-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <BookOpen className="h-5 w-5" /> {t("page.title")}
        </h1>
        <div className="flex flex-wrap items-center justify-between gap-2">
          {areas && <AreaSwitcher areas={areas} currentAreaId={areaId} onSelect={handleSelectArea} />}
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              size="icon"
              variant="outline"
              title={t("page.newDocument")}
              aria-label={t("page.newDocument")}
              onClick={() => setPrompt("new-file")}
            >
              <FilePlus className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="outline"
              title={t("page.newFolder")}
              aria-label={t("page.newFolder")}
              onClick={() => setPrompt("new-folder")}
            >
              <FolderPlus className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="outline"
              disabled={!selectedPath}
              title={selectedPath ? t("page.download", { path: selectedPath }) : t("page.selectToDownload")}
              aria-label={t("page.downloadButton")}
              onClick={() => areaId && selectedPath && downloadDoc(areaId, selectedPath)}
            >
              <Download className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="outline"
              disabled={uploadFile.isPending}
              title={t("page.uploadTo", { folder: workingDir || t("page.theRoot") })}
              aria-label={t("page.upload")}
              onClick={() => uploadRef.current?.click()}
            >
              {uploadFile.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            </Button>
            <Button
              size="icon"
              variant="outline"
              title={t("page.drawAndInsert")}
              aria-label={t("page.whiteboard")}
              onClick={handleOpenNewWhiteboard}
            >
              <Palette className="h-4 w-4" />
            </Button>
            <AssistantToggleButton
              size="icon"
              openTitle={t("page.openAssistantForDoc")}
            />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-[280px_1fr] items-center gap-4">
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <button
            type="button"
            title={t("page.useRoot")}
            aria-label={t("page.useRoot")}
            onClick={() => setWorkingDir("")}
            className="mt-0.5 shrink-0 text-muted-foreground hover:text-foreground"
          >
            <Folder className="h-3.5 w-3.5" />
          </button>
          <span className="flex min-w-0 flex-wrap items-center gap-1.5">
            <code className="break-all text-foreground">{workingDir ? `/${workingDir}` : "/"}</code>
          </span>
        </p>
        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="outline"
            title={hideTree ? t("page.showTree") : t("page.hideTree")}
            aria-label={hideTree ? t("page.showTree") : t("page.hideTree")}
            onClick={() => setHideTree((v) => !v)}
          >
            {hideTree ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
          <Button
            size="icon"
            variant="outline"
            title={allExpanded ? t("page.collapseAll") : t("page.expandAll")}
            aria-label={allExpanded ? t("page.collapseAll") : t("page.expandAll")}
            onClick={toggleAllExpanded}
          >
            {allExpanded ? <FoldVertical className="h-4 w-4" /> : <UnfoldVertical className="h-4 w-4" />}
          </Button>
          <SearchFilterInput
            value={treeSearch}
            onChange={setTreeSearch}
            placeholder={t("page.searchPlaceholder")}
            className="flex-1"
          />
          <ViewModeToggle
            viewMode={viewMode}
            onViewModeChange={setViewMode}
            mindMapDisabled={!selectedPath}
            labels={{ mindMap: t("page.mindMap"), graph: t("page.graph") }}
          />
        </div>
      </div>

      {whiteboardData !== undefined && (
        <WhiteboardModal
          initialData={whiteboardData}
          onClose={() => setWhiteboardData(undefined)}
          onSave={handleWhiteboardSave}
        />
      )}
      {whiteboardNote && (
        <p className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
          {whiteboardNote}
        </p>
      )}

      {prompt === "new-file" && (
        <PathPrompt
          label={t("page.newFilePathLabel")}
          initial={workingDir ? `${workingDir}/` : ""}
          pending={saveFile.isPending}
          confirmLabel={t("pathPrompt.ok")}
          cancelLabel={t("pathPrompt.cancel")}
          onConfirm={handleCreateFile}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "new-folder" && (
        <PathPrompt
          label={t("page.newFolderPathLabel")}
          initial={workingDir ? `${workingDir}/` : ""}
          pending={createFolder.isPending}
          confirmLabel={t("pathPrompt.ok")}
          cancelLabel={t("pathPrompt.cancel")}
          onConfirm={(p) => createFolder.mutate(p, { onSuccess: () => setPrompt(null) })}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "rename" && renameTarget && (
        <PathPrompt
          label={t("page.renamePathLabel", { path: renameTarget })}
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

      {isError && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-6 text-destructive">
            <AlertCircle className="h-5 w-5" />
            <span>{t("page.failedToLoadTree", { message: (error as Error)?.message })}</span>
          </CardContent>
        </Card>
      )}

      <div className={cn("grid min-h-0 flex-1 gap-4", hideTree ? "grid-cols-1" : "grid-cols-[280px_1fr]")}>
        {!hideTree && (
          <Card className="min-h-0 overflow-hidden">
            <CardContent className="h-full overflow-y-auto p-2">
              {isLoading && <Loader2 className="m-4 h-5 w-5 animate-spin text-muted-foreground" />}
              {tree && tree.length === 0 && (
                <p className="p-3 text-xs italic text-muted-foreground">{t("page.emptyFolder")}</p>
              )}
              {tree && tree.length > 0 && filteredTree && filteredTree.length === 0 && (
                <p className="p-3 text-xs italic text-muted-foreground">{t("page.noSearchMatch")}</p>
              )}
              {filteredTree && filteredTree.length > 0 && (
                <DocTree
                  nodes={filteredTree}
                  selectedPath={selectedPath ?? undefined}
                  onSelectFile={setSelectedPath}
                  workingDir={workingDir}
                  onSelectFolder={setWorkingDir}
                  actions={{
                    onCreateFile: handleCreateFileIn,
                    onCreateFolder: handleCreateFolderIn,
                    onRename: handleRenamePath,
                    onDelete: handleDeletePath,
                  }}
                  expandedPaths={expandedPaths}
                  onToggleExpand={toggleExpanded}
                  onMove={handleMove}
                  getAssistantDragPayload={areaId && currentArea ? (node) =>
                    node.type === "dir"
                      ? {
                          source: "host-folder",
                          path: `${currentArea.host_path.replace(/\/$/, "")}/${node.path}`,
                          name: node.name,
                        }
                      : {
                          source: "docs",
                          areaId,
                          path: node.path,
                          name: node.name,
                        }
                  : undefined}
                />
              )}
            </CardContent>
          </Card>
        )}

        <Card className="min-h-0 overflow-hidden">
          <CardContent
            className={cn(
              "h-full",
              viewMode === "note" ? "flex flex-col gap-2 overflow-y-auto p-4" : "overflow-hidden p-0"
            )}
          >
            {viewMode === "mindmap" && (
              <div className="h-full overflow-hidden">
                {!selectedPath && (
                  <p className="p-6 text-sm italic text-muted-foreground">{t("page.selectDocumentFirst")}</p>
                )}
                {selectedPath && !isEditable && (
                  <p className="p-6 text-sm italic text-muted-foreground">{t("page.binaryFile")}</p>
                )}
                {selectedPath && isEditable && fileLoading && (
                  <Loader2 className="m-6 h-5 w-5 animate-spin text-muted-foreground" />
                )}
                {selectedPath && isEditable && file && <MindMapView markdown={draft ?? file.content} />}
              </div>
            )}
            {viewMode === "graph" && (
              <div className="h-full overflow-hidden">
                {graphLoading && (
                  <div className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t("page.buildingGraph")}
                  </div>
                )}
                {graph && <GraphView graph={graph} onSelectNode={handleSelectFromGraph} />}
              </div>
            )}
            {viewMode === "note" && !selectedPath && (
              <p className="m-auto text-sm italic text-muted-foreground">
                {t("page.selectOrCreate")}
              </p>
            )}
            {viewMode === "note" && selectedPath && (
              <div
                ref={fullscreenRef}
                className={cn("flex flex-1 flex-col gap-2", isFullscreen && "overflow-y-auto bg-background p-6")}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <code className="truncate text-xs text-muted-foreground">{selectedPath}</code>
                  <div className="flex flex-wrap items-center gap-0.5">
                    {isEditable && (
                      <CopyButton getText={() => draft ?? file?.content ?? ""} title={t("page.copyDocument")} />
                    )}
                    <Button
                      size="icon"
                      variant="outline"
                      title={isFullscreen ? t("page.exitFullscreen") : t("page.fullscreen")}
                      aria-label={isFullscreen ? t("page.exitFullscreen") : t("page.fullscreen")}
                      onClick={toggleFullscreen}
                    >
                      {isFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                    </Button>
                    {isEditable && isDocsArea && (
                      <Button
                        size="icon"
                        variant={showConvert ? "secondary" : "outline"}
                        title={showConvert ? t("page.hideForward") : t("page.forwardThisDocument")}
                        aria-label={t("page.forward")}
                        onClick={() => setShowConvert((v) => !v)}
                      >
                        <ArrowRightCircle className="h-4 w-4" />
                      </Button>
                    )}
                    {isEditable && draft == null && (
                      <Button
                        size="icon"
                        variant="outline"
                        title={t("page.edit")}
                        aria-label={t("page.edit")}
                        onClick={() => setDraft(file?.content ?? "")}
                      >
                        <FileEdit className="h-4 w-4" />
                      </Button>
                    )}
                    {draft != null && (
                      <>
                        <Button
                          size="icon"
                          title={t("page.save")}
                          aria-label={t("page.save")}
                          disabled={saveFile.isPending || !dirty}
                          onClick={handleSave}
                        >
                          {saveFile.isPending ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Save className="h-4 w-4" />
                          )}
                        </Button>
                        <Button
                          size="icon"
                          variant="outline"
                          title={t("page.view")}
                          aria-label={t("page.view")}
                          onClick={() => setDraft(null)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                    <Button
                      variant="outline"
                      size="icon"
                      title={t("page.renameMove")}
                      aria-label={t("page.rename")}
                      onClick={() => handleRenamePath(selectedPath)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      title={t("page.delete")}
                      aria-label={t("page.delete")}
                      className="text-destructive"
                      onClick={() => setDeleting(selectedPath)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {saveFile.isError && (
                  <p className="text-xs text-destructive">{t("page.failedToSave", { message: (saveFile.error as Error)?.message })}</p>
                )}

                <div className="min-h-0 flex-1 overflow-hidden">
                  {!isEditable && !isScene && (
                    <p className="text-sm text-muted-foreground">
                      {t("page.binaryFile")}
                    </p>
                  )}
                  {isScene && (
                    <div className="flex flex-col items-start gap-2">
                      <p className="text-sm text-muted-foreground">
                        {t("page.whiteboardScene")}
                      </p>
                      {fileLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                      {fileError && (
                        <p className="text-xs text-destructive">{t("page.couldNotReadScene")}</p>
                      )}
                      {file && (
                        <Button size="sm" className="gap-1.5" onClick={handleEditScene}>
                          <Palette className="h-3.5 w-3.5" /> {t("page.editInWhiteboard")}
                        </Button>
                      )}
                    </div>
                  )}
                  {isEditable && fileLoading && (
                    <Loader2 className="m-4 h-5 w-5 animate-spin text-muted-foreground" />
                  )}
                  {isEditable && fileError && (
                    <p className="text-sm text-destructive">{t("page.couldNotReadFile")}</p>
                  )}
                  {isEditable && file && draft == null && (
                    <div className="h-full overflow-y-auto pr-2">
                      <Markdown content={file.content} />
                    </div>
                  )}
                  {isEditable && draft != null && (
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      spellCheck={false}
                      className="h-full w-full resize-none rounded-md border border-input bg-background p-3 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    />
                  )}
                </div>

                {isEditable && isDocsArea && showConvert && (
                  <ConvertMenu
                    defaultTitle={selectedPath.split("/").pop()?.replace(/\.(md|markdown|txt)$/i, "") ?? ""}
                    onConvert={(payload) => {
                      setConvertMessage(null);
                      convertDoc.mutate(
                        { sourcePath: selectedPath, payload },
                        { onSuccess: (result) => setConvertMessage(convertResultMessage(result)) }
                      );
                    }}
                    isPending={convertDoc.isPending}
                    error={(convertDoc.error as Error)?.message}
                  />
                )}
                {convertMessage && <p className="text-xs text-emerald-600">{convertMessage}</p>}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
