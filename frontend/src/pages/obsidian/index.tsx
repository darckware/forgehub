import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2, Pencil, Save, Trash2, X } from "lucide-react";
import {
  DocumentBrowser,
  filterDocumentTree,
  type DocumentViewMode,
} from "@/components/DocumentBrowser";
import { DocTree } from "@/components/DocTree";
import { GraphView } from "@/components/GraphView";
import { Markdown } from "@/components/Markdown";
import { MindMapView } from "@/components/MindMapView";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  useDeleteVaultNote,
  useUpdateVaultNote,
  useVaultGraph,
  useVaultNote,
  useVaultTree,
} from "@/hooks/useVault";

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
  const deleteNote = useDeleteVaultNote();

  const [viewMode, setViewMode] = useState<DocumentViewMode>("note");
  const { data: graph, isLoading: graphLoading } = useVaultGraph();

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setIsEditing(false);
  }, [selectedPath]);

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
    if (!window.confirm(t("confirmDelete", { path: selectedPath }))) return;
    deleteNote.mutate(selectedPath, {
      onSuccess: () => setSelectedPath(undefined),
    });
  }

  return (
    <DocumentBrowser
      title={t("title")}
      searchValue={noteSearch}
      onSearchChange={setNoteSearch}
      searchPlaceholder={t("searchPlaceholder")}
      viewMode={viewMode}
      onViewModeChange={setViewMode}
      mindMapDisabled={!selectedPath}
      bodyClassName="h-[calc(100vh-11rem)]"
      actions={viewMode === "note" && selectedPath && (
        !isEditing ? (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleStartEdit} disabled={!note}>
              <Pencil className="mr-2 h-3.5 w-3.5" />
              {t("edit")}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDelete}
              disabled={!note || deleteNote.isPending}
              className="text-destructive hover:text-destructive"
            >
              {deleteNote.isPending ? (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="mr-2 h-3.5 w-3.5" />
              )}
              {t("delete")}
            </Button>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={updateNote.isPending}>
              <X className="mr-2 h-3.5 w-3.5" />
              {t("cancel")}
            </Button>
            <Button size="sm" onClick={handleSave} disabled={updateNote.isPending}>
              {updateNote.isPending ? (
                <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="mr-2 h-3.5 w-3.5" />
              )}
              {t("save")}
            </Button>
          </div>
        )
      )}
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
      {viewMode === "note" && (
        <div className="flex-1 overflow-y-auto p-4">
          {!selectedPath && <p className="text-sm italic text-muted-foreground">{t("selectNoteToRead")}</p>}
          {selectedPath && noteLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t("loadingNote")}
            </div>
          )}
          {updateNote.isError && (
            <p className="mb-3 text-sm text-destructive">{t("failedToSave", { message: (updateNote.error as Error)?.message })}</p>
          )}
          {deleteNote.isError && (
            <p className="mb-3 text-sm text-destructive">{t("failedToDelete", { message: (deleteNote.error as Error)?.message })}</p>
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
        <div className="flex-1 overflow-hidden">
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
        <div className="flex-1 overflow-hidden">
          {!note && <p className="p-6 text-sm italic text-muted-foreground">{t("selectNoteFirst")}</p>}
          {note && <MindMapView markdown={note.content} />}
        </div>
      )}
    </DocumentBrowser>
  );
}
