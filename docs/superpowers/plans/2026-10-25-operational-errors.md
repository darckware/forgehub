# Operational errors correction plan

**Goal:** Repair confirmed operational defects and preserve evidence for unresolved failures.

**Scope:** Existing incident #41560 and the live ecosystem audit findings from 25 October.

- [x] Validate the existing ForgeHub incident patch with isolated database tests.
- [x] Reproduce and fix obsolete runtime and backup checks with regression tests.
- [x] Correct the system backup target's nonexistent `/root/agents` path, then execute and inspect a new backup through the normal queue.
- [ ] Validate voice policy against dated decisions without overwriting Lara/Maia's female voices.
- [x] Diagnose listener and log rotation findings before preparing service changes.
- [x] Re-run affected controls and record exact remaining failures, release requirements and rollback.

Preserve unrelated SSH/UI work, message/run history and credentials. Do not retry uncertain agent runs or send external messages. Production changes must have a concrete reviewed diff and observable verification.

Backup execution reached remote upload, which failed on Google Drive quota; local recovery is retained. Voice activation and production backend deployment require the pending operator decisions. Plan review is recorded separately at `/root/project/forgehub/docs/reports/2026-10-26-integrated-plan-readiness-review.md`.
