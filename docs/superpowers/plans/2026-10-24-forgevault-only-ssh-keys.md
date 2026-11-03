# ForgeVault-only SSH keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ForgeVault the only durable store for ForgeHub-managed SSH private keys and retire `/root/agents` after verified migration.

**Architecture:** The host bridge creates keys in `/dev/shm` and writes them directly to ForgeVault. ForgeHub stores only the secret id and public key, and runs SSH through a temporary agent. A legacy migration path verifies the Vault key before clearing persisted filesystem/database copies.

**Tech Stack:** FastAPI, Python 3.13, SQLAlchemy, Pydantic, React/TypeScript, ForgeVault host bridge.

**Spec:** `docs/superpowers/specs/2026-10-24-forgevault-only-ssh-keys-design.md`

## Global Constraints

- Private-key values must not be printed, logged, or committed.
- Temporary private-key files must be created only under `/dev/shm` with restrictive permissions and removed on success or failure.
- ForgeVault must be verified as the active authentication source before local copies or database fallback values are cleared.
- `host-pve01` and `host-pve02` have no recoverable local key or Vault reference; do not invent or rotate credentials for them.
- Preserve pre-existing user edits in `.gitignore` and `docs/guides/MESSAGES_TELEGRAM_OPERATIONS.md`.
- Do not run tests unless the user asks; use static checks and code/diff inspection for this change.

## Review Focus

- Vault write failure must leave an existing usable key untouched.
- Remote install failure must not replace the server row's active `ssh_key_ref`.
- Rotation must keep the old Vault secret active until the new Vault key logs in.
- Legacy file cleanup must happen only after a strict Vault-only probe succeeds.
- Missing legacy files must not be reported as migrated or silently treated as usable.

---

### Task 1: Bridge key generation and install contract

**Files:**
- Modify: `host-bridge/app.py`
- Modify: `host-bridge/forgevault_proxy.py` only if the current Vault client needs a narrow helper.

- [ ] Add an authenticated bridge operation that generates an Ed25519 pair only in `/dev/shm`, stores the private half directly in ForgeVault, and returns `{ssh_key_ref, public_key, created}` without a file path or private value.
- [ ] Change key installation to accept and install a validated public key instead of generating a persistent pair in `SSH_KEYS_DIR`.
- [ ] Add a constrained legacy-file removal operation for migration, including its `.pub`, with canonical path validation and no parent-directory creation.
- [ ] Ensure temporary key files are removed on every return and error path.

### Task 2: Vault-only backend lifecycles

**Files:**
- Modify: `backend/app/api/routes/server.py`
- Modify: `backend/app/db/models/server.py` only where the stored-key indicator needs to follow `ssh_key_ref`.

- [ ] Use the new bridge operation for server-key installation and station preparation; persist `ssh_key_ref`, public key, and no path or Fernet private copy.
- [ ] Change SSH rotation to create a unique Vault secret, test with that secret id, and switch the server row only after the new key succeeds.
- [ ] Make legacy backup and `keys:to-vault` clear `ssh_key_path` and the encrypted database fallback and remove the old local files only after strict Vault authentication.
- [ ] Prevent the key-restore route from writing a private key back to disk; keep the UI aligned with Vault-only storage.
- [ ] Preserve audit events and existing access rows when a migration fails.

### Task 3: Remove local-path authoring and stale references

**Files:**
- Modify: `backend/app/api/schemas/server.py`
- Modify: `frontend/src/hooks/useServers.ts`
- Modify: `frontend/src/pages/servers/ServerForm.tsx` and key-vault UI as needed.
- Modify: `docs/architecture/REMOTE_ACCESS_SERVERS_UNIFICATION_PLAN.md` and `docs/screens/servers.md`.

- [ ] Remove the editable local private-key path from new server writes while retaining compatibility for the legacy migration reader.
- [ ] Remove restore-to-disk UI actions and update copy to explain Vault-backed access.
- [ ] Update architecture documentation to state ForgeVault-only persistence and the remaining Proxmox reconfiguration blocker.

### Task 4: Live migration and requested directory removal

**Files:**
- No source changes for the operational step beyond Tasks 1–3.

- [ ] Deploy the reviewed ForgeHub/host-bridge changes using the project's deploy workflow.
- [ ] Run the guarded Vault migration for all rows that still have a recoverable local key; retain any row that fails the strict probe.
- [ ] Clear stale path references for already-missing keys without claiming they were migrated.
- [ ] Classify every remaining file under `/root/agents`; migrate any ForgeHub-managed credential into ForgeVault before deleting its local copy.
- [ ] Remove `/root/agents` only after no actual private-key file remains and no active ForgeHub writer targets it.
- [ ] Confirm the running service is healthy, Vault-backed SSH commands resolve to an agent socket, and the requested directory is absent.
