import { useState } from "react";
import { ChevronDown, ChevronRight, FilePlus, FileText, Folder, FolderPlus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface DocTreeNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: DocTreeNode[];
}

/** Create/rename/delete actions for the tree rows -- optional so read-only
 * consumers (the Knowledge Base page) render the exact same tree with no
 * action icons at all. */
export interface DocTreeActions {
  onCreateFile: (folderPath: string) => void;
  onCreateFolder: (folderPath: string) => void;
  onRename: (path: string) => void;
  onDelete: (path: string) => void;
}

interface DocTreeItemProps {
  node: DocTreeNode;
  depth: number;
  selectedPath: string | undefined;
  onSelectFile: (path: string) => void;
  workingDir?: string;
  onSelectFolder?: (path: string) => void;
  actions?: DocTreeActions;
}

function ActionIcon({
  icon: Icon,
  label,
  onClick,
  destructive,
}: {
  icon: typeof Pencil;
  label: string;
  onClick: () => void;
  destructive?: boolean;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("h-5 w-5 shrink-0", destructive && "text-destructive")}
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
    >
      <Icon className="h-3 w-3" />
    </Button>
  );
}

function DocTreeItem({
  node,
  depth,
  selectedPath,
  onSelectFile,
  workingDir,
  onSelectFolder,
  actions,
}: DocTreeItemProps) {
  const [expanded, setExpanded] = useState(depth === 0);

  if (node.type === "dir") {
    const isWorkingDir = workingDir === node.path;
    return (
      <div>
        <div
          className={cn(
            "group flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
            isWorkingDir
              ? "bg-accent/70 text-accent-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          )}
        >
          <button
            type="button"
            onClick={() => {
              setExpanded((v) => !v);
              onSelectFolder?.(node.path);
            }}
            className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
            style={{ paddingLeft: `${depth * 0.9 + 0.5}rem` }}
            title={onSelectFolder ? "Selecionar como pasta de trabalho" : undefined}
          >
            {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
            <Folder className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{node.name}</span>
          </button>
          {actions && (
            <div className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
              <ActionIcon icon={FilePlus} label="Novo documento aqui" onClick={() => actions.onCreateFile(node.path)} />
              <ActionIcon icon={FolderPlus} label="Nova pasta aqui" onClick={() => actions.onCreateFolder(node.path)} />
              <ActionIcon icon={Pencil} label="Renomear pasta" onClick={() => actions.onRename(node.path)} />
              <ActionIcon icon={Trash2} label="Excluir pasta" destructive onClick={() => actions.onDelete(node.path)} />
            </div>
          )}
        </div>
        {expanded &&
          node.children?.map((child) => (
            <DocTreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelectFile={onSelectFile}
              workingDir={workingDir}
              onSelectFolder={onSelectFolder}
              actions={actions}
            />
          ))}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "group flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
        node.path === selectedPath
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      )}
    >
      <button
        type="button"
        onClick={() => onSelectFile(node.path)}
        className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
        style={{ paddingLeft: `${depth * 0.9 + 0.5 + 1.25}rem` }}
      >
        <FileText className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate">{node.name.replace(/\.md$/i, "")}</span>
      </button>
      {actions && (
        <div className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
          <ActionIcon icon={Pencil} label="Renomear arquivo" onClick={() => actions.onRename(node.path)} />
          <ActionIcon icon={Trash2} label="Excluir arquivo" destructive onClick={() => actions.onDelete(node.path)} />
        </div>
      )}
    </div>
  );
}

export function DocTree({
  nodes,
  selectedPath,
  onSelectFile,
  workingDir,
  onSelectFolder,
  actions,
}: {
  nodes: DocTreeNode[];
  selectedPath: string | undefined;
  onSelectFile: (path: string) => void;
  /** Currently selected folder new files/folders/uploads target -- "" is the
   * root. Only meaningful together with onSelectFolder. */
  workingDir?: string;
  onSelectFolder?: (path: string) => void;
  actions?: DocTreeActions;
}) {
  return (
    <>
      {nodes.map((node) => (
        <DocTreeItem
          key={node.path}
          node={node}
          depth={0}
          selectedPath={selectedPath}
          onSelectFile={onSelectFile}
          workingDir={workingDir}
          onSelectFolder={onSelectFolder}
          actions={actions}
        />
      ))}
    </>
  );
}
