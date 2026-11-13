---
version: alpha
colors:
  primary: "hsl(239 84% 67%)"
  background: "hsl(222 47% 8%)"
  foreground: "hsl(210 40% 98%)"
  card: "hsl(222 47% 11%)"
  muted: "hsl(217 33% 17%)"
  mutedForeground: "hsl(215 20% 65%)"
  border: "hsl(217 33% 20%)"
  success: "hsl(160 84% 39%)"
  warning: "hsl(38 92% 50%)"
  destructive: "hsl(0 63% 31%)"
typography:
  interface:
    fontFamily: "ui-sans-serif, system-ui, sans-serif"
    lineHeight: "1.5"
  data:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
    lineHeight: "1.4"
rounded:
  DEFAULT: "0.5rem"
  compact: "0.375rem"
spacing:
  unit: "0.25rem"
components:
  application:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
  surface:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.DEFAULT}"
  rosterTable:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.mutedForeground}"
    rounded: "{rounded.compact}"
    padding: "{spacing.unit}"
  avatar:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.mutedForeground}"
    rounded: "9999px"
    size: "3rem"
  successBadge:
    backgroundColor: "{colors.success}"
  warningBadge:
    backgroundColor: "{colors.warning}"
  destructiveAction:
    textColor: "{colors.destructive}"
  divider:
    backgroundColor: "{colors.border}"
---

# ForgeHub Design Context

Mission registration and metadata editing use full pages. Team roles and responsibilities are edited
inline beneath the mission form; dialogs only confirm membership/permission changes or cancellation.
Use the existing Select, Textarea and ConfirmDialog owners. Native select and datetime popups remain
browser-owned. A mission's removal action is cancellation, preserving history and evidence. Show the
orchestrator separately from executor/reviewer roles and explain that the approved brief supplies the
dispatch objective. Team changes use the guarded mission command rather than generic automation APIs.

Personal Demands preserve source independently of capture suggestions. Keep group/contact identity and requester visible in the existing inset metadata area. Show status and registration date/actor in the compact metadata row, and completion date/actor when present. Never infer the completing agent for historical records without that evidence.

## Overview

Workspace Explorer archives use the existing context menu and NameDialog. ZIP
creation saves the current selection in the displayed directory; extraction
creates a new named folder there. Operations never merge into an existing
destination. Errors remain in the dialog, progress disables submission, and the
listing refreshes after completion. Local and selected SSH-server views share
this behavior. Supported extraction formats are ZIP and TAR (gzip/bzip2/xz).

ForgeHub is an operator console for Marcelo's agent ecosystem. Its product surfaces should feel like a calm mission-control ledger: dense enough to scan operational state, restrained enough that warnings and failures remain unmistakable. The interface is a product/admin surface, not a marketing page.

The characteristic interaction is progressive disclosure inside operational lists. Summary rows carry identity and health; deeper configuration opens in place without losing the roster context. Avoid decorative dashboard tiles, novelty gradients, glass effects, or visual metaphors that compete with system state.

## Colors

Runtime CSS variables in `frontend/src/index.css` are the canonical token source. The values above document the established dark theme used most often in ForgeHub; the light theme uses the corresponding variables from the same file. Semantic states retain their existing badge variants and must include text or icons in addition to color.

## Typography

Use the existing system sans stack for interface text and the system monospace stack for profile slugs, paths, schedules, and other machine identifiers. Hierarchy comes from weight, size, and spacing rather than new font dependencies.

## Layout

Pessoal → Tarefas dos agentes separates Moodle approvals, incubations and executable agent tasks into three nested groups. Each group owns its filters and counts. Task rows expose View details and Archive; the table owns horizontal overflow on narrow screens. Source failures never imply zero pending decisions. Moodle operation outcomes and execution-report outcomes are presented separately.

Administrative lists use full-width native tables with comfortable rows and horizontal overflow owned by the table surface. Expanded details appear directly beneath their owning row. Page-level controls remain above the table and do not move when a row opens.

## Elevation & Depth

Static surfaces use borders and small background shifts, not prominent shadows. Dialogs remain the only strongly elevated surfaces. Expanded table rows use a muted inset surface and a left identity accent rather than floating cards.

## Shapes

Use the established `--radius` family. Avatars are circular because they represent identity; badges remain pill-shaped metadata; table and detail surfaces use compact rounded corners only where they have a containing border.

## Components

