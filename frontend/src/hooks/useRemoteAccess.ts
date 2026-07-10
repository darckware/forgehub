import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

/**
 * Remote-access domain -- backs the Dashboard's remote-access card. Starts/
 * stops a Cloudflare quick tunnel that exposes the whole app (same origin,
 * see frontend/nginx.conf) at a temporary public URL. See
 * backend/app/api/routes/remote_access.py (admin-only) and host-bridge's
 * /v1/remote-access/* for where the cloudflared process actually lives.
 */

export interface RemoteAccessStatus {
  status: "running" | "stopped" | "error";
  url: string | null;
}

const RESOURCE = "/api/v1/remote-access";

export function useRemoteAccessStatus() {
  return useQuery({
    queryKey: ["remote-access-status"],
    queryFn: () => apiClient.get<RemoteAccessStatus>(`${RESOURCE}/status`),
    // The tunnel is started/stopped from elsewhere too (a server restart
    // tears it down) -- poll so the card doesn't show a stale "running".
    refetchInterval: 15_000,
  });
}

export function useStartRemoteAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<RemoteAccessStatus>(`${RESOURCE}/start`),
    onSuccess: (data) => qc.setQueryData(["remote-access-status"], data),
  });
}

export function useStopRemoteAccess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post<RemoteAccessStatus>(`${RESOURCE}/stop`),
    onSuccess: (data) => qc.setQueryData(["remote-access-status"], data),
  });
}
