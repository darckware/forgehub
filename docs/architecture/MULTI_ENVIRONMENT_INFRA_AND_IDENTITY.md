# Multi-Environment Infrastructure Registry and Cross-Environment Identity

**Status:** proposed, not yet implemented
**Owner:** Athos (governance) / Daedalus (implementation)
**Policy this spec implements:** `/root/.hermes/foundation/36_governance/MULTI_ENVIRONMENT_OPERATING_RULE.md`
**Context:** ForgeHub now runs as more than one independent deployment — this host (`Local`) and
a first production VPS (`vmi3547248`, see `/root/.hermes/foundation/HANDOVER_VPS.md`), each with
its own `forgehub` database. Future client VPS deployments will follow the same pattern. This spec
defines the concrete schema and endpoints needed so (a) the server inventory stops mixing
infrastructure from different environments together, and (b) a user's access can be scoped
per-environment without syncing a full user table blindly between databases.

Each ForgeHub deployment referenced below is its own independent Postgres database (own
`company` schema, own migration history) — nothing here introduces cross-database foreign keys
or shared connections. Every "sync" described is an authenticated HTTP call between two
already-running ForgeHub backends, never direct DB-to-DB replication.

---

## 1. Naming: `infra_environment`, not `environment`

The word `environment` is already used in this codebase for a different concept: which
deployment stage a *product being built* runs in (`db/models/product.py`'s per-version URLs,
`db/models/backlog.py`'s `BugReport.environment` string, `db/models/system_scope.py`'s
`environment_target` deployment-unit kind — dev/staging/production of a client's application).
That is unrelated to which *physical ForgeHub installation* a piece of infrastructure or a user
belongs to.

This spec introduces a new domain, `infra`, and a new noun, **`InfraEnvironment`**, everywhere a
name is needed (table `infra_environments`, FK column `infra_environment_id`, module name
`"infra"` in `MODULES`). Never reuse `environment` bare for this concept in code, docs, or UI copy
— it will silently collide with the existing per-product meaning in search, grep, and
conversation.

## 2. `InfraEnvironment` — the environment registry

New file `backend/app/db/models/infra.py`, new table `infra_environments`, schema `company`
(inherits from `Base` like every other domain model — see `db/base.py`'s PK convention: UUID,
Python-side `uuid.uuid4` default, never server-side).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | String(100), unique | e.g. `"Local"`, `"VPS-vmi3547248"`, `"VPS-ClienteA"` |
| `kind` | String(20), CheckConstraint | `"local" \| "vps"` — plain string + constraint, per this codebase's convention (`db/base.py`'s stated reasoning: avoids `ALTER TYPE` churn), not a native enum |
| `base_url` | String(500) | this environment's own ForgeHub backend API, e.g. `https://100.105.235.114:8000` — how the frontend/switcher and the sync client reach it |
| `tailscale_ip` | String(100), nullable | reference only, not used for routing logic |
| `is_identity_source` | Boolean, default False | exactly one row should carry `True` at any time — the environment whose `users`/`profiles` tables are authoritative (today: the VPS, per `MULTI_ENVIRONMENT_OPERATING_RULE.md` §"VPS como fonte central"). Enforced at the API layer (a write that would set a second row `True` is rejected), consistent with this codebase's "business rules live at the route, not a DB constraint" convention for anything needing a cross-row check. |
| `last_healthcheck_at` | DateTime(timezone=True), nullable | last time `/health` was probed |
| `last_healthcheck_status` | String(20), nullable, CheckConstraint `"ok" \| "degraded" \| "down"` | feeds the readiness gate in `MULTI_ENVIRONMENT_OPERATING_RULE.md` §4 |
| `description` | Text, nullable | |

`Server` gains `infra_environment_id: Mapped[uuid.UUID | None]` — `ForeignKey("company.infra_environments.id")`, nullable at first (existing 13 rows need a backfill migration assigning them to the `"Local"` row before the column can be made `NOT NULL` in a follow-up migration; see §6). This is the direct fix for "servidores cadastrados todos misturados" — the Servers page groups/filters by this column once it exists.

