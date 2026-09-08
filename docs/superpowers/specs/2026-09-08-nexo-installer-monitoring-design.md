# Nexo Installer Distribution and Installation Monitoring Design

**Date:** 2026-09-08
**Status:** proposed for implementation review
**Scope:** ForgeHub-side implementation of §6 of
[`docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md`](../../architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md),
extended with installation-state monitoring and immutable history.

## Objective

Provide one internal control surface where an administrator can build versioned Nexo Remote Agent
binaries, generate a workstation-specific installation bundle, download it, and follow the
installation from package generation through the agent's first authenticated report.

The feature replaces per-machine manual compilation and YAML editing without introducing remote
command execution on client workstations.

## Approved product decisions

- The primary UI is a dedicated `/nexo-agents` page covering every client and workstation.
- Client detail keeps only contextual quick actions and a link to the installation history.
- Installation progress includes current state and immutable event history.
- A download does not prove installation. The first valid authenticated agent report is the only
  event that promotes an installation to `online`.
- A workstation-specific ZIP contains the platform binary, `agent.yaml`, an installation script, a
  manifest, and short instructions.
- A raw device token is generated for a package and exists only during that generation response. A
  later package generation rotates the token and produces a new package.
- Binaries are built once per Nexo Git revision and platform, then reused across workstation bundles.
- Remote update, reinstall, or command execution on a workstation is outside this delivery.

## Architecture

ForgeHub remains the system of record for installation intent and state. The Nexo repository remains
the source of the agent binary. The host bridge performs a small allowlisted build operation because
the containerized backend cannot compile `/root/project/nexo` directly.

The backend owns four boundaries:

1. **Build catalog:** records the Nexo revision and the Linux/Windows artifact produced from it.
2. **Package delivery:** rotates the workstation token, materializes a temporary ZIP, streams it in
   the same request, and records the delivery result.
3. **Installation tracking:** retains the current expectation and its append-only state history.
4. **Report reconciliation:** uses the existing report-ingestion transaction to confirm that the
   workstation is online and compare its reported version with the expected build.

The browser never submits a shell command or filesystem path. It selects a supported platform and an
existing workstation; the backend maps that request to a fixed host-bridge operation.

## Data model

### `NexoAgentBuild`

One row represents one compiled artifact for one Git revision and platform.

| Field | Contract |
|---|---|
| `id` | UUID primary key |
| `git_sha` | Full Nexo commit SHA |
| `agent_version` | Version reported/embedded by that source revision |
| `os_kind` | `linux` or `windows` |
| `status` | `queued`, `building`, `ready`, or `failed` |
| `artifact_path` | Server-controlled relative storage key; never accepted from the client |
| `artifact_size` | Size in bytes after a successful build |
| `sha256` | Lowercase checksum of the stored binary |
| `build_log_excerpt` | Redacted and bounded diagnostic excerpt |
| `started_at`, `completed_at` | Build lifecycle timestamps |
| timestamps | `TimestampMixin` |

`(git_sha, os_kind)` is unique. A ready artifact is immutable. A retry after failure updates the
failed row's lifecycle fields; a different source revision creates a new row.

### `WorkstationInstallation`

One row is the current installation expectation for a workstation. It is updated only when a new
package rotates the device token and selects another build.

| Field | Contract |
|---|---|
| `id` | UUID primary key |
| `workstation_id` | Unique FK to `workstations`, cascade delete |
| `build_id` | FK to the expected `NexoAgentBuild` |
| `status` | `package_ready`, `downloaded`, `online`, `outdated`, or `error` |
| `package_generated_at` | Time the latest token/package was generated |
| `downloaded_at` | First successful download response for this package |
| `online_at` | First accepted report matching this installation generation |
| `last_error` | Redacted operator-facing error, nullable and bounded |
| timestamps | `TimestampMixin` |

`online` means a valid report arrived after `package_generated_at`. `outdated` means a valid report
arrived but `last_seen_agent_version` does not match the selected build's `agent_version`. `error`
means the latest package generation left no deliverable current generation. A failed attempt against
an existing usable generation records `last_error` and an `error` event without replacing that
generation's status. Build failures remain on `NexoAgentBuild.status` and do not create a false
installation.

