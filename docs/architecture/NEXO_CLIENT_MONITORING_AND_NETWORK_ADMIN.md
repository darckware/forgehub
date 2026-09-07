# Nexo Client Monitoring, Network Administration, and Installer Distribution

**Status:** proposed, not yet implemented
**Owner:** Athos (governance) / Daedalus (implementation)
**Upstream:** `/root/project/nexo` (Remote Agent, merged to `main`; ACL/Headscale overlay, Fase 1
done) — this spec is entirely on the ForgeHub side, consuming what Nexo produces.
**Related:** `/root/project/nexo/docs/superpowers/specs/2026-09-05-remote-agent-minimo-e-irregularidades.md`
(§2.2/§5 originally sketched the Client/Workstation/Irregularity shape this spec formalizes),
`docs/architecture/MULTI_ENVIRONMENT_INFRA_AND_IDENTITY.md` (the `InfraEnvironment`/multi-tenant
identity work this reuses conventions from, though that spec is about Marcelo's own
Local/VPS environments — this one is about client-owned devices, a different tenancy axis).

## 1. Objective

ForgeHub becomes the single control plane for everything Nexo needs on the server side, so that
none of it lives as hand-edited files or ad hoc scripts:

1. A **Client** registry (one row per client company, e.g. Clube de Tiro Gatling), each owning a
   set of **Workstations** (servers/desktops with the Nexo Remote Agent installed).
2. An **ingestion endpoint** that receives the Remote Agent's periodic reports and turns rule
   violations into **Irregularities** (and a `Notification`, reusing the existing bell).
3. An **Irregularities screen** to see and act on what the agents found.
4. **Report generation** — the monthly "Relatório de Acompanhamento" the Gatling contract already
   promises, plus an on-demand report for a specific occurrence — both built from the same
   Irregularity/Workstation data, never hand-written.
5. **Network administration for Nexo's Headscale overlay** — Client = the grouping unit (one
   Headscale tag per client), with default-deny between clients enforced structurally, and an
   explicit, auditable control for Marcelo to grant (and revoke) direct communication between two
   specific Workstations of the *same* client when there's a real operational need — never on by
   default.
6. An **installer/download area** — pick a Workstation, get back a ready-to-copy install bundle
   (the correct platform binary + a pre-filled `agent.yaml` with that Workstation's own device
   token and settings) instead of hand-building the Go binary and hand-writing YAML per machine.

## 2. Domain model

