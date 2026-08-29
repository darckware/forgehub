import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface SystemControlStatus {
  git: {
    repo_key: string;
    repo_root: string;
    branch: string;
    head: string;
    short_head: string;
    dirty_count: number;
    status_lines: string[];
    last_commit: {
      hash: string;
      author: string | null;
      date: string | null;
      subject: string | null;
    };
  };
  /** "hermes" (fixed system entry) or every registered Project with a
   * working_directory_path set -- there is no separate ad-hoc registry
   * anymore, Project registration is the one source of truth (see
   * backend/app/api/routes/system_control.py's module-level comment). */
  available_repos: { key: string; path: string; removable: boolean; label: string; kind: "system" | "project" }[];
  backups: {
    path: string;
    count: number;
    entries: { name: string; path: string; size: number | null; type: string }[];
  };
}

/** `repo` is an available_repos key from a previous call ("hermes" or
 * "project:<uuid>") -- omitted/unknown falls back to the backend's default
 * repo rather than erroring. */
export function useSystemControlStatus(repo?: string) {
  return useQuery<SystemControlStatus>({
    queryKey: ["system-control", "status", repo ?? "default"],
    queryFn: () => apiClient.get("/api/v1/system-control/status", { params: repo ? { repo } : undefined }),
    refetchInterval: 30_000,
    retry: false,
    // Keeps showing the previously-selected repo's numbers (branch,
    // working tree, last commit) while the new one loads, instead of the
    // whole page (including the picker itself) blanking to a spinner on
    // every dropdown change -- see SystemControlPage's `isLoading` guard.
    placeholderData: keepPreviousData,
  });
}

export interface BackupTarget {
  key: string; // "hermes" | "project:<uuid>"
  label: string;
  kind: "system" | "project";
  /** false when a project has backup_enabled but no working_directory_path
   * yet -- selectable but running a backup on it will fail. */
  ready: boolean;
  /** What gets archived -- always "/root/.hermes" for the "hermes" target;
   * a project's working_directory_path (null if not set yet). */
  source: string | null;
  /** Where archives for this target land -- Project.backup_location if
   * set, else BACKUP_DIR/<slug-of-name> (e.g. "/root/backup/forgehub"). */
  location: string;
}

/** "hermes" (always present) plus every Project with backup_enabled=true
 * -- what POST /backups/run's `target` (or its "all" pseudo-target) can
 * act on, and what GET /backups can list. */
export function useBackupTargets() {
  return useQuery<{ targets: BackupTarget[] }>({
    queryKey: ["system-control", "backup-targets"],
    queryFn: () => apiClient.get("/api/v1/system-control/backup-targets"),
    retry: false,
  });
}

export interface BackupListing {
  target: string;
  path: string;
  count: number;
  entries: { name: string; path: string; size: number | null; type: string }[];
}

/** Archives for ONE target only -- Hermes and each project's backups are
 * stored in separate directories and never listed together (see the
 * module docstring in backend/app/api/routes/system_control.py). */
export function useBackupListing(target: string) {
  return useQuery<BackupListing>({
    queryKey: ["system-control", "backups", target],
    queryFn: () => apiClient.get("/api/v1/system-control/backups", { params: { target } }),
    retry: false,
    // Same reasoning as useSystemControlStatus -- avoid blanking the table
    // to a spinner every time the backup target dropdown changes.
    placeholderData: keepPreviousData,
  });
}

export interface BackupRunResult {
  target: string;
  label: string;
  status: string;
  archive_path: string;
  size_bytes: number;
}

export interface BackupRunResponse {
  results: BackupRunResult[];
  errors: { target: string; detail: string }[];
}

/** target = "hermes" | "project:<uuid>" | "all" (fans out to Hermes + every
 * ready backup_enabled project, each still landing in its own directory --
 * see POST /backups/run's docstring). */
export function useRunBackup() {
  const queryClient = useQueryClient();
  return useMutation<BackupRunResponse, Error, { target: string }>({
    mutationFn: (payload) => apiClient.post("/api/v1/system-control/backups/run", payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["system-control", "backups"] });
      await queryClient.invalidateQueries({ queryKey: ["system-control", "status"] });
    },
  });
}

export function useDeleteBackup() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, { target: string; filename: string }>({
    mutationFn: ({ target, filename }) =>
      apiClient.delete(
        `/api/v1/system-control/backups/${encodeURIComponent(target)}/${encodeURIComponent(filename)}`
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["system-control", "backups"] });
      await queryClient.invalidateQueries({ queryKey: ["system-control", "status"] });
    },
  });
}

