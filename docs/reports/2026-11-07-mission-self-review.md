# Mission release review requested by Marcelo

**Verdict: APPROVED AFTER CORRECTIONS for the mission-management release.** No blocking findings
remain in the reviewed code. This is not acceptance of the real FileNest mission.

Authorization: Marcelo explicitly instructed **“faça você a revisão”** after the official
Porthus request #42236 was blocked by quota. Aramis therefore performs this release review in
the current session. This is an explicitly authorized self-review of this delivery, not a
Porthus approval or an ecosystem-wide change to review policy. Mission task self-review and
human acceptance guards are unchanged.

Scope: commit `3954f37801013191dc53b16c3a680e2b43a131a2` against `d84a445`, plus the corrections
below. Unrelated ECO-047, diagnostics and integrated-plan changes are excluded.

## Findings and corrections

1. **P1 — generic project PATCH bypasses mission metadata controls.** The existing project route
   still accepted mission name, description and working directory without mission authority,
   row version or state checks. It now refuses these fields for missions with
   `MISSION_METADATA_REQUIRES_COMMAND`. Administrative edits must use the guarded mission
   command. Nine regressions cover all three fields in draft, active and completed states;
   values and row versions remain unchanged after refusal. Common projects retain their API.
2. **P2 — edit validations diverge from creation.** Mission PATCH accepted a relative working
   directory and a name already used in the same product version. It now uses the creation
   rules: absolute directory (or null), and normalized name uniqueness under the shared advisory
   lock. Existing-name case-only edits remain valid. Two regressions cover relative paths and
   case/whitespace-insensitive name collisions with no partial writes.
3. **P2 — quota failover could replace the selected reviewer silently.** The review demand now
   has `fixed_agent=True`. It waits for the selected agent rather than having its prompt handed
   to another identity while the review row still names the original membership. An explicit
   reviewer change continues through the existing independent-review guard. The regression
   failed with the original false flag and checks the real `can_switch` predicate after the fix.

The eleven metadata regressions failed before the corrections. The focused mission/project suite
then passed 67 tests; scoped Ruff and diff checks passed. A full run on those metadata fixes
passed 1,974 tests with 21 skipped. The final complete run including reviewer ownership also
passed **1,974 tests, 21 skipped**, with 23 warnings, in 377.15 seconds. The current frontend
mission pages passed 25 tests; no frontend source changes were
needed for the backend corrections above.

## Review boundaries

Inspected creation/edit/cancellation authority, projected states, row-version snapshot behavior,
baseline protection, member role/permission validation, inactive member release, retry keys,
review independence and atomic refusal, task/brief/criteria source selection, source hashes,
32 KiB refusal and separate executor/reviewer instructions.

The earlier local review's stale-form and inactive-member issues were verified as fixed in
`3954f37`. Native select popup keyboard behavior remains a documented verification limitation.

Publication is recorded separately. The final reviewed commit, verification results,
image IDs and publication evidence will be recorded in the release manifest after completion.
The real FileNest pilot requires its actual plan/baseline and readiness gates; a code review is
not evidence of that mission's acceptance.

The superseded Porthus request #42236 was updated with Marcelo's instruction and archived through
the canonical ForgeHub channel without a run or fabricated approval. Its original content was
retained. No quota/availability fields were changed.

Planned release configuration: enable `MISSION_TOOLS_ENABLED` so the guarded team-management
command used by the delivered UI is available; keep `MISSION_CYCLE_ENABLED=false` until the
real mission's plan and readiness gates are met. This does not create a FileNest mission or
approve a baseline, and does not change independent-review enforcement on mission tasks.
