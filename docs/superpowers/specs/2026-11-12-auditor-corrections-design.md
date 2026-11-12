# Auditor correctness and module coverage

The operator authorized correcting the issues in the post-deployment review
`/tmp/forgehub-auditor-review-2026-11-12.md`. Preserve real failures; improve
what the Auditor measures rather than mark unknown state healthy.

Extend the existing Auditor domain and installed-script release source. Do
not build a second monitoring application. Do not mutate production, access
credential values, reveal key material, rewrite audit history or invoke repair
functions during verification. Existing permission and approval boundaries stay.

The implementation approach is additive: reconcile incident lifecycle on all
verification paths; compute evidence freshness separately from recorded results;
strengthen the existing deterministic read-only checks; add independent module
coverage and worker pass observations. Keep the current table and admin UI,
with an explicit expired-evidence indicator. An eight-day freshness window
matches the existing weekly monitoring contract. No absence or disabled feature
may be silently treated as a working active module.

Coverage must include Messages queue/deadlines/feedback, Activities delivery,
Mission/Factory traceability, worker progress, machine observations/execution
deadlines, session expiry and a versioned target inventory for the existing
applications plus FileNest/SAEDAS. Checks use aggregate metadata and pure
predicates. Negative fixture tests run only against the isolated test database.
New checks are registered through a migration using canonical metadata and
safe default activation; profile installation, production migration and deploy
require the existing backup/rollback process. Hindsight backup and memory
curation remain operational incidents; this change does not fabricate recovery.

The IPv6 ECO-047 authorization baseline is not widened. ECO-060 remains metadata
only and retains the exact seven already acknowledged rows.
