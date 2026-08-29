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

## Overview

ForgeHub is an operator console for Marcelo's agent ecosystem. Its product surfaces should feel like a calm mission-control ledger: dense enough to scan operational state, restrained enough that warnings and failures remain unmistakable. The interface is a product/admin surface, not a marketing page.

The characteristic interaction is progressive disclosure inside operational lists. Summary rows carry identity and health; deeper configuration opens in place without losing the roster context. Avoid decorative dashboard tiles, novelty gradients, glass effects, or visual metaphors that compete with system state.

## Colors

Runtime CSS variables in `frontend/src/index.css` are the canonical token source. The values above document the established dark theme used most often in ForgeHub; the light theme uses the corresponding variables from the same file. Semantic states retain their existing badge variants and must include text or icons in addition to color.

## Typography

Use the existing system sans stack for interface text and the system monospace stack for profile slugs, paths, schedules, and other machine identifiers. Hierarchy comes from weight, size, and spacing rather than new font dependencies.

## Layout

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
