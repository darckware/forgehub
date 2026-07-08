import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  BookOpen,
  Bot,
  ChevronDown,
  Download,
  Eye,
  FilePlus,
  Folder,
  FolderPlus,
  Loader2,
  Palette,
  Pencil,
  Plus,
  Save,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { DocTree, type DocTreeNode } from "@/components/DocTree";
import { Markdown } from "@/components/Markdown";
import { DocLinkPanel } from "@/components/DocLinkPanel";
import { ConvertMenu, convertResultMessage } from "@/components/ConvertMenu";
import { useConvertDoc } from "@/hooks/useDemands";
import { AssistantDrawer } from "@/components/chat/AssistantDrawer";
import { WhiteboardModal, type WhiteboardSaveResult } from "@/components/whiteboard/WhiteboardModal";
import type { ExcalidrawInitialDataState } from "@excalidraw/excalidraw/types";
import {
  downloadDoc,
  useCreateDocArea,
  useCreateDocFolder,
  useDeleteDocArea,
  useDeleteDocPath,
  useDocAreas,
  useDocFile,
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

/** Small inline prompt row (new file / new folder / rename). */
function PathPrompt({
  label,
  initial,
  onConfirm,
  onCancel,
  pending,
}: {
  label: string;
  initial: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
  pending: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 p-2">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <Input
        autoFocus
        value={value}
        className="h-8 text-xs"
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) onConfirm(value.trim());
          if (e.key === "Escape") onCancel();
        }}
      />
      <Button size="sm" disabled={pending || !value.trim()} onClick={() => onConfirm(value.trim())}>
        {pending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "OK"}
      </Button>
      <Button size="sm" variant="outline" onClick={onCancel}>
        Cancelar
      </Button>
    </div>
  );
}

