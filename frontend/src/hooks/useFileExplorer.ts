import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/**
 * Workspace Explorer -- data layer for the Windows-Explorer-style host file
 * manager (components/explorer/FileExplorerPane.tsx). Every path is an
 * absolute HOST path; the backend (api/routes/file_explorer.py) is
 * admin-only and delegates the actual filesystem work to the host-bridge.
 * Screen state (history, selection, clipboard, dialogs, upload queue) lives
 * in useFileExplorerViewModel.ts, not here.
 */

export interface ExplorerEntry {
  name: string;
  path: string;
  type: "file" | "dir";
  size: number | null;
  modified: number | null;
  is_symlink: boolean;
}

export interface ExplorerListing {
  path: string;
  parent: string | null;
  entries: ExplorerEntry[];
}

export interface ExplorerSearchResult {
  path: string;
  query: string;
  entries: ExplorerEntry[];
  truncated: boolean;
}

export interface ExplorerFileContent {
  path: string;
  content: string;
}

const RESOURCE = "/api/v1/file-explorer";

export const explorerKeys = {
  all: ["file-explorer"] as const,
  list: (path: string) => ["file-explorer", "list", path] as const,
  search: (path: string, q: string) => ["file-explorer", "search", path, q] as const,
  content: (path: string) => ["file-explorer", "content", path] as const,
};

export function useExplorerListing(path: string, enabled = true) {
  return useQuery({
    queryKey: explorerKeys.list(path),
    queryFn: () => apiClient.get<ExplorerListing>(RESOURCE, { params: { path } }),
    enabled: enabled && Boolean(path),
    placeholderData: keepPreviousData,
    retry: false,
  });
}

export function useExplorerSearch(path: string, q: string) {
  return useQuery({
    queryKey: explorerKeys.search(path, q),
    queryFn: () => apiClient.get<ExplorerSearchResult>(`${RESOURCE}/search`, { params: { path, q } }),
    enabled: Boolean(path && q.trim()),
    retry: false,
    staleTime: 10_000,
  });
}

export function useExplorerFileContent(path: string | null) {
  return useQuery({
    queryKey: explorerKeys.content(path ?? ""),
    queryFn: () => apiClient.get<ExplorerFileContent>(`${RESOURCE}/content`, { params: { path: path! } }),
    enabled: Boolean(path),
    retry: false,
  });
}

export function useInvalidateExplorer() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: explorerKeys.all });
}

export function useExplorerMutations() {
  const invalidate = useInvalidateExplorer();
  const onSettled = () => void invalidate();
  return {
    createFolder: useMutation({
      mutationFn: (path: string) => apiClient.post<ExplorerEntry>(`${RESOURCE}/directory`, { path }),
      onSettled,
    }),
    createFile: useMutation({
      mutationFn: (path: string) => apiClient.post<ExplorerEntry>(`${RESOURCE}/file`, { path }),
      onSettled,
    }),
    move: useMutation({
      mutationFn: ({ path, newPath }: { path: string; newPath: string }) =>
        apiClient.patch<ExplorerEntry>(`${RESOURCE}/move`, { path, new_path: newPath }),
      onSettled,
    }),
    copy: useMutation({
      mutationFn: ({ path, newPath }: { path: string; newPath: string }) =>
        apiClient.post<ExplorerEntry>(`${RESOURCE}/copy`, { path, new_path: newPath }),
      onSettled,
    }),
    remove: useMutation({
      mutationFn: (path: string) =>
        apiClient.delete<void>(RESOURCE, { params: { path, recursive: true } }),
      onSettled,
    }),
    writeContent: useMutation({
      mutationFn: ({ path, content }: { path: string; content: string }) =>
        apiClient.put<ExplorerFileContent>(`${RESOURCE}/content`, { content }, { params: { path } }),
      onSettled,
    }),
  };
}

export function uploadExplorerFile(
  destination: string,
  file: Blob,
  overwrite: boolean,
  onProgress?: (loaded: number, total: number) => void,
  signal?: AbortSignal,
) {
  return apiClient.uploadBinary<ExplorerEntry>(
    `${RESOURCE}/upload`,
    file,
    { path: destination, overwrite },
    onProgress,
    signal,
  );
}

