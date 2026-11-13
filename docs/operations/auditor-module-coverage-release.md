# Auditor module coverage release

This release adds company checks ECO-061–066 and the
`company.operational_worker_observations` table plus nullable audit-run
`batch_id`. It does not synchronize the separate Foundation checklist
automatically. Recorded check runs remain
unchanged, including their original results and descriptions.

## Operator installation

1. Back up the application database using the established database backup
   procedure, and verify the backup can be restored. Record the current release
   commit and migration revision. Back up Athos's installed verifier and any
   existing helper files outside the installation directory.
2. Pause the scheduled ecosystem audit while the release is in progress. Keep
   the prior profile verifier and catalog available for rollback.
3. Apply migration `4c219b76ae03` through the normal deployment process after
   the previous head `1994f24fd6e1`. It inserts only the six new company audit
   rows, preserves preexisting enablement on conflict, and refreshes descriptions
   for ECO-005, ECO-006 and ECO-053. It does not update audit run history, retired
   IDs, existing disabled checks, or the ECO-047 IPv4 authorization baseline.
   Then apply append-only migration `6e29cba08d41`, adding nullable indexed
   `audit_check_runs.batch_id`. It leaves all historical timestamps/verdicts
   intact. Full checklist runs share a batch UUID while each command keeps its
   actual completion time; single checks and remediation remain unbatched.
   Cron completeness uses that UUID; legacy null-batch runs retain only their
   shared transaction timestamp as evidence of full coverage.
4. Deploy/restart the backend containing worker instrumentation. Then install
   the reviewed release files from `ops/athos/`: the verifier,
   `module_health.py`, and the versioned target manifest. Keep these from the
   same release and preserve file ownership and modes. The module helper may
   live beside the installed verifier; the repository release path is the
   fallback. Do not install from a developer's uncommitted checkout.
   Initialization by a process that owns background workers
   registers workers as starting, with an explicit disabled row for Mission
   when only that feature is off. Processes with all background workers
   disabled do not write observations: this prevents a dev/test API instance
   sharing the database from masking a stopped production worker. Existing
   evidence therefore ages and eventually fails; absent evidence fails too. Wait for real
   successful passes before interpreting coverage: dispatch 30s, feedback 120s,
   routine 60s, mission 60s, machine status 900s. Successful machine collection
   is required; source-unavailable passes record an error.
5. The operator must separately synchronize the governed Foundation catalog
   using its established catalog workflow: register ECO-061–066, refresh the
   three revised descriptions, preserve existing row identities and log history,
   and retain retired ECO-021 and all disabled controls. Review a catalog diff
   before applying it. No Foundation synchronization was performed during this
   implementation.
6. Resume the scheduled audit. Run each new check through the existing Auditor
   flow and review aggregate counts. A missing worker fails. Explicit disabled counts describe policy and
   are not evidence of active execution. Empty module populations describe idle
   state, not exercised behavior. Do not repair or change production records to
   manufacture passing evidence.

## Read-only coverage and limits

The six new checks read bounded aggregate metadata through the existing
verifier psql transport, exclusively from the company schema. They never invoke
Mission's watchdog, repair, host execution, SSH, profile configuration parsing,
or secret-value reads. Output contains counts; unavailable or malformed data
fails as not verified without exposing exception text.

ECO-061 checks all five registered workers, exact interval policy, failed or
stale passes, future timestamps and stalled in-flight passes. Its allowance is
`max(2 * interval + 120, 180)` seconds. An older run cannot overwrite a newer
run's completion. Telemetry failures do not interrupt operational work.

ECO-062 checks Mission status projection, live baseline ownership, active
orchestrator coordinator membership and coordination routines when cycles are
enabled. Explicit disabled cycle policy does not require an enabled routine.
ECO-063 checks task origin/project consistency, allowing change-request origins
and accepted historical tasks without retroactive execution/review requirements.
These metadata checks cannot prove file contents, repository integration or
artifact correctness; existing completion guards retain those responsibilities.

ECO-064 requires all enabled registered machines to have an observation within 35
minutes, reports unavailable machine collection, and checks host execution
heartbeats, overdue running machine results and agent Task links. Client-linked
machines are included through stored observation metadata only; no client login
or remote session is opened. Browser sessions belong to ECO-065. Heartbeat staleness
uses the runner's 90-second policy. Per-result deadline grace is five minutes
and respects an open retry window.

ECO-065 checks session ownership/time metadata and activity after expiry. An
expired session with a still-active row is valid when activity stopped before
expiry: authentication already rejects expired tokens. ECO-066 checks overdue
scheduled/running occurrences on enabled routines, ordinary running occurrences
without a Messages demand, and completed ordinary runs lacking expected evidence
unless they recorded no action. Mission coordination has its own decision
records and is exempt from ordinary demand/evidence requirements.

## Rollback

Restore the previous backend and reviewed profile backup as one release.
Disable ECO-061–066 in both catalogs using the operator workflow, preserving
existing IDs and history. A schema downgrade disables the six company rows and
drops worker observations and the new batch column/index; it never deletes audit runs or changes recorded verdicts/times. Prefer leaving the
additive table in place until rollback stability is confirmed. Keep observations
or a database backup if their diagnostic evidence is needed. Re-upgrading
preserves existing enablement, so an operator must explicitly review whether to
re-enable rolled-back rows.
