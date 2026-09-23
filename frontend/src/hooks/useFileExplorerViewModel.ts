import { useCallback, useMemo, useRef, useState } from "react";
import { ApiError, apiClient } from "@/lib/api";
import {
  baseName,
  copyName,
  downloadExplorerPath,
  downloadExplorerZip,
  joinPath,
  parentPath,
  saveBlob,
  uploadExplorerFile,
  useExplorerListing,
  useExplorerMutations,
  useExplorerSearch,
  useInvalidateExplorer,
  type ExplorerEntry,
} from "@/hooks/useFileExplorer";
import { topLevelNames, type PendingUpload } from "@/components/explorer/droppedFiles";

/**
 * ViewModel Hook for the Workspace Explorer (components/explorer/
 * FileExplorerPane.tsx), per the frontend standard's §21: the pane owns no
 * state of its own and renders this hook's return value.
 *
 * Two independent state machines, because they fail independently:
 * - `status` -- the folder being shown: loading -> ready | error.
 * - `operation` -- the last user action (paste, delete, download, ...):
 *   idle -> working -> idle | error. A failed paste must not blank the
 *   listing, and a folder that fails to load must not block a download
 *   from the previous one.
 * Uploads have their own per-file queue (`uploads`) since a folder upload
 * is many files, each with its own progress and outcome.
 */

export type ExplorerSortKey = "name" | "modified" | "size" | "type";
export type ExplorerViewMode = "details" | "icons";

export type ExplorerDialog =
  | { kind: "newFolder" }
  | { kind: "newFile" }
  | { kind: "rename"; entry: ExplorerEntry }
  | { kind: "delete"; entries: ExplorerEntry[] }
  | { kind: "uploadConflict"; uploads: PendingUpload[]; destination: string; conflicts: string[] }
  | { kind: "edit"; path: string }
  | { kind: "preview"; entry: ExplorerEntry; url: string };

export interface UploadItem {
  id: string;
  name: string;
  destination: string;
  loaded: number;
  total: number;
  status: "queued" | "uploading" | "done" | "skipped" | "error";
  error?: string;
}

export interface ExplorerClipboard {
  mode: "copy" | "cut";
  entries: ExplorerEntry[];
}

const UPLOAD_CONCURRENCY = 3;

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (error.status === 403) return "Admin access required";
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}

function extOf(entry: ExplorerEntry): string {
  if (entry.type === "dir") return "";
  const idx = entry.name.lastIndexOf(".");
  return idx > 0 ? entry.name.slice(idx + 1).toLowerCase() : "";
}

export function sortEntries(entries: ExplorerEntry[], key: ExplorerSortKey, asc: boolean): ExplorerEntry[] {
  const dir = asc ? 1 : -1;
  return [...entries].sort((a, b) => {
    // Folders first regardless of direction, like Explorer.
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    let cmp = 0;
    if (key === "modified") cmp = (a.modified ?? 0) - (b.modified ?? 0);
    else if (key === "size") cmp = (a.size ?? 0) - (b.size ?? 0);
    else if (key === "type") cmp = extOf(a).localeCompare(extOf(b));
    if (cmp === 0) cmp = a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" });
    return cmp * dir;
  });
}

