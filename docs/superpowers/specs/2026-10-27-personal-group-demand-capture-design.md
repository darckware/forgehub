# Personal contacts and monitored WhatsApp groups

User authorization: fix Maia's group demand registration; add separate Personal contacts and WhatsApp groups tabs; register only monitored groups; Maia may register those groups. Existing suggestions still require explicit acceptance before a personal demand/task/note is created. No group post or business record is created by verification.

Reuse existing contact capture and Pessoal UI. Add a monitored-group registry (real backend UUID, unique WhatsApp group id) and group-origin suggestions; contact ids become nullable with exactly-one-origin constraint. Backend independently validates registry/intake against the fixed Maia monitoring inventory and actual message record, exposed through the existing read-only /host-root mount; no arbitrary paths or fabricated contact. MCP reads return a stable reference to actual captured records (the plugin currently does not preserve a native WhatsApp message id). Suggestions get a real database UUID.

Create group/suggestion idempotently with unique origin+message+kind+item key, rejecting conflicting replays. Accept locks the suggestion, creates an item only once and audits actual actor, origin and result ids. Preserve source group, author, timestamp and record fingerprint; do not duplicate whole conversations into audit payloads. Group history remains linked when monitoring stops; active registry lists only monitored groups. Missing monitoring source is unavailable, never empty or implicit authorization.

Add group registration/capture tools only to Maia's existing personal MCP scope. Update her scoped overlay with actual signatures/identifiers. Existing contact tools keep working. PersonalPage preserves its contacts tab id but labels it Personal contacts and adds WhatsApp groups using existing tokens/tables/detail primitives; source details appear in suggestions. No theme changes.

Verify source validation/traversal/ref stability, API permissions, idempotency/concurrency, audit and provenance, original contact conversion, MCP registration and fixture-backed UI at 390/1440. Use an isolated synthetic PostgreSQL fixture, never production conftest or real group demand for testing. Publish additive migration and isolated backend/frontend builds after independent review, preserving current monitoring release and unrelated original checkout.


## Verification and rollout

Source/MCP unit tests: 22 passed. Isolated PostgreSQL API/migration tests: 6 passed, including Maia-only access, concurrent intake and acceptance, unchanged contact provenance, rollback refusal with group data, and empty-schema downgrade/upgrade preserving contacts. Host runtime/monitoring tests: 23 passed. Existing frontend and new group-tab tests: 18 passed. TypeScript/Vite production build and mocked browser flows at 390/1440 passed. Synthetic browser screenshots are in /tmp/personal-{demands-origins,whatsapp-groups}-{390,1440}.png; no personal production record was inserted for testing.

The Messages failures #41594/#41596/#41598/#41599 occurred before work, because Codex was invoked outside a Git repository. The runner now permits an explicitly supplied non-Git directory with --skip-git-repo-check while preserving its sandbox mode and approval behavior. A .git placeholder alone is not a repository: recognize a worktree .git file or .git/HEAD. Original failed runs remain immutable. #41608 is a separate partial Moodle delivery blocked by tool access; this patch does not claim its completion.

Release must back up affected tables and migration state before the additive migration. Keep the additive schema on an application rollback once group data exists; never erase captures to force downgrade. Deliver the same MCP files to the host factory-server source and update Maia's scoped reference after backend availability. Never restart the shared Hermes gateway. Existing group requests are not automatically accepted or fabricated during deployment.
