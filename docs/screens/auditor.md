# Auditor

Route: `/auditor`; navigation: **Operations → Auditor**.

The screen is the operational surface for the weekly Hermes/Foundation ecosystem audit. The
canonical catalog v2 covers `ECO-001`…`ECO-057`; `ECO-021` is retired and stays disabled. The
`ecosystem-weekly-audit` job in the Athos profile runs Sunday at 19:00 (`0 19 * * 0`) and triggers
the same controls as manual runs.

## Athos scheduler monitor

`GET /api/v1/audit/status` includes `athos_monitor` alongside the existing checklist counts. The
monitor reads the Athos cron store through the Foundation loader and compares the job name, script,
schedule, enabled state, scheduler health, and latest ForgeHub run requested by `cron`. Its state is
`healthy`, `degraded`, `failed`, or `not_configured`, with concrete reasons in `issues`. A missing or
duplicate job, drift, overdue scheduler, or audit run older than eight days degrades it; a scheduler
error or unreadable Athos store fails it. An individual failed control changes the checklist count,
not the scheduler state. The existing bridge-token-protected endpoint remains the only cron trigger.

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
