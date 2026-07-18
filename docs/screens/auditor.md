# Auditor

Route: `/auditor`; navigation: **Operations → Auditor**.

The screen is the operational surface for the weekly Hermes/Foundation ecosystem audit. It shows
the same `ECO-001`…`ECO-039` controls used by the Sunday 19:00 Athos cron, so scheduled and manual
evidence cannot drift into separate checklists.

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