### `WorkstationInstallationEvent`

Append-only history for one installation row.

| Field | Contract |
|---|---|
| `id` | UUID primary key |
| `installation_id` | FK to `workstation_installations`, cascade delete |
| `event_type` | `package_generated`, `downloaded`, `first_report`, `version_mismatch`, or `error` |
| `from_status`, `to_status` | State transition snapshot |
| `detail` | Redacted and bounded explanation |
| `actor_user_id` | Admin actor for manual actions; null for agent-report events |
| `created_at` | Immutable event timestamp |

Events are not edited or deleted independently. Re-generating a package appends a new
`package_generated` event and resets the current installation timestamps appropriate to the new
generation while preserving history.

## State transitions

```text
ready build + generation committed -> package_ready
package_ready + completed streaming response -> downloaded
package_ready/downloaded + valid matching report -> online
package_ready/downloaded/online + valid mismatching report -> outdated
package generation failure with no usable current generation -> error
error + newly generated package -> package_ready
outdated + newly generated package -> package_ready
```

There is no re-download of a current package: each request generates a new token and archive. The
`package_ready` state therefore represents the short interval between committing the new token hash
and completing the response, or an interrupted delivery that requires generating another package.
Repeated reports update the existing workstation heartbeat; they do not append repeated
`first_report` events.

## Build and storage flow

1. An admin requests a build refresh.
2. ForgeHub obtains the Nexo `main` SHA through a fixed host-bridge operation.
3. For each missing platform artifact, ForgeHub inserts/updates a build row and requests the fixed
   build operation.
4. The host bridge checks out no branch and accepts no arbitrary ref from the browser. It builds the
   currently resolved revision with fixed commands for Linux and Windows, writes into a configured
   artifact root, and returns metadata.
5. ForgeHub independently verifies file existence, size, and SHA-256 before marking the row `ready`.

The artifact root is configured outside the repository. Binaries and ZIP packages are never
committed. Persistent storage contains only shared binaries. Workstation ZIPs are created in a secure
temporary directory for the response and removed afterward.

Only one build for a `(git_sha, os_kind)` may execute concurrently. Concurrent requests receive the
existing build state rather than launching duplicate compilers.

## Package contents

The archive name is deterministic and safe, for example
`nexo-agent-<workstation-id-prefix>-<os_kind>-<short-sha>.zip`.

```text
nexo-remote-agent[.exe]
agent.yaml
install.sh | install.ps1
manifest.json
README.txt
```

`manifest.json` contains the workstation ID, OS, Nexo version, full Git SHA, binary checksum, package
generation time, and configuration schema version. It does not repeat the raw device token.

The generated `agent.yaml` includes the ingestion URL, raw one-time device token, report interval and
the approved monitoring defaults. Configuration values are validated against explicit schemas; they
are not interpolated into shell commands. Installation scripts copy fixed files into documented
locations, register/start the supported service, and return a non-zero exit status on failure.

## API