**Visibility is scoped, deliberately not "all environments visible everywhere."** A client VPS's
own ForgeHub should not learn that a different client's VPS exists at all — the same leak class
this spec's §4 avoids for users. `GET /api/v1/infra-environments` returns:
- every row, if the calling deployment's own `infra_environments` table has more than one row
  registered locally (this is what makes `Local` — Marcelo's orchestration hub — able to list and
  switch between all known environments): each deployment only ever knows about the environments
  someone deliberately registered *in its own database*, there is no automatic discovery.
- In practice: a client VPS's `infra_environments` table should only ever contain its own single
  row (seeded at install time, §6) — it was never told about siblings, so it structurally cannot
  leak them. `Local`'s table is the only one meant to accumulate every environment over time.

## 3. Extending existing RBAC instead of a parallel permission system

`db/models/profile.py` already implements real RBAC: `User.profile_id → Profile → ProfilePermission` (per-module `can_view/can_query/can_write/can_delete`) `+ ProfileActionPermission` (named sensitive actions), with `User.is_admin` as a full bypass. `auth.py`'s `/api/v1/auth/token` already issues real JWTs against the `users` table (the `CLAUDE.md` note calling `auth.py` a placeholder is stale). This is exactly the "permissão dada pelo perfil do usuário" mechanism — no second permission system is needed, only an environment scope on top of it.

New table `profile_infra_environment_access`:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `profile_id` | UUID, FK `company.profiles.id`, `ondelete="CASCADE"` | |
| `infra_environment_id` | UUID, FK `company.infra_environments.id`, `ondelete="CASCADE"` | |

`UniqueConstraint("profile_id", "infra_environment_id")`. A `Profile` with no row here for a given
`InfraEnvironment` grants no access there, full stop — `User.is_admin` still bypasses everything,
same as it already bypasses per-module checks (an admin is assumed global, not per-environment;
if a future need arises for an admin scoped to one environment only, that is a new profile with
targeted `ProfilePermission` rows plus one `profile_infra_environment_access` row, not a change to
this table).

`"infra"` is added to `MODULES` in `profile.py` so access to the Servers/Infra-environment screens
themselves is governed the same way as every other module.

## 4. Cross-environment identity sync

