import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";
import type { HostExecutionDetail } from "@/hooks/useHostExecutions";

/** Remote Access plan step 1: script library (classified, versioned,
 * parameterized) and schedules. Execution itself goes through
 * useHostExecutions. */

export type ScriptPlatform = "windows" | "linux" | "macos";
export type ScriptRisk = "read" | "change" | "destructive";

export interface ScriptCategory {
  id: string;
  slug: string;
  label: string;
  description: string | null;
}

export interface ScriptParameter {
  name: string;
  label: string | null;
  required: boolean;
  default: string | null;
  secret: boolean;
  /** Left blank, the value is read from ForgeVault under this name when the script runs. */
  vault_secret?: string | null;
  /** A choice parameter: the allowed values, rendered as a select. */
  options?: string[] | null;
}

export interface HostScript {
  id: string;
  name: string;
  category_id: string;
  description: string | null;
  platform: ScriptPlatform;
  risk: ScriptRisk;
  timeout_seconds: number;
  parameters: ScriptParameter[];
  content: string;
  current_version: number;
  is_system: boolean;
  system_key: string | null;
  archived: boolean;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
}

export interface HostScriptVersion {
  version: number;
  content: string;
  parameters: ScriptParameter[];
  changed_by: string;
  note: string | null;
  created_at: string;
}

export interface HostScriptDetail extends HostScript {
  versions: HostScriptVersion[];
}

export interface HostScriptInput {
  name: string;
  category_id: string;
  description: string | null;
  platform: ScriptPlatform;
  risk: ScriptRisk;
  timeout_seconds: number;
  parameters: ScriptParameter[];
  content: string;
  note?: string | null;
}

export interface HostSchedule {
  id: string;
  name: string;
  script_id: string;
  script_name: string | null;
  parameter_values: Record<string, string | null>;
  server_ids: string[];
  group_ids: string[];
  kind: "once" | "weekly";
  run_at: string | null;
  weekdays: number[] | null;
  time_of_day: string | null;
  timezone: string;
  window_minutes: number;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_execution_id: string | null;
  created_by: string;
  agent_id: string | null;
  created_at: string;
}

export interface HostScheduleInput {
  name: string;
  script_id: string;
  parameter_values: Record<string, string | null>;
  server_ids: string[];
  group_ids: string[];
  kind: "once" | "weekly";
  run_at: string | null;
  weekdays: number[] | null;
  time_of_day: string | null;
  timezone: string;
  window_minutes: number;
}

const SCRIPTS = ["host-scripts"] as const;
const SCHEDULES = ["host-schedules"] as const;

export function useScriptCategories() {
  return useQuery<ScriptCategory[]>({
    queryKey: [...SCRIPTS, "categories"],
    queryFn: () => apiClient.get("/api/v1/host-scripts/categories"),
    staleTime: 60_000,
  });
}

export function useCreateScriptCategory() {
  const qc = useQueryClient();
  return useMutation<ScriptCategory, Error, { label: string; description?: string | null }>({
    mutationFn: (data) => apiClient.post("/api/v1/host-scripts/categories", data),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...SCRIPTS, "categories"] }),
  });
}

export function useHostScripts(includeArchived = false) {
  return useQuery<HostScript[]>({
    queryKey: [...SCRIPTS, "list", includeArchived],
    queryFn: () => apiClient.get(`/api/v1/host-scripts${includeArchived ? "?include_archived=true" : ""}`),
    staleTime: 15_000,
  });
}

export function useHostScript(id: string | null) {
  return useQuery<HostScriptDetail>({
    queryKey: [...SCRIPTS, "detail", id],
    queryFn: () => apiClient.get(`/api/v1/host-scripts/${id}`),
    enabled: Boolean(id),
  });
}

function useInvalidateScripts() {
  const qc = useQueryClient();
  return () => void qc.invalidateQueries({ queryKey: SCRIPTS });
}

export function useSaveHostScript() {
  const invalidate = useInvalidateScripts();
  return useMutation<HostScript, Error, { id: string | null; data: HostScriptInput }>({
    mutationFn: ({ id, data }) =>
      id ? apiClient.put(`/api/v1/host-scripts/${id}`, data) : apiClient.post("/api/v1/host-scripts", data),
    onSuccess: invalidate,
  });
}

export function useArchiveHostScript() {
  const invalidate = useInvalidateScripts();
  return useMutation<HostScript, Error, { id: string; archived: boolean }>({
    mutationFn: ({ id, archived }) => apiClient.post(`/api/v1/host-scripts/${id}:${archived ? "archive" : "restore"}`, {}),
    onSuccess: invalidate,
  });
}

export function useHostSchedules() {
  return useQuery<HostSchedule[]>({
    queryKey: SCHEDULES,
    queryFn: () => apiClient.get("/api/v1/host-schedules"),
    refetchInterval: 60_000,
  });
}

function useInvalidateSchedules() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: SCHEDULES });
    void qc.invalidateQueries({ queryKey: ["host-executions"] });
  };
}

export function useCreateHostSchedule() {
  const invalidate = useInvalidateSchedules();
  return useMutation<HostSchedule, Error, HostScheduleInput>({
    mutationFn: (data) => apiClient.post("/api/v1/host-schedules", data),
    onSuccess: invalidate,
  });
}

export function useUpdateHostSchedule() {
  const invalidate = useInvalidateSchedules();
  return useMutation<HostSchedule, Error, { id: string; data: Partial<HostScheduleInput> & { enabled?: boolean } }>({
    mutationFn: ({ id, data }) => apiClient.put(`/api/v1/host-schedules/${id}`, data),
    onSuccess: invalidate,
  });
}

export function useDeleteHostSchedule() {
  const invalidate = useInvalidateSchedules();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/host-schedules/${id}`),
    onSuccess: invalidate,
  });
}

export function useRunHostScheduleNow() {
  const invalidate = useInvalidateSchedules();
  return useMutation<HostExecutionDetail, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/host-schedules/${id}:run-now`, {}),
    onSuccess: invalidate,
  });
}

/** Which platforms a set of machines' OS families allow; a Linux script
 * also fits machines whose OS was never stated (mirrors the backend). */
export function scriptFits(platform: ScriptPlatform, osFamily: string | null): boolean {
  if (platform === "linux") return osFamily === "linux" || osFamily === null;
  return osFamily === platform;
}

export interface RenderedScript {
  script_id: string;
  version: number;
  shell: "sh" | "powershell";
  script: string;
}

/** The script with its parameters filled, to paste through RustDesk on a
 * machine without SSH. Audited on the backend; never stored. */
export function useRenderHostScript() {
  return useMutation<RenderedScript, Error, { id: string; parameter_values: Record<string, string | null> }>({
    mutationFn: ({ id, parameter_values }) => apiClient.post(`/api/v1/host-scripts/${id}:render`, { parameter_values }),
  });
}

/** System script variants are keyed "<action>:<platform>". */
export function systemScriptFor(scripts: HostScript[] | undefined, action: string, platform: ScriptPlatform) {
  return scripts?.find((s) => s.system_key === `${action}:${platform}`) ?? null;
}
