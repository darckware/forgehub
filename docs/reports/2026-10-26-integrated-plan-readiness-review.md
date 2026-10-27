# Integrated plan readiness review

Scope: `docs/plano-integrado/`, the most recent consolidated system-adjustment plan found locally. Marcelo requested review after the operational corrections. This is a review artifact; it does not approve implementation or modify the plan.

## Verdict

The proposal is not ready to dispatch as implementation tasks. The existing consolidated review correctly identifies unresolved design and verification issues, but its proposals have not yet been incorporated into the normative phase documents. Phase 0.14 and Marcelo's decisions in 0.15 remain gates, not formalities.

## Findings requiring correction before approval

1. **Independent review assigns two names to the same identity.** Consolidated item D2 (`revisao/CONSOLIDADO.md:86`) assigns implementation to Claude Code and review to Porthus. Foundation `14_agents/WORK_AGENT_ROLES.md:12` identifies Porthus as Claude Code. This cannot satisfy independent review merely by changing labels. Assign distinct registered agent identities and enforce `reviewer_agent_id != executor_agent_id`; retain Porthus as reviewer when Aramis/Dartan implement, or explicitly appoint another independent reviewer when Porthus implements. The older task M0.2 in `04-missao-pipeline-e-papeis.md:206` assigns Aramis, which avoids this collision and illustrates the unresolved ownership divergence.

2. **The wave order blocks its own exit.** P.6 depends on G.11 (`07-fases-de-implementacao.md:82`), while the diagnostic assigns P to Wave 2 and G to Wave 3 (`01-diagnostico-e-ondas.md:49–72`). Wave 3 starts after Wave 2 exits. As written, the Wave 2 supervision screen waits for a later wave. Move a minimal G.11 decision queue into Wave 2, or split P.6 so its Wave 2 acceptance does not depend on G.11. Record the chosen dependency in both the wave inventory and task graph.

3. **Test isolation is a principle without a prerequisite edge on V-a.** `07-fases-de-implementacao.md:36–64` defines validation before the minimal mission, while its parallelism diagram starts T and V-a together (`:335–343`). T.6 explicitly requires V to use the test environment (`:167`). Make T.2 plus simulated external integrations in T.3 prerequisites to state-changing V-a tests. A local schema-only test database used for the operational correction does not implement the plan's full separate test container, frontend, secrets, mocked integrations or reset workflow.

4. **The authoritative first-mission and test rules still conflict.** The diagnostic suggests C.0+C.1 as the first mission (`01:83`), but M0.5 names the complete integrated plan (`04:209`). The consolidated review proposes C.0+C.1 and says the mission record stays in production while each system-changing task first runs in test (`CONSOLIDADO:49,107`); the Wave 1 exit still says the first mission itself ran in the test area (`01:46`). These proposals must become one operational rule before agents receive tasks. This was already recognized in A1/F6; it remains an unapplied correction, not a new finding.

5. **Backup readiness is overstated.** The diagnostic's blanket statement that external backup works (`01:24`) and G.12's prerequisite "backup externo (já funcionando)" (`08-inteligencia-operacional.md:52`) are insufficient today. Per-project snapshots exist, but the system target failed on a nonexistent path, then the corrected upload hit shared Google Drive quota. Require recent successful evidence per critical target and a sample restore before marking recovery ready; keep aggregate successful runs separate from completeness. The private local Foundation SQL copy is useful recovery material, not proof of offsite protection.

## Already identified in the consolidated review

Carry these items into the updated tasks rather than opening duplicate work: verified execution plus independent approval before `done/deployed` (B1), preserve `TaskExecutionReview` and membership permissions during orchestration retirement (B2), dispatch authorization tied to baseline content hash (B4), mission-tool endpoint/auth/idempotency contracts (D3), code-delivery specification Q.0 (D4), typed evidence verification in Wave 1 (B7), and authoritative mission state/model mapping (A2–A4).

Eight explicit operator decisions remain listed at `revisao/CONSOLIDADO.md:169–180`, including how to cover Dartan's unavailable frontend review. Technical agreement on the direction is not approval of these choices or proof of delivery.

## Recommended next review gate

First incorporate the accepted consolidation into 01/04/07/08/09 and mark superseded sections of `missao-especificacao.md`. Then check distinct identities, dependency edges and Wave 1 acceptance against the same version of the plan. Complete the cross-review, present D-1 through D-8 to Marcelo, and only then register/release the approved implementation tasks. No implementation was started by this review.