**Source of truth:** the `InfraEnvironment` row with `is_identity_source=True` (today, the VPS).
Its own `users`, `profiles`, `profile_permissions`, `profile_action_permissions`, and
`profile_infra_environment_access` tables are what every other environment mirrors — never the
reverse. This section defines the endpoints; it does not change how login itself works (`auth.py`
already validates against the local `users` table — that stays exactly as is, satisfying "login
never depends on reaching another environment").

### 4.1 Export (called on the identity-source environment only)

`GET /api/v1/infra-sync/export?for_environment_id=<uuid>` — authenticated by a **service
credential** distinct from a human JWT (a new `InfraEnvironment.sync_token_encrypted` column,
Fernet-encrypted like `Server.private_key_encrypted`/`Agent.forgerouter_api_key_encrypted`,
`core/secrets.py`'s existing boundary). The caller identifies which environment it is; the server
filters strictly to what that specific environment is entitled to:

```
users:    every User referenced by a profile_infra_environment_access row
          for_environment_id, plus their hashed_password (never plaintext --
          it is already a hash in the source row) and profile_id
profiles: every Profile with a profile_infra_environment_access row for
          for_environment_id, plus its permissions/action_permissions
```

A request for an unregistered `for_environment_id`, or with an invalid/revoked token, gets 403 —
never a filtered-to-empty 200, so a satellite can tell "you're not authorized" apart from "you're
authorized and nobody's currently granted."

### 4.2 Import (called on every satellite environment, including `Local`)

`POST /api/v1/infra-sync/run` — admin-only (`get_current_admin`, already used elsewhere e.g.
`server.py`'s `install_server_key`), no request body. Reads this environment's own
`InfraEnvironment` row to find the identity source's `base_url`, calls its `/infra-sync/export`
with this environment's own stored sync token, then **reconciles** (not appends):

- upsert every returned `User`/`Profile`/permission row by stable key (`User.email`, not
  `username` — see §5) into the local tables;
- **delete** any locally-held `User`/`Profile` that no longer appears in the response — a
  revocation on the identity source must remove access here, not just fail to add new access;
- never touch `User.is_active`/other locally-set fields the sync payload doesn't carry, if any are
  ever added later that are meant to be environment-local rather than synced.

Exposed in the UI as the "Sincronizar usuários" button (per `MULTI_ENVIRONMENT_OPERATING_RULE.md`),
plus a background poll on the same interval convention this codebase already uses for other
reconciliation sweeps (`demand.py`'s `_dispatch_completion_poll_loop` /
`_incubation_maturation_poll_loop` pattern — a dedicated asyncio task in `main.py`, independent
failure domain from the rest of the app).

### 4.3 Bootstrap — already solved, no new code

`auth.py`'s existing `DEV_USER_USERNAME`/`DEV_USER_PASSWORD` fallback (used "before the admin row
is persisted") already covers the chicken-and-egg problem of a freshly installed environment with
no synced users yet and no sync token configured yet: the first login on a new `InfraEnvironment`
uses that fallback, an admin sets the environment's `sync_token_encrypted` value (pasted from the
identity source, same manual-paste pattern as `Agent.forgerouter_api_key_encrypted`), and only
then does `/infra-sync/run` become callable. Onboarding checklist for a brand-new environment:

1. Create its `InfraEnvironment` row (on the identity source, so it exists to be granted access).
2. Generate and store its `sync_token_encrypted` there; paste the same token into the new
   environment's own row.
3. Grant the relevant `Profile`s access via `profile_infra_environment_access`.
4. Log into the new environment via the `DEV_USER` fallback.
5. Run `/infra-sync/run` there for the first time.
6. Only then does this environment satisfy the readiness gate in
   `MULTI_ENVIRONMENT_OPERATING_RULE.md` §4.

## 5. Stable identity key: email, not username

`User.username` is unique but is a display handle; two independently-administered environments
could pick the same username for different people before ever syncing. `User.email` (already
`unique=True, nullable=True` in the model) becomes the required reconciliation key for sync
specifically — this spec makes `email` mandatory (`nullable=False`) for any `User` that
participates in cross-environment sync, without forcing it for a purely local dev/admin account
that never leaves its own environment.

## 6. Migration plan

1. `alembic revision --autogenerate` for `InfraEnvironment` + `profile_infra_environment_access`
   + `Server.infra_environment_id` (nullable) + `InfraEnvironment.sync_token_encrypted`.
2. Data migration: insert one `InfraEnvironment(name="Local", kind="local", is_identity_source=False)`
   row (or `True`, if Marcelo designates `Local` rather than the VPS after all — this spec assumes
   the VPS per the approved operating rule, but the migration should read the flag from a config
   value, not hardcode the choice twice); backfill every existing `Server` row's
   `infra_environment_id` to it.
3. Follow-up migration (separate, after backfill is confirmed complete) tightens
   `Server.infra_environment_id` to `NOT NULL`.
4. `MODULES` in `profile.py` gains `"infra"`; existing profiles get no automatic
   `ProfilePermission` row for it (default-deny, same as any newly added module).

## 7. Explicitly deferred, not part of this spec

- **`VpnOperationEvent.target`** (`db/models/vpn.py`) is a hardcoded `CheckConstraint("target IN
  ('local', 'remote'))")` — a real but separate generalization (FK to `InfraEnvironment` instead of
  a fixed pair) once more than one remote target actually exists. Not blocking this spec.
- **Revocation latency and session lifetime** — per `MULTI_ENVIRONMENT_OPERATING_RULE.md`, a
  revoked user keeps local access until the next `/infra-sync/run` and until their session expires.
  No change to JWT expiry is proposed here; if the accepted window is judged too long once real
  client VPS access exists, that is a `core/security.py` token-lifetime change, tracked separately.
- **Backups** — `users`, `profiles`, `profile_permissions`, `profile_action_permissions`,
  `profile_infra_environment_access`, and `infra_environments` on the identity-source environment
  must be added to that environment's existing backup routine (`HANDOVER_VPS.md` §5); no schema
  work needed, just confirming the dump command's table list.
- **Audit trail** — sync runs and grant/revoke actions should flow into the existing
  `audit`/`governance` domains (`db/models/audit.py`, `db/models/governance.py`) rather than being
  invisible; left as a follow-up task once this spec's core tables exist to audit.