export interface CommitResult {
  repo_key: string;
  hash: string | null;
  author: string | null;
  date: string | null;
  subject: string | null;
}

/** `git add -A` + `git commit -m <message>` against the given repo (see
 * CommitRequest in backend/app/api/routes/system_control.py) -- never
 * pushes. */
export function useCommitChanges() {
  const queryClient = useQueryClient();
  return useMutation<CommitResult, Error, { message: string; repo?: string }>({
    mutationFn: (payload) => apiClient.post("/api/v1/system-control/commit", payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["system-control", "status"] });
    },
  });
}

export interface CleanupFile {
  path: string;
  name: string;
  size: number;
  mtime: string;
}

export interface CleanupCategory {
  category: string;
  count: number;
  total_size: number;
  files: CleanupFile[];
}

export interface CleanupScan {
  root: string;
  total_count: number;
  total_size: number;
  categories: CleanupCategory[];
}

/** Read-only inventory of everything under ~/.hermes the ecosystem's
 * cleanup scripts already consider fair game (logs/backups/cron output),
 * grouped by type -- see GET /cleanup-scan's docstring. Nothing is deleted
 * by loading this. */
export function useCleanupScan() {
  return useQuery<CleanupScan>({
    queryKey: ["system-control", "cleanup-scan"],
    queryFn: () => apiClient.get("/api/v1/system-control/cleanup-scan"),
    retry: false,
  });
}

export interface CleanupRunResult {
  trash_root: string;
  backup_root: string;
  script: string;
  output: string;
  policy: "no-docker-volume-prune";
}

/** Runs the authoritative Athos weekly cleanup policy immediately. The
 * foundation-clear cron invokes this same script; the UI does not maintain
 * a second set of deletion rules. Docker volumes/database data are excluded. */
export function useRunCleanup() {
  const queryClient = useQueryClient();
  return useMutation<CleanupRunResult, Error>({
    mutationFn: () => apiClient.post("/api/v1/system-control/cleanup-run", {}),
    // Not awaited: cleanup-scan re-scans the whole host filesystem (10s+,
    // longer under load) -- awaiting it here would keep this mutation (and
    // any UI bound to its pending state) stuck "loading" for the length of
    // that rescan even though the run itself already finished. The query
    // still refetches and the UI still updates once it resolves.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["system-control", "cleanup-scan"] });
    },
  });
}

export interface CleanupDeleteResult {
  category: string;
  count: number;
  total_size: number;
  trash_path: string;
}

/** Clears one cleanup-scan category card on demand (2026-08-24) -- moves
 * every file currently in that category to TRASH_ROOT (never a hard
 * delete, same recoverable-by-default philosophy as useRunCleanup) without
 * waiting for or triggering the full weekly policy. `category` goes as a
 * query param, not a path segment -- some category names contain "/". */
export function useDeleteCleanupCategory() {
  const queryClient = useQueryClient();
  return useMutation<CleanupDeleteResult, Error, string>({
    mutationFn: (category: string) =>
      apiClient.post("/api/v1/system-control/cleanup-scan/delete", undefined, { params: { category } }),
    // Not awaited -- see useRunCleanup's comment: cleanup-scan's own rescan
    // (not this delete) was what made the confirm dialog's spinner sit for
    // 10s+ looking like the click had done nothing.
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["system-control", "cleanup-scan"] });
    },
  });
}

export interface TrashStatus {
  trash_root: string;
  total_size: number;
  item_count: number;
}

/** Size/count of everything currently sitting in TRASH_ROOT -- every
 * cleanup-scan/delete click and the weekly policy's own files land here
 * first (recoverable), so this is what "Empty trash" removes for good. */
export function useTrashStatus() {
  return useQuery<TrashStatus>({
    queryKey: ["system-control", "trash-status"],
    queryFn: () => apiClient.get("/api/v1/system-control/trash-status"),
    retry: false,
  });
}

/** Permanently deletes everything under TRASH_ROOT -- a hard delete, unlike
 * every other action on this page (cleanup-scan/delete and Run Cleanup only
 * ever move things here). Separate from Run Cleanup so clearing trash
 * doesn't also trigger Docker/journal/backup-expiry pruning. */
export function useEmptyTrash() {
  const queryClient = useQueryClient();
  return useMutation<{ trash_root: string }, Error>({
    mutationFn: () => apiClient.post("/api/v1/system-control/trash:empty", undefined),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["system-control", "trash-status"] });
      void queryClient.invalidateQueries({ queryKey: ["system-control", "cleanup-scan"] });
    },
  });
}
