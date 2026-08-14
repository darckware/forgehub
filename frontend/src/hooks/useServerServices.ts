/**
 * Web services registered on a server (`company.server_services`), plus the
 * port scan that helps register them.
 *
 * The URL is built by the backend from the parent server's current address and
 * arrives ready to open -- the frontend never concatenates an IP with a port,
 * so a server that changes IP does not leave stale links behind here.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
import { apiClient } from "@/lib/api";

export interface ServerService {
  id: string;
  server_id: string;
  name: string;
  port: number;
  scheme: "http" | "https";
  path: string | null;
  description: string | null;
  /** Built server-side, e.g. "http://172.15.2.3:8000/admin". */
  url: string;
  created_at: string;
  updated_at: string;
}

export interface ServerServiceInput {
  name: string;
  port: number;
  scheme: "http" | "https";
  path?: string | null;
  description?: string | null;
}

export interface ServerPortScanEntry {
  port: number;
  scheme: "http" | "https";
  registered: boolean;
  /** False for ports that answer TCP but speak their own protocol (5432,
   * 3306, 27017) -- reported, never offered as a link. */
  likely_web: boolean;
}

export interface ServerPortScanResult {
  server_id: string;
  scanned: number;
  open_ports: ServerPortScanEntry[];
}

export const serverServiceSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(120),
  port: z
    .number({ invalid_type_error: "Port must be a number between 1 and 65535" })
    .int()
    .min(1, "Port must be between 1 and 65535")
    .max(65535, "Port must be between 1 and 65535"),
  scheme: z.enum(["http", "https"]),
  path: z.string().trim().max(255).optional(),
});

export type ServerServiceFormValues = z.infer<typeof serverServiceSchema>;

const servicesKey = (serverId: string) => ["servers", serverId, "services"] as const;

export function useServerServices(serverId: string | undefined, enabled = true) {
  return useQuery<ServerService[]>({
    queryKey: servicesKey(serverId ?? ""),
    queryFn: () => apiClient.get(`/api/v1/servers/${serverId}/services`),
    enabled: Boolean(serverId) && enabled,
    staleTime: 30_000,
  });
}

export function useCreateServerService(serverId: string) {
  const qc = useQueryClient();
  return useMutation<ServerService, Error, ServerServiceInput>({
    mutationFn: (data) => apiClient.post(`/api/v1/servers/${serverId}/services`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: servicesKey(serverId) }),
  });
}

export function useUpdateServerService(serverId: string) {
  const qc = useQueryClient();
  return useMutation<ServerService, Error, { id: string; data: Partial<ServerServiceInput> }>({
    mutationFn: ({ id, data }) => apiClient.put(`/api/v1/servers/${serverId}/services/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: servicesKey(serverId) }),
  });
}

export function useDeleteServerService(serverId: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/servers/${serverId}/services/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: servicesKey(serverId) }),
  });
}

/** TCP-connect scan of common ports. A mutation, not a query: it is an action
 * with a cost on the network, run when asked and never on a cache refresh. */
export function useScanServerPorts(serverId: string) {
  return useMutation<ServerPortScanResult, Error, void>({
    mutationFn: () => apiClient.post(`/api/v1/servers/${serverId}/services:scan`),
  });
}
