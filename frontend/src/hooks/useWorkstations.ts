import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Workstation {
  id: string;
  client_id: string;
  hostname: string | null;
  os_kind: string;
  device_token_issued_at: string;
  device_token_revoked_at: string | null;
  /** Serialized by the backend's `device_token_active` computed_field --
   * `device_token_revoked_at === null`, computed server-side so the frontend
   * never has to duplicate that rule. */
  device_token_active: boolean;
  last_report_at: string | null;
  last_seen_agent_version: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkstationCreate {
  client_id: string;
  os_kind: string;
}

/** Returned exactly once, at issuance (create, reissue) -- the only response
 * that ever carries the raw device token. */
export interface WorkstationTokenIssued {
  workstation: Workstation;
  device_token: string;
}

const WORKSTATIONS_KEY = ["workstations"] as const;

export function useWorkstations(clientId?: string) {
  return useQuery<Workstation[]>({
    queryKey: [...WORKSTATIONS_KEY, clientId],
    queryFn: () =>
      apiClient.get("/api/v1/workstations", {
        params: clientId ? { client_id: clientId } : undefined,
      }),
    staleTime: 30_000,
  });
}

export function useCreateWorkstation() {
  const qc = useQueryClient();
  return useMutation<WorkstationTokenIssued, Error, WorkstationCreate>({
    mutationFn: (data) => apiClient.post("/api/v1/workstations", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORKSTATIONS_KEY }),
  });
}

export function useDeleteWorkstation() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/workstations/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORKSTATIONS_KEY }),
  });
}

export function useReissueWorkstationToken() {
  const qc = useQueryClient();
  return useMutation<WorkstationTokenIssued, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/workstations/${id}/token:reissue`),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORKSTATIONS_KEY }),
  });
}

export function useRevokeWorkstationToken() {
  const qc = useQueryClient();
  return useMutation<Workstation, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/workstations/${id}/token:revoke`),
    onSuccess: () => qc.invalidateQueries({ queryKey: WORKSTATIONS_KEY }),
  });
}
