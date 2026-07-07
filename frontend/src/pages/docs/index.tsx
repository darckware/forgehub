import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AlertCircle,
  BookOpen,
  Download,
  Eye,
  FilePlus,
  FolderPlus,
  Loader2,
  Palette,
  Pencil,
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
  useCreateDocFolder,
  useDeleteDocPath,
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

function parentDir(path: string): string {
  const idx = path.lastIndexOf("/");
  return idx === -1 ? "" : path.slice(0, idx);
}

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

export default function DocsPage() {
  const { data: tree, isLoading, isError, error } = useDocsTree();
  const [searchParams] = useSearchParams();
  // Deep-link from EntityDocsCard (/docs?path=...) -- only seeds the
  // initial selection, so navigating the tree afterwards isn't fought.
  const [selectedPath, setSelectedPath] = useState<string | null>(() => searchParams.get("path"));
  const isEditable = selectedPath ? EDITABLE_RE.test(selectedPath) : false;
  const isScene = selectedPath ? SCENE_RE.test(selectedPath) : false;
  // .excalidraw is read as text too (backend allows it) so a saved scene
  // can be reopened for editing without a dedicated endpoint.
  const { data: file, isLoading: fileLoading, isError: fileError } = useDocFile(
    isEditable || isScene ? selectedPath : null
  );
  const saveFile = useSaveDocFile();
  const deletePath = useDeleteDocPath();
  const createFolder = useCreateDocFolder();
  const renamePath = useRenameDocPath();
  const uploadFile = useUploadDocFile();

  // null = viewing; string = editing draft. Cleared when switching files.
  const [draft, setDraft] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<"new-file" | "new-folder" | "rename" | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  // Whiteboard: undefined = closed; object (possibly {}) = open, reopening
  // that scene when non-empty (see handleOpenWhiteboard).
  const [whiteboardData, setWhiteboardData] = useState<ExcalidrawInitialDataState | undefined>();
  const [whiteboardNote, setWhiteboardNote] = useState<string | null>(null);

  useEffect(() => setDraft(null), [selectedPath]);
  const convertDoc = useConvertDoc();
  const [convertMessage, setConvertMessage] = useState<string | null>(null);

  useEffect(() => setWhiteboardNote(null), [selectedPath]);
  useEffect(() => setConvertMessage(null), [selectedPath]);

  // New files/uploads land next to the selected file (or its folder).
  const targetFolder = selectedPath ? parentDir(selectedPath) : "";
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
      uploadFile.mutate({ folder: targetFolder, file: f });
    }
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
        tabId="assistant:docs"
        workingDir="/root/docs"
        contextLabel="Usar documento atual"
        buildContext={() => {
          if (!selectedPath) return null;
          const lines = [
            "Estou trabalhando na área Docs do ForgeHub (arquivos em /root/docs, no host).",
            `Documento atual: /root/docs/${selectedPath}`,
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
        description="Remove o arquivo (ou a pasta inteira, recursivamente) de /root/docs. Esta ação não pode ser desfeita."
        loading={deletePath.isPending}
        onConfirm={() => {
          if (deleting)
            deletePath.mutate(deleting, {
              onSuccess: () => {
                if (selectedPath?.startsWith(deleting)) setSelectedPath(null);
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
          <span className="text-sm font-normal text-muted-foreground">
            área de criação · /root/docs
          </span>
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
            disabled={uploadFile.isPending}
            title={`Upload para ${targetFolder || "a raiz"}`}
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
          label="Caminho do novo .md:"
          initial={targetFolder ? `${targetFolder}/` : ""}
          pending={saveFile.isPending}
          onConfirm={handleCreateFile}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "new-folder" && (
        <PathPrompt
          label="Caminho da nova pasta:"
          initial={targetFolder ? `${targetFolder}/` : ""}
          pending={createFolder.isPending}
          onConfirm={(p) => createFolder.mutate(p, { onSuccess: () => setPrompt(null) })}
          onCancel={() => setPrompt(null)}
        />
      )}
      {prompt === "rename" && selectedPath && (
        <PathPrompt
          label={`Renomear ${selectedPath} para:`}
          initial={selectedPath}
          pending={renamePath.isPending}
          onConfirm={(p) =>
            renamePath.mutate(
              { path: selectedPath, newPath: p },
              {
                onSuccess: () => {
                  setPrompt(null);
                  setSelectedPath(p);
                },
              }
            )
          }
          onCancel={() => setPrompt(null)}
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
                      onClick={() => setPrompt("rename")}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      title="Download"
                      aria-label="Download"
                      onClick={() => downloadDoc(selectedPath)}
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

                {isEditable && (
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

                <DocLinkPanel docPath={selectedPath} />
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
