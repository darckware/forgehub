/**
 * ViewModel hook for a server row's SSH key vault (§21 of the org's
 * `05-FRONTEND-ARCHITECTURE-AND-CODING-STANDARD.md`, same shape as
 * `useImprovePromptViewModel.ts` — read that one first for why a hook rather
 * than a class).
 *
 * The section it backs has four actions that all touch the same row, a paste
 * field, and a confirmation step, so it is exactly the case the standard asks
 * to pull out of the component: `ServersPage`'s edit dialog only renders what
 * this returns.
 *
 * `status` names the step in flight rather than carrying one boolean per
 * mutation, because the steps are mutually exclusive — a row cannot be
 * restoring and clearing at once, and a `isRestoring && isClearing` state
 * should not even be expressible.
 */
import { useCallback, useMemo, useState } from "react";

import {
  useBackupServerKey,
  useClearServerKey,
  useRestoreServerKey,
  useStoreServerKey,
  type Server,
} from "@/hooks/useServers";

export type ServerKeyVaultStatus =
  | "idle"
  | "backing_up"
  | "restoring"
  | "storing"
  | "confirming_clear"
  | "clearing"
  | "error";

export interface ServerKeyVaultViewModel {
  status: ServerKeyVaultStatus;
  /** Any mutation in flight — drives the disabled/spinner state of every button. */
  isBusy: boolean;
  /** An encrypted copy exists on the row. */
  vaulted: boolean;
  /** The row points at an identity file, so there is something to read/write. */
  hasKeyPath: boolean;
  pastedKey: string;
  setPastedKey: (value: string) => void;
  /** Outcome of the last completed action, for the section's status line. */
  message: string | null;
  error: string | null;
  backup: () => void;
  restore: () => void;
  storePasted: () => void;
  requestClear: () => void;
  cancelClear: () => void;
  confirmClear: () => void;
}

export function useServerKeyVaultViewModel(server: Server): ServerKeyVaultViewModel {
  const [status, setStatus] = useState<ServerKeyVaultStatus>("idle");
  const [pastedKey, setPastedKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const backupKey = useBackupServerKey();
  const restoreKey = useRestoreServerKey();
  const storeKey = useStoreServerKey();
  const clearKey = useClearServerKey();

  const fail = useCallback((err: Error) => {
    setStatus("error");
    setError(err.message);
    setMessage(null);
  }, []);

  const succeed = useCallback((text: string) => {
    setStatus("idle");
    setError(null);
    setMessage(text);
  }, []);

  const backup = useCallback(() => {
    setStatus("backing_up");
    setError(null);
    backupKey.mutate(server.id, {
      onSuccess: (result) => succeed(`Key read from ${result.key_path} and stored encrypted.`),
      onError: fail,
    });
  }, [backupKey, server.id, succeed, fail]);

  const restore = useCallback(() => {
    setStatus("restoring");
    setError(null);
    restoreKey.mutate(server.id, {
      onSuccess: (result) =>
        succeed(
          result.written.length > 0
            ? `Restored to ${result.written.join(", ")}.`
            : "Nothing was written.",
        ),
      onError: fail,
    });
  }, [restoreKey, server.id, succeed, fail]);

  const storePasted = useCallback(() => {
    const material = pastedKey.trim();
    if (!material) return;
    setStatus("storing");
    setError(null);
    storeKey.mutate(
      { id: server.id, private_key: material },
      {
        onSuccess: () => {
          setPastedKey("");
          succeed("Pasted key stored encrypted.");
        },
        onError: fail,
      },
    );
  }, [pastedKey, storeKey, server.id, succeed, fail]);

  const requestClear = useCallback(() => setStatus("confirming_clear"), []);
  const cancelClear = useCallback(() => setStatus("idle"), []);

  const confirmClear = useCallback(() => {
    setStatus("clearing");
    setError(null);
    clearKey.mutate(server.id, {
      onSuccess: () => succeed("Vaulted copy removed. The file on the host was not touched."),
      onError: fail,
    });
  }, [clearKey, server.id, succeed, fail]);

  const isBusy = useMemo(
    () => status === "backing_up" || status === "restoring" || status === "storing" || status === "clearing",
    [status],
  );

  return {
    status,
    isBusy,
    vaulted: server.private_key_stored,
    hasKeyPath: Boolean(server.ssh_key_path),
    pastedKey,
    setPastedKey,
    message,
    error,
    backup,
    restore,
    storePasted,
    requestClear,
    cancelClear,
    confirmClear,
  };
}
