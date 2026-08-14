# Screen: Servers

## Route & Purpose

- Route: `/servers` (registered in `frontend/src/App.tsx:120`, nav entry in `frontend/src/components/layout/navSections.ts:141` under **Operations**, icon `Network`, permission module `servers`).
- Component: `frontend/src/pages/servers/index.tsx` (`ServersPage`, default export).
- Purpose: the inventory of SSH-reachable machines. It answers four questions and lets an operator act on each: *which servers exist* (name, IP, user, port, description), *which are actually reachable right now* (live probe per row), *how do I get a shell on one* (hands the built `ssh` command to the Workspace terminal), and *is this server's access recoverable* — the key vault, which keeps an encrypted copy of the identity file on the row so losing the file on the host no longer means losing the server.
- One of ForgeHub's own DB-backed domains (`company.servers`), but deliberately standalone: no FK into the product/version/project traceability chain, since this is infrastructure, not planned work (see the model docstring, `backend/app/db/models/server.py:1-7`).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/servers/index.tsx` (`ServersPage`) | Page shell: header with "Check status"/"Import CSV"/"New server"/assistant toggle, the inventory table, and the four modals/dialogs. Owns `formTarget`/`importOpen`/`deleteTarget`/`installTarget`/`statuses`/`checkingIds` local state. |
| `frontend/src/pages/servers/index.tsx` (`ModalShell`, local) | Shared modal chrome (backdrop + card + close button) used by the three modals below. |
| `frontend/src/pages/servers/index.tsx` (`ServerFormModal`, local) | Create/edit form: name, IP, port, remote user, SSH key path (+ copy-public-key button), description, the read-only installed public key, and — when editing — the key vault section. |
| `frontend/src/pages/servers/index.tsx` (`KeyVaultSection`, local, `:82`) | The key vault UI. A pure render of `useServerKeyVaultViewModel` with no state of its own — the §21 ViewModel pair described in `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md`. |
| `frontend/src/hooks/useServerKeyVaultViewModel.ts` (`useServerKeyVaultViewModel`) | ViewModel for that section: `status` state machine (`idle`/`backing_up`/`restoring`/`storing`/`confirming_clear`/`clearing`/`error`), the paste field, the confirmation step, and the four actions. |
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
| Read + store the public key | `useReadServerPublicKey()` | `/api/v1/servers/{id}/public-key` | POST |
| Vault the host's identity file | `useBackupServerKey()` | `/api/v1/servers/{id}/key:backup` | POST |
| Vault a pasted key | `useStoreServerKey()` | `/api/v1/servers/{id}/key` | PUT |
| Write the vaulted key back | `useRestoreServerKey()` | `/api/v1/servers/{id}/key:restore` | POST |
| Drop the vaulted copy | `useClearServerKey()` | `/api/v1/servers/{id}/key` | DELETE |

Every mutation except the probe invalidates the `["servers"]` query key on success. `useCheckServer` deliberately does not: each result is an ephemeral snapshot, so `ServersPage` keeps them in local `statuses` state instead of the query cache.

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

**Key vault section (edit dialog only)**
- **Store key from host / Update copy from host** — `key:backup`. Disabled without an `ssh_key_path` (there is nothing to read). Overwrites any previous copy: the file on the host is what `ssh` actually uses, so it wins when both exist.
- **Restore to host** — `key:restore`. Disabled unless a copy is vaulted *and* a path is set. Refuses (409) when a file is already at that path.
- **Store pasted key** — `PUT key`, for material this host does not have (recovered from a backup by hand, or living on another machine).
- **Remove copy** — `ConfirmDialog` ("The file on the host is left untouched — but if it is ever lost, there will be no copy to restore from"), then `DELETE key`.

**SSH key path field**
- **Copy public key** (copy icon, only when the row already has an `ssh_key_path`) — calls `/public-key`, writes the result to the clipboard and persists it on the row; shows a green check for 1.5s.

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
- **Private key material never leaves the backend.** `ServerOut` exposes only the boolean `private_key_stored` (`schemas/server.py`), derived from the `Server.private_key_stored` property. No endpoint returns `private_key_encrypted`, and the restore path writes to the host rather than answering the browser.
- **A restore never overwrites.** Restoring is for a key that is *missing*; silently replacing a working identity is the worse failure, so the bridge 409s and the section surfaces the conflict (`host-bridge/app.py:2823-2824`).
- **Nothing about the vault is automatic.** No backup on save, no restore on a failed connection. A key reappearing on disk from a stale copy would be its own surprise — every vault action is an explicit click.

