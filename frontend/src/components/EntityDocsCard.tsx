import { useState } from "react";
import { Link } from "react-router-dom";
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  File,
  FileText,
  Folder,
  Loader2,
  Plus,
  X,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  useCreateDocLink,
  useDeleteDocLink,
  useEntityDocLinks,
  type DocLinkEntityType,
} from "@/hooks/useDocLinks";
import { useProjectFileList, type ProjectFileEntry } from "@/hooks/useProjectFiles";

interface ProjectFileSelectorTreeProps {
  projectId: string;
  dirPath: string;
  depth: number;
  onSelectDoc: (path: string) => void;
  linkedPaths: Set<string>;
}

function ProjectFileSelectorTree({
  projectId,
  dirPath,
  depth,
  onSelectDoc,
  linkedPaths,
}: ProjectFileSelectorTreeProps) {
  const { data, isLoading } = useProjectFileList(projectId, dirPath);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => ({ ...prev, [path]: !prev[path] }));
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-1 text-xs text-muted-foreground" style={{ paddingLeft: `${depth * 0.75 + 0.5}rem` }}>
        <Loader2 className="h-3 w-3 animate-spin" /> Carregando...
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {data?.entries.map((entry: ProjectFileEntry) => {
        const isDir = entry.type === "dir";
        const isExpanded = Boolean(expandedDirs[entry.path]);
        const isLinked = linkedPaths.has(entry.path);
        const isMd = /\.md$/i.test(entry.name);

        if (isDir) {
          return (
            <div key={entry.path}>
              <button
                type="button"
                onClick={() => toggleDir(entry.path)}
                className="flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
                style={{ paddingLeft: `${depth * 0.75 + 0.5}rem` }}
              >
                {isExpanded ? (
                  <ChevronDown className="h-3 w-3 shrink-0" />
                ) : (
                  <ChevronRight className="h-3 w-3 shrink-0" />
                )}
                <Folder className="h-3.5 w-3.5 shrink-0 text-primary/70" />
                <span className="truncate">{entry.name}</span>
              </button>
              {isExpanded && (
                <ProjectFileSelectorTree
                  projectId={projectId}
                  dirPath={entry.path}
                  depth={depth + 1}
                  onSelectDoc={onSelectDoc}
                  linkedPaths={linkedPaths}
                />
              )}
            </div>
          );
        }

        return (
          <div
            key={entry.path}
            className="flex items-center justify-between gap-2 rounded px-2 py-1 hover:bg-accent/60 text-xs"
            style={{ paddingLeft: `${depth * 0.75 + 0.5 + 1}rem` }}
          >
            <div className="flex items-center gap-1.5 min-w-0">
              {isMd ? (
                <FileText className="h-3.5 w-3.5 shrink-0 text-primary" />
              ) : (
                <File className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              )}
              <span className="truncate font-mono">{entry.name}</span>
            </div>

            {isLinked ? (
              <span className="flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400 font-medium px-1.5 py-0.5 rounded bg-emerald-500/10">
                <Check className="h-2.5 w-2.5" /> Vinculado
              </span>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-6 text-[11px] px-2 gap-1 text-primary hover:text-primary hover:bg-primary/10"
                onClick={() => onSelectDoc(entry.path)}
              >
                <Plus className="h-3 w-3" /> Vincular
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * "Docs" section for a Planning entity's detail screen:
 * Displays documents linked to this entity and allows selecting files directly
 * from the project's folder to serve as context.
 */
export function EntityDocsCard({
  entityType,
  entityId,
  projectId,
}: {
  entityType: DocLinkEntityType;
  entityId: string | undefined;
  projectId?: string;
}) {
  const { data: links, isLoading } = useEntityDocLinks(entityType, entityId);
  const deleteLink = useDeleteDocLink();
  const createLink = useCreateDocLink();
  const [showFilePicker, setShowFilePicker] = useState(false);

  if (!entityId) return null;

  const linkedPaths = new Set((links || []).map((l) => l.doc_path));
  const effectiveProjectId = projectId || (entityType === "project" ? entityId : undefined);

  const handleLinkFile = (filePath: string) => {
    createLink.mutate({
      doc_path: filePath,
      entity_type: entityType,
      entity_id: entityId,
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-3">
        <div>
          <CardTitle className="flex items-center gap-2 text-base font-semibold">
            <BookOpen className="h-4 w-4 text-primary" /> Documentos de Contexto
            {links && <span className="text-xs font-normal text-muted-foreground">({links.length})</span>}
          </CardTitle>
          <CardDescription className="text-xs mt-0.5">
            Arquivos e especificações vinculados como contexto para este projeto.
          </CardDescription>
        </div>

        {effectiveProjectId && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="text-xs gap-1.5 h-8 font-medium"
            onClick={() => setShowFilePicker((v) => !v)}
          >
            <Plus className="h-3.5 w-3.5" />
            {showFilePicker ? "Fechar Seletor" : "Selecionar Arquivo da Pasta"}
          </Button>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Painel seletor de arquivos da pasta do projeto */}
        {showFilePicker && effectiveProjectId && (
          <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
            <div className="flex items-center justify-between border-b pb-1.5">
              <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Folder className="h-3.5 w-3.5 text-primary" /> Arquivos na pasta do projeto:
              </span>
              <span className="text-[11px] text-muted-foreground">Clique em "Vincular" no arquivo desejado</span>
            </div>
            <div className="max-h-60 overflow-y-auto pr-1">
              <ProjectFileSelectorTree
                projectId={effectiveProjectId}
                dirPath=""
                depth={0}
                onSelectDoc={handleLinkFile}
                linkedPaths={linkedPaths}
              />
            </div>
          </div>
        )}

        {isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}

        {links && links.length === 0 && !showFilePicker && (
          <div className="p-4 rounded-md border border-dashed text-center bg-muted/10">
            <p className="text-xs italic text-muted-foreground">
              Nenhum documento vinculado ainda. Use o botão acima para selecionar arquivos da pasta do projeto.
            </p>
          </div>
        )}

        {links && links.length > 0 && (
          <div className="rounded-md border divide-y">
            {links.map((link) => (
              <div
                key={link.id}
                className="flex items-center justify-between gap-2 p-2 hover:bg-accent/40 text-xs transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-primary" />
                  <Link
                    to={`/docs?path=${encodeURIComponent(link.doc_path)}`}
                    className="truncate hover:underline font-mono text-foreground"
                    title={link.doc_path}
                  >
                    {link.doc_path}
                  </Link>
                  <Link
                    to={`/docs?path=${encodeURIComponent(link.doc_path)}`}
                    className="text-muted-foreground hover:text-foreground shrink-0"
                    title="Abrir documento"
                  >
                    <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                  aria-label="Desvincular"
                  title="Desvincular"
                  onClick={() => deleteLink.mutate(link.id)}
                >
                  <X className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
