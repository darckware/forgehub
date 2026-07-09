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

// Custom MIME type for the dragged node's path -- namespaced so dropping
// something dragged from elsewhere on the page (or another app) is a no-op
// instead of misreading unrelated drag data as a move.
const DRAG_MIME = "application/x-forgehub-doc-path";

interface DocTreeItemProps {
  node: DocTreeNode;
  depth: number;
  selectedPath: string | undefined;
  onSelectFile: (path: string) => void;
  workingDir?: string;
  onSelectFolder?: (path: string) => void;
  actions?: DocTreeActions;
  onMove?: (sourcePath: string, destFolderPath: string) => void;
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
  onMove,
}: DocTreeItemProps) {
  const [expanded, setExpanded] = useState(depth === 0);
  const [dragOver, setDragOver] = useState(false);
  const draggable = Boolean(onMove);

  function handleDragStart(e: React.DragEvent) {
    e.dataTransfer.setData(DRAG_MIME, node.path);
    e.dataTransfer.effectAllowed = "move";
  }

  if (node.type === "dir") {
    const isWorkingDir = workingDir === node.path;
    return (
      <div>
        <div
          draggable={draggable}
          onDragStart={handleDragStart}
          onDragOver={(e) => {
            if (!onMove) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
          }}
          onDragEnter={(e) => {
            if (!onMove) return;
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            if (!onMove) return;
            e.preventDefault();
            setDragOver(false);
            const sourcePath = e.dataTransfer.getData(DRAG_MIME);
            if (sourcePath && sourcePath !== node.path) onMove(sourcePath, node.path);
          }}
          className={cn(
            "group flex w-full items-center gap-1.5 rounded-md pr-1 text-sm",
            dragOver
              ? "bg-accent ring-1 ring-inset ring-primary"
              : isWorkingDir
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
            title={onSelectFolder ? "Select as working folder" : undefined}
          >
            {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0" />}
            <Folder className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{node.name}</span>
          </button>
          {actions && (
            <div className="flex shrink-0 items-center opacity-0 group-hover:opacity-100">
              <ActionIcon icon={FilePlus} label="New document here" onClick={() => actions.onCreateFile(node.path)} />
              <ActionIcon icon={FolderPlus} label="New folder here" onClick={() => actions.onCreateFolder(node.path)} />
              <ActionIcon icon={Pencil} label="Rename folder" onClick={() => actions.onRename(node.path)} />
              <ActionIcon icon={Trash2} label="Delete folder" destructive onClick={() => actions.onDelete(node.path)} />
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
              onMove={onMove}
            />
          ))}
      </div>
    );
  }

  return (
    <div
      draggable={draggable}
      onDragStart={handleDragStart}
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
          <ActionIcon icon={Pencil} label="Rename file" onClick={() => actions.onRename(node.path)} />
          <ActionIcon icon={Trash2} label="Delete file" destructive onClick={() => actions.onDelete(node.path)} />
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
  onMove,
}: {
  nodes: DocTreeNode[];
  selectedPath: string | undefined;
  onSelectFile: (path: string) => void;
  /** Currently selected folder new files/folders/uploads target -- "" is the
   * root. Only meaningful together with onSelectFolder. */
  workingDir?: string;
  onSelectFolder?: (path: string) => void;
  actions?: DocTreeActions;
  /** Drag-and-drop move: dragging any row and dropping it onto a folder row
   * (or the root drop zone below the tree) calls this with (sourcePath,
   * destFolderPath). Optional, like `actions` -- undefined disables
   * dragging entirely (the Knowledge Base page's read-only tree). */
  onMove?: (sourcePath: string, destFolderPath: string) => void;
}) {
  const [rootDragOver, setRootDragOver] = useState(false);
  return (
    <div className="flex min-h-full flex-col">
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
          onMove={onMove}
        />
      ))}
      {onMove && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
          }}
          onDragEnter={(e) => {
            e.preventDefault();
            setRootDragOver(true);
          }}
          onDragLeave={() => setRootDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setRootDragOver(false);
            const sourcePath = e.dataTransfer.getData(DRAG_MIME);
            if (sourcePath) onMove(sourcePath, "");
          }}
          className={cn(
            "min-h-8 flex-1 rounded-md",
            rootDragOver && "bg-accent ring-1 ring-inset ring-primary"
          )}
          title="Drop here to move to the area's root"
        />
      )}
    </div>
  );
}
