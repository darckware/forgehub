import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/** Human-confirmed per-agent configuration. Backend remains the authority. */
export const DIRECT_DURATIONS = [0, 1, 4, 24] as const;
export const DIRECT_PURPOSES = ["development", "support"] as const;
const PATH = "/api/v1/remote-access/direct";
const KEY = ["remote-access", "direct"];
const AGENTS_KEY = [...KEY, "agents"];
const CONTROL_KEY = [...KEY, "control"];

export type DirectPurpose = (typeof DIRECT_PURPOSES)[number];
export type DirectDuration = (typeof DIRECT_DURATIONS)[number];

export interface DirectAccess {
  id: string;
  agent_id: string;
  agent_name: string;
  purpose: DirectPurpose | null;
  allow_elevation: boolean;
  reason: string | null;
  machines: { id: string; name: string; sensitive: boolean }[];
  granted_by: string | null;
  opened_at: string;
  expires_at: string | null;
  open_ended: boolean;
  all_machines: boolean;
  duration_hours: DirectDuration;
}

export interface DirectAccessInput {
  all_machines: boolean;
  server_ids: string[];
  group_ids: string[];
  reason: string | null;
  purpose: DirectPurpose | null;
  duration_hours: DirectDuration;
  allow_elevation: boolean;
  confirm_sensitive: boolean;
}

/** An active agent: on the list or not, and the code of why it can't use an
 * access -- `unsupported_reason` for free commands (run_remote_command),
 * `scripts_unsupported_reason` for library scripts (run_maintenance_script). */
export interface DirectAgent {
  id: string;
  name: string;
  runtime_type: string | null;
  allowed: boolean;
  unsupported_reason: string | null;
  scripts_unsupported_reason?: string | null;
  configuration: DirectAccess | null;
}

export interface DirectAgentRemoved {
  agent_id: string;
  closed_accesses: number;
  running_commands: number;
  notice: string;
}

/** The pause of every agent's access to machines through ForgeHub. */
export interface AgentAccessControl {
  paused: boolean;
  paused_at: string | null;
  paused_by: string | null;
  reason: string | null;
}

export function useDirectAgents() {
  return useQuery({ queryKey: AGENTS_KEY, queryFn: () => apiClient.get<DirectAgent[]>(`${PATH}/agents`), refetchInterval: 30_000 });
}

export function useConfigureDirectAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ agentId, input }: { agentId: string; input: DirectAccessInput }) =>
      apiClient.put<DirectAgent>(`${PATH}/agents/${agentId}`, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRemoveDirectAgent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.delete<DirectAgentRemoved>(`${PATH}/agents/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useAgentAccessControl() {
  return useQuery({
    queryKey: CONTROL_KEY, queryFn: () => apiClient.get<AgentAccessControl>(`${PATH}/control`), refetchInterval: 30_000,
  });
}

export function usePauseAgentAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => apiClient.post<AgentAccessControl>(`${PATH}/control:pause`, { reason: reason || null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONTROL_KEY }),
  });
}

export function useResumeAgentAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<AgentAccessControl>(`${PATH}/control:resume`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: CONTROL_KEY }),
  });
}

export function useDirectAccesses() {
  return useQuery({ queryKey: KEY, queryFn: () => apiClient.get<DirectAccess[]>(PATH), refetchInterval: 30_000 });
}
