import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface SystemControlStatus {
  git: {
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
  backups: {
    path: string;
    count: number;
    entries: { name: string; path: string; size: number | null; type: string }[];
  };
}

export function useSystemControlStatus() {
  return useQuery<SystemControlStatus>({
    queryKey: ["system-control", "status"],
    queryFn: () => apiClient.get("/api/v1/system-control/status"),
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
