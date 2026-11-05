# Execution ledger

Plan: docs/superpowers/plans/2026-11-05-personal-work-groups.md
Base: 2d0d6b9
User authorized implementation after diagnosis, including visible archive buttons and batch investigation.
Ruling: work in an isolated sibling checkout to preserve concurrent ops changes in develop.
Preflight: backend group predicates supply frontend filters, counts and contexts. Existing API default all remains compatible; new UI defaults tasks. Source-specific Moodle approval remains authoritative.
Diagnosis: #42028/#42029 approved remotely but blocked run interpreted local pending as no approval; current MCP source already removed the historical sticky claim guard and skill warns local pending is not authoritative. Later batches #42087-89 and #42090-91 finished successfully. #42095 Moodle finished completed but execution report malformed. No reapproval/replay permitted.
Ruling: add an explicit read-only remote approval-status tool and mark local status as local instead of changing authorization storage. This adds MCP/skill scope requested by batch investigation; it does not alter the Telegram plugin or credentials.
Ruling: preserve strict completion-report parsing; display operation outcome separately from runner/report outcome rather than guessing task completion from prose.

Backend: 40 regressions passed on isolated test Postgres. Frontend: 460 full-suite tests passed; targeted 20 passed after archive selection fix. MCP: 148 passed, one harness-dependent skipped. Build passed.
Final review: independent reviewer completed both diffs; important findings fixed with RED→GREEN tests. MCP read-only annotation regraded as important because clients use it to distinguish queries from mutation; fixed with catalog regression.
Ruling: preserve static-audit backlog (51 baseline occurrences, no new signatures), rather than modify unrelated screens.
Ruling: promotion uses stable Messages identity, avoiding lifecycle-dependent empty results. Loading/error headings omit counts.
Ruling: clear item selection after confirmed mutations to avoid subsequent batches reusing stale versions; regression reproduced before fix.
Browser: Chrome local fixtures passed groups, archive confirmation, empty active queue, Moodle/report separation and 390px page-width assertion. Artifacts: /tmp/forgehub-groups-browser.
Deployment, installed skill sync and historical archival not performed. Archive cutoff unresolved.