New domain `clients` (`backend/app/db/models/client.py`, `api/schemas/client.py`,
`api/routes/client.py` — following this codebase's domain-module pattern, UUID PK / Python-side
`uuid.uuid4` default, `TimestampMixin`, `String` + `CheckConstraint` instead of native enums, per
`db/base.py`'s stated conventions).

### 2.1 `Client`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | String(255), unique | e.g. "Clube de Tiro Gatling" |
| `contact_name` / `contact_phone` / `contact_email` | String, nullable | who to reach at the client |
| `support_plan` | String(20), CheckConstraint `"4h" \| "8h" \| "12h"`, nullable | matches the
  contracted franchise plan (see the Gatling proposal PDF this whole feature was scoped from) —
  informational for now, not enforced by any quota logic in this spec |
| `headscale_tag` | String(100), unique | e.g. `tag:cliente-gatling` — the Headscale ACL tag this
  client's devices are enrolled under (§5) |
| `notes` | Text, nullable | |

### 2.2 `Workstation`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `client_id` | UUID, FK `company.clients.id`, `ondelete="CASCADE"` | |
| `hostname` | String(255) | last-reported hostname (updated on each ingested report — see §3) |
| `os_kind` | String(20), CheckConstraint `"linux" \| "windows"` | |
| `device_token_hash` | String(64), unique | SHA-256 of the device token, same boundary as
  `AgentServiceCredential.token_hash` (`db/models/agent.py`) — never store the raw token |
| `device_token_issued_at` | DateTime(timezone=True) | |
| `device_token_revoked_at` | DateTime(timezone=True), nullable | revoking sets this; ingestion
  rejects a revoked token (401), same pattern `AgentServiceCredential`/`get_actor_principal`
  already use for agent credentials |
| `last_report_at` | DateTime(timezone=True), nullable | updated on every accepted ingestion |
| `last_seen_agent_version` | String(50), nullable | from `Report.AgentVersion` |

`hostname` is not the identity key (a workstation could rename itself) — the device token is. A
`Workstation` row is created once, manually, when Marcelo registers a new machine for a client
(§6 covers issuing the token as part of that same action); ingestion never creates a `Workstation`
implicitly from an unrecognized token.

### 2.3 `Irregularity`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `workstation_id` | UUID, FK `company.workstations.id`, `ondelete="CASCADE"` | |
| `rule_key` | String(50), CheckConstraint, one of: `disk_space_low`, `backup_stale`,
  `unauthorized_remote_tool`, `critical_service_down`, `collection_failed`, `agent_unreachable` | |
| `severity` | String(20), CheckConstraint `"info" \| "warning" \| "critical"` | |
| `detail` | Text | human-readable specifics (e.g. the matched software name, the disk path and
  percent, which service) |
| `status` | String(20), CheckConstraint `"open" \| "acknowledged" \| "resolved"`, default `"open"` | |
| `detected_at` | DateTime(timezone=True) | |
| `resolved_at` | DateTime(timezone=True), nullable | |
| `resolved_by_user_id` | UUID, FK `company.users.id`, nullable | |

`agent_unreachable` (per the Nexo final-review recommendation) is raised by a scheduled sweep, not
by an ingested report — see §3.3.

`"infra"` and `"clients"` module names are both added to `MODULES` in `profile.py`, so access to
Clients/Workstations/Irregularities screens is governed by the same RBAC as everything else.

## 3. Ingestion endpoint

`POST /api/v1/agent-reports` — the exact path already hardcoded in the Nexo `agent.yaml` example
(`docs/runbooks/instalar-remote-agent.md` in the Nexo repo). Authenticated by the `X-Device-Token`
header the Remote Agent already sends (`internal/reporter/reporter.go`); looked up by
`sha256(token)` against `Workstation.device_token_hash`, rejecting (401) an unknown or revoked
token — new logic, not the existing `agt_`-prefixed `get_actor_principal` path (`core/deps.py`),
since a device token authenticates a `Workstation`, not an `Agent`/`User` principal, and must not
be able to reach any other endpoint.

Request body: the Nexo `collector.Report` JSON shape (§7 of the Nexo remote-agent-minimo spec, as
amended by its final-review fix wave — includes `Hostname`, `OS`, `AgentVersion`, `SchemaVersion`,
`CollectionErrors`, `DiskUsage []{Path, UsedPercent}`, etc.). `SchemaVersion` is checked and a
mismatch is rejected (400) rather than silently misparsed — this is the "freeze the contract"
recommendation from that review, landing on the consumer side now that it exists to freeze against.

### 3.1 On each accepted report

1. Update `Workstation.hostname`/`last_report_at`/`last_seen_agent_version`.
2. Evaluate rules (§3.2) against the report body.
3. For each rule that fires and has no existing **open** `Irregularity` with the same
   `rule_key` for this `Workstation`, insert one and a matching `Notification`
   (`source="system"`, reusing `db/models/notification.py` exactly as `demand.py`'s existing
   ingestion already does — no parallel notification mechanism).
4. A rule that no longer fires does **not** auto-resolve its `Irregularity` — resolution is a
   human action (§4). A stale open `Irregularity` for a since-fixed condition is a known,
   accepted noise cost of this design; auto-resolution risks a `Irregularity` disappearing before
   anyone saw it, which is worse.

### 3.2 Rules (evaluated against the ingested `Report`)

| `rule_key` | Fires when |
|---|---|
| `disk_space_low` | any entry in `DiskUsage` has `UsedPercent > 90` |
| `backup_stale` | `BackupStatus.Stale == true` |
| `unauthorized_remote_tool` | `Software` (the denylist matches) is non-empty |
| `critical_service_down` | any `ServiceStatus.Status == "stopped"` |
| `collection_failed` | `CollectionErrors` is non-empty — surfaces the fail-open cases the Nexo
  final review fixed (a `dpkg -l` failure on a non-Debian host, etc.) as a first-class
  irregularity of its own, since "I could not check" is itself something Marcelo needs to see |

### 3.3 `agent_unreachable` (scheduled, not ingestion-triggered)

A poll loop (same pattern as `demand.py`'s existing `_dispatch_completion_poll_loop`/
`_incubation_maturation_poll_loop` — a dedicated `asyncio` task registered in `main.py`, an
independent failure domain from the request path) runs every few minutes: any `Workstation` whose
`last_report_at` is older than 3× its agent's configured `report_interval` (the report interval
itself is not currently sent in the payload — add `ReportInterval` to the Nexo `Report`/`Collect`
shape as a small follow-up to Nexo, or use a fixed conservative threshold, e.g. 15 minutes, until
that's added) gets one `agent_unreachable` `Irregularity`, deduplicated the same way as §3.1 (no
new one while an open one already exists). This is the finding from the Nexo final review that "a
silent agent is indistinguishable from a healthy one" — closing it here, server-side, since the
agent structurally cannot report its own absence.

