import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Server {
  id: string;
  name: string;
  ip_address: string;
  remote_user: string;
  ssh_port: number;
  ssh_key_path: string | null;
  public_key: string | null;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ServerCreate {
  name: string;
  ip_address: string;
  remote_user: string;
  ssh_port?: number;
  ssh_key_path?: string | null;
  description?: string | null;
}

/** Builds the terminal SSH command for a registered server, picking the auth
 * form from whether a key is on file -- the two modes the inventory supports:
 *
 *  - Key on file  -> `ssh -i <key> ...`: key authentication, no password.
 *  - No key       -> force an interactive password login. The host's
 *    HermesOps-managed ~/.ssh/config hardens 172.15.* to key-only
 *    (`BatchMode yes` + `PasswordAuthentication no`), which would make a bare
 *    `ssh user@ip` fail instantly without ever prompting. We override just
 *    that on the command line -- per connection, never globally -- so the
 *    terminal actually asks for the password.
 */
export function buildSshCommand(server: Server): string {
  const parts = ["ssh"];
  if (server.ssh_key_path) {
    parts.push("-i", server.ssh_key_path);
  } else {
    parts.push(
      "-o", "PubkeyAuthentication=no",
      "-o", "PasswordAuthentication=yes",
      "-o", "BatchMode=no",
    );
  }
  if (server.ssh_port && server.ssh_port !== 22) parts.push("-p", String(server.ssh_port));
  parts.push(`${server.remote_user}@${server.ip_address}`);
  return parts.join(" ");
}

export type ServerUpdate = Partial<ServerCreate>;

export interface ServerImportResult {
  created: number;
  updated: number;
  errors: string[];
}

export type ServerCheckStatus = "online" | "offline" | "no_key";

export interface ServerCheckResult {
  server_id: string;
  status: ServerCheckStatus;
  detail: string;
}

const SERVERS_KEY = ["servers"] as const;

export function useServers() {
  return useQuery<Server[]>({
    queryKey: SERVERS_KEY,
    queryFn: () => apiClient.get("/api/v1/servers"),
    staleTime: 30_000,
  });
}

export function useCreateServer() {
  const qc = useQueryClient();
  return useMutation<Server, Error, ServerCreate>({
    mutationFn: (data) => apiClient.post("/api/v1/servers", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

export function useUpdateServer() {
  const qc = useQueryClient();
  return useMutation<Server, Error, { id: string; data: ServerUpdate }>({
    mutationFn: ({ id, data }) => apiClient.put(`/api/v1/servers/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

export function useDeleteServer() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/servers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

export function useImportServers() {
  const qc = useQueryClient();
  return useMutation<ServerImportResult, Error, string>({
    mutationFn: (csv_text) => apiClient.post("/api/v1/servers/import", { csv_text }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

export interface ServerInstallKeyResult {
  ok: boolean;
  steps: string[];
  error: string | null;
  failed_step: string | null;
  key_path: string | null;
  public_key: string | null;
}

/** One-shot dedicated-key installation (generate on host + ssh-copy-id +
 * verify). The password travels only inside this request. */
export function useInstallServerKey() {
  const qc = useQueryClient();
  return useMutation<
    ServerInstallKeyResult,
    Error,
    { id: string; password: string; remote_user?: string; admin_user?: string | null }
  >({
    mutationFn: ({ id, password, remote_user, admin_user }) =>
      apiClient.post(`/api/v1/servers/${id}/install-key`, {
        password,
        remote_user: remote_user ?? null,
        admin_user: admin_user ?? null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

/** Reads the public key from the row's configured ssh_key_path on the host
 * and persists it into public_key, returning the updated server. */
export function useReadServerPublicKey() {
  const qc = useQueryClient();
  return useMutation<Server, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/servers/${id}/public-key`),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

/** On-demand SSH reachability probe -- not cached/invalidated via react-query
 * since each result is a live, ephemeral snapshot (see backend's
 * ServerCheckResult docstring). Callers track results in local state. */
export function useCheckServer() {
  return useMutation<ServerCheckResult, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/servers/${id}/check`),
  });
}
