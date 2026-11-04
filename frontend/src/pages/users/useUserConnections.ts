import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface UserConnection {
  id: string; ip_address: string | null; user_agent: string | null; device_summary: string | null;
  agent_name: string | null; remember_me: boolean; is_active: boolean; is_current: boolean;
  created_at: string; last_activity_at: string; expires_at: string;
}

export function useUserConnections(userId: string) {
  const qc = useQueryClient();
  const key = ["users", userId, "sessions"];
  const query = useQuery({ queryKey: key, queryFn: () => apiClient.get<UserConnection[]>(`/api/v1/users/${userId}/sessions`) });
  const revoke = useMutation({
    mutationFn: (id: string | null) => apiClient.delete<void>(`/api/v1/users/${userId}/sessions${id ? `/${id}` : ""}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });
  return { query, revoke };
}