## 4. Irregularities screen

`pages/irregularities/index.tsx` + `hooks/useIrregularities.ts`, following this codebase's
per-domain page+hook pairing. List grouped by Client → Workstation, filterable by `status`/
`severity`/`rule_key`, each row showing `detail`, `detected_at`, and an "Marcar como tratada" action
(`PATCH` to `status="resolved"`, stamping `resolved_by_user_id`/`resolved_at` — the same
confirm-dialog + pending-spinner convention already used ~70 places in this codebase, per
`CLAUDE.md`'s CRUD UX section, not a new pattern).

## 5. Nexo network administration

### 5.1 Client → Headscale tag, one-to-one

**Integration mechanism, confirmed (2026-09-06) by reading Nexo's actual integration tests, not
assumed:** every existing interaction with Headscale in this ecosystem — `TestAdminUserExists`,
`createPreAuthKey`, `waitForNodeCount` in `test/integration/02_admin_user_test.go` and
`04_enrollment_test.go` — goes through the `headscale` CLI binary (`headscale users list -o
json`, `headscale preauthkeys create --tags ... -o json`, `headscale nodes list -o json`), never
an HTTP/gRPC API call. In dev this runs via `docker exec <container> headscale ...`; in production
(`infra/headscale/remoto-headscale.service`) Headscale runs as a bare systemd service on the VPS
host, so the same CLI is invoked directly there. ForgeHub's backend runs inside its own Docker
container with no path to either the Headscale container or the host's `headscale` binary — the
exact same constraint `system_control.py` (git status) and `hindsight.py` (docker restart) already
solved via the host-bridge's `/v1/exec`. `core/headscale_client.py` is therefore a host-bridge
proxy adapter, not a direct-API or direct-exec client: it builds `headscale <subcommand> ... -o
json` argument lists and posts them to `/v1/exec`, parses the JSON response, and never talks to
Headscale over the network itself. (A direct-API path remains possible later if Headscale's gRPC
port is ever deliberately exposed to ForgeHub's network — not the case today, and not blocking this
spec.)

**Rendering strategy, confirmed:** Headscale in this deployment runs in file-mode policy
(`policy.mode: file`, `infra/headscale/config.dev.yaml`/`config.prod.yaml.example`), reading
`/etc/headscale/acl-policy.hujson`. ForgeHub never hand-edits or diffs that file — every
tag-provisioning or peer-grant change **re-renders the entire policy from the current DB state**
(every `Client.headscale_tag`, every active `WorkstationPeerGrant`) into one HuJSON document, then
pushes it via `/v1/exec` (write the file to a host-bridge-writable path, then `headscale policy
set --file <path>` to validate-and-apply in one step — Headscale's own subcommand for loading a
new file-mode policy without a service restart). Full-render-and-push, not incremental patching,
is deliberate: it makes "what the DB says is granted" and "what Headscale is actually enforcing"
structurally unable to drift apart — there is no diff logic to have a bug in. Creating a `Client`
still writes its `Client` row *and* triggers this same full re-render (its new `tag:cliente-<slug>`
now appears in the rendered `tagOwners`/`grants`), mirroring the shape already hand-maintained in
`infra/headscale/acl-policy.hujson` today, just generated instead of typed by hand.

### 5.2 Selective same-client peer access (default off, explicit grant, auditable)

New table `WorkstationPeerGrant` (`workstation_a_id`, `workstation_b_id`, both FK
`company.workstations.id`, `granted_by_user_id`, `granted_at`, `revoked_at` nullable) —
`UniqueConstraint` on the pair (store canonically with the lexicographically-smaller UUID first
so `(A,B)` and `(B,A)` are never two rows). Creating a grant:

1. Validates both workstations belong to the **same** `Client` — a grant spanning two different
   clients must be rejected (400), not merely discouraged, since that is the one invariant this
   whole feature exists to never violate.
2. Writes the `WorkstationPeerGrant` row.
3. Triggers the same full policy re-render described in §5.1. The render step, for every currently
   active `WorkstationPeerGrant`, resolves each workstation's live Headscale overlay IP via
   `headscale nodes list -o json` (matched by the node's registered name against the
   `Workstation`'s known hostname — the same lookup Nexo's own `tailscaleIP` test helper performs),
   adds both IPs to the policy's `hosts` map under stable aliases (e.g.
   `ws-<workstation_id>`), and adds one `{"src": ["ws-<a>"], "dst": ["ws-<b>"], "ip": ["*"]}` grant
   per pair — never `tag → tag` (that would open every device in the client to every other device).
   IPs are resolved fresh on every render rather than cached, since Headscale can reassign a node's
   address on re-registration; nothing in ForgeHub's own DB stores an IP.
