import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardPaste,
  Copy,
  Download,
  Eye,
  EyeOff,
  File,
  FileArchive,
  FileCode2,
  FileImage,
  FilePlus,
  FileText,
  FileVideo,
  Folder,
  FolderOpen,
  FolderPlus,
  FolderInput,
  FolderUp,
  LayoutGrid,
  Link2,
  List,
  Loader2,
  Pencil,
  RefreshCw,
  Scissors,
  Search,
  SquareCheck,
  SquareX,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useClickOutside } from "@/hooks/useClickOutside";
import {
  fileKind,
  formatSize,
  isTextLike,
  parentPath,
  pathSegments,
  type ExplorerEntry,
} from "@/hooks/useFileExplorer";
import { useFileExplorerViewModel, type ExplorerSortKey, type FileExplorerViewModel } from "@/hooks/useFileExplorerViewModel";
import { ExplorerDialogs } from "./ExplorerDialogs";
import { ExplorerTree, type QuickAccessItem } from "./ExplorerTree";
import { filesFromDataTransfer, filesFromInput, isExternalFileDrag } from "./droppedFiles";

/**
 * Workspace Explorer -- a Windows-Explorer-style manager for the HOST's
 * files (2026-09-23, Marcelo: "um icone igual ao explorer para manipulação
 * de pastas e arquivos... enviar e baixar... manipular, pesquisar...
 * envio de vários arquivos selecionados, pastas inteiras... renomear").
 * Pure view over useFileExplorerViewModel; the backend is admin-only
 * (api/routes/file_explorer.py) and audits every change and download.
 */

const INTERNAL_DRAG_TYPE = "application/x-forgehub-explorer-paths";
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"]);
const isImage = (name: string) => IMAGE_EXTENSIONS.has(name.toLowerCase().split(".").pop() ?? "");