/** Switch between "áreas de criação" (any host folder) -- add/remove/select. */
function AreaSwitcher({
  areas,
  currentAreaId,
  onSelect,
}: {
  areas: { id: string; name: string; host_path: string }[];
  currentAreaId: string | null;
  onSelect: (areaId: string) => void;
}) {
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
        área de criação · <code className="text-foreground">{current?.host_path ?? "..."}</code>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <Card className="absolute left-0 top-full z-50 mt-1 w-96 shadow-xl">
            <CardContent className="max-h-80 overflow-y-auto p-2">
              <ConfirmDialog
                open={deletingArea !== null}
                title="Remover área de criação"
                description="Remove apenas o registro da área -- os arquivos continuam no host, intactos."
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
                    title={areas.length <= 1 ? "Pelo menos uma área precisa existir" : "Remover área"}
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
                    placeholder="Nome (ex: Projeto)"
                    value={newName}
                    className="h-8 text-xs"
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <Input
                    placeholder="Caminho absoluto no host (ex: /root/project)"
                    value={newPath}
                    className="h-8 font-mono text-xs"
                    onChange={(e) => setNewPath(e.target.value)}
                  />
                  {createArea.isError && (
                    <p className="text-xs text-destructive">{(createArea.error as Error)?.message}</p>
                  )}
                  <div className="flex justify-end gap-1.5">
                    <Button size="sm" variant="outline" onClick={resetAddForm}>
                      Cancelar
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
                      {createArea.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Adicionar"}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button variant="ghost" size="sm" className="mt-1 w-full justify-start gap-1.5" onClick={() => setAdding(true)}>
                  <Plus className="h-3.5 w-3.5" /> Nova área
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
  const [prompt, setPrompt] = useState<"new-file" | "new-folder" | "rename" | null>(null);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  // Explicit "pasta de trabalho": click a folder in the tree (or use the
  // reset button) to choose where "Novo documento"/"Nova pasta"/"Upload"
  // and the tree's own inline create actions land. "" is the area's root.
  const [workingDir, setWorkingDir] = useState("");

  // Whiteboard: undefined = closed; object (possibly {}) = open, reopening
  // that scene when non-empty (see handleOpenWhiteboard).
  const [whiteboardData, setWhiteboardData] = useState<ExcalidrawInitialDataState | undefined>();
  const [whiteboardNote, setWhiteboardNote] = useState<string | null>(null);
  const [assistantOpen, setAssistantOpen] = useState(false);

  useEffect(() => setDraft(null), [selectedPath]);
  const convertDoc = useConvertDoc();
  const [convertMessage, setConvertMessage] = useState<string | null>(null);

  useEffect(() => setWhiteboardNote(null), [selectedPath]);
  useEffect(() => setConvertMessage(null), [selectedPath]);

  // Switching areas invalidates every bit of per-file/per-folder state --
  // each area is its own distinct working space (per-area selection/draft).
  function handleSelectArea(nextAreaId: string) {
    setAreaId(nextAreaId);
    setSelectedPath(null);
    setDraft(null);
    setWorkingDir("");
    setWhiteboardData(undefined);
    setWhiteboardNote(null);
    setConvertMessage(null);
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

  function handleOpenNewWhiteboard() {
    setWhiteboardData({});
  }

  function handleEditScene() {
    if (!file) return;
    try {
      const scene = JSON.parse(file.content);
      setWhiteboardData({ elements: scene.elements ?? [], appState: scene.appState, files: scene.files });
    } catch {
      setWhiteboardNote("Não foi possível ler esta cena (JSON inválido).");
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
    const imageRef = `![lousa](${WHITEBOARD_ASSETS_FOLDER}/${base}.png)`;
    if (selectedPath && isEditable) {
      const currentContent = draft ?? file?.content ?? "";
      setDraft(`${currentContent}\n\n${imageRef}\n`);
      setWhiteboardNote(null);
    } else {
      setWhiteboardNote(
        `Desenho salvo em ${WHITEBOARD_ASSETS_FOLDER}/${base}.png — abra um documento markdown para inserir a imagem, ou copie o caminho acima.`
      );
    }
    setWhiteboardData(undefined);
  }

  return (
    <div className="flex min-h-0 w-full flex-1 flex-col gap-4 p-6">
      <AssistantDrawer
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        tabId="assistant:docs"
        workingDir={currentArea?.host_path ?? "/root/docs"}
        contextLabel="Usar documento atual"
        buildContext={() => {
          if (!selectedPath || !currentArea) return null;
          const lines = [
            `Estou trabalhando na área "${currentArea.name}" do ForgeHub Docs (arquivos em ${currentArea.host_path}, no host).`,
            `Documento atual: ${currentArea.host_path}/${selectedPath}`,
            "",
            "Me ajude a criar/editar este documento. Escreva o resultado diretamente no arquivo (você tem acesso ao host) e me avise quando salvar.",
          ];
          const content = draft ?? file?.content;
          if (content) lines.push("", "Conteúdo atual:", "```markdown", content, "```");
          return lines.join("\n");
        }}
      />
      <ConfirmDialog
        open={deleting !== null}
        title={`Excluir "${deleting ?? ""}"`}
        description="Remove o arquivo (ou a pasta inteira, recursivamente) desta área. Esta ação não pode ser desfeita."
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

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <BookOpen className="h-5 w-5" /> Docs
          {areas && <AreaSwitcher areas={areas} currentAreaId={areaId} onSelect={handleSelectArea} />}
        </h1>
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setPrompt("new-file")}>
            <FilePlus className="h-4 w-4" /> Novo documento
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setPrompt("new-folder")}>
            <FolderPlus className="h-4 w-4" /> Nova pasta
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={!selectedPath}
            title={selectedPath ? `Baixar ${selectedPath}` : "Selecione um documento na árvore para baixar"}
            onClick={() => areaId && selectedPath && downloadDoc(areaId, selectedPath)}
          >
            <Download className="h-4 w-4" /> Download
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            disabled={uploadFile.isPending}
            title={`Upload para ${workingDir || "a raiz"}`}
            onClick={() => uploadRef.current?.click()}
          >
            {uploadFile.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Upload
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            title="Desenhar e inserir a imagem no documento aberto"
            onClick={handleOpenNewWhiteboard}
          >
            <Palette className="h-4 w-4" /> Lousa
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            title="Abrir o assistente para ajudar a criar/preencher este documento"
            onClick={() => setAssistantOpen(true)}
          >
            <Bot className="h-4 w-4" /> Agente
          </Button>
        </div>
      </div>

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Folder className="h-3.5 w-3.5" />
        Pasta de trabalho: <code className="text-foreground">{currentArea?.host_path ?? ""}/{workingDir || ""}</code>
        {workingDir && (
          <button type="button" className="underline hover:text-foreground" onClick={() => setWorkingDir("")}>
            usar raiz
          </button>
        )}
      </p>

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
          label="Caminho do novo .md:"
          initial={workingDir ? `${workingDir}/` : ""}
          pending={saveFile.isPending}
          onConfirm={handleCreateFile}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "new-folder" && (
        <PathPrompt
          label="Caminho da nova pasta:"
          initial={workingDir ? `${workingDir}/` : ""}
          pending={createFolder.isPending}
          onConfirm={(p) => createFolder.mutate(p, { onSuccess: () => setPrompt(null) })}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "rename" && renameTarget && (
        <PathPrompt
          label={`Renomear ${renameTarget} para:`}
          initial={renameTarget}
          pending={renamePath.isPending}
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
            <span>Falha ao carregar a árvore: {(error as Error)?.message}</span>
          </CardContent>
        </Card>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-[280px_1fr] gap-4">
        <Card className="min-h-0 overflow-hidden">
          <CardContent className="h-full overflow-y-auto p-2">
            {isLoading && <Loader2 className="m-4 h-5 w-5 animate-spin text-muted-foreground" />}
            {tree && tree.length === 0 && (
              <p className="p-3 text-xs italic text-muted-foreground">Pasta vazia.</p>
            )}
            {tree && (
              <DocTree
                nodes={tree as DocTreeNode[]}
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
                onMove={handleMove}
              />
            )}
          </CardContent>
        </Card>

        <Card className="min-h-0 overflow-hidden">
          <CardContent className="flex h-full flex-col gap-2 overflow-y-auto p-4">
            {!selectedPath && (
              <p className="m-auto text-sm italic text-muted-foreground">
                Selecione um documento na árvore, ou crie um novo.
              </p>
            )}
            {selectedPath && (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <code className="truncate text-xs text-muted-foreground">{selectedPath}</code>
                  <div className="flex items-center gap-0.5">
                    {isEditable && draft == null && (
                      <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setDraft(file?.content ?? "")}>
                        <Pencil className="h-3.5 w-3.5" /> Editar
                      </Button>
                    )}
                    {draft != null && (
                      <>
                        <Button size="sm" className="gap-1.5" disabled={saveFile.isPending || !dirty} onClick={handleSave}>
                          {saveFile.isPending ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Save className="h-3.5 w-3.5" />
                          )}
                          Salvar
                        </Button>
                        <Button size="sm" variant="outline" className="gap-1.5" onClick={() => setDraft(null)}>
                          <Eye className="h-3.5 w-3.5" /> Visualizar
                        </Button>
                      </>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Renomear/mover"
                      aria-label="Renomear"
                      onClick={() => handleRenamePath(selectedPath)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Download"
                      aria-label="Download"
                      onClick={() => areaId && downloadDoc(areaId, selectedPath)}
                    >
                      <Download className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Excluir"
                      aria-label="Excluir"
                      className="text-destructive"
                      onClick={() => setDeleting(selectedPath)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {saveFile.isError && (
                  <p className="text-xs text-destructive">Falha ao salvar: {(saveFile.error as Error)?.message}</p>
                )}

                <div className="min-h-0 flex-1 overflow-hidden">
                  {!isEditable && !isScene && (
                    <p className="text-sm text-muted-foreground">
                      Arquivo binário — use Download para abrir ou substitua via Upload.
                    </p>
                  )}
                  {isScene && (
                    <div className="flex flex-col items-start gap-2">
                      <p className="text-sm text-muted-foreground">
                        Cena da Lousa (Excalidraw). Reabra para continuar o desenho.
                      </p>
                      {fileLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                      {fileError && (
                        <p className="text-xs text-destructive">Não foi possível ler a cena.</p>
                      )}
                      {file && (
                        <Button size="sm" className="gap-1.5" onClick={handleEditScene}>
                          <Palette className="h-3.5 w-3.5" /> Editar na Lousa
                        </Button>
                      )}
                    </div>
                  )}
                  {isEditable && fileLoading && (
                    <Loader2 className="m-4 h-5 w-5 animate-spin text-muted-foreground" />
                  )}
                  {isEditable && fileError && (
                    <p className="text-sm text-destructive">Não foi possível ler o arquivo.</p>
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

                {isEditable && isDocsArea && (
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

                {isDocsArea && <DocLinkPanel docPath={selectedPath} />}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