4. Revoking sets `revoked_at` (never deletes the row — audit trail of who granted/revoked and
   when) and triggers the same full re-render, which now omits that pair's `hosts` entries and
   `grants` line since the query behind the render only ever includes grants with `revoked_at IS
   NULL`.

Every grant/revoke is written to the existing `audit`/`governance` domain (`db/models/audit.py`),
per the Nexo final review's recommendation to make this kind of state-changing action reviewable,
not just effective.

UI: on a Client's detail page, a "Comunicação entre estações" panel lists the client's
Workstations as a matrix/pair-picker, each cell showing granted/not-granted with a toggle — no
bulk "allow all" action exists in this spec; every grant is one deliberate pair.

## 6. Installer / download area

`pages/nexo-agents/index.tsx` (or a tab on the Workstation detail page — left to the plan to
decide the exact placement) lets Marcelo, for one `Workstation`:

1. **Issue a device token** — the one point where the raw token is ever shown (once, at issuance,
   same UX convention as `Server`'s SSH key vault "shown once" pattern in `server.py`), stored only
   hashed thereafter.
2. **Download a ready-to-install bundle** for that workstation's `os_kind`: the compiled
   `nexo-remote-agent` binary (`.exe` for Windows, plain binary for Linux) plus a generated
   `agent.yaml` pre-filled with `endpoint_url` (this ForgeHub's own public ingestion URL),
   the freshly issued `device_token`, and sane defaults for the rest (`report_interval`,
   `critical_services`, `unauthorized_software`, `backup_paths`, `disk_paths` — editable by
   Marcelo before download, defaulting to the values already documented in the Nexo runbook's
   example config).

Binaries are **not** committed to either repo or rebuilt per-download. `POST
/api/v1/nexo-agents/build` (admin-only) triggers a build once per Nexo version bump — via the
host-bridge `/v1/exec` pattern already used elsewhere in this codebase, running
`go build -o <path> ./cmd/remote-agent` and the `GOOS=windows` cross-compile inside
`/root/project/nexo` — and stores the two resulting binaries under a ForgeHub-managed path (e.g.
alongside the existing `docs`/`vault` filesystem-backed domains' storage convention). The
download endpoint (`GET /api/v1/nexo-agents/download/{os_kind}`) serves whatever was last built,
via `FileResponse` (the exact pattern already in `docs.py`), plus the workstation-specific
generated `agent.yaml` bundled alongside it (e.g. as a zip, or two separate downloads — a plan-level
choice). A "última build: `<sha>`, em `<data>`" indicator on the screen tells Marcelo whether the
served binary matches the Nexo repo's current `main` — reading Nexo's own git SHA the same way
`system_control.py` already reads this repo's git status for the equivalent indicator.

## 7. Report generation

Two entry points, both producing the same document shape (a PDF or equivalent, structure loosely
following the Gatling contract's own "Relatório Mensal de Acompanhamento" content list — atendimentos,
horas, saldo, alterações, incidentes, riscos, pendências) built entirely from `Irregularity`/
`Workstation`/`Client` data already in the database — never hand-written:

1. **Scheduled monthly** — one report per `Client` per billing cycle, generated by a scheduled
   job (same poll-loop pattern as §3.3) and left for Marcelo to review/send, not auto-emailed.
2. **On-demand, per occurrence** — a button on an `Irregularity` or on a `Client`'s page, for the
   "mais de um relatório por mês, devido a ocorrências" case Marcelo described — generates the same
   document shape scoped to a specific incident/date range instead of the full month.

No PDF/report-generation library exists yet in this backend (`grep` confirmed none of
`reportlab`/`weasyprint`/`pdfkit` are in `requirements.txt`) — selecting one is a plan-level
decision, not a spec-level one; a Markdown-to-PDF or HTML-to-PDF path that reuses this codebase's
existing Jinja/templating conventions (if any) should be preferred over inventing a new templating
mechanism just for this.

## 8. Client-facing display lives in the Darckware site's existing client area, not here

**Correction to an earlier assumption in this conversation:** the Darckware public site
(`/root/project/darckware`) already has a real, authenticated client area (`/cliente/contrato`,
`/cliente/configurador`, with its own Postgres-backed models — `ClientContract`,
`TicketTimeEntry`, `InteractionLedger` — per that project's "Onda 2" delivery). Client-facing
monitoring data (Irregularities, the generated reports from §7) should be surfaced as a new tab or
page **inside that existing client area**, not as a separate login/portal built in ForgeHub or in
this spec. ForgeHub stays the internal control plane (Marcelo-only); Darckware's `/cliente/` area
is the one and only place an actual client authenticates and looks at their own data.

This spec's `Client` (§2.1) needs a way to resolve to the matching client account in the Darckware
site's own database — the exact linkage (a shared `client_id`/email match, or a small
cross-service lookup) is a decision for whoever specs the Darckware-side work, not this document.
What this spec commits to on the ForgeHub side: expose a narrow, read-only, client-scoped API
(e.g. `GET /api/v1/clients/{id}/irregularities`, `GET /api/v1/clients/{id}/reports`) that the
Darckware backend calls server-to-server (a service credential, same `agt_`-style bearer pattern
already in `core/deps.py`, scoped so it can only ever read the one `Client` it asks for) — never a
direct database connection between the two projects, and never the client's browser talking to
ForgeHub directly. Darckware's own client area already has a precedent for this class of
isolation bug to avoid: its ticket-detail endpoints return 404 (not 403) for a resource belonging
to a different client company, so cross-tenant existence can't be inferred from the error code —
this API should follow the same discipline.

Concretely: this ForgeHub spec is unchanged (§1-7 stay exactly as designed); a **separate,
follow-up spec on the Darckware side** covers the actual `/cliente/` UI, the account-linkage
decision, and consuming this new read-only API — out of scope for the plan this spec leads into.

## 9. Explicitly deferred, not part of this spec

- Automated device-token rotation/expiry — tokens are long-lived until manually revoked, matching
  the "emitido manualmente para este piloto" note already in the Nexo runbook.
- Any UI for editing the Headscale ACL policy's raw HuJSON — this spec's grant/revoke actions are
  the only sanctioned write path; direct policy editing stays a manual, out-of-band operation for
  now.
- Billing/franchise-hour tracking against `Client.support_plan` — the column exists for future use;
  reconciling it against Darckware's own `ClientContract`/`TicketTimeEntry` hour-balance engine is
  a follow-up, not this spec.
- The Darckware `/cliente/` UI itself, and the client-account linkage decision (§8) — a separate
  spec, in the Darckware repo.
