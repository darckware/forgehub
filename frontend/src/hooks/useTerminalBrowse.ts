import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/** Host directory browser, used by the chat page's working-directory
 * picker (before opening a bash terminal or a CLI launcher like Claude/
 * Codex/Antigravity) -- proxies to the host bridge's real filesystem,
 * see backend/app/api/routes/terminal.py + host-bridge/app.py. */

export interface BrowseDirEntry {
  name: string;
  path: string;
}

export interface BrowseDirsResult {
  path: string;
  parent: string | null;
  entries: BrowseDirEntry[];
}

export function useBrowseDirs(path: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["terminal-browse-dirs", path ?? ""],
    queryFn: () =>
      apiClient.get<BrowseDirsResult>("/api/v1/terminal/browse-dirs", {
        params: path ? { path } : undefined,
      }),
    enabled,
  });
}

export interface FsEntry {
  name: string;
  path: string;
  type: "file" | "dir";
  size: number | null;
}

export interface FsListResult {
  path: string;
  parent: string | null;
  entries: FsEntry[];
}

/** Files + dirs (unlike useBrowseDirs, which is dirs-only) -- backs the chat
 * composer's "@" file-mention picker. */
export function useFsList(path: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["terminal-fs-list", path ?? ""],
    queryFn: () =>
      apiClient.get<FsListResult>("/api/v1/terminal/fs-list", {
        params: path ? { path } : undefined,
      }),
    enabled,
  });
}
