# ForgeHub UX Contract

## Product context

- Audience: Marcelo and authorized operators coordinating the ForgeHub agent ecosystem.
- Primary jobs: plan, govern, execute, inspect, and validate software delivery with traceable agent work.
- Target markets: operator-owned internal control plane; no market-specific regulated flow is inferred here.
- Active locales: `pt-BR`, `en`, and `es`, with `pt-BR` as the fallback.
- Language policy: direct operational copy; domain namespaces own translations and accessible labels.
- Timezone/calendar policy: preserve source instants, format through the active locale, and use the Gregorian calendar unless a domain contract says otherwise.
- Accessibility target: WCAG 2.2 AA.

## Business-context sources

| Domain / scope | Authoritative source | Source type | Reviewed date |
|---|---|---|---|
| Product purpose and governed delivery | `docs/specs/PRD.md` | Product requirements | 2026-08-30 |
| Implemented domain transitions and validation | `docs/reference/BUSINESS_RULES.md` | Business rule specification | 2026-08-30 |
| Implemented data ownership and relationships | `docs/reference/DATA_MODEL.md` | Data contract | 2026-08-30 |
| Planning and delivery boundaries | `docs/architecture/PLANNING_DELIVERY_ARCHITECTURE.md` | Architecture contract | 2026-08-30 |
| Agent Activity continuity | `docs/plans/2026-08-29-agent-activity-continuity-design.md` in commit `4b11de3` | Approved product design | 2026-08-30 |

Permissions, deletion/retention, billing, and legal policy remain owned by their backend/domain sources. This contract does not create policy where no maintained source exists.

## Visual contract

- Project design context: `DESIGN.md`.
- Token ownership: existing runtime tokens remain canonical.
- Runtime source: semantic CSS variables in `frontend/src/index.css`, adapted through Tailwind and shared components under `frontend/src/components/ui/`.
- Drift gate: premium strict audit, frontend tests/build, and browser inspection in the supported themes/locales.
- Supported themes: light and dark.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Table Selection | Native checkbox/button semantics in the owning table component | This contract + domain list behavior | page; all-results only with explicit API support | component + browser |
| Select/Listbox | `frontend/src/components/ui/select.tsx` and explicit native selects | This contract + runtime browser support | native; authored only through a future maintained shared primitive | keyboard + popup |
| Date | Semantic native date/time inputs in owning forms | This contract + typed API schemas | native; typed text only when the domain requires it | locale + keyboard + browser |
| Form | Owning form schema/handler with `noValidate` | Backend schemas/routes + this contract | create / edit | unit + integration + browser |
| Scrollbar | Global rules in `frontend/src/index.css` | `DESIGN.md` + runtime CSS variables | global baseline; local geometry exceptions | audit + computed style |
| Toast | Localized shared/inline live regions (`role=status` or `role=alert`) | This contract + owning mutation hook | success / warning / info / error | live-region test |
| CRUD | Domain routes and TanStack Query hooks | Backend business rules + API schemas | return / stay follows the owning workflow | integration + browser |

## Component behavior

| Component | Default | Hover | Focus | Active | Disabled | Busy | Error |
|---|---|---|---|---|---|---|---|
| Button | semantic intent + label | tokenized contrast | visible ring | pressed feedback | native disabled | stable size + `aria-busy` | inline/live-region recovery |
| Icon button | localized accessible name | tokenized contrast | visible ring | pressed feedback | native disabled | stable geometry | owning surface explains failure |
| Input | labeled native input | border/foreground cue | visible ring | n/a | native disabled | owning form blocks duplicates | text + association |
| Secret input | masked | reveal control | visible ring | reveal state | native disabled | n/a | never expose secret in feedback |
| Search | explicit localized clear | visible action | visible ring | immediate clear | native disabled | background state | stale requests cannot overwrite |
| Textarea | `resize: none`, adequate rows/height | border cue | visible ring | n/a | native disabled | owning form blocks duplicates | text + association |
| Table/list | semantic rows and actions | row/action cue | control focus | selected/expanded state | unavailable action explained | stable footprint | inline recoverable state |

## Dataset navigation

- Messages groups are mutually exclusive lifecycle stages. Incubation is
  excluded from Incoming and Outgoing; dispatched/running rows leave both
  queues. Archived rows leave all active stages. List and badge predicates
  must agree. This follows the operator's September 2026 lifecycle decision.