- Agent avatars reserve their geometry before image data renders and fall back to initials.
- Sortable headers are real buttons and expose `aria-sort` on the header cell.
- Agent rows provide a visible expand/collapse button; clicking elsewhere on the row is a pointer convenience, while keyboard access remains on the native button.
- Only one agent detail is expanded at a time. Opening another closes the previous detail.
- Upload controls state accepted formats and size limits before selection, validate on both client and server, preserve the current photo on failure, and expose replace/remove actions.
- Loading, empty, error, no-results, pending upload, and delete-conflict states retain stable geometry and actionable copy.

## Do's and Don'ts

- Do preserve the existing dark navy palette, Lucide icon language, compact badges, and direct operational copy.
- Do keep paths and slugs visually secondary but selectable.
- Do make status and runtime easy to scan without turning every cell into a badge wall.
- Don't restore the previous wall of nested cards.
- Don't hide archived roles or test residue by name-only frontend filters; roster eligibility belongs to the backend/Foundation contract.
- Don't delete historical operational data implicitly when an agent is removed.


## Live monitoring dashboard

The dashboard uses the established shared tokens and Card primitives. At widths below 768px, show one column; above, use two independent-height columns with 16/24px gaps. Keep wide data inside keyboard-focusable scrolling table regions. Summaries remain visible while extended socket, disk and container details use native disclosure.

Represent source availability and collection time explicitly. A failed refresh may retain old data only with a stale indicator. Missing data is never a zero, an offline host or a healthy service. Tailscale presence, active traffic, process state and healthchecks remain separate signals. Technical names are original data; interface text exists in pt-BR, en and es.

The operational monitoring contract is docs/superpowers/specs/2026-10-26-server-monitoring-dashboard-design.md. No dashboard control kills processes, blocks connections or restarts services.


## Pessoal: origens de demandas (2026-10-27)

Preserve the existing theme and tab ids. Use separate “Contatos pessoais” and “Grupos do WhatsApp” tabs, with a horizontally scrollable tab strip on narrow screens. Only monitored WhatsApp groups may be registered. Missing monitoring data is an explicit unavailable state, never an empty registry. Suggestions and converted demands show the actual contact or group, requester, and message date. Registration and pending intake do not imply acceptance. Keep loading, empty, error, pending, and accepted states distinct; repeated acceptance yields the existing demand.

Remote Access approvals use the shared ConfirmDialog and a status-bearing ViewModel.
Show the full script, machines, risk, elevation, reason, effect, rollback and SHA-256.
The fingerprint wraps at 390 px. Approval lasts 24 hours; rejection requires a reason.
Agent authority defaults to 24 hours and requires explicit machines or groups.

Command history and execution details distinguish expired output from empty output using the same muted, localized “Output expired” label. Expiration preserves the command, machine, actor, time and outcome; it never changes the verdict or presents output controls for deleted content.

## Agent machine configuration (2026-11-08)

Remote Access lists each active agent once and expands one configuration form inline.
Reuse the canonical native Select, Textarea, Button and ConfirmDialog. No separate opening
or closing workflow remains. Defaults are all machines, indefinite 0 h, and elevation off;
only an administrator-confirmed save grants scope. Display awaiting-configuration, empty
scope, expiry, pause, unsupported runtime and unavailable inventory explicitly. Sensitive
coverage confirmation names production/client coverage; edits invalidate that confirmation.
Selected groups save current machines; all-machine scope includes future prepared machines.

## Messages triage (2026-11-08)

Personal agent work keeps the existing compact ledger, source groups, table overflow and
inset details. The primary action is “Analisar e encaminhar”; archive remains secondary.
Tasks and incubations default to operator decisions, with separate handling, waiting and resolved views.
A row carries a short analysis, reason and next step; use the API's readable source context.
Raw instructor identifiers stay in detailed evidence. The stable inline status region reports
analysis loading, queued/running progress, completion and recoverable failure without moving
the filters. Task next-check dates appear only for a scheduled wait; incubation owns maturation.


## Terminal session identity (2026-11-10)

System Control identifies terminal sessions by the persisted Workspace tab name,
with the tmux UUID as secondary technical detail. Reopening retains both identity
and name. Connection state describes browser attachment only: a disconnected
terminal can still run work. Never label a detached session orphaned or infer it
is safe to terminate. Destructive confirmation names the selected session and
explains that its processes will end. Reuse terminal metadata hooks, shared table,
badge, button and confirmation owners; names do not create another session registry.
