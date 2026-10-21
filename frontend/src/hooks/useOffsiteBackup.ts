import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

/** Off-site backup (System Control -> "Backup externo", 2026-10-20): one
 * restic snapshot per target in the Google Drive repository. ForgeHub keeps
 * the list and the history; Athos' worker on the host does the backup. */
export type OffsiteRunStatus = "running" | "ok" | "failed" | "interrupted";

export interface OffsiteBackupRun {
  id: string;
  target_id: string | null;
  target_name: string;
  trigger: "schedule" | "manual";
  status: OffsiteRunStatus;
  started_at: string;
  finished_at: string | null;
  snapshot_id: string | null;
  files_new: number | null;
  data_added: number | null;
  total_bytes: number | null;
  error: string | null;
}

export interface OffsiteBackupTarget {
  id: string;
  /** restic tag of every snapshot -- fixed after creation. */
  name: string;
  label: string;
  paths: string[];
  excludes: string[];
  postgres_container: string | null;
  include_system_state: boolean;
  enabled: boolean;
  sort_order: number;
  last_run: OffsiteBackupRun | null;
  last_success: OffsiteBackupRun | null;
}

export interface OffsiteBackupOverview {
  repository: string;
  script: string;
  schedule: {
    job_id: string;
    expression: string;
    enabled: boolean;
    next_run_at: string | null;
    last_run_at: string | null;
    last_status: string | null;
  } | null;
  /** "not_scheduled" when Athos has no cron job for the script yet. */
  schedule_error: string | null;
  running: boolean;
  repository_maintenance: OffsiteBackupRun | null;
  targets: OffsiteBackupTarget[];
}

export const OFFSITE_TARGET_NAME_RE = /^[a-z0-9][a-z0-9-]{0,62}$/;

function lines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export const offsiteTargetFormSchema = z.object({
  label: z.string().trim().min(1, "required").max(255, "tooLong"),
  name: z.string().trim().regex(OFFSITE_TARGET_NAME_RE, "badName"),
  paths: z
    .string()
    .refine((text) => lines(text).length > 0, "required")
    .refine((text) => lines(text).every((path) => path.startsWith("/")), "absolute")
    .refine((text) => lines(text).every((path) => path.replace(/\/+$/, "") !== ""), "root"),
  excludes: z.string(),
  postgres_container: z.string(),
  include_system_state: z.boolean(),
  enabled: z.boolean(),
});
export type OffsiteTargetFormInput = z.infer<typeof offsiteTargetFormSchema>;

export interface OffsiteTargetPayload {
  name?: string;
  label: string;
  paths: string[];
  excludes: string[];
  postgres_container: string | null;
  include_system_state: boolean;
  enabled: boolean;
  sort_order?: number;
}

export function toOffsiteTargetPayload(input: OffsiteTargetFormInput): OffsiteTargetPayload {
  return {
    name: input.name.trim(),
    label: input.label.trim(),
    paths: lines(input.paths),
    excludes: lines(input.excludes),
    postgres_container: input.postgres_container || null,
    include_system_state: input.include_system_state,
    enabled: input.enabled,
  };
}

export function offsiteTargetFormDefaults(target?: OffsiteBackupTarget): OffsiteTargetFormInput {
  return {
    label: target?.label ?? "",
    name: target?.name ?? "",
    paths: target?.paths.join("\n") ?? "",
    excludes: target?.excludes.join("\n") ?? "",
    postgres_container: target?.postgres_container ?? "",
    include_system_state: target?.include_system_state ?? false,
    enabled: target?.enabled ?? true,
  };
}

/** "Meu Projeto 2" -> "meu-projeto-2", the identifier suggested from the name. */
export function slugifyTargetName(label: string): string {
  return label
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

const OVERVIEW_KEY = ["offsite-backup", "overview"];

export function useOffsiteBackupOverview() {
  return useQuery<OffsiteBackupOverview>({
    queryKey: OVERVIEW_KEY,
    queryFn: () => apiClient.get("/api/v1/offsite-backup/overview"),
    retry: false,
    // While a backup runs, each target's row changes as the worker reports.
    refetchInterval: (query) => (query.state.data?.running ? 10_000 : 60_000),
  });
}

export function useOffsiteBackupRuns(target: string | null) {
  return useQuery<OffsiteBackupRun[]>({
    queryKey: ["offsite-backup", "runs", target],
    queryFn: () => apiClient.get("/api/v1/offsite-backup/runs", { params: { target: target ?? undefined, limit: 15 } }),
    enabled: target !== null,
    retry: false,
  });
}

export function usePostgresContainers(enabled: boolean) {
  return useQuery<{ containers: string[] }>({
    queryKey: ["offsite-backup", "postgres-containers"],
    queryFn: () => apiClient.get("/api/v1/offsite-backup/postgres-containers"),
    enabled,
    retry: false,
    staleTime: 60_000,
  });
}

function useInvalidateOverview() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["offsite-backup"] });
}

export function useSaveOffsiteTarget() {
  const invalidate = useInvalidateOverview();
  return useMutation<OffsiteBackupTarget, Error, { id?: string; payload: OffsiteTargetPayload }>({
    mutationFn: ({ id, payload }) => {
      if (!id) return apiClient.post("/api/v1/offsite-backup/targets", payload);
      const { name: _name, ...rest } = payload;
      return apiClient.put(`/api/v1/offsite-backup/targets/${id}`, rest);
    },
    onSuccess: invalidate,
  });
}

export function useDeleteOffsiteTarget() {
  const invalidate = useInvalidateOverview();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/offsite-backup/targets/${id}`),
    onSuccess: invalidate,
  });
}

export function useRunOffsiteBackup() {
  const invalidate = useInvalidateOverview();
  return useMutation<{ started: boolean; targets: string[] }, Error, string[]>({
    mutationFn: (targets) => apiClient.post("/api/v1/offsite-backup/run", { targets }),
    onSuccess: invalidate,
  });
}
