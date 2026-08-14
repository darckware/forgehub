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
  /** An encrypted copy of the identity file is vaulted on the row. The key
   * material itself is never sent to the browser -- see the backend's
   * Server.private_key_encrypted note for why the copy exists at all. */
  private_key_stored: boolean;
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
 *  - No key on file -> let the host's own ~/.ssh/config decide, and allow a
 *    password prompt as the fallback. The host's HermesOps-managed config
 *    hardens 172.15.* to key-only (`BatchMode yes` + `PasswordAuthentication
 *    no`), which would make a bare `ssh user@ip` fail instantly without ever
 *    prompting, so those two are overridden here -- per connection, never
 *    globally.
 *
 *    `PubkeyAuthentication=no` used to be in that override set, and was the
 *    bug (2026-08-14): "no key *in ForgeHub's row*" is not "no key on the
 *    host". Every row in the inventory has a NULL ssh_key_path (the keys were
 *    installed by HermesOps' own sync, which writes ~/.ssh/config and never
 *    touches this table), so disabling pubkey auth turned a connection that
 *    works from any shell into a password prompt for a password nobody has --
 *    the account is key-only by design. Dropping it costs nothing in the
 *    genuinely keyless case: ssh simply finds no identity and moves on to the
 *    password prompt.
 */
export function buildSshCommand(server: Server): string {
  const parts = ["ssh"];
  if (server.ssh_key_path) {
    parts.push("-i", server.ssh_key_path);
  } else {
    parts.push(
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

export interface ServerKeyVaultResult {
  server_id: string;
  private_key_stored: boolean;
  key_path: string | null;
  written: string[];
}

/** Reads the identity file from the host and keeps an encrypted copy on the
 * row, so losing the file on disk no longer means losing access to the
 * server (which is exactly what happened to 172.15.2.5 on 2026-07-07). */
export function useBackupServerKey() {
  const qc = useQueryClient();
  return useMutation<ServerKeyVaultResult, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/servers/${id}/key:backup`),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

/** Writes the vaulted key back to the host at the row's ssh_key_path. Fails
 * with 409 when a file is already there -- restoring never overwrites a
 * working identity. */
export function useRestoreServerKey() {
  const qc = useQueryClient();
  return useMutation<ServerKeyVaultResult, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/servers/${id}/key:restore`),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

/** Vaults a pasted private key, for a server whose file this host does not
 * have (recovered from a backup by hand, or living on another machine). */
export function useStoreServerKey() {
  const qc = useQueryClient();
  return useMutation<ServerKeyVaultResult, Error, { id: string; private_key: string }>({
    mutationFn: ({ id, private_key }) => apiClient.put(`/api/v1/servers/${id}/key`, { private_key }),
    onSuccess: () => qc.invalidateQueries({ queryKey: SERVERS_KEY }),
  });
}

/** Drops the vaulted copy. Never touches the file on the host. */
export function useClearServerKey() {
  const qc = useQueryClient();
  return useMutation<ServerKeyVaultResult, Error, string>({
    mutationFn: (id) => apiClient.delete(`/api/v1/servers/${id}/key`),
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
