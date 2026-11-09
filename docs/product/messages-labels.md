# Messages: automatic labels and operator routing

**Publication status:** the read-only catalog, legend and classification slice is prepared in
the development worktree. It is not active in the current production artifact. The factual and
operator-answer reachability checks in Task 1 of
`docs/superpowers/plans/2026-11-09-mission-messages-maturation.md` are its qualification gate.

Messages uses its existing folders. Labels describe backend facts; they neither create a
queue nor authorize actions. The frontend displays up to three known, distinct labels per
message, using the same catalog in the main row, reading pane and right-side legend.
Names and explanations are localized in pt-BR, English and Spanish.

The toolbar's **Legenda das etiquetas** icon opens a right-side, read-only dialog. Escape
closes it and restores focus to the opener. On narrow screens it occupies the viewport
width; content scrolls within the panel. The existing modal owner handles keyboard focus
and makes the background inert.

## Entrada

Received work which has not entered execution. `analysis_pending` means analysis has not
finished; `missing_context` identifies missing source/objective/execution data. Only
`authorization_pending` (Aguardando sua autorização) or `decision_pending` (Aguardando sua
decisão), with a backend operator destination, directs the operator to Personal.

## Saída

Routed work which has not entered execution. `analysis_pending`, `ready` and `scheduled`
separate analysis, eligibility and a registered future schedule. A real authorization or
question retains its explicit decision label and destination. An executor wait leaves
Entrada/Saída and belongs to the existing Execução folder; list membership and counts use
the same predicate.

## Incubações

Parked work and ideas remain incubations. Analysis is not permission to implement them.
`decision_pending` links a genuine incubation decision to its existing guarded promotion
workflow. `awaiting_information` and `awaiting_dependency` describe blockers; they do not
imply a human decision. `possible_obsolete` is a suggestion, not proof.

## Execução

This existing folder includes open attempts and already-authorized tasks labeled
`awaiting_executor`, even before their first attempt. It does not absorb ordinary new
unclassified tasks. `quota_unavailable`, `executor_busy`, `executor_unavailable` and
`executor_unassigned` explain the wait. They never request approval again. A known next
check uses `execution_wait_until`; no date is invented.

Other blockers remain distinct: `awaiting_information`, `awaiting_dependency` and
`awaiting_service`. `scheduled` is a recorded schedule, `ready` is eligibility subject to
server checks, and `running` means an attempt is active. `awaiting_verification` requires
outcome verification, `uncertain_execution` prohibits blind repetition, and
`needs_correction` identifies an unfinished attempt without inventing human approval.

## Concluídas

`completed` records completion by the owning workflow. A completed diagnostic describes only
that diagnostic record; it does not complete its original task or prove the original delivery. `delivery_verified` records proof
bound to the current work; it never rewrites previous failed attempts as successes.
`informational_feedback` is information, not new executable work or authorization.

## Arquivo

`archived` (Arquivada) records that the message was archived, including an unverified failed
attempt. It never labels that attempt as completed or successful. Archive preserves history
and removes items from active folders. It does not complete,
cancel or authorize execution. `obsolete` is a recorded supersession;
`possible_obsolete` and `possible_duplicate` remain advisory. Similar wording alone never
proves delivery, permits closure/merging, or grants permission to delete history.

## Human destinations

The backend fields `operator_decision` and `operator_destination` identify actual pending
human work. The links are:

- `agent_tasks`: Pessoal · Tarefas dos agentes, decision view.
- `incubations`: Pessoal · Incubações, decision view.
- `moodle_approvals`: Pessoal · Aprovações Moodle, existing approval panel.

Executor capacity waits are handled by the existing analysis/dispatch engine. The UI does
not re-approve, enqueue, retry or create another task merely to render a label. Backend
execution guards, context/version checks, authority and evidence remain authoritative.

Catalog owner: `frontend/src/lib/messageLabels.ts`. Localized copy owner:
`frontend/src/i18n/locales/{pt-BR,en,es}/demands.json`. Runtime fields are additive and default
to an empty label list/null metadata for older responses.
