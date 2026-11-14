# External agent quota waits

## Intent and requirements

Marcelo requests a visible indicator when Codex, Claude Code or agy exhausts its
quota and awaits reset. This is not a work failure and must not cause archival.
Existing message labels and availability records are the presentation owners.

## Approaches

1. Change only labels: insufficient; failure notifications, diagnostics and
   mission transitions still treat quota as failed work.
2. Reuse the queued/null status: insufficient for unknown resets and protected
   executions; null with a persisted run ID means an active execution today.
3. Recommended: explicit nonterminal `waiting_quota` dispatch state, using the
   existing quota label and optional reset timestamp. Preserve the run evidence.

## Behavior

- Show “Aguardando reset da cota”, executor identity, reset date/time when supplied,
  and “Horário não informado pelo provedor” otherwise. Reuse localized badges in
  Messages and the personal agent work queue; verify at 390px and 1440px.
- Waiting tasks belong to waiting/execution views, not errors or completed work.
  Do not emit work-failure notifications, create failure diagnostics or archive
  merely because the runtime reports quota exhaustion.
- Preserve attempt history, run identity, result and authorization. Quota cannot
  exhaust the work-failure retry budget. Waiting does not occupy an executor slot.
- Release a recognized reset through the existing scheduler and current dispatch
  guards. An unknown reset remains null and blocks automatic retry; no guessed
  timestamp. Marcelo confirmed that the task waits for the same agent.
- Approval-bound executions, project execution records and missions resume only
  through their owning workflow, with effect/approval checks intact. Never create
  parallel executions or bypass review independence to resume after quota.
- Do not reopen archived historical records automatically. Historic cleanup is a
  separate explicit operation based on verified records.

## Implementation and verification

Add the dispatch state and optional reset metadata with a migration; update
finalization, scheduling, mission waiting, classification, triage and API/frontend
contracts together. Reuse the current availability parser for all three runtimes.
Tests cover known/unknown reset, retry-budget exhaustion, protected executions,
mission/reviewer identity, no diagnostic or archival, safe resumption, and genuine
failures retaining their behavior. Use only the isolated database; run lint,
frontend typecheck/build and browser checks. Independent review targets dispatch
and mission safety before any production publication.

## Current status

Design approved by Marcelo on 2026-11-14. Implementation and validation proceed in
fix/quota-wait-indicator. Approval covers the same-agent policy. Integration and
production publication require approval of the final reviewed content.
