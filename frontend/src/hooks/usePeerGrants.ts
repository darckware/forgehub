import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface PeerGrant {
  id: string;
  workstation_a_id: string;
  workstation_b_id: string;
  granted_by_user_id: string | null;
  granted_at: string;
  revoked_at: string | null;
}

const PEER_GRANTS_KEY = ["peer-grants"] as const;

export function usePeerGrants(clientId: string) {
  return useQuery<PeerGrant[]>({
    queryKey: [...PEER_GRANTS_KEY, clientId],
    queryFn: () =>
      apiClient.get("/api/v1/peer-grants", {
        params: { client_id: clientId },
      }),
    enabled: Boolean(clientId),
  });
}

export function useCreatePeerGrant() {
  const queryClient = useQueryClient();
  return useMutation<
    PeerGrant,
    Error,
    { workstationAId: string; workstationBId: string }
  >({
    mutationFn: ({ workstationAId, workstationBId }) =>
      apiClient.post("/api/v1/peer-grants", {
        workstation_a_id: workstationAId,
        workstation_b_id: workstationBId,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PEER_GRANTS_KEY }),
  });
}

export function useRevokePeerGrant() {
  const queryClient = useQueryClient();
  return useMutation<PeerGrant, Error, string>({
    mutationFn: (grantId) =>
      apiClient.post(`/api/v1/peer-grants/${grantId}:revoke`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: PEER_GRANTS_KEY }),
  });
}
