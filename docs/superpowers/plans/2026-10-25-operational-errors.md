# Operational errors correction plan

**Goal:** Repair confirmed operational defects and preserve evidence for unresolved failures.

**Scope:** Existing incident #41560 and the live ecosystem audit findings from 25 October.

- [ ] Validate the existing ForgeHub incident patch with isolated database tests.
- [ ] Reproduce and fix obsolete runtime and backup checks with regression tests.
- [ ] Correct the system backup target's nonexistent `/root/agents` path, then execute and inspect a new backup through the normal queue.
- [ ] Validate voice policy against dated decisions without overwriting Lara/Maia's female voices.
- [ ] Diagnose listener and log rotation findings before preparing service changes.
- [ ] Re-run affected controls and record exact remaining failures, release requirements and rollback.

Preserve unrelated SSH/UI work, message/run history and credentials. Do not retry uncertain agent runs or send external messages. Production changes must have a concrete reviewed diff and observable verification.