export function useFileExplorerViewModel(initialPath: string, onPathChange?: (path: string) => void) {
  const [history, setHistory] = useState<{ stack: string[]; index: number }>({ stack: [initialPath], index: 0 });
  const path = history.stack[history.index];
  const [viewMode, setViewMode] = useState<ExplorerViewMode>("details");
  const [sort, setSort] = useState<{ key: ExplorerSortKey; asc: boolean }>({ key: "name", asc: true });
  const [showHidden, setShowHidden] = useState(false);
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const anchorRef = useRef<string | null>(null);
  const [clipboard, setClipboard] = useState<ExplorerClipboard | null>(null);
  const [dialog, setDialog] = useState<ExplorerDialog | null>(null);
  const [operation, setOperation] = useState<{ status: "idle" | "working" | "error"; message?: string }>({
    status: "idle",
  });
  const [uploads, setUploads] = useState<UploadItem[]>([]);

  const listing = useExplorerListing(path);
  const search = useExplorerSearch(path, searchQuery);
  const mutations = useExplorerMutations();
  const invalidate = useInvalidateExplorer();

  const searching = searchQuery.trim().length > 0;
  const status: "loading" | "ready" | "error" = searching
    ? search.isError
      ? "error"
      : search.isLoading
      ? "loading"
      : "ready"
    : listing.isError
    ? "error"
    : listing.isLoading
    ? "loading"
    : "ready";
  const loadError = searching ? search.error : listing.error;

  const rawEntries = useMemo(
    () => (searching ? search.data?.entries : listing.data?.entries) ?? [],
    [searching, search.data, listing.data]
  );
  const entries = useMemo(() => {
    const visible = showHidden ? rawEntries : rawEntries.filter((e) => !e.name.startsWith("."));
    return sortEntries(visible, sort.key, sort.asc);
  }, [rawEntries, showHidden, sort]);
  const entryByPath = useMemo(() => new Map(entries.map((e) => [e.path, e])), [entries]);
  const selectedEntries = useMemo(() => entries.filter((e) => selected.has(e.path)), [entries, selected]);
  const currentNames = useMemo(() => new Set((listing.data?.entries ?? []).map((e) => e.name)), [listing.data]);

  // ---- navigation --------------------------------------------------------

  const navigate = useCallback(
    (target: string) => {
      const normalized = target.trim() === "" ? "/" : target.trim().replace(/\/+$/, "") || "/";
      setHistory((h) => {
        if (h.stack[h.index] === normalized) return h;
        const stack = [...h.stack.slice(0, h.index + 1), normalized];
        return { stack, index: stack.length - 1 };
      });
      setSelected(new Set());
      setSearchInput("");
      setSearchQuery("");
      onPathChange?.(normalized);
    },
    [onPathChange]
  );

  function stepHistory(delta: -1 | 1) {
    const index = history.index + delta;
    if (index < 0 || index >= history.stack.length) return;
    setHistory({ ...history, index });
    setSelected(new Set());
    onPathChange?.(history.stack[index]);
  }
  const goBack = () => stepHistory(-1);
  const goForward = () => stepHistory(1);
  const goUp = () => {
    const parent = parentPath(path);
    if (parent) navigate(parent);
  };
  const refresh = () => void invalidate();

  // ---- selection ---------------------------------------------------------

  async function namesIn(destination: string): Promise<Set<string>> {
    if (destination === path) return new Set(currentNames);
    const data = await apiClient.get<{ entries: ExplorerEntry[] }>("/api/v1/file-explorer", {
      params: { path: destination },
    });
    return new Set(data.entries.map((e) => e.name));
  }

  function select(entry: ExplorerEntry, mods: { ctrl?: boolean; shift?: boolean } = {}) {
    if (mods.shift && anchorRef.current) {
      const paths = entries.map((e) => e.path);
      const a = paths.indexOf(anchorRef.current);
      const b = paths.indexOf(entry.path);
      if (a !== -1 && b !== -1) {
        const [from, to] = a < b ? [a, b] : [b, a];
        const range = paths.slice(from, to + 1);
        setSelected((prev) => (mods.ctrl ? new Set([...prev, ...range]) : new Set(range)));
        return;
      }
    }
    anchorRef.current = entry.path;
    if (mods.ctrl) {
      setSelected((prev) => {
        const next = new Set(prev);
        if (next.has(entry.path)) next.delete(entry.path);
        else next.add(entry.path);
        return next;
      });
    } else {
      setSelected(new Set([entry.path]));
    }
  }

  /** Right-click keeps an existing multi-selection if the item is in it. */
  function selectForContext(entry: ExplorerEntry) {
    if (!selected.has(entry.path)) {
      anchorRef.current = entry.path;
      setSelected(new Set([entry.path]));
    }
  }

  const selectAll = () => setSelected(new Set(entries.map((e) => e.path)));
  const clearSelection = () => setSelected(new Set());

  function moveSelection(delta: number, extend: boolean) {
    if (entries.length === 0) return;
    const paths = entries.map((e) => e.path);
    const current = anchorRef.current ? paths.indexOf(anchorRef.current) : -1;
    const nextIndex = Math.max(0, Math.min(paths.length - 1, current === -1 ? 0 : current + delta));
    const target = entries[nextIndex];
    if (extend) select(target, { shift: true });
    else select(target);
    anchorRef.current = target.path;
  }

  // ---- open --------------------------------------------------------------

  async function open(entry: ExplorerEntry, isTextLike: (name: string) => boolean, isImage: (name: string) => boolean) {
    if (entry.type === "dir") {
      navigate(entry.path);
      return;
    }
    if (isTextLike(entry.name)) {
      setDialog({ kind: "edit", path: entry.path });
      return;
    }
    if (isImage(entry.name)) {
      await run(async () => {
        const { blob } = await downloadExplorerPath(entry.path);
        setDialog({ kind: "preview", entry, url: URL.createObjectURL(blob) });
      });
      return;
    }
    await download([entry]);
  }

  function closeDialog() {
    if (dialog?.kind === "preview") URL.revokeObjectURL(dialog.url);
    setDialog(null);
  }

  // ---- operations --------------------------------------------------------

  async function run(action: () => Promise<void>) {
    setOperation({ status: "working" });
    try {
      await action();
      setOperation({ status: "idle" });
      return true;
    } catch (error) {
      setOperation({ status: "error", message: errorMessage(error) });
      return false;
    }
  }

  const dismissError = () => setOperation({ status: "idle" });

  async function createItem(kind: "newFolder" | "newFile", name: string) {
    const target = joinPath(path, name.trim());
    const ok = await run(async () => {
      if (kind === "newFolder") await mutations.createFolder.mutateAsync(target);
      else await mutations.createFile.mutateAsync(target);
    });
    if (ok) {
      setDialog(null);
      setSelected(new Set([target]));
      anchorRef.current = target;
    }
    return ok;
  }

  async function rename(entry: ExplorerEntry, newName: string) {
    const trimmed = newName.trim();
    if (trimmed === entry.name) {
      setDialog(null);
      return true;
    }
    const target = joinPath(parentPath(entry.path) ?? "/", trimmed);
    const ok = await run(() => mutations.move.mutateAsync({ path: entry.path, newPath: target }).then(() => undefined));
    if (ok) {
      setDialog(null);
      setSelected(new Set([target]));
      anchorRef.current = target;
    }
    return ok;
  }

  async function removeEntries(targets: ExplorerEntry[]) {
    const ok = await run(async () => {
      for (const entry of targets) await mutations.remove.mutateAsync(entry.path);
    });
    if (ok) {
      setDialog(null);
      setSelected(new Set());
    }
    return ok;
  }

  const copySelection = () => selectedEntries.length && setClipboard({ mode: "copy", entries: selectedEntries });
  const cutSelection = () => selectedEntries.length && setClipboard({ mode: "cut", entries: selectedEntries });

  /** Paste into `destination` (current folder by default). Copying onto an
   * existing name gets a Windows-style "- Copy" name; a cut onto an
   * existing name is refused rather than overwriting silently. */
  async function paste(destination: string = path) {
    if (!clipboard) return;
    const { mode, entries: items } = clipboard;
    let taken: Set<string>;
    try {
      taken = await namesIn(destination);
    } catch (error) {
      setOperation({ status: "error", message: errorMessage(error) });
      return false;
    }
    const ok = await run(async () => {
      const skipped: string[] = [];
      for (const item of items) {
        if (mode === "cut" && parentPath(item.path) === destination) continue;
        let name = item.name;
        if (taken.has(name)) {
          if (mode === "cut") {
            skipped.push(name);
            continue;
          }
          name = copyName(name, taken, item.type === "dir");
        }
        const target = joinPath(destination, name);
        if (mode === "copy") await mutations.copy.mutateAsync({ path: item.path, newPath: target });
        else await mutations.move.mutateAsync({ path: item.path, newPath: target });
        taken.add(name);
      }
      if (skipped.length) throw new Error(`Already exists in destination: ${skipped.join(", ")}`);
    });
    if (mode === "cut") setClipboard(null);
    return ok;
  }

  /** Drag an item onto a folder: move (copy with Ctrl). */
  async function dropEntries(paths: string[], destination: string, copyInstead: boolean) {
    const items = paths
      .map((p) => entryByPath.get(p))
      .filter((e): e is ExplorerEntry => Boolean(e))
      .filter((e) => e.path !== destination && !destination.startsWith(`${e.path}/`));
    if (items.length === 0) return;
    await run(async () => {
      for (const item of items) {
        if (!copyInstead && parentPath(item.path) === destination) continue;
        const target = joinPath(destination, item.name);
        if (copyInstead) await mutations.copy.mutateAsync({ path: item.path, newPath: target });
        else await mutations.move.mutateAsync({ path: item.path, newPath: target });
      }
    });
  }

  async function download(targets: ExplorerEntry[] = selectedEntries) {
    if (targets.length === 0) return;
    await run(async () => {
      if (targets.length === 1) {
        const { blob } = await downloadExplorerPath(targets[0].path);
        saveBlob(blob, targets[0].type === "dir" ? `${targets[0].name}.zip` : targets[0].name);
      } else {
        const name = `${baseName(path) === "/" ? "root" : baseName(path)}-${targets.length}-items.zip`;
        const { blob } = await downloadExplorerZip(
          targets.map((t) => t.path),
          name
        );
        saveBlob(blob, name);
      }
    });
  }

  // ---- uploads -----------------------------------------------------------

  /** Entry point for every upload (file picker, folder picker, drop).
   * Asks first when anything at the top level would collide. */
  async function requestUpload(pending: PendingUpload[], destination: string = path) {
    if (pending.length === 0) return;
    let existing: Set<string>;
    try {
      existing = await namesIn(destination);
    } catch {
      existing = new Set();
    }
    const conflicts = topLevelNames(pending).filter((name) => existing.has(name));
    if (conflicts.length > 0) {
      setDialog({ kind: "uploadConflict", uploads: pending, destination, conflicts });
      return;
    }
    void startUpload(pending, destination, false);
  }

  async function startUpload(pending: PendingUpload[], destination: string, overwrite: boolean) {
    setDialog(null);
    const batch: UploadItem[] = pending.map((p, i) => ({
      id: `${Date.now()}-${i}-${p.relativePath}`,
      name: p.relativePath,
      destination: joinPath(destination, p.relativePath),
      loaded: 0,
      total: p.file.size,
      status: "queued",
    }));
    setUploads((prev) => [...prev.filter((u) => u.status === "uploading" || u.status === "queued"), ...batch]);
    const update = (id: string, patch: Partial<UploadItem>) =>
      setUploads((prev) => prev.map((u) => (u.id === id ? { ...u, ...patch } : u)));

    let cursor = 0;
    async function worker() {
      while (cursor < batch.length) {
        const index = cursor++;
        const item = batch[index];
        update(item.id, { status: "uploading" });
        try {
          await uploadExplorerFile(item.destination, pending[index].file, overwrite, (loaded, total) =>
            update(item.id, { loaded, total })
          );
          update(item.id, { status: "done", loaded: item.total });
        } catch (error) {
          if (!overwrite && error instanceof ApiError && error.status === 409) {
            update(item.id, { status: "skipped", error: errorMessage(error) });
          } else {
            update(item.id, { status: "error", error: errorMessage(error) });
          }
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(UPLOAD_CONCURRENCY, batch.length) }, worker));
    void invalidate();
  }

  const clearFinishedUploads = () =>
    setUploads((prev) => prev.filter((u) => u.status === "uploading" || u.status === "queued"));

  return {
    // state
    path,
    status,
    loadError: loadError ? errorMessage(loadError) : null,
    entries,
    totalCount: rawEntries.length,
    selected,
    selectedEntries,
    clipboard,
    dialog,
    operation,
    uploads,
    viewMode,
    sort,
    showHidden,
    searchInput,
    searchQuery,
    searching,
    searchTruncated: Boolean(search.data?.truncated),
    canGoBack: history.index > 0,
    canGoForward: history.index < history.stack.length - 1,
    canGoUp: parentPath(path) !== null,
    // actions
    navigate,
    goBack,
    goForward,
    goUp,
    refresh,
    select,
    selectForContext,
    selectAll,
    clearSelection,
    moveSelection,
    open,
    setDialog,
    closeDialog,
    dismissError,
    createItem,
    rename,
    removeEntries,
    copySelection,
    cutSelection,
    paste,
    dropEntries,
    download,
    requestUpload,
    startUpload,
    clearFinishedUploads,
    setViewMode,
    setSort,
    setShowHidden,
    setSearchInput,
    submitSearch: () => setSearchQuery(searchInput.trim()),
    clearSearch: () => {
      setSearchInput("");
      setSearchQuery("");
    },
    saveContent: (target: string, content: string) =>
      run(() => mutations.writeContent.mutateAsync({ path: target, content }).then(() => undefined)),
  };
}

export type FileExplorerViewModel = ReturnType<typeof useFileExplorerViewModel>;
