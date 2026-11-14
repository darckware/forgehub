# Auditor

Route: `/auditor`; navigation: **Operations → Auditor**.

The screen is the operational surface for the Hermes/Foundation ecosystem audit. The
canonical catalog covers `ECO-001`…`ECO-066`; `ECO-021` is retired and stays disabled.
Four Athos routines in Operação 24x7 run the daily, weekly, monthly and quarterly tiers,
at 19:00 America/Sao_Paulo: daily, Sunday, day 1 of each month, and day 1 of
January/April/July/October respectively. Controls can change tier on the Auditor page;
“Executar faixa agora” requests a routine batch. Manual full runs and routine batches
share the same execution lock. See [frequencies and activation](../runbooks/auditor-frequencies.md).
The legacy `ecosystem-weekly-audit` Hermes cron remains the fallback until activation
is verified and the cron is paused.

## Athos scheduler monitor

`GET /api/v1/audit/status` includes `athos_monitor` alongside the existing checklist counts. The
monitor reads the Athos cron store through the Foundation loader and compares the job name, script,
schedule, enabled state, scheduler health, and latest ForgeHub run requested by `cron`. Its state is
`healthy`, `degraded`, `failed`, or `not_configured`, with concrete reasons in `issues`. A missing or
duplicate job, drift, overdue scheduler, or audit run older than eight days degrades it; a scheduler
error or unreadable Athos store fails it. With all four routines enabled and the legacy cron
paused, the monitor shows “Substituído pelas rotinas” (`replaced`). An individual failed
control changes the checklist count, not the scheduler state. The existing
bridge-token-protected endpoint remains the cron trigger.

ECO-023 requires the four schedules and recent complete batch evidence (2/8/32/93 days),
or the initial grace period from `enabled_at`; future timestamps do not establish recency.
A completed empty tier requires `no_action=true`, `evidence_received=false`, no enabled
controls and no batch results. The enabled legacy cron can still satisfy ECO-023 during transition.

ECO-064 checks machine observations, execution health and task linkage, plus historical
collaboration authorizations, executions, machine results and session/server audit witnesses.
It emits only counts and does not compare the Task's current run with an older authorization.
Each command-run event on both the session and server must carry the original
`command_sha256` and `execution_command_sha256`, captured after trusted Python
masking by `launch_execution`. ECO-064 verifies these digests and the exact stored
command in the execution's started event; it does not translate masking regexes
into SQL. A missing digest fails verification, including older collaboration
records. The API has remained dormant; no compatibility bypass is provided.
The collaboration API remains dormant. Missing optional tables are inapplicable only when
both are absent, the verifier's `REMOTE_COLLABORATION_ENABLED` switch is false and no
collaboration audit history exists. Partial/missing expected schema and unreadable metadata
fail verification. Any future activation must propagate that switch to the verifier too.
This check imposes no collaboration session requirement on authorized direct development;
the Foundation exception of 2026-11-14 retains protected credentials and trusted capture.

## Profile view

The profile pills filter controls by their responsible Hermes profile. `ECO-031`…`ECO-038` each
validate one profile's required `AGENTS.md`, `FOUNDATION_LINK.md`, `HEARTBEAT.md`, `IDENTITY.md`,
`MEMORY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`, active memory files, `config.yaml`, Knowledge Base
directory, Foundation/ForgeHub/ForgeRouter/Hindsight context, knowledge hook, and owned script.

## Correction cycle

Correction is never part of a normal audit run. The wrench appears for an unhealthy control and an
administrator must confirm the action explicitly. ForgeHub sends the full control, latest evidence,
working directory and configured correction to the Athos profile through the dedicated host-bridge
remediation route. Athos diagnoses and applies the smallest scoped correction with filesystem
checkpoints enabled. The backend records this as `athos-remediation`, then independently executes
the original control as `remediation-verification`.

The verification result, not Athos's wording, decides the outcome. A successful verification closes
the cycle. If the control remains unhealthy or Athos could not act, ForgeHub automatically creates a
new Inbox demand and system notification containing the before/after evidence, Athos output and
commands required for manual continuation.

The shared Assistant header control is icon-only on every screen. Its accessible name and tooltip
remain localized, so visual consistency does not remove keyboard or screen-reader context.

The API is implemented in `backend/app/api/routes/audit.py`; frontend data contracts are in
`frontend/src/hooks/useAudit.ts`; the page is `frontend/src/pages/auditor/index.tsx`.