export function downloadExplorerPath(path: string) {
  return apiClient.downloadFile(`${RESOURCE}/download?path=${encodeURIComponent(path)}`);
}

export function downloadExplorerZip(paths: string[], name: string) {
  return apiClient.postDownload(`${RESOURCE}/download-zip`, { paths, name });
}

/** Hand a fetched blob to the browser's own save flow. */
export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ---------------------------------------------------------------------------
// Pure path helpers (POSIX, absolute). Exported for tests.
// ---------------------------------------------------------------------------

export function joinPath(dir: string, name: string): string {
  const base = dir === "/" ? "" : dir.replace(/\/+$/, "");
  const rest = name.replace(/^\/+/, "");
  return `${base}/${rest}` || "/";
}

export function parentPath(path: string): string | null {
  if (path === "/") return null;
  const trimmed = path.replace(/\/+$/, "");
  const idx = trimmed.lastIndexOf("/");
  return idx <= 0 ? "/" : trimmed.slice(0, idx);
}

export function baseName(path: string): string {
  if (path === "/") return "/";
  return path.replace(/\/+$/, "").split("/").pop() ?? path;
}

/** Breadcrumb segments: "/root/project" -> [{/}, {root,/root}, {project,/root/project}]. */
export function pathSegments(path: string): { name: string; path: string }[] {
  const parts = path.split("/").filter(Boolean);
  const segments = [{ name: "/", path: "/" }];
  let acc = "";
  for (const part of parts) {
    acc += `/${part}`;
    segments.push({ name: part, path: acc });
  }
  return segments;
}

/** Windows-style collision name: "a.txt" -> "a - Copy.txt", then "a - Copy (2).txt". */
export function copyName(name: string, taken: Set<string>, isDir: boolean): string {
  const dot = isDir ? -1 : name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name;
  const ext = dot > 0 ? name.slice(dot) : "";
  let candidate = `${stem} - Copy${ext}`;
  for (let i = 2; taken.has(candidate); i++) candidate = `${stem} - Copy (${i})${ext}`;
  return candidate;
}

/** A name the user typed for a new/renamed item: no slashes, not "."/"..". */
export function isValidName(name: string): boolean {
  const trimmed = name.trim();
  return trimmed.length > 0 && trimmed !== "." && trimmed !== ".." && !trimmed.includes("/") && !trimmed.includes("\0");
}

export function formatSize(bytes: number | null): string {
  if (bytes === null) return "";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "json", "yaml", "yml", "toml", "ini", "cfg", "conf", "env", "log", "csv", "tsv",
  "xml", "html", "htm", "css", "scss", "js", "jsx", "ts", "tsx", "mjs", "cjs", "py", "sh", "bash", "zsh",
  "sql", "go", "rs", "java", "kt", "c", "h", "cpp", "hpp", "cs", "rb", "php", "lua", "pl", "r", "swift",
  "dockerfile", "gitignore", "service", "properties", "gradle", "vue", "svelte",
]);

/** Opened in the built-in text editor on double-click (vs. downloaded). */
export function isTextLike(name: string): boolean {
  const lower = name.toLowerCase();
  if (!lower.includes(".")) return true; // Makefile, Dockerfile, LICENSE, ...
  if (lower.startsWith(".") && lower.indexOf(".", 1) === -1) return true; // .bashrc, .gitignore
  return TEXT_EXTENSIONS.has(lower.split(".").pop() ?? "");
}

export function fileKind(entry: Pick<ExplorerEntry, "name" | "type">): string {
  if (entry.type === "dir") return "folder";
  const lower = entry.name.toLowerCase();
  const ext = lower.includes(".") ? lower.split(".").pop()! : "";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "ico"].includes(ext)) return "image";
  if (["zip", "gz", "tgz", "tar", "bz2", "xz", "7z", "rar"].includes(ext)) return "archive";
  if (["mp4", "mov", "webm", "mkv", "avi", "mp3", "wav", "ogg", "flac"].includes(ext)) return "media";
  if (["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt"].includes(ext)) return "document";
  if (["js", "jsx", "ts", "tsx", "py", "sh", "go", "rs", "java", "c", "cpp", "cs", "rb", "php", "sql", "html", "css"].includes(ext))
    return "code";
  return isTextLike(entry.name) ? "text" : "file";
}
