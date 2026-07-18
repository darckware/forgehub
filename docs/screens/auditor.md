# Auditor

Route: `/auditor`; navigation: **Operations → Auditor**.

The screen is the operational surface for the weekly Hermes/Foundation ecosystem audit. It shows
the same `ECO-001`…`ECO-038` controls used by the Sunday 19:00 Athos cron, so scheduled and manual
evidence cannot drift into separate checklists.

## Profile view

The profile pills filter controls by their responsible Hermes profile. `ECO-031`…`ECO-038` each
validate one profile's required `AGENTS.md`, `FOUNDATION_LINK.md`, `HEARTBEAT.md`, `IDENTITY.md`,
`MEMORY.md`, `SOUL.md`, `TOOLS.md`, `USER.md`, active memory files, `config.yaml`, Knowledge Base
directory, Foundation/ForgeHub/ForgeRouter/Hindsight context, knowledge hook, and owned script.

## Correction cycle

An enabled remediation is never part of a normal audit run. An administrator must open the repair
confirmation explicitly. The backend records the repair as `remediation`, then executes and records
the original control as `remediation-verification`. Controls where a generic repair could overwrite
identity, documentation, source code, memory, or data intentionally remain assisted/manual and can
be sent to the Assistant with their complete hidden context.

The API is implemented in `backend/app/api/routes/audit.py`; frontend data contracts are in
`frontend/src/hooks/useAudit.ts`; the page is `frontend/src/pages/auditor/index.tsx`.
