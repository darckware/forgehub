import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";
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
  /** A passphrase for that key is on file. Like the key, never sent to the
   * browser -- the form renders "stored" from this boolean alone. */
  key_passphrase_stored: boolean;
  /** ForgeHub-side access switch. False parks the server: no status probe, no
   * terminal -- while the key, the vaulted copy and the server itself are all
   * left exactly as they were. */
  access_enabled: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface ServerDetail extends Server {
  /** Decrypted, admin-only, single-server read only. */
  key_passphrase: string | null;
}

export interface ServerCreate {
  name: string;
  ip_address: string;
  remote_user: string;
  ssh_port?: number;
  ssh_key_path?: string | null;
  /** Write-only. Omit to keep whatever is stored (the form never receives it);
   * send "" to clear it. */
  key_passphrase?: string | null;
  access_enabled?: boolean;
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

/** Re-reads a row that was captured earlier -- typically the `Server` a dialog
 * was opened with -- from the live list.
 *
 * A dialog that holds the object it was opened with never sees the result of
 * its own mutations (2026-08-14): the key-vault actions invalidate
 * `["servers"]` and the table below updates, but the captured object does not,
 * so the vault section kept reading "No copy stored" (and "Restore to host"
 * stayed disabled) after a key had just been stored, until the dialog was
 * closed and reopened. Same for the public key the "copy public key" button
 * persists.
 *
 * Falls back to the captured row while the list is still loading, and if the
 * row is gone -- an open dialog should keep rendering what it had rather than
 * blank out because the row was deleted in another tab.
 */
export function resolveLiveServer(servers: Server[] | undefined, captured: Server): Server {
  return servers?.find((s) => s.id === captured.id) ?? captured;
}

export type ServerUpdate = Partial<ServerCreate>;

/** Validation for the create/edit form (`ServerForm.tsx`). Colocated with the
 * domain hook, per the coding standard's rule for Zod schemas.
 *
 * `key_passphrase` is intentionally unconstrained: any string is a valid
 * passphrase, and an empty one is the documented way to clear a stored value.
 */
export const serverFormSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(255),
  ip_address: z.string().trim().min(1, "IP address is required").max(100),
  remote_user: z.string().trim().min(1, "Remote user is required").max(100),
  // Registered with `valueAsNumber`, so the field arrives here already a
  // number (NaN when blank, which fails the type check with the message
  // below) -- no z.coerce, which would leave input and output types different
  // and force a three-generic useForm.
  ssh_port: z
    .number({ invalid_type_error: "Port must be a number between 1 and 65535" })
    .int()
    .min(1, "Port must be between 1 and 65535")
    .max(65535, "Port must be between 1 and 65535"),
  ssh_key_path: z.string().trim().max(500).optional(),
  key_passphrase: z.string().optional(),
  description: z.string().optional(),
});

export type ServerFormValues = z.infer<typeof serverFormSchema>;

export interface ServerImportResult {
  created: number;
  updated: number;
  errors: string[];
}

export type ServerCheckStatus = "online" | "offline" | "unreachable" | "auth_failed" | "key_missing" | "no_key" | "disabled" | "probe_error";

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

/** Single-server read. Admin-only on the backend, and the only response that
 * carries `key_passphrase` decrypted -- the list never does. Mirrors how the
 * agent detail query feeds the ForgeRouter API key card. Not used for the
 * table; only the edit form needs it. */
export function useServer(id: string | undefined) {
  return useQuery<ServerDetail>({
    queryKey: [...SERVERS_KEY, id],
    queryFn: () => apiClient.get(`/api/v1/servers/${id}`),
    enabled: Boolean(id),
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

/** Turns ForgeHub's use of a server on or off without deleting anything --
 * no key removed here, nothing revoked on the server itself. Returns the
 * updated row. */
export function useToggleServerAccess() {
  const qc = useQueryClient();
  return useMutation<Server, Error, string>({
    mutationFn: (id) => apiClient.post(`/api/v1/servers/${id}/access:toggle`),
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

export interface ServerStatusProbe {
  /** Last result per server id. Absent means "not probed yet". */
  statuses: Record<string, ServerCheckResult>;
  checkingIds: Set<string>;
  isChecking: boolean;
  checkOne: (id: string) => void;
  /** Probes every *enabled* server. A parked one is skipped rather than
   * probed: the backend answers "disabled" without touching the network
   * anyway, and a bulk check should not spend a request per server it was told
   * not to use. */
  checkAll: (servers: Server[]) => void;
  /** Record the parked state without a round trip, for the moment the access
   * switch is flipped. */
  markDisabled: (id: string) => void;
  /** Forget a result, so the row reads "not checked" until re-probed. */
  clearStatus: (id: string) => void;
}

/** Shared probe state for every screen that shows live server status: the
 * Servers page's table and the Workspace toolbar's SSH menu.
 *
 * A hook rather than a copy in each screen because the tricky part is not the
 * request but the bookkeeping around it -- see checkOne's note on mutateAsync,
 * which is a bug the second copy would have had to rediscover.
 */
export function useServerStatusProbe(): ServerStatusProbe {
  const checkServer = useCheckServer();
  const [statuses, setStatuses] = useState<Record<string, ServerCheckResult>>({});
  const [checkingIds, setCheckingIds] = useState<Set<string>>(new Set());

  const checkOne = useCallback(
    (id: string) => {
      setCheckingIds((prev) => new Set(prev).add(id));
      // mutateAsync's returned promise is bound to this specific call, unlike
      // mutate()'s { onSuccess, onSettled } options -- those are stored on the
      // single shared mutation observer, so firing many mutate() calls back to
      // back (checkAll below) would leave only the *last* call's callbacks
      // installed, silently dropping updates for every earlier server.
      checkServer
        .mutateAsync(id)
        .then((result) => setStatuses((prev) => ({ ...prev, [id]: result })))
        .catch((error: unknown) => {
          setStatuses((prev) => ({
            ...prev,
            [id]: {
              server_id: id,
              status: "probe_error",
              detail: error instanceof Error ? error.message : "Server status probe failed",
            },
          }));
        })
        .finally(() =>
          setCheckingIds((prev) => {
            const next = new Set(prev);
            next.delete(id);
            return next;
          }),
        );
    },
    [checkServer],
  );

  const checkAll = useCallback(
    (servers: Server[]) => {
      servers.filter((s) => s.access_enabled).forEach((s) => checkOne(s.id));
    },
    [checkOne],
  );

  const markDisabled = useCallback((id: string) => {
    setStatuses((prev) => ({
      ...prev,
      [id]: {
        server_id: id,
        status: "disabled",
        detail: "Access is turned off in ForgeHub — the key is untouched",
      },
    }));
  }, []);

  const clearStatus = useCallback((id: string) => {
    setStatuses((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  }, []);

  return {
    statuses,
    checkingIds,
    isChecking: checkingIds.size > 0,
    checkOne,
    checkAll,
    markDisabled,
    clearStatus,
  };
}
