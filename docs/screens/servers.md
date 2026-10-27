# Screen: Servers

## Route & Purpose

- Route: `/servers` (registered in `frontend/src/App.tsx:120`, nav entry in `frontend/src/components/layout/navSections.ts:141` under **Operations**, icon `Network`, permission module `servers`).
- Component: `frontend/src/pages/servers/index.tsx` (`ServersPage`, default export).
- Purpose: the inventory of SSH-reachable machines. It answers four questions and lets an operator act on each: *which servers exist* (name, IP, user, port, description), *which are actually reachable right now* (live probe per row), *how do I get a shell on one* (hands the built `ssh` command to the Workspace terminal), and *where the private key lives* — ForgeVault is the only persistent store; the host bridge loads key material only into temporary memory for SSH operations.
- One of ForgeHub's own DB-backed domains (`company.servers`), but deliberately standalone: no FK into the product/version/project traceability chain, since this is infrastructure, not planned work (see the model docstring, `backend/app/db/models/server.py:1-7`).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/servers/index.tsx` (`ServersPage`) | Page shell: header with "Check status"/"Import CSV"/"New server"/assistant toggle, the inventory table, and the four modals/dialogs. Owns `formTarget`/`importOpen`/`deleteTarget`/`installTarget`/`statuses`/`checkingIds` local state. |
| `frontend/src/pages/servers/index.tsx` (`ModalShell`, local) | Shared modal chrome (backdrop + card + close button) used by the three modals below. |
| `frontend/src/pages/servers/ServerForm.tsx` (`ServerForm`) | Create/edit form without a local SSH path; private keys are managed in ForgeVault. Editable fields read from `form` (seeded once, so a refetch never overwrites typing); the read-only blocks read from `live` (`resolveLiveServer`), so an action taken *inside* the dialog is visible without reopening it. |
| `frontend/src/pages/servers/index.tsx` (`KeyVaultSection`, local, `:82`) | The key vault UI. A pure render of `useServerKeyVaultViewModel` with no state of its own — the §21 ViewModel pair described in `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`. |
| `frontend/src/hooks/useServerKeyVaultViewModel.ts` (`useServerKeyVaultViewModel`) | Paste a key into ForgeVault or remove its ForgeVault reference.
| `frontend/src/pages/servers/index.tsx` (`InstallKeyModal`, local, `:331`) | One-shot dedicated-key installation: admin/registered-user choice, password field, step-by-step result list. Mirrors `/root/.hermes/scripts/configure_ssh.sh`, parameterized. |
| `frontend/src/pages/servers/index.tsx` (`ImportCsvModal`, local, `:510`) | CSV paste/file-pick bulk upsert, with a created/updated/errors result block. |
| `frontend/src/pages/servers/index.tsx` (`StatusBadge`, local, `:475`) | Renders one probe result: Online / Offline / No key / Checking… / "not checked". |
| `frontend/src/components/ui/confirm-dialog.tsx` (`ConfirmDialog`) | Both destructive confirmations: deleting a server, and removing the vaulted key copy. |

## Data & API Calls

| Data shown / action | Source hook (`frontend/src/hooks/useServers.ts` unless noted) | Backend endpoint | Method |
|---|---|---|---|
| Inventory table | `useServers()` (30s `staleTime`) | `/api/v1/servers` | GET |
| Create a server | `useCreateServer()` | `/api/v1/servers` | POST |
| Save an edit | `useUpdateServer()` | `/api/v1/servers/{id}` | PUT |
| Delete a server | `useDeleteServer()` | `/api/v1/servers/{id}` | DELETE |
| Bulk CSV upsert | `useImportServers()` | `/api/v1/servers/import` | POST |
| Live reachability probe | `useCheckServer()` | `/api/v1/servers/{id}/check` | POST |
| Install a dedicated key | `useInstallServerKey()` | `/api/v1/servers/{id}/install-key` | POST |
| Vault a pasted key | `useStoreServerKey()` | `/api/v1/servers/{id}/key` | PUT |
| Drop the vaulted copy | `useClearServerKey()` | `/api/v1/servers/{id}/key` | DELETE |

Every mutation except the probe invalidates the `["servers"]` query key on success — which is what `resolveLiveServer` (`useServers.ts`) turns into a visible update inside an already-open dialog, by re-reading the captured row from that same list instead of trusting the object the dialog was opened with. `useCheckServer` deliberately does not: each result is an ephemeral snapshot, so `ServersPage` keeps them in local `statuses` state instead of the query cache.

