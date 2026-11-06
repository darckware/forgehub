import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/** Direct remote access (2026-11-06): a human admin opens it for an agent on
 * chosen machines for 1, 4 or 24 hours. Durations and rules live in the
 * backend (core/remote_authority.py); these lists only feed the form. */
export const DIRECT_DURATIONS = [1, 4, 24] as const;
export const DIRECT_PURPOSES = ["development", "support"] as const;
/** Only these runtimes receive a run credential. Hermes stays out: Marcelo's call. */
export const DIRECT_RUNTIMES: readonly string[] = ["claude", "codex", "agy"];
const PATH = "/api/v1/remote-access/direct";
const KEY = ["remote-access", "direct"];

export type DirectPurpose = (typeof DIRECT_PURPOSES)[number];
export type DirectDuration = (typeof DIRECT_DURATIONS)[number];

export interface DirectAccess {
  id: string;
  agent_id: string;
  agent_name: string;
  purpose: DirectPurpose;
  allow_elevation: boolean;
  reason: string | null;
  machines: { id: string; name: string; sensitive: boolean }[];
  granted_by: string | null;
  opened_at: string;
  expires_at: string;
}

export interface DirectAccessInput {
  agent_id: string;
  server_ids: string[];
  group_ids: string[];
  reason: string;
  purpose: DirectPurpose;
  duration_hours: DirectDuration;
  allow_elevation: boolean;
  confirm_sensitive: boolean;
}

export interface DirectAccessClosed {
  id: string;
  closed_at: string;
  running_commands: number;
  notice: string;
}

export function useDirectAccesses() {
  return useQuery({ queryKey: KEY, queryFn: () => apiClient.get<DirectAccess[]>(PATH), refetchInterval: 30_000 });
}

export function useOpenDirectAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: DirectAccessInput) => apiClient.post<DirectAccess>(PATH, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useCloseDirectAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiClient.post<DirectAccessClosed>(`${PATH}/${id}:close`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
