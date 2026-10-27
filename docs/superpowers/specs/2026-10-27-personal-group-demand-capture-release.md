# Personal group capture release

Published on 2026-10-27 from `fix/personal-group-demand-capture`, implementation commits `dab6be5` and `721ae6c`. Original authorization is ForgeHub request #41598, explicitly covering tests, commit, push and deploy; Marcelo resumed that work in the current conversation. Independent review #41615 approved the implementation with nonblocking findings.

Root cause: group history exposed no persisted capture suggestion UUID. Maia passed invented identifiers to an acceptance tool that correctly requires a real UUID. The group intake API now validates a monitored source message, creates a real pending suggestion, and preserves group and requester provenance. Acceptance still requires Marcelo's explicit approval. Two new tools must also be included in Maia's scoped ForgeHub allowlist.

Addressed the review's three decision/retry findings: dismissal now locks and rechecks the suggestion and records an audit event; capture retries preserve a decided suggestion's UUID after edited acceptance; acceptance retries normalize whitespace. Added regression tests, observed all three fail before the fix, and then confirmed they pass. Remaining low-priority review notes include all-or-nothing group sync, synchronous source-file reads for currently small inventories, and ORM/migration naming differences.

Fresh verification: 22 source/MCP tests, 9 isolated PostgreSQL API/migration tests, 23 bridge runtime/monitoring tests, and 2 group-tab frontend tests passed. Frontend locale validation, TypeScript and Vite build passed, with existing bundle-size/dynamic-import warnings. Runtime tests report existing FastAPI lifecycle deprecation warnings. The production database was never used as a test fixture.

Deployment artifacts and read-only verification are under `/root/.forgehub/releases/personal-capture-721ae6c/`. The production database backup is mode 0600 inside its mode 0700 `backup/` directory; its PostgreSQL custom archive table of contents was checked. Migration advanced from `7d3a9e5c2b18` to `6b20f44a9e12`. Backend and frontend use the `personal-capture-721ae6c` images. This release preserves the existing monitoring base and does not replace or restart the host bridge or Hermes gateway.

Maia's loader now uses the versioned MCP source, including its Messages module dependency. Her scoped skill is version 0.7.0. Exactly `personal_whatsapp_group_register` and `personal_capture_from_group` were added to her ForgeHub tool allowlist. Configuration guard baseline was accepted with `--no-vault` because no credential changed. Original loader, skill and configuration backups remain in the release directory. The original repository checkout was left clean and unchanged.

A fresh MCP process using Maia's exact configured command/environment successfully initialized, advertised the required tools, and performed read-only project and suggestion calls. Authenticated reads of groups, suggestions and demands returned successfully; anonymous group access returned 401. Published frontend HTML matches the tested build. No personal production records or WhatsApp messages were created by verification.

## Remaining session activation

The already-open Maia Telegram session can retain the previous tool schema. Marcelo must issue `/reload-mcp` in that conversation and confirm the built-in prompt. The installed Hermes supports a profile-scoped reload that refreshes cached tools without discarding history. No supported remote endpoint for this Telegram-session reload was found; no gateway restart or process termination was used as a substitute. Until the reload is observed, this release does not claim that the existing Telegram session has loaded the new tools or that the seven actual requests have been registered.

## Rollback

Use `rollback.override.yml` to restore `monitoring-b7f802f` application images, restore Maia's loader/skill/configuration backups, and accept the intentional configuration rollback in the guard. Retain the additive database schema after group records exist; the migration refuses destructive downgrade. Do not erase personal captures or reset historical agent runs to retry them.