Two more rules live in the frontend:

- **A NULL `ssh_key_path` means "ForgeHub knows of no key", never "the host has none"** (`buildSshCommand`, `useServers.ts`). The command adds `-o PasswordAuthentication=yes -o BatchMode=no` so a genuinely keyless server can still prompt, but it must **not** add `PubkeyAuthentication=no` — that was the 2026-08-14 bug: every inventory row has a NULL path (HermesOps installs keys by writing `~/.ssh/config` and never touched this table), so disabling pubkey auth turned working connections into a password prompt for a password nobody has. Regression test: `frontend/src/hooks/useServers.test.ts`.
- **Admin-gated actions.** `install-key`, `public-key` and the four vault routes require an admin; plain CRUD and CSV import do not.

## Dependencies

- **Host bridge** (`host-bridge/app.py`, systemd unit `forgehub-chat-bridge.service`, `settings.CHAT_BRIDGE_URL` + `X-Bridge-Token`) — required for the status probe's primary path, key installation, public-key read, and both halves of the vault round trip. With the bridge down: probes silently degrade to the in-container `paramiko` fallback, while every key action fails with `502 Host bridge unreachable`.
- **`core/secrets.py`** (Fernet) — the same encryption boundary `Agent.forgerouter_api_key_encrypted` uses. A rotated/lost key makes vaulted copies undecryptable.
- **`/workspace` screen** — the navigation target of the terminal action; it consumes `location.state.openSsh` to open a PTY with the built command.
- **Migration `a7c31e9b2d40`** — adds `servers.private_key_encrypted`.
- **Tests** — `backend/app/tests/test_server_key_vault.py` (6 tests, real DB, bridge mocked), `frontend/src/hooks/useServers.test.ts` (3 tests, `buildSshCommand`).

## Notes / Improvement Opportunities

- **The vault badge goes stale while the dialog is open.** `ServerFormModal` receives `initial` from `formTarget`, a `Server` object captured when Edit was clicked. `useBackupServerKey` invalidates `["servers"]`, but the captured object is never replaced, so after storing a key the section keeps showing "No copy stored" (and "Restore to host" stays disabled) until the dialog is closed and reopened. The success message is the only feedback that the action worked. Fixing it means re-reading the row from the query cache by id instead of holding the object in state.
- **A failed inventory load looks like an empty inventory.** `useServers()`'s `isError`/`error` are never read (`:580`); if the request fails, the table renders "No servers registered." — the §48 error state the coding standard asks for is missing.
- **Delete failures are silent.** `deleteServer.mutate` (`:768`) has an `onSuccess` only; on error the `ConfirmDialog` stays open with no message and the row remains.
- **The page is not full-bleed.** `/servers` is absent from `AppLayout.tsx`'s `isFullBleed` list, so the table grows with the page instead of scrolling inside its own container — fine at today's row count, awkward at a few dozen.
- **The auto-probe fans out unbounded.** `checkAll` fires one `POST /check` per row in parallel on first load, each up to a 15s bridge call; with a large inventory this is a burst of concurrent SSH probes with no concurrency cap.
- **No search, sort or pagination** on the table.
- **ViewModel conversion is partial.** Only `KeyVaultSection` is a §21 pair; the form modal, install-key modal and probe state are still inline `useState` in the page, which is why the screen's checkbox in `docs/architecture/FRONTEND_VIEWMODEL_MIGRATION_PLAN.md` stays unchecked.
- **A vaulted key cannot be restored without a path.** `key:restore` 400s when `ssh_key_path` is NULL — reasonable (it needs a destination), but it means the vault cannot by itself answer "where did this key live?" for a row whose path was never recorded. The path and the key are stored together; only one of them is validated as present at backup time.
- **Backup overwrites the previous copy with no confirmation.** Deliberate (the host file is the authority), but there is no history — an older vaulted key is not recoverable once replaced.
- **Newly installed keys and existing keys land in different directories.** "Install SSH key" generates into `SSH_KEYS_DIR` = `/root/agents/aegis/server-management/ssh_keys` (`host-bridge/app.py:2688`, created on demand by `os.makedirs`), but the inventory's actual keys live in `/root/agents/aegis/forgenet/ssh_keys/<ip_with_underscores>_key` — verified on the host, where the `server-management` path does not exist at all. Nothing breaks (`/root/agents` is itself a `PRIVATE_KEY_ROOTS` entry, so both are allowed, and each row records its own `ssh_key_path`), but the fleet ends up split across two conventions and `SSH_KEYS_DIR` names a directory that has never been used. Worth reconciling before the next key is installed.