Backend (`backend/app/api/routes/server.py`):

- `check_server_status` (`:198`) probes **through the host bridge first** (`_check_via_bridge` → `/v1/servers/check-status`, a TCP check plus a real `ssh … true` with the host's own keys) and only falls back to the in-container `paramiko` probe (`_probe_ssh`, `:111`) when the bridge is unreachable. The reason is in the module comment (`:61-68`): the Workspace terminal's `ssh` runs on the *host*, so the host's default identities are what "ready to use" actually means — probing from inside the container can only ever validate an explicit `ssh_key_path`, which is why servers that connect fine from the terminal used to report "No key".
- `install_server_key` (`:222`) delegates the whole generate/copy/verify sequence to the bridge and, on success, writes `ssh_key_path` + `public_key` back onto the row. The password is forwarded in the request body and never persisted or logged.
- `read_and_store_public_key` (`:283`) reads `<ssh_key_path>.pub` on the host and persists it — the fallback for servers whose key was installed by hand, so the row still records what is in `authorized_keys`.
- The four vault routes (`:357`, `:388`, `:412`, `:449`) are the round trip described below. All four are `Depends(get_current_admin)`.
- `import_servers` (`:464`) upserts by exact `SERVER_NAME`; `SSH port` is not part of the CSV format and is left untouched on update.

Host bridge (`host-bridge/app.py`), for the vault:

- `read_private_key` (`:2785`) reads the identity file (and its `.pub` if present), rejecting anything that does not contain `PRIVATE KEY`.
- `write_private_key` (`:2809`) creates the file with `O_EXCL` and mode `0600` from the start — writing then `chmod`-ing would leave a window where the private key is world-readable — and **409s rather than overwriting** an existing file.
- `_resolve_key_path` (`:2759`) validates the path against `PRIVATE_KEY_ROOTS` (`/root/.ssh`, `/root/agents`, `/root/.hermes/profiles`, `SSH_KEYS_DIR`) **after** `os.path.realpath`, and rejects a path ending in `.pub`.

## Actions Available

**Page level**
- **Check status** — fires `checkOne` for every row (`checkAll`, `:611`). Also runs once automatically on first load (`:615-621`, guarded by `autoCheckedRef` so it never repeats).
- **Import CSV** — opens `ImportCsvModal`; paste text or pick a `.csv` file. Header must include `SERVER_NAME,SERVER_IP,REMOTE_USER`; rows matching an existing name are updated in place.
- **New server** — opens `ServerFormModal` with an empty form.

**Per row**
- **Open SSH terminal** (terminal icon, shown only while the row's probe says `online`) — navigates to `/workspace` with `state.openSsh = { label, command: buildSshCommand(s) }`.
- **Install SSH key** (key icon, shown in *every* non-online state, including "not checked") — opens `InstallKeyModal`. Enabled even when Offline on purpose (`:707-709`): "Offline" may just be a blocked ICMP/TCP probe while SSH-with-password still works.
- **Check status** (refresh icon) — re-probes that row only.
- **Edit** (pencil) — opens `ServerFormModal` pre-filled; the key vault section appears only in edit mode (a vault action needs a persisted row).
- **Delete** (trash) — `ConfirmDialog`, then `useDeleteServer`.

**ForgeVault key section (edit dialog only)**
- New keys are generated under `/dev/shm`, stored in ForgeVault, and installed remotely using only the public key.
- Pasted private keys go directly to ForgeVault. The UI has no action to restore private keys to disk.
- The old host file read/write routes and migration button were removed. Rows without a ForgeVault reference must be reinstalled.

## States

- **Loading (inventory)**: a single spinner row spanning the table (`index.tsx:664-670`).
- **Empty**: "No servers registered." in an italic centered row (`:671-677`).
- **Probe pending**: per-row `Checking…` badge with a spinner; the row's refresh button is disabled and its icon spins (`:475-482`, `:724-729`). The page-level "Check status" button is disabled while *any* probe is in flight.
- **Probe result**: `Online` (emerald, `Wifi`), `No key` (amber, `KeyRound`), `Offline` (red, `WifiOff`), each with the backend's `detail` string as its `title` tooltip; `not checked` in muted italics before the first probe.
- **Form error**: inline destructive text — client-side "Name, IP and remote user are required.", or "Could not save. The name may already exist." after a rejected create (the backend 409s on a duplicate name).
- **Install-key progress**: "Generating key, installing on the server and verifying…" with a spinner, then a step list with a green check per completed step, or a red `Failed at "{step}": {error}` line.
- **Vault outcome**: one emerald line on success (`Key read from {path} and stored encrypted.`, `Restored to {paths}.`, `Pasted key stored encrypted.`, `Vaulted copy removed…`) or one destructive line carrying the API error message; the section's badge reads `Encrypted copy stored` / `No copy stored`.
- **No explicit UI state** for a failed inventory *load* or a failed *delete* — see Notes.

## Business Rules Surfaced Here

The domain has no SPEC.md §6 rules (it is outside the traceability chain), but four safety rules are enforced server-side and visible on this screen:

- **Unique server name.** `create_server` 409s on a duplicate (`server.py:159-161`), and `import_servers` treats the name as the upsert key.
- **Private key material never leaves the backend.** `ServerOut` exposes only the boolean `private_key_stored` (`schemas/server.py`), derived from the `Server.private_key_stored` property. Private keys are stored only in ForgeVault; the database keeps a secret reference and public key.
- **ForgeVault is the only persistent key store.** The bridge generates in `/dev/shm`; no private key file is created on the host.

Two more rules live in the frontend:

- **A NULL `ssh_key_path` means "ForgeHub knows of no key", never "the host has none"** (`buildSshCommand`, `useServers.ts`). The command adds `-o PasswordAuthentication=yes -o BatchMode=no` so a genuinely keyless server can still prompt, but it must **not** add `PubkeyAuthentication=no` — that was the 2026-08-14 bug: every inventory row has a NULL path (HermesOps installs keys by writing `~/.ssh/config` and never touched this table), so disabling pubkey auth turned working connections into a password prompt for a password nobody has. Regression test: `frontend/src/hooks/useServers.test.ts`.
- **Admin-gated actions.** Key installation and ForgeVault key management require an admin; plain CRUD and CSV import do not.

## Dependencies

- **Host bridge** (`host-bridge/app.py`, systemd unit `forgehub-chat-bridge.service`, `settings.CHAT_BRIDGE_URL` + `X-Bridge-Token`) — required for the status probe's primary path, key installation, public-key read, and both halves of the vault round trip. With the bridge down: probes silently degrade to the in-container `paramiko` fallback, while every key action fails with `502 Host bridge unreachable`.
- **`core/secrets.py`** (Fernet) — the same encryption boundary `Agent.forgerouter_api_key_encrypted` uses. A rotated/lost key makes vaulted copies undecryptable.
- **`/workspace` screen** — the navigation target of the terminal action; it consumes `location.state.openSsh` to open a PTY with the built command.
- **Migration `a7c31e9b2d40`** — adds `servers.private_key_encrypted`.
- **Tests** — `backend/app/tests/test_server_key_vault.py` (6 tests, real DB, bridge mocked), `frontend/src/hooks/useServers.test.ts` (3 tests, `buildSshCommand`).

## Notes / Improvement Opportunities

- **A failed inventory load looks like an empty inventory.** `useServers()`'s `isError`/`error` are never read (`:580`); if the request fails, the table renders "No servers registered." — the §48 error state the coding standard asks for is missing.
- **Delete failures are silent.** `deleteServer.mutate` (`:768`) has an `onSuccess` only; on error the `ConfirmDialog` stays open with no message and the row remains.
- **The page is not full-bleed.** `/servers` is absent from `AppLayout.tsx`'s `isFullBleed` list, so the table grows with the page instead of scrolling inside its own container — fine at today's row count, awkward at a few dozen.
- **The auto-probe fans out unbounded.** `checkAll` fires one `POST /check` per row in parallel on first load, each up to a 15s bridge call; with a large inventory this is a burst of concurrent SSH probes with no concurrency cap.
- **No search, sort or pagination** on the table.
- **ViewModel conversion is partial.** Only `KeyVaultSection` is a §21 pair; the form modal, install-key modal and probe state are still inline `useState` in the page, which is why the screen's checkbox in `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` stays unchecked.
- **Backup overwrites the previous copy with no confirmation.** Deliberate (the host file is the authority), but there is no history — an older vaulted key is not recoverable once replaced.