All endpoints except the existing agent-report ingestion require an authenticated administrator.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/v1/nexo-agent-builds` | List builds and current source revision |
| `POST` | `/api/v1/nexo-agent-builds` | Start/retry the fixed Linux and Windows builds |
| `GET` | `/api/v1/nexo-installations` | List installation rows with client/workstation/build projections and filters |
| `GET` | `/api/v1/nexo-installations/{id}` | Installation detail and ordered event history |
| `POST` | `/api/v1/workstations/{id}/installation-package` | Rotate the token, generate the package and stream its one-time download |

The package endpoint requires a ready matching build and returns the ZIP directly with
`Content-Disposition: attachment`; it does not return the raw token in JSON. The archive is fully
materialized and validated before the transaction rotates the token hash and records
`package_generated`. After commit it is streamed once, then removed. Successful response completion
records `downloaded`; an interrupted response leaves `package_ready` and the administrator must
generate a new package/token. The endpoint never exposes storage paths.

## Report reconciliation

The existing `POST /api/v1/agent-reports` route already authenticates by the hashed workstation token.
Within its database transaction, after updating `last_report_at` and `last_seen_agent_version`, it:

1. finds the current installation for that workstation;
2. ignores reports whose authentication token predates the current package generation;
3. appends `first_report` once and sets `online_at` for the first accepted report;
4. compares the reported agent version with the expected build version;
5. transitions to `online` on match or `outdated` on mismatch;
6. appends `version_mismatch` only when entering or changing the mismatch condition.

Report ingestion remains successful when no installation row exists, preserving compatibility with
manually installed agents.

## User experience

### `/nexo-agents`

The page uses the existing authenticated `AppLayout` and adds one Operations navigation item. It
contains:

- a compact heading with the current Nexo source revision and a build action;
- platform build status with last successful build, checksum prefix, and failure details;
- filters for client, OS and installation status;
- a responsive table listing client, workstation, OS, expected version, detected version, package
  time, last report and current state;
- row actions to generate and download a new package, and to open history;
- stable inline pending/error regions so rows do not shift during mutations;
- empty, loading, partial-data and retry states.

Status is communicated by text and icon in addition to color. Destructive token rotation requires a
confirmation dialog naming the workstation and explaining that the previous package/token will stop
working.

### Client detail

Each workstation row shows its installation status and offers `Generate and download package` and
`View history` when applicable. It links to the dedicated page with the client/workstation filter
preselected rather than duplicating the full history UI.

All copy is localized in the existing English, Portuguese and Spanish namespaces. Layout remains
usable at narrow widths without dropping status or actions.

## Security and audit

- Build, package and download operations are admin-only.
- Raw device tokens are never logged, stored, returned as JSON, or placed in events.
- A package-generation transaction stores only the token hash already used by `Workstation`.
- Artifact paths are server-generated and constrained to the configured artifact root.
- ZIP entry names are fixed to prevent path traversal.
- Build commands and arguments are allowlisted in the host bridge; no generic `/v1/exec` payload is
  accepted from the frontend.
- Logs and database errors are redacted and bounded before persistence.
- Existing audit/governance records capture build requests, token rotation, package generation and
  downloads in addition to installation events.
- Responses do not expose whether a workstation belongs to another client outside the authorized
  admin scope.

## Failure handling

- Host bridge unavailable: build becomes `failed` with a safe diagnostic; existing ready builds stay
  downloadable.
- Build timeout or compiler failure: temporary output is discarded and no ready artifact is exposed.
- Artifact checksum mismatch or missing file: download is refused and the build is marked failed.
- Package materialization failure: token rotation and installation mutation do not occur; the failed
  attempt is audited with a redacted error.
- Client disconnect during streaming: no `downloaded` transition is recorded unless the response
  completes; the temporary archive is removed and the next attempt creates a new token/package.
- Report version mismatch: report ingestion succeeds and installation becomes `outdated`.
- Concurrent build/package requests: database uniqueness and row locking return the existing operation
  or a conflict response without duplicate artifacts or token rotations.

## Verification strategy

Backend tests cover:

- model constraints, migrations and append-only events;
- build idempotency, retry and concurrent-request behavior;
- fixed host-bridge command mapping and rejection of user-controlled paths/commands;
- artifact validation and checksum failures;
- package contents for Linux and Windows without persisting raw tokens;
- transactional rollback during package generation;
- authenticated one-time package delivery and event recording;
- report-driven `online`/`outdated` transitions and compatibility without an installation row.

Frontend tests cover:

- loading, empty, error and populated states;
- filtering and responsive action availability;
- build and generate/download mutation states;
- token-rotation confirmation;
- installation history rendering and accessibility labels.

Integration verification uses a synthetic workstation and a temporary artifact root. Operational
verification builds both binaries from an identified Nexo revision, downloads and inspects both ZIPs,
starts a test agent with the generated configuration, observes the first authenticated report, and
records the resulting `online` transition. No production client token or package is used.

## Out of scope

- Remote execution, automatic update, reinstall or uninstall on client workstations.
- Automatic delivery of packages to clients.
- Darckware client-area display and account linkage.
- Report/PDF generation.
- Editing raw Headscale policy.
- CI/CD release publishing or external artifact registries.
- Long-term retention policy beyond keeping shared versioned binaries and database history; retention
  may be specified after real storage usage is measured.
