# ForgeVault-only SSH keys

## Intent

ForgeVault is the only persistent source for private keys used by ForgeHub Remote Access. The host filesystem and ForgeHub database must not keep durable copies after a key is available and verified in ForgeVault. This prevents the same machine credential from being scattered across `/root/agents`, profile directories, and the ForgeHub database.

## Goals

- Generate new keys in a private temporary directory on `/dev/shm`, store them in ForgeVault, and remove the temporary files before returning.
- Install only the public key on a remote machine.
- Use `ssh_key_ref` and a short-lived `ssh-agent` for remote access.
- For legacy keys, verify authentication with the ForgeVault key before clearing database copies or deleting the local private-key file.
- Remove the ForgeHub writer that recreates `/root/agents/aegis/server-management/ssh_keys`.
- Retain audit evidence of migrated paths and preserve existing server rows.

## Non-goals and constraints

- Do not rotate or revoke the remote machine's authorized keys as part of storage cleanup.
- Do not change the VPS's own `/root/.ssh/id_ed25519` identity.
- Do not fabricate keys for `host-pve01` or `host-pve02`: their recorded files are absent and they have no ForgeVault key. Their access must be configured again when reachable.
- The two Aegis profile keys outside `/root/agents` are a separate operational identity surface; do not delete them as a side effect of the ForgeHub change.
- Do not print, log, or commit private-key contents.

## Approaches

1. Keep the existing file-first flow and store a second copy in ForgeVault. This preserves compatibility but keeps the duplication that prompted the request.
2. Generate keys under `/dev/shm`, write directly to ForgeVault through the host bridge, and pass only public keys to installation flows. Migrate legacy files only after a strict Vault-only login succeeds. **Selected**, because ForgeVault becomes the durable source and the existing ephemeral-agent path can use the key without a file.
3. Delete `/root/agents` before changing generation and migration. Rejected because current code still writes there and two server rows still refer to it.

## Behavior

- The bridge generates an Ed25519 key in a mode-0700 `/dev/shm` directory, stores the private half in ForgeVault, returns only the secret id and public half, and removes its temporary directory in all outcomes.
- Install, preparation, and rotation flows use the Vault secret id for verification and subsequent SSH operations. Rotation creates a separate Vault secret so the old key stays usable until the new key is verified.
- The legacy migration route stores a local key in ForgeVault, performs the existing strict probe, then clears `ssh_key_path` and the encrypted database fallback, removes the local private and public files, and records the old path in the audit event.
- If the Vault probe fails, the old local key and database reference remain available for retry; cleanup does not proceed.
- Once the new code is deployed and every actual key file under `/root/agents` is either verified in ForgeVault or explicitly classified as an orphan, the directory can be removed. Missing Proxmox keys remain a reconfiguration blocker, not a reason to invent credentials.

## Verification

- Review the diff and run non-test static checks for the changed Python and TypeScript code.
- Inspect the live ForgeHub server rows for legacy paths and Vault references before cleanup.
- After migration, confirm ForgeHub's active SSH command uses `IdentityAgent`, the local key files are absent, and `/root/agents` is gone.
- No deployment or removal occurs until the reviewed code is ready and the Vault-only connection checks succeed for every migrated row.