- Admin tables use the API's bounded pagination when available; otherwise the owning screen must document its bounded dataset.
- Committed search/filter/sort/page state belongs in URL parameters unless it is sensitive or explicitly transient.
- Loading, empty, no-results, partial degradation, and failure states preserve the owning surface's geometry.
- Bulk/all-results selection is not implied by a page checkbox; it requires explicit backend scope support.

## Flow ledger

| Operation | Trigger | Pending | Success destination | Success feedback | Failure recovery | Focus outcome | Source ref |
|---|---|---|---|---|---|---|---|
| Create | labeled submit | disable duplicate submit | owning list or canonical detail | localized status | preserve values + inline error | destination heading or first error | owning API route |
| Edit | labeled save | disable duplicate submit | canonical sibling behavior | localized status | preserve values + retry | destination heading or first error | owning API route |
| Delete | explicit object action | disable duplicate submit | owning list | localized status | dialog remains recoverable | restore trigger on cancel/failure | `docs/reference/BUSINESS_RULES.md` |
| Search | input/change or explicit submit | distinct background state | same list | result count/state | clear/retry | input remains reachable | owning query hook |
| Cancel/back | cancel/back action | n/a | owning list/previous safe route | none | unsaved-loss guard when applicable | restored trigger/route heading | sibling workflow |
| Upload/background job | explicit start | progress/busy state | owning record | localized status | retry/cancel where API supports it | initiating control or result | owning API route |

## Navigation and responsive behavior

- Every navigable route sets an honest localized document title.
- Authenticated permission failures must remain distinguishable from unauthenticated and not-found states.
- Sidebar ownership remains in `AppLayout`; feature pages do not reproduce application chrome.
- Responsive transformations preserve actions, identifiers, statuses, and full-value access.
- Modal dismissal restores focus to the trigger; sticky surfaces must not obscure focused controls.

## Overlays and feedback

- Confirmation owner: `frontend/src/components/ui/confirm-dialog.tsx`.
- Confirmation names the operation and consequence; serious actions initially focus Cancel.
- Dialogs trap focus, make the background inert, lock document scroll, close on Escape when safe, and restore focus.
- Inline errors persist where correction is needed. Success/status feedback uses localized live regions and never carries secrets.
- Overlay stacking follows existing shared application layers; dialog surfaces remain the strongly elevated exception in `DESIGN.md`.

## Async and resilience

- Mutations are pessimistic unless a domain explicitly proves optimistic rollback safe.
- Submit controls block duplicates and preserve dimensions while pending.
- TanStack Query owns request lifecycle, invalidation, background refresh, and stale-response protection.
- Offline/timeout/partial-source states remain distinct; durable data stays visible when an optional source fails.
- Mutation failure preserves form/dialog context and offers retry.

## Validation

- Backend Pydantic schemas and route business rules are authoritative for domain validity.
- Frontend forms declare `noValidate` and render localized application-owned validation/recovery.
- Invalid fields retain values, expose text errors, and use native semantics/ARIA associations.
- Sensitive values remain masked and never enter URLs, logs, analytics, or status messages.

## Permission and clipboard

- Permission behavior follows authenticated backend enforcement; the UI does not invent authority.
- Disabled controls explain non-obvious unavailability in adjacent text or an accessible description.
- Clipboard feedback never repeats secrets.

## Migration status

- Canonical owners: shared controls in `frontend/src/components/ui/`, global theme/scrollbar rules in `frontend/src/index.css`, and domain hooks/routes for data behavior.
- Current migration: clear the 2026-08-30 premium audit and prevent new unresolved ownership, form, textarea, affordance, and scrollbar violations.
- Rollback gate: frontend tests/build and domain tests must remain green; no business transition changes are included.

## Verification

- Static: premium audit in strict mode with zero findings.
- Runtime: `cd frontend && npm test -- --run` and `npm run build`.
- Browser: desktop and narrow viewport, light/dark, `pt-BR`/`en`, keyboard, reduced motion, loading/empty/error/degraded/success states as applicable.
- Canonical sibling: existing shared `ConfirmDialog` consumers and domain CRUD forms.
- Failure-path evidence: `frontend/src/pages/agent-activity/index.test.tsx` and domain-specific tests.
