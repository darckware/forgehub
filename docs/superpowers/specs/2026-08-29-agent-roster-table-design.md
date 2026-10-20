# Agent roster table and canonical registry design

## Goal

Replace the Agents card wall with a sortable table whose rows expand in place, add uploadable agent photos, and ensure only Foundation-recognized agents appear as active roster members.

## Canonical roster

The active roster is the intersection of provisioned Hermes directories and the active runtime registry in `ECOSYSTEM_AGENTS.md`, plus the four external runtime agents already registered by runtime sync. `PROFILE_LIFECYCLE_REGISTRY.yaml` remains authoritative that archived specialist names are roles, not active agents; a restored directory alone cannot reactivate one.

Foundation sync will no longer register undocumented directories. Existing Hermes rows outside the active registry will be soft-retired so their audit history is preserved. The Agents page defaults to active rows. A migration will remove only records whose names and slugs prove they are automated-test fixtures; it will first remove their test-owned chat data in dependency order.

Tests continue using the real application database, as required by repository guidance, but session startup and teardown will clean known fixture signatures so interrupted prior runs cannot keep polluting the next run.

## Agent photo

`agents.avatar_data_url` is nullable text, matching the established user-avatar storage pattern. Updates accept JPEG, PNG, or WebP data URLs only, with a decoded size limit of 512 KiB enforced by the backend. The frontend validates before reading/sending and preserves the current image on error. The detail row supports upload, replacement, and removal; the table uses initials when absent.

## Table interaction

The native table includes photo, agent, function, organization, runtime/tier, status, and inventory columns. Sortable headers are buttons with `aria-sort`; sort key and direction live in URL parameters. Clicking a summary row opens the current detailed content immediately below it. Clicking it again closes it, and opening another row closes the previous one. A dedicated native button provides keyboard access without changing table semantics.

The canonical roster is intentionally small, so this release uses bounded client-side sorting rather than pagination. Loading, error, empty, no-results, expanded, pending-upload, upload-error, delete-pending, and delete-conflict states are explicit.

## Delete behavior

Deleting a legitimate agent with dependent operational history must not silently destroy that history. The API catches the foreign-key conflict and returns HTTP 409 with guidance to retire the agent. The confirmation UI stays open and displays the server message. The migration cleanup is narrower: it deletes only recognized fixture records and their recognized test-owned chats.

## Verification

Backend tests cover canonical profile selection, soft retirement, avatar validation/update, fixture cleanup selection, and delete conflicts. Frontend tests cover sorting, URL state, one-row expansion, keyboard activation, avatar fallback/upload validation, and visible mutation errors. Final verification includes Ruff, targeted and full pytest where feasible, Vitest, TypeScript/Vite build, premium static audit, DESIGN.md lint, and browser checks in desktop and narrow viewports.
