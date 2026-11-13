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

import { apiErrorText } from "@/lib/apiErrorText";

import {
  useClearServerKey,
  useFillServerPublicKey,
  useStoreServerKey,
  type Server,
} from "@/hooks/useServers";

export type ServerKeyVaultStatus =
  | "idle"
  | "storing"
  | "filling"
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
  /** Optional public half (.pub): required by the backend only when it can't
   * read the private key (passphrase, unknown format) to check rule 3. */
  pastedPublicKey: string;
  setPastedPublicKey: (value: string) => void;
  /** Other machines already sharing this row's key (pre-rule-3 rows). */
  duplicateKeyWith: string[];
  /** Key in ForgeVault, public half unknown: rule 3 can't check this row. */
  publicKeyUnknown: boolean;
  /** Reads the public half from the vault key (public only) and stores it. */
  fillPublicKey: () => void;
  /** Outcome of the last completed action, for the section's status line. */
  message: string | null;
  error: string | null;
  storePasted: () => void;
  requestClear: () => void;
  cancelClear: () => void;
  confirmClear: () => void;
}

export function useServerKeyVaultViewModel(server: Server): ServerKeyVaultViewModel {
  const [status, setStatus] = useState<ServerKeyVaultStatus>("idle");
  const [pastedKey, setPastedKey] = useState("");
  const [pastedPublicKey, setPastedPublicKey] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const storeKey = useStoreServerKey();
  const clearKey = useClearServerKey();
  const fillKey = useFillServerPublicKey();

  const fail = useCallback((err: Error) => {
    setStatus("error");
    // The backend's message as is (e.g. 409 SSH_KEY_IN_USE names the machine
    // that already has this key), never the generic "failed with status".
    setError(apiErrorText(err));
    setMessage(null);
  }, []);

  const succeed = useCallback((text: string) => {
    setStatus("idle");
    setError(null);
    setMessage(text);
  }, []);

  const storePasted = useCallback(() => {
    const material = pastedKey.trim();
    if (!material) return;
    setStatus("storing");
    setError(null);
    storeKey.mutate(
      { id: server.id, private_key: material, public_key: pastedPublicKey.trim() || null },
      {
        onSuccess: () => {
          setPastedKey("");
          setPastedPublicKey("");
          succeed("Pasted key stored encrypted.");
        },
        onError: fail,
      },
    );
  }, [pastedKey, pastedPublicKey, storeKey, server.id, succeed, fail]);

  const fillPublicKey = useCallback(() => {
    setStatus("filling");
    setError(null);
    fillKey.mutate(server.id, {
      onSuccess: () => succeed("Public key filled in from the vault key."),
      onError: fail,
    });
  }, [fillKey, server.id, succeed, fail]);

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
    () => status === "storing" || status === "clearing" || status === "filling",
    [status],
  );

  return {
    status,
    isBusy,
    vaulted: server.private_key_stored,
    hasKeyPath: Boolean(server.ssh_key_path),
    pastedKey,
    setPastedKey,
    pastedPublicKey,
    setPastedPublicKey,
    duplicateKeyWith: server.duplicate_key_with ?? [],
    publicKeyUnknown: Boolean(server.key_public_unknown),
    fillPublicKey,
    message,
    error,
    storePasted,
    requestClear,
    cancelClear,
    confirmClear,
  };
}
