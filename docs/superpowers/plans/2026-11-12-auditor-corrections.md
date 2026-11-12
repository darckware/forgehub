# Auditor Corrections Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task by task; targeted implementation may be delegated with review before integration.

**Goal:** Fix incorrect audit lifecycle/results and cover the new operational modules.

**Architecture:** Extend the existing API, read-only check scripts and canonical catalog. Keep recorded results immutable and expose evidence freshness separately. Independent progress checks must not call remediation or mission cycle functions.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, Python, React/TypeScript, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-12-auditor-corrections-design.md`

## Global Constraints

- No secret values, production mutation or direct SSH during implementation/testing.
- Use the isolated test database only; preserve real failures and historical audit rows.
- Eight-day evidence validity; future-dated evidence is unverified.
- Reuse the UI, badges and translations for pt-BR/en/es; no redesign.
- Honor disabled features, authorization boundaries and independent review.

## Review Focus

- Concurrent repair/verification must preserve one incident and archive only on proven recovery.
- A recent unrelated check must not make an old or incomplete audit look healthy.
- Queued, running or feedback-pending work must not disappear from health checks.
- Idle agents and explicitly disabled features differ from active but unobserved behavior.
- New checks must never invoke repair code or query credential values.

### Task 1: Incident reconciliation and expired evidence

- [x] Add failing API tests for remediation recovery, delayed verdicts, batch ordering and eight-day/future evidence.
- [x] Reconcile verification results using `_sync_check_incident` on remediation; assign explicit batch IDs without altering individual completion timestamps.
- [x] Add pure freshness classification; expose per-check `evidence_state` and `expires_at`, status `stale`/`last_complete_cron_run_at`; exclude stale evidence from green count.
- [x] Update Auditor UI and pt-BR/en/es text to show expired evidence, preserving historical results.
- [x] Run targeted backend/UI tests and build; review task.

### Task 2: Existing checks and application inventory

- [x] Add negative fixtures for missing deadlines, old work, due eligible queue and unsent terminal feedback.
- [x] Strengthen ECO-054 with aggregate metadata, known eligibility and explicit SLA constants.
- [x] Replace ECO-053 substring proof with structured safe validation/delivery evidence without reading credential values.
- [x] Add versioned target manifest for current applications, FileNest and SAEDAS; validate schema and fail closed for missing targets.
- [x] Align catalog descriptions and require explicit catalog IDs rather than a minimum count.
- [x] Run isolated ops tests; review task.

### Task 3: Independent module coverage

- [x] Instrument completed/failed worker passes without an always-alive heartbeat masking stuck work.
- [x] Add metadata checks for worker progress, Mission/Factory linkage, routine/activity evidence, machine freshness/execution deadlines and session expiration.
- [x] Register additive canonical checks/migrations; distinguish disabled features and missing evidence.
- [x] Add isolated negative cases and migration/checklist coverage tests; review task.

### Task 4: Integrated validation and delivery

- [x] Run backend suite, frontend suite/build, isolated ops suite, lint/diff checks.
- [x] Independent whole-change review; fix important findings.
- [x] Document release/install/rollback and remaining operational incidents.
- [ ] Commit reviewable changes; preserve main/develop alignment when publishing authorized work.

## Execution decisions

- Activity delivery uses only signed receiver metadata, never profile configuration or secret-bearing files. Idle agents are reported explicitly and are not delivery proof.
- Queue and terminal-feedback SLAs are 15 minutes; Activity webhook delivery SLA is 5 minutes. These are observation thresholds, not permission to reprocess work.
- Queue health uses the dispatcher's last examination timestamp to distinguish legitimate dependency/capacity waits from an unexamined due queue. Every due candidate must be stamped without changing content updated_at.
- Application inventory includes FileNest web port 8096 and SAEDAS web port 3200, confirmed from published Docker ports, with no configuration or credential inspection.
- All prospective Factory completion rules respect existing historical records; the audit does not invalidate historical accepted work retrospectively.
