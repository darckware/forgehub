import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  available_repos: { key: string; path: string }[];
  backups: {
    path: string;
    count: number;
    entries: { name: string; path: string; size: number | null; type: string }[];
  };
}

/** `repo` is the KNOWN_REPOS key from a previous call's `available_repos`
 * (see backend/app/api/routes/system_control.py) -- omitted/unknown falls
 * back to the backend's default repo rather than erroring. */
export function useSystemControlStatus(repo?: string) {
  return useQuery<SystemControlStatus>({
    queryKey: ["system-control", "status", repo ?? "default"],
    queryFn: () => apiClient.get("/api/v1/system-control/status", { params: repo ? { repo } : undefined }),
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useHermesBackup() {
  const queryClient = useQueryClient();
  return useMutation<{ status: string; archive_path: string; size_bytes: number }, Error>({
    mutationFn: () => apiClient.post("/api/v1/system-control/backup-hermes", {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["system-control", "status"] });
    },
  });
}

export function useDeleteBackup() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (filename) => apiClient.delete(`/api/v1/system-control/backup/${encodeURIComponent(filename)}`),
    onSuccess: async () => {
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
