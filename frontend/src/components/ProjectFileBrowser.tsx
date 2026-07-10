import { useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  File,
  FileText,
  FilePlus,
  Folder,
  FolderPlus,
  Loader2,
  MoreVertical,
  Pencil,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Markdown } from "@/components/Markdown";
import { useClickOutside } from "@/hooks/useClickOutside";
import { cn } from "@/lib/utils";
import {
  useCreateProjectDirectory,
  useCreateProjectFile,
  useDeleteProjectFile,
  useProjectFileContent,
  useProjectFileList,
  useRenameProjectFile,
  useWriteProjectFile,
  type ProjectFileEntry,
} from "@/hooks/useProjectFiles";

/** Per-row "..." menu: new file / new folder (dirs only) / rename / delete.
 * Same hover-reveal pattern as Workspace's ChatItemMenu. */
function FileRowMenu({
  entry,
  onNewFile,
  onNewFolder,
  onRename,
  onDelete,
}: {
  entry: ProjectFileEntry;
  onNewFile?: () => void;
  onNewFolder?: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  useClickOutside(containerRef, () => setOpen(false), open);

  return (
    <div className="relative shrink-0" ref={containerRef}>
      <button
        type="button"
        aria-label={`${entry.name} options`}
        title="Options"
        className="rounded-md p-1 opacity-0 hover:bg-accent group-hover:opacity-100"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        <MoreVertical className="h-3.5 w-3.5" />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-10 mt-1 w-44 overflow-hidden rounded-md border border-border bg-card py-1 shadow-md">
          {entry.type === "dir" && onNewFile && (
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                onNewFile();
              }}
            >
              <FilePlus className="h-3.5 w-3.5" />
              New file
            </button>
          )}
          {entry.type === "dir" && onNewFolder && (
            <button
              type="button"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                onNewFolder();
              }}
            >
              <FolderPlus className="h-3.5 w-3.5" />
              New folder
            </button>
          )}
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
              onRename();
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
            Rename
          </button>
          <button
            type="button"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-destructive hover:bg-accent"
            onClick={(e) => {
              e.stopPropagation();
              setOpen(false);
              onDelete();
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

interface ProjectFileTreeProps {
  projectId: string;
  dirPath: string;
  depth: number;
  selectedPath: string | undefined;
  onSelectFile: (path: string) => void;
  onFileRenamed: (oldPath: string, newPath: string) => void;
  onFileDeleted: (path: string) => void;
}

function joinPath(dir: string, name: string): string {
  return dir ? `${dir}/${name}` : name;
}

/** Lists the children of `dirPath` -- only ever mounted while expanded
 * (the root instance mounts immediately; nested instances are mounted by
 * their parent row's own expand toggle, see ProjectFileTreeRow), so this
 * always fetches as soon as it exists rather than tracking its own
 * separate expanded flag. */
function ProjectFileTreeDir({
  projectId,
  dirPath,
  depth,
  selectedPath,
  onSelectFile,
  onFileRenamed,
  onFileDeleted,
}: ProjectFileTreeProps) {
  const { data, isLoading, isError } = useProjectFileList(projectId, dirPath);
  const createFile = useCreateProjectFile(projectId);
  const createDir = useCreateProjectDirectory(projectId);
  const renameFile = useRenameProjectFile(projectId);
  const deleteFile = useDeleteProjectFile(projectId);

  function handleNewFile(parentPath: string) {
    const name = window.prompt("New file name (relative to this folder):");
    if (!name) return;
    createFile.mutate(joinPath(parentPath, name));
  }

  function handleNewFolder(parentPath: string) {
    const name = window.prompt("New folder name (relative to this folder):");
    if (!name) return;
    createDir.mutate(joinPath(parentPath, name));
  }

  function handleRename(entry: ProjectFileEntry) {
    const name = window.prompt("Rename to:", entry.name);
    if (!name || name === entry.name) return;
    const parent = entry.path.includes("/") ? entry.path.slice(0, entry.path.lastIndexOf("/")) : "";
    const newPath = joinPath(parent, name);
    renameFile.mutate({ path: entry.path, newPath }, { onSuccess: () => onFileRenamed(entry.path, newPath) });
  }

  function handleDelete(entry: ProjectFileEntry) {
    if (!window.confirm(`Delete "${entry.name}"? This removes it from disk permanently.`)) return;
    deleteFile.mutate(
      { path: entry.path, recursive: entry.type === "dir" },
      { onSuccess: () => onFileDeleted(entry.path) }
    );
  }

  return (
    <div>
      {isLoading && (
        <div
          className="flex items-center gap-2 px-2 py-1 text-xs text-muted-foreground"
          style={{ paddingLeft: `${depth * 0.9 + 0.5 + 1.25}rem` }}
        >
          <Loader2 className="h-3 w-3 animate-spin" />
          Loading…
        </div>
      )}
      {isError && (
        <p className="px-2 py-1 text-xs text-destructive" style={{ paddingLeft: `${depth * 0.9 + 0.5 + 1.25}rem` }}>
          Failed to list directory.
        </p>
      )}
      {data?.entries.length === 0 && (
        <p
          className="px-2 py-1 text-xs italic text-muted-foreground"
          style={{ paddingLeft: `${depth * 0.9 + 0.5 + 1.25}rem` }}
        >
          Empty
        </p>
      )}
      {data?.entries.map((entry) =>
        entry.type === "dir" ? (
          <ProjectFileTreeRow
            key={entry.path}
            entry={entry}
            depth={depth + 1}
            projectId={projectId}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            onFileRenamed={onFileRenamed}
            onFileDeleted={onFileDeleted}
            onNewFile={() => handleNewFile(entry.path)}
            onNewFolder={() => handleNewFolder(entry.path)}
            onRename={() => handleRename(entry)}
            onDelete={() => handleDelete(entry)}
          />
        ) : (
          <ProjectFileTreeRow
            key={entry.path}
            entry={entry}
            depth={depth + 1}
            projectId={projectId}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            onFileRenamed={onFileRenamed}
            onFileDeleted={onFileDeleted}
            onRename={() => handleRename(entry)}
            onDelete={() => handleDelete(entry)}
          />
        )
      )}
    </div>
  );
}

function ProjectFileTreeRow({
  entry,
  depth,
  projectId,
  selectedPath,
  onSelectFile,
  onFileRenamed,
  onFileDeleted,
  onNewFile,
  onNewFolder,
  onRename,
  onDelete,
}: {
  entry: ProjectFileEntry;
  depth: number;
  projectId: string;
  selectedPath: string | undefined;
  onSelectFile: (path: string) => void;
  onFileRenamed: (oldPath: string, newPath: string) => void;
  onFileDeleted: (path: string) => void;
  onNewFile?: () => void;
  onNewFolder?: () => void;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [dirExpanded, setDirExpanded] = useState(false);

  if (entry.type === "dir") {
    return (
      <div>
        <div
          className="group flex items-center justify-between rounded-md px-2 py-1 hover:bg-accent hover:text-accent-foreground"
          style={{ paddingLeft: `${depth * 0.9 + 0.5}rem` }}
        >
          <button
            type="button"
            onClick={() => setDirExpanded((v) => !v)}
            className="flex flex-1 items-center gap-1.5 text-left text-sm text-muted-foreground"
          >
            {dirExpanded ? (
              <ChevronDown className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 shrink-0" />
            )}
            <Folder className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{entry.name}</span>
          </button>
          <FileRowMenu entry={entry} onNewFile={onNewFile} onNewFolder={onNewFolder} onRename={onRename} onDelete={onDelete} />
        </div>
        {dirExpanded && (
          <ProjectFileTreeDir
            projectId={projectId}
            dirPath={entry.path}
            depth={depth}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
            onFileRenamed={onFileRenamed}
            onFileDeleted={onFileDeleted}
          />
        )}
      </div>
    );
  }

  const isMd = /\.md$/i.test(entry.name);
  return (
    <div
      className={cn(
        "group flex items-center justify-between rounded-md px-2 py-1",
        entry.path === selectedPath
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      )}
      style={{ paddingLeft: `${depth * 0.9 + 0.5}rem` }}
    >
      <button
        type="button"
        onClick={() => onSelectFile(entry.path)}
        className="flex flex-1 items-center gap-1.5 text-left text-sm"
      >
        {isMd ? <FileText className="h-3.5 w-3.5 shrink-0" /> : <File className="h-3.5 w-3.5 shrink-0" />}
        <span className="truncate">{entry.name}</span>
      </button>
      <FileRowMenu entry={entry} onRename={onRename} onDelete={onDelete} />
    </div>
  );
}

export function ProjectFileBrowser({ projectId }: { projectId: string }) {
  const [selectedPath, setSelectedPath] = useState<string | undefined>();
  const { data: doc, isLoading: docLoading, isError: docError, error: docErrorObj } = useProjectFileContent(
    projectId,
    selectedPath
  );
  const writeFile = useWriteProjectFile(projectId);
  const createFile = useCreateProjectFile(projectId);
  const createDir = useCreateProjectDirectory(projectId);

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const isMd = selectedPath ? /\.md$/i.test(selectedPath) : false;

  function handleSelectFile(path: string) {
    setSelectedPath(path);
    setIsEditing(false);
  }

  function handleFileRenamed(oldPath: string, newPath: string) {
    setSelectedPath((current) => (current === oldPath ? newPath : current));
  }

  function handleFileDeleted(path: string) {
    setSelectedPath((current) => (current === path ? undefined : current));
  }

  function handleStartEdit() {
    setDraft(doc?.content ?? "");
    setIsEditing(true);
  }

  function handleSave() {
    if (!selectedPath) return;
    writeFile.mutate({ path: selectedPath, content: draft }, { onSuccess: () => setIsEditing(false) });
  }

  function handleNewFileAtRoot() {
    const name = window.prompt("New file name (relative to the working directory):");
    if (!name) return;
    createFile.mutate(name, { onSuccess: () => setSelectedPath(name) });
  }

  function handleNewFolderAtRoot() {
    const name = window.prompt("New folder name (relative to the working directory):");
    if (!name) return;
    createDir.mutate(name);
  }

  return (
    <div className="flex h-[32rem] gap-3">
      <aside className="flex w-64 shrink-0 flex-col overflow-y-auto rounded-md border border-border p-2">
        <div className="mb-1 flex items-center justify-end gap-1 border-b border-border pb-1">
          <Button variant="ghost" size="icon" className="h-6 w-6" title="New file" aria-label="New file at root" onClick={handleNewFileAtRoot}>
            <FilePlus className="h-3.5 w-3.5" />
          </Button>
          <Button variant="ghost" size="icon" className="h-6 w-6" title="New folder" aria-label="New folder at root" onClick={handleNewFolderAtRoot}>
            <FolderPlus className="h-3.5 w-3.5" />
          </Button>
        </div>
        <ProjectFileTreeDir
          projectId={projectId}
          dirPath=""
          depth={0}
          selectedPath={selectedPath}
          onSelectFile={handleSelectFile}
          onFileRenamed={handleFileRenamed}
          onFileDeleted={handleFileDeleted}
        />
      </aside>

      <div className="flex flex-1 flex-col overflow-hidden rounded-md border border-border">
        <div className="flex items-center justify-between border-b border-border px-3 py-1.5">
          <span className="truncate text-sm font-medium text-muted-foreground">
            {selectedPath ?? "Select a file"}
          </span>
          {selectedPath && doc && (
            !isEditing ? (
              <Button variant="outline" size="sm" onClick={handleStartEdit}>
                <Pencil className="mr-2 h-3.5 w-3.5" />
                Edit
              </Button>
            ) : (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => setIsEditing(false)} disabled={writeFile.isPending}>
                  <X className="mr-2 h-3.5 w-3.5" />
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} disabled={writeFile.isPending}>
                  {writeFile.isPending ? (
                    <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-3.5 w-3.5" />
                  )}
                  Save
                </Button>
              </div>
            )
          )}
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {!selectedPath && <p className="text-sm italic text-muted-foreground">Select a file to view it.</p>}
          {selectedPath && docLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading file…
            </div>
          )}
          {selectedPath && docError && (
            <p className="text-sm text-destructive">
              {(docErrorObj as { body?: { detail?: string } })?.body?.detail ?? "Failed to load file."}
            </p>
          )}
          {writeFile.isError && (
            <p className="mb-3 text-sm text-destructive">Failed to save: {(writeFile.error as Error)?.message}</p>
          )}
          {doc && isEditing && (
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="h-full min-h-[24rem] resize-none font-mono text-sm"
            />
          )}
          {doc && !isEditing && isMd && <Markdown content={doc.content} className="text-sm" />}
          {doc && !isEditing && !isMd && (
            <pre className="whitespace-pre-wrap break-all font-mono text-sm">{doc.content}</pre>
          )}
        </div>
      </div>
    </div>
  );
}