export function FileExplorerPane({
  initialPath,
  quickAccess,
  active,
  onPathChange,
}: {
  initialPath: string;
  quickAccess: QuickAccessItem[];
  active: boolean;
  onPathChange?: (path: string) => void;
}) {
  const { t, i18n } = useTranslation("explorer");
  const vm = useFileExplorerViewModel(initialPath, onPathChange);
  const listRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [menu, setMenu] = useState<{ x: number; y: number; entry: ExplorerEntry | null } | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [editingAddress, setEditingAddress] = useState(false);

  const dateFormatter = useMemo(
    () => new Intl.DateTimeFormat(i18n.language, { dateStyle: "short", timeStyle: "short" }),
    [i18n.language]
  );

  useEffect(() => {
    if (active) listRef.current?.focus({ preventScroll: true });
  }, [active]);

  const hasSelection = vm.selectedEntries.length > 0;
  const single = vm.selectedEntries.length === 1 ? vm.selectedEntries[0] : null;
  const busy = vm.operation.status === "working";
  const openEntry = (entry: ExplorerEntry) => void vm.open(entry, isTextLike, isImage);
  const askDelete = (entries = vm.selectedEntries) => entries.length && vm.setDialog({ kind: "delete", entries });
  const askRename = (entry = single) => entry && vm.setDialog({ kind: "rename", entry });

  // ---- keyboard ------------------------------------------------------------

  function onListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (vm.dialog) return;
    const ctrl = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    const handled = () => {
      event.preventDefault();
      event.stopPropagation();
    };
    if (ctrl && key === "a") return handled(), vm.selectAll();
    if (ctrl && key === "c") return handled(), vm.copySelection();
    if (ctrl && key === "x") return handled(), vm.cutSelection();
    if (ctrl && key === "v") return handled(), void vm.paste();
    if (ctrl && key === "f") return handled(), searchRef.current?.focus();
    if (event.key === "Delete") return handled(), askDelete();
    if (event.key === "F2") return handled(), askRename();
    if (event.key === "F5") return handled(), vm.refresh();
    if (event.key === "Enter" && single) return handled(), openEntry(single);
    if (event.key === "Backspace" || (event.altKey && event.key === "ArrowUp")) return handled(), vm.goUp();
    if (event.altKey && event.key === "ArrowLeft") return handled(), vm.goBack();
    if (event.altKey && event.key === "ArrowRight") return handled(), vm.goForward();
    if (event.key === "ArrowDown") return handled(), vm.moveSelection(1, event.shiftKey);
    if (event.key === "ArrowUp") return handled(), vm.moveSelection(-1, event.shiftKey);
    if (event.key === "Escape") return handled(), vm.clearSelection();
  }

  // ---- drag & drop ---------------------------------------------------------

  function onDragStartEntry(event: DragEvent, entry: ExplorerEntry) {
    if (!vm.selected.has(entry.path)) vm.select(entry);
    const paths = vm.selected.has(entry.path) ? vm.selectedEntries.map((e) => e.path) : [entry.path];
    event.dataTransfer.setData(INTERNAL_DRAG_TYPE, JSON.stringify(paths));
    event.dataTransfer.effectAllowed = "copyMove";
  }

  function onDragOverTarget(event: DragEvent, path: string) {
    const internal = Array.from(event.dataTransfer.types).includes(INTERNAL_DRAG_TYPE);
    if (!internal && !isExternalFileDrag(event.dataTransfer)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = internal && !(event.ctrlKey || event.metaKey) ? "move" : "copy";
    setDropTarget(path);
  }

  async function onDropTarget(event: DragEvent, path: string) {
    event.preventDefault();
    event.stopPropagation();
    setDropTarget(null);
    const internal = event.dataTransfer.getData(INTERNAL_DRAG_TYPE);
    if (internal) {
      await vm.dropEntries(JSON.parse(internal) as string[], path, event.ctrlKey || event.metaKey);
      return;
    }
    if (isExternalFileDrag(event.dataTransfer)) {
      const uploads = await filesFromDataTransfer(event.dataTransfer);
      await vm.requestUpload(uploads, path);
    }
  }

  const drop = { onDragOver: onDragOverTarget, onDrop: (e: DragEvent, p: string) => void onDropTarget(e, p), dropTarget };

  // ---- context menu --------------------------------------------------------

  function openMenu(event: MouseEvent, entry: ExplorerEntry | null) {
    event.preventDefault();
    event.stopPropagation();
    if (entry) vm.selectForContext(entry);
    else vm.clearSelection();
    setMenu({ x: event.clientX, y: event.clientY, entry });
  }

  function onRowClick(event: MouseEvent, entry: ExplorerEntry) {
    event.stopPropagation();
    vm.select(entry, { ctrl: event.ctrlKey || event.metaKey, shift: event.shiftKey });
  }

  const totalSelectedSize = vm.selectedEntries.reduce((sum, e) => sum + (e.size ?? 0), 0);

  return (
    <div
      className="relative flex h-full min-h-0 flex-col bg-background text-sm"
      onKeyDown={(event) => {
        // The list handles its own keys; this catches the same shortcuts when
        // focus sits on the toolbar or tree, so Ctrl+A/C/X/V don't depend on
        // having clicked the list first. Text fields keep their own meaning.
        const target = event.target as HTMLElement;
        if (listRef.current?.contains(target)) return;
        if (target.closest("input, textarea, [contenteditable=true]")) return;
        if (target.closest('[role="dialog"]')) return;
        // Only the shortcuts -- Enter/arrows on a focused toolbar button
        // must keep activating/moving within the toolbar.
        const shortcut = event.ctrlKey || event.metaKey || ["Delete", "F2", "F5"].includes(event.key);
        if (shortcut) onListKeyDown(event as unknown as KeyboardEvent<HTMLDivElement>);
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => {
          const uploads = filesFromInput(e.target.files);
          e.target.value = "";
          void vm.requestUpload(uploads);
        }}
      />
      <input
        ref={folderInputRef}
        type="file"
        multiple
        className="hidden"
        // Non-standard but supported by every current browser: pick a folder.
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        onChange={(e) => {
          const uploads = filesFromInput(e.target.files);
          e.target.value = "";
          void vm.requestUpload(uploads);
        }}
      />

      {/* Ribbon */}
      <div className="flex flex-wrap items-center gap-1 border-b border-border px-2 py-1.5">
        <NewMenu vm={vm} />
        <RibbonButton icon={<Upload className="h-4 w-4" />} label={t("actions.uploadFiles")} onClick={() => fileInputRef.current?.click()} />
        <RibbonButton icon={<FolderUp className="h-4 w-4" />} label={t("actions.uploadFolder")} onClick={() => folderInputRef.current?.click()} />
        <Divider />
        <RibbonButton icon={<Scissors className="h-4 w-4" />} label={t("actions.cut")} shortcut="Ctrl+X" disabled={!hasSelection} onClick={vm.cutSelection} />
        <RibbonButton icon={<Copy className="h-4 w-4" />} label={t("actions.copy")} shortcut="Ctrl+C" disabled={!hasSelection} onClick={vm.copySelection} />
        <RibbonButton icon={<ClipboardPaste className="h-4 w-4" />} label={t("actions.paste")} shortcut="Ctrl+V" disabled={!vm.clipboard || busy} onClick={() => void vm.paste()} />
        <RibbonButton icon={<FolderInput className="h-4 w-4" />} label={t("actions.moveTo")} disabled={!hasSelection || busy} onClick={() => vm.setDialog({ kind: "transferTo", entries: vm.selectedEntries, mode: "move" })} />
        <RibbonButton icon={<Copy className="h-4 w-4" />} label={t("actions.copyTo")} disabled={!hasSelection || busy} onClick={() => vm.setDialog({ kind: "transferTo", entries: vm.selectedEntries, mode: "copy" })} />
        <RibbonButton icon={<Pencil className="h-4 w-4" />} label={t("actions.rename")} shortcut="F2" disabled={!single} onClick={() => askRename()} />
        <RibbonButton icon={<Trash2 className="h-4 w-4 text-destructive" />} label={t("actions.delete")} shortcut="Del" disabled={!hasSelection} onClick={() => askDelete()} />
        <Divider />
        <RibbonButton
          icon={busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          label={vm.selectedEntries.length > 1 ? t("actions.downloadZip", { count: vm.selectedEntries.length }) : t("actions.download")}
          disabled={!hasSelection || busy}
          onClick={() => void vm.download()}
        />
        <Divider />
        <RibbonButton icon={<SquareCheck className="h-4 w-4" />} label={t("actions.selectAll")} shortcut="Ctrl+A" disabled={vm.entries.length === 0 || vm.allSelected} onClick={vm.selectAll} />
        <RibbonButton icon={<SquareX className="h-4 w-4" />} label={t("actions.selectNone")} shortcut="Esc" disabled={!hasSelection} onClick={vm.clearSelection} />
        <div className="flex-1" />
        <RibbonButton
          icon={vm.showHidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          label={vm.showHidden ? t("actions.hideHidden") : t("actions.showHidden")}
          active={vm.showHidden}
          onClick={() => vm.setShowHidden(!vm.showHidden)}
        />
        <RibbonButton icon={<List className="h-4 w-4" />} label={t("view.details")} active={vm.viewMode === "details"} onClick={() => vm.setViewMode("details")} />
        <RibbonButton icon={<LayoutGrid className="h-4 w-4" />} label={t("view.icons")} active={vm.viewMode === "icons"} onClick={() => vm.setViewMode("icons")} />
      </div>

      {/* Address bar */}
      <div className="flex items-center gap-1 border-b border-border px-2 py-1.5">
        <NavButton label={t("nav.back")} disabled={!vm.canGoBack} onClick={vm.goBack} icon={<ArrowLeft className="h-4 w-4" />} />
        <NavButton label={t("nav.forward")} disabled={!vm.canGoForward} onClick={vm.goForward} icon={<ArrowRight className="h-4 w-4" />} />
        <NavButton label={t("nav.up")} disabled={!vm.canGoUp} onClick={vm.goUp} icon={<ArrowUp className="h-4 w-4" />} />
        <NavButton label={t("nav.refresh")} onClick={vm.refresh} icon={<RefreshCw className={cn("h-4 w-4", vm.status === "loading" && "animate-spin")} />} />
        <AddressBar
          path={vm.path}
          editing={editingAddress}
          setEditing={setEditingAddress}
          onNavigate={vm.navigate}
          drop={drop}
        />
        <form
          className="relative w-56 shrink-0"
          onSubmit={(e) => {
            e.preventDefault();
            vm.submitSearch();
          }}
        >
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            value={vm.searchInput}
            onChange={(e) => vm.setSearchInput(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && vm.clearSearch()}
            placeholder={t("search.placeholder", { name: pathSegments(vm.path).pop()?.name })}
            title={t("search.help")}
            aria-label={t("search.label")}
            className="h-8 w-full rounded-md border border-input bg-background pl-7 pr-7 text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          {vm.searchInput && (
            <button
              type="button"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
              aria-label={t("search.clear")}
              onClick={vm.clearSearch}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </form>
      </div>

      {/* Body */}
      <div className="flex min-h-0 flex-1">
        <div className="hidden w-60 shrink-0 border-r border-border md:flex md:flex-col">
          <ExplorerTree currentPath={vm.path} quickAccess={quickAccess} showHidden={vm.showHidden} onNavigate={vm.navigate} drop={drop} />
        </div>

        <div
          ref={listRef}
          tabIndex={0}
          role="grid"
          aria-label={t("list.label")}
          aria-multiselectable="true"
          className={cn(
            "relative min-h-0 min-w-0 flex-1 overflow-auto outline-none",
            dropTarget === vm.path && "bg-primary/5 ring-2 ring-inset ring-primary/60"
          )}
          onKeyDown={onListKeyDown}
          onClick={() => vm.clearSelection()}
          onContextMenu={(e) => openMenu(e, null)}
          onDragOver={(e) => onDragOverTarget(e, vm.path)}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node)) setDropTarget(null);
          }}
          onDrop={(e) => void onDropTarget(e, vm.path)}
        >
          {vm.searching && (
            <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-muted/60 px-3 py-1 text-xs text-muted-foreground backdrop-blur">
              <Search className="h-3.5 w-3.5" />
              {t("search.resultsIn", { query: vm.searchQuery, path: vm.path })}
              {vm.searchTruncated && <span className="text-amber-500">· {t("search.truncated")}</span>}
            </div>
          )}
          {vm.status === "loading" && vm.entries.length === 0 ? (
            <CenterState icon={<Loader2 className="h-6 w-6 animate-spin" />} text={vm.searching ? t("search.searching") : t("list.loading")} />
          ) : vm.status === "error" ? (
            <CenterState
              icon={<AlertCircle className="h-6 w-6 text-destructive" />}
              text={vm.loadError ?? t("list.error")}
              action={
                <Button variant="outline" size="sm" onClick={vm.canGoBack ? vm.goBack : vm.goUp}>
                  {t("nav.back")}
                </Button>
              }
            />
          ) : vm.entries.length === 0 ? (
            <CenterState
              icon={vm.searching ? <Search className="h-6 w-6" /> : <FolderOpen className="h-6 w-6" />}
              text={vm.searching ? t("search.noResults") : t("list.empty")}
              hint={vm.searching ? undefined : t("list.dropHint")}
            />
          ) : vm.viewMode === "details" ? (
            <DetailsView vm={vm} dateFormatter={dateFormatter} onRowClick={onRowClick} onOpen={openEntry} onMenu={openMenu} onDragStart={onDragStartEntry} drop={drop} />
          ) : (
            <IconsView vm={vm} onRowClick={onRowClick} onOpen={openEntry} onMenu={openMenu} onDragStart={onDragStartEntry} drop={drop} />
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center gap-3 border-t border-border px-3 py-1 text-xs text-muted-foreground">
        <span>{t("status.items", { count: vm.entries.length })}</span>
        {hasSelection && (
          <span>
            {t("status.selected", { count: vm.selectedEntries.length })}
            {totalSelectedSize > 0 && ` · ${formatSize(totalSelectedSize)}`}
          </span>
        )}
        {vm.clipboard && (
          <span className="flex items-center gap-1">
            {vm.clipboard.mode === "cut" ? <Scissors className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
            {t(vm.clipboard.mode === "cut" ? "status.clipboardCut" : "status.clipboardCopy", { count: vm.clipboard.entries.length })}
          </span>
        )}
        <div className="flex-1" />
        {busy && (
          <span className="flex items-center gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t("status.working")}
          </span>
        )}
        {vm.operation.status === "error" && !vm.dialog && (
          <span className="flex min-w-0 items-center gap-1 text-destructive">
            <AlertCircle className="h-3 w-3 shrink-0" />
            <span className="truncate" title={vm.operation.message}>{vm.operation.message}</span>
            <button type="button" aria-label={t("actions.close")} onClick={vm.dismissError}>
              <X className="h-3 w-3" />
            </button>
          </span>
        )}
      </div>

      <UploadPanel vm={vm} />
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          items={
            menu.entry
              ? [
                  { label: menu.entry.type === "dir" ? t("actions.open") : isTextLike(menu.entry.name) ? t("actions.edit") : t("actions.open"), icon: <FolderOpen className="h-3.5 w-3.5" />, onClick: () => openEntry(menu.entry!), hidden: vm.selectedEntries.length > 1 },
                  { label: t("actions.openLocation"), icon: <Folder className="h-3.5 w-3.5" />, onClick: () => vm.navigate(parentPath(menu.entry!.path) ?? "/"), hidden: !vm.searching },
                  { label: vm.selectedEntries.length > 1 ? t("actions.downloadZip", { count: vm.selectedEntries.length }) : t("actions.download"), icon: <Download className="h-3.5 w-3.5" />, onClick: () => void vm.download() },
                  "divider",
                  { label: t("actions.cut"), icon: <Scissors className="h-3.5 w-3.5" />, shortcut: "Ctrl+X", onClick: vm.cutSelection },
                  { label: t("actions.copy"), icon: <Copy className="h-3.5 w-3.5" />, shortcut: "Ctrl+C", onClick: vm.copySelection },
                  { label: t("actions.moveTo"), icon: <FolderInput className="h-3.5 w-3.5" />, onClick: () => vm.setDialog({ kind: "transferTo", entries: vm.selectedEntries, mode: "move" }) },
                  { label: t("actions.copyTo"), icon: <Copy className="h-3.5 w-3.5" />, onClick: () => vm.setDialog({ kind: "transferTo", entries: vm.selectedEntries, mode: "copy" }) },
                  { label: t("actions.pasteInto"), icon: <ClipboardPaste className="h-3.5 w-3.5" />, onClick: () => void vm.paste(menu.entry!.path), hidden: menu.entry.type !== "dir" || !vm.clipboard || vm.selectedEntries.length > 1 },
                  { label: t("actions.copyPath"), icon: <Link2 className="h-3.5 w-3.5" />, onClick: () => void navigator.clipboard?.writeText(vm.selectedEntries.map((e) => e.path).join("\n")) },
                  "divider",
                  { label: t("actions.rename"), icon: <Pencil className="h-3.5 w-3.5" />, shortcut: "F2", onClick: () => askRename(menu.entry!), hidden: vm.selectedEntries.length > 1 },
                  { label: t("actions.delete"), icon: <Trash2 className="h-3.5 w-3.5 text-destructive" />, shortcut: "Del", onClick: () => askDelete(), destructive: true },
                ]
              : [
                  { label: t("actions.newFolder"), icon: <FolderPlus className="h-3.5 w-3.5" />, onClick: () => vm.setDialog({ kind: "newFolder" }) },
                  { label: t("actions.newFile"), icon: <FilePlus className="h-3.5 w-3.5" />, onClick: () => vm.setDialog({ kind: "newFile" }) },
                  "divider",
                  { label: t("actions.uploadFiles"), icon: <Upload className="h-3.5 w-3.5" />, onClick: () => fileInputRef.current?.click() },
                  { label: t("actions.uploadFolder"), icon: <FolderUp className="h-3.5 w-3.5" />, onClick: () => folderInputRef.current?.click() },
                  { label: t("actions.paste"), icon: <ClipboardPaste className="h-3.5 w-3.5" />, shortcut: "Ctrl+V", onClick: () => void vm.paste(), hidden: !vm.clipboard },
                  "divider",
                  { label: t("actions.selectAll"), icon: <List className="h-3.5 w-3.5" />, shortcut: "Ctrl+A", onClick: vm.selectAll },
                  { label: t("actions.copyPath"), icon: <Link2 className="h-3.5 w-3.5" />, onClick: () => void navigator.clipboard?.writeText(vm.path) },
                  { label: t("nav.refresh"), icon: <RefreshCw className="h-3.5 w-3.5" />, shortcut: "F5", onClick: vm.refresh },
                ]
          }
        />
      )}
      <ExplorerDialogs vm={vm} quickAccess={quickAccess} />
    </div>
  );
}

// ---------------------------------------------------------------------------

function EntryIcon({ entry, large }: { entry: ExplorerEntry; large?: boolean }) {
  const cls = large ? "h-10 w-10" : "h-4 w-4";
  const kind = fileKind(entry);
  if (kind === "folder") return <Folder className={cn(cls, "shrink-0 fill-amber-400/30 text-amber-400")} />;
  if (kind === "image") return <FileImage className={cn(cls, "shrink-0 text-violet-500")} />;
  if (kind === "archive") return <FileArchive className={cn(cls, "shrink-0 text-orange-500")} />;
  if (kind === "media") return <FileVideo className={cn(cls, "shrink-0 text-pink-500")} />;
  if (kind === "code") return <FileCode2 className={cn(cls, "shrink-0 text-sky-500")} />;
  if (kind === "text" || kind === "document") return <FileText className={cn(cls, "shrink-0 text-slate-400")} />;
  return <File className={cn(cls, "shrink-0 text-muted-foreground")} />;
}

interface ItemViewProps {
  vm: FileExplorerViewModel;
  onRowClick: (event: MouseEvent, entry: ExplorerEntry) => void;
  onOpen: (entry: ExplorerEntry) => void;
  onMenu: (event: MouseEvent, entry: ExplorerEntry) => void;
  onDragStart: (event: DragEvent, entry: ExplorerEntry) => void;
  drop: { onDragOver: (e: DragEvent, p: string) => void; onDrop: (e: DragEvent, p: string) => void; dropTarget: string | null };
}

function itemHandlers(props: ItemViewProps, entry: ExplorerEntry) {
  return {
    draggable: true,
    onClick: (e: MouseEvent) => props.onRowClick(e, entry),
    onDoubleClick: () => props.onOpen(entry),
    onContextMenu: (e: MouseEvent) => props.onMenu(e, entry),
    onDragStart: (e: DragEvent) => props.onDragStart(e, entry),
    ...(entry.type === "dir"
      ? {
          onDragOver: (e: DragEvent) => props.drop.onDragOver(e, entry.path),
          onDrop: (e: DragEvent) => props.drop.onDrop(e, entry.path),
        }
      : {}),
  };
}

function DetailsView(props: ItemViewProps & { dateFormatter: Intl.DateTimeFormat }) {
  const { t } = useTranslation("explorer");
  const { vm, dateFormatter } = props;
  const cut = new Set(vm.clipboard?.mode === "cut" ? vm.clipboard.entries.map((e) => e.path) : []);
  const columns: { key: ExplorerSortKey; label: string; className: string }[] = [
    { key: "name", label: t("columns.name"), className: "" },
    { key: "modified", label: t("columns.modified"), className: "w-40" },
    { key: "type", label: t("columns.type"), className: "w-28" },
    { key: "size", label: t("columns.size"), className: "w-24 text-right" },
  ];
  return (
    <table className="w-full table-fixed border-collapse text-sm">
      <thead className="sticky top-0 z-[5] bg-card">
        <tr className="border-b border-border text-left text-xs text-muted-foreground">
          <th className="w-9 py-1.5 pl-3">
            <SelectBox
              checked={vm.allSelected}
              indeterminate={vm.selected.size > 0 && !vm.allSelected}
              label={t("actions.selectAll")}
              onToggle={vm.toggleAll}
            />
          </th>
          {columns.map((col) => (
            <th key={col.key} className={cn("px-3 py-1.5 font-medium", col.className)}>
              <button
                type="button"
                className={cn("inline-flex items-center gap-1 hover:text-foreground", col.key === "size" && "flex-row-reverse")}
                onClick={(e) => {
                  e.stopPropagation();
                  vm.setSort({ key: col.key, asc: vm.sort.key === col.key ? !vm.sort.asc : true });
                }}
              >
                {col.label}
                {vm.sort.key === col.key && (vm.sort.asc ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
              </button>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {vm.entries.map((entry) => {
          const selected = vm.selected.has(entry.path);
          return (
            <tr
              key={entry.path}
              role="row"
              aria-selected={selected}
              className={cn(
                "cursor-default select-none border-b border-border/40",
                selected ? "bg-primary/15" : "hover:bg-accent/50",
                cut.has(entry.path) && "opacity-50",
                props.drop.dropTarget === entry.path && "outline outline-1 outline-primary"
              )}
              {...itemHandlers(props, entry)}
            >
              <td className="py-1 pl-3">
                <SelectBox checked={selected} label={entry.name} onToggle={() => vm.toggle(entry)} />
              </td>
              <td className="px-3 py-1">
                <div className="flex min-w-0 items-center gap-2">
                  <EntryIcon entry={entry} />
                  <div className="min-w-0">
                    <div className="truncate" title={entry.path}>
                      {entry.name}
                      {entry.is_symlink && <Link2 className="ml-1 inline h-3 w-3 text-muted-foreground" />}
                    </div>
                    {vm.searching && (
                      <div className="truncate font-mono text-[10px] text-muted-foreground">{parentPath(entry.path)}</div>
                    )}
                  </div>
                </div>
              </td>
              <td className="truncate px-3 py-1 text-xs text-muted-foreground">
                {entry.modified ? dateFormatter.format(new Date(entry.modified * 1000)) : ""}
              </td>
              <td className="truncate px-3 py-1 text-xs text-muted-foreground">{kindLabel(entry, t)}</td>
              <td className="px-3 py-1 text-right text-xs tabular-nums text-muted-foreground">{formatSize(entry.size)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/** Windows' "item check boxes": toggles one item without clearing the rest
 * of the selection -- the discoverable way to pick several items (or all,
 * from the header box) without knowing Ctrl/Shift+click. */
function SelectBox({
  checked,
  indeterminate = false,
  label,
  onToggle,
}: {
  checked: boolean;
  indeterminate?: boolean;
  label: string;
  onToggle: () => void;
}) {
  return (
    <input
      type="checkbox"
      checked={checked}
      ref={(el) => {
        if (el) el.indeterminate = indeterminate;
      }}
      aria-label={label}
      aria-checked={indeterminate ? "mixed" : checked}
      className="h-4 w-4 cursor-pointer accent-primary align-middle"
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onChange={onToggle}
    />
  );
}

function kindLabel(entry: ExplorerEntry, t: (key: string, opts?: Record<string, unknown>) => string) {
  if (entry.type === "dir") return t("kinds.folder");
  const idx = entry.name.lastIndexOf(".");
  return idx > 0 ? t("kinds.fileExt", { ext: entry.name.slice(idx + 1).toUpperCase() }) : t("kinds.file");
}

function IconsView(props: ItemViewProps) {
  const { vm } = props;
  const cut = new Set(vm.clipboard?.mode === "cut" ? vm.clipboard.entries.map((e) => e.path) : []);
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(104px,1fr))] gap-1 p-2">
      {vm.entries.map((entry) => {
        const selected = vm.selected.has(entry.path);
        return (
          <div
            key={entry.path}
            role="gridcell"
            aria-selected={selected}
            title={entry.path}
            className={cn(
              "group relative flex cursor-default select-none flex-col items-center gap-1 rounded-md p-2 text-center",
              selected ? "bg-primary/15 ring-1 ring-primary/40" : "hover:bg-accent/50",
              cut.has(entry.path) && "opacity-50",
              props.drop.dropTarget === entry.path && "ring-1 ring-primary"
            )}
            {...itemHandlers(props, entry)}
          >
            <div className={cn("absolute left-1.5 top-1.5", !selected && "opacity-0 group-hover:opacity-100 focus-within:opacity-100")}>
              <SelectBox checked={selected} label={entry.name} onToggle={() => vm.toggle(entry)} />
            </div>
            <EntryIcon entry={entry} large />
            <span className="line-clamp-2 w-full break-all text-xs">{entry.name}</span>
          </div>
        );
      })}
    </div>
  );
}

function AddressBar({
  path,
  editing,
  setEditing,
  onNavigate,
  drop,
}: {
  path: string;
  editing: boolean;
  setEditing: (v: boolean) => void;
  onNavigate: (path: string) => void;
  drop: ItemViewProps["drop"];
}) {
  const { t } = useTranslation("explorer");
  const [draft, setDraft] = useState(path);
  useEffect(() => setDraft(path), [path]);

  if (editing) {
    return (
      <form
        className="min-w-0 flex-1"
        onSubmit={(e) => {
          e.preventDefault();
          setEditing(false);
          if (draft.trim().startsWith("/")) onNavigate(draft.trim());
        }}
      >
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => setEditing(false)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setDraft(path);
              setEditing(false);
            }
          }}
          aria-label={t("nav.address")}
          spellCheck={false}
          className="h-8 w-full rounded-md border border-input bg-background px-2 font-mono text-xs outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </form>
    );
  }

  const segments = pathSegments(path);
  return (
    <div
      className="flex h-8 min-w-0 flex-1 cursor-text items-center overflow-hidden rounded-md border border-input bg-background px-1"
      onClick={() => setEditing(true)}
      title={t("nav.editAddress")}
    >
      <HardDriveMini />
      <div
        className="flex min-w-0 items-center overflow-x-auto"
        // Long paths: show the end (current folder), like Explorer does.
        ref={(el) => {
          if (el) el.scrollLeft = el.scrollWidth;
        }}
      >
        {segments.map((segment, index) => (
          <span key={segment.path} className="flex shrink-0 items-center">
            {index > 1 && <ChevronRight className="h-3 w-3 text-muted-foreground" />}
            <button
              type="button"
              className={cn(
                "rounded px-1.5 py-0.5 text-xs hover:bg-accent",
                index === segments.length - 1 && "font-medium",
                drop.dropTarget === segment.path && "ring-1 ring-primary"
              )}
              onClick={(e) => {
                e.stopPropagation();
                onNavigate(segment.path);
              }}
              onDragOver={(e) => drop.onDragOver(e, segment.path)}
              onDrop={(e) => drop.onDrop(e, segment.path)}
            >
              {segment.name}
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}

function HardDriveMini() {
  return <Folder className="mx-1 h-3.5 w-3.5 shrink-0 text-amber-400" />;
}

function NewMenu({ vm }: { vm: FileExplorerViewModel }) {
  const { t } = useTranslation("explorer");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useClickOutside(ref, () => setOpen(false), open);
  return (
    <div className="relative" ref={ref}>
      <Button variant="default" size="sm" className="h-8 gap-1" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <FolderPlus className="h-4 w-4" />
        {t("actions.new")}
        <ChevronDown className="h-3 w-3" />
      </Button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-44 overflow-hidden rounded-md border border-border bg-card py-1 shadow-md">
          <MenuItem icon={<FolderPlus className="h-3.5 w-3.5" />} label={t("actions.newFolder")} onClick={() => (setOpen(false), vm.setDialog({ kind: "newFolder" }))} />
          <MenuItem icon={<FilePlus className="h-3.5 w-3.5" />} label={t("actions.newFile")} onClick={() => (setOpen(false), vm.setDialog({ kind: "newFile" }))} />
        </div>
      )}
    </div>
  );
}

type ContextMenuItem =
  | "divider"
  | { label: string; icon: ReactNode; onClick: () => void; shortcut?: string; hidden?: boolean; destructive?: boolean };

function ContextMenu({ x, y, items, onClose }: { x: number; y: number; items: ContextMenuItem[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });
  useClickOutside(ref, onClose, true);
  useEffect(() => {
    // Keep the menu inside the viewport, like a native one.
    const el = ref.current;
    if (!el) return;
    const { innerWidth, innerHeight } = window;
    setPos({
      left: Math.min(x, innerWidth - el.offsetWidth - 8),
      top: Math.min(y, innerHeight - el.offsetHeight - 8),
    });
    const onKey = (e: globalThis.KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    window.addEventListener("blur", onClose);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("blur", onClose);
    };
  }, [x, y, onClose]);

  const visible = items.filter((item) => item === "divider" || !item.hidden);
  // Drop leading/trailing/double dividers left behind by hidden items.
  const cleaned = visible.filter(
    (item, i) => item !== "divider" || (i > 0 && i < visible.length - 1 && visible[i - 1] !== "divider")
  );
  return (
    <div
      ref={ref}
      role="menu"
      className="fixed z-50 w-56 overflow-hidden rounded-md border border-border bg-card py-1 shadow-lg"
      style={{ left: pos.left, top: pos.top }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {cleaned.map((item, i) =>
        item === "divider" ? (
          <div key={`d-${i}`} className="my-1 h-px bg-border" />
        ) : (
          <MenuItem
            key={item.label}
            icon={item.icon}
            label={item.label}
            shortcut={item.shortcut}
            destructive={item.destructive}
            onClick={() => {
              onClose();
              item.onClick();
            }}
          />
        )
      )}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  shortcut,
  destructive,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  shortcut?: string;
  destructive?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      className={cn(
        "flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground",
        destructive && "text-destructive"
      )}
      onClick={onClick}
    >
      {icon}
      <span className="flex-1 truncate">{label}</span>
      {shortcut && <span className="text-[10px] text-muted-foreground">{shortcut}</span>}
    </button>
  );
}

function RibbonButton({
  icon,
  label,
  shortcut,
  disabled,
  active,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  shortcut?: string;
  disabled?: boolean;
  active?: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant={active ? "secondary" : "ghost"}
      size="sm"
      className="h-8 gap-1.5 px-2"
      disabled={disabled}
      title={shortcut ? `${label} (${shortcut})` : label}
      aria-label={label}
      onClick={onClick}
    >
      {icon}
      <span className="hidden text-xs xl:inline">{label}</span>
    </Button>
  );
}

function NavButton({ icon, label, disabled, onClick }: { icon: ReactNode; label: string; disabled?: boolean; onClick: () => void }) {
  return (
    <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" disabled={disabled} title={label} aria-label={label} onClick={onClick}>
      {icon}
    </Button>
  );
}

function Divider() {
  return <div className="mx-1 h-5 w-px bg-border" />;
}

function CenterState({ icon, text, hint, action }: { icon: ReactNode; text: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-2 p-6 text-center text-muted-foreground">
      {icon}
      <p className="text-sm">{text}</p>
      {hint && <p className="text-xs">{hint}</p>}
      {action}
    </div>
  );
}

function UploadPanel({ vm }: { vm: FileExplorerViewModel }) {
  const { t } = useTranslation("explorer");
  const [collapsed, setCollapsed] = useState(false);
  if (vm.uploads.length === 0) return null;
  const active = vm.uploads.filter((u) => u.status === "uploading" || u.status === "queued");
  const done = vm.uploads.filter((u) => u.status === "done").length;
  const failed = vm.uploads.filter((u) => u.status === "error").length;
  const skipped = vm.uploads.filter((u) => u.status === "skipped").length;
  const loaded = vm.uploads.reduce((s, u) => s + (u.status === "done" ? u.total : u.loaded), 0);
  const total = vm.uploads.reduce((s, u) => s + u.total, 0) || 1;
  const percent = Math.round((loaded / total) * 100);

  return (
    <div className="absolute bottom-10 right-4 z-20 w-96 max-w-[calc(100%-2rem)] overflow-hidden rounded-lg border border-border bg-card shadow-xl">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        {active.length > 0 ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        ) : failed > 0 ? (
          <AlertCircle className="h-4 w-4 text-destructive" />
        ) : (
          <CheckCircle2 className="h-4 w-4 text-green-500" />
        )}
        <span className="flex-1 truncate text-xs font-medium">
          {active.length > 0
            ? t("upload.progress", { done, total: vm.uploads.length, percent })
            : t("upload.finished", { done, failed, skipped })}
        </span>
        <button type="button" className="rounded p-0.5 text-muted-foreground hover:text-foreground" onClick={() => setCollapsed((v) => !v)} aria-label={t("upload.toggle")}>
          {collapsed ? <ChevronDown className="h-3.5 w-3.5 rotate-180" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
        {active.length === 0 && (
          <button type="button" className="rounded p-0.5 text-muted-foreground hover:text-foreground" onClick={vm.clearFinishedUploads} aria-label={t("actions.close")}>
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      <div className="h-1 bg-muted">
        <div className="h-full bg-primary transition-all" style={{ width: `${percent}%` }} />
      </div>
      {!collapsed && (
        <ul className="max-h-56 overflow-auto py-1 text-xs">
          {vm.uploads.map((u) => (
            <li key={u.id} className="flex items-center gap-2 px-3 py-1" title={u.error ?? u.destination}>
              {u.status === "done" ? (
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-green-500" />
              ) : u.status === "error" ? (
                <AlertCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
              ) : u.status === "skipped" ? (
                <X className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              ) : u.status === "uploading" ? (
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
              ) : (
                <File className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              )}
              <span className="min-w-0 flex-1 truncate">{u.name}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {u.status === "uploading"
                  ? `${Math.round((u.loaded / (u.total || 1)) * 100)}%`
                  : u.status === "skipped"
                  ? t("upload.skipped")
                  : u.status === "error"
                  ? t("upload.failed")
                  : formatSize(u.total)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
