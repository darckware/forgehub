# Tech Stack Guide — organization's approved tools per layer

> Status: living reference, distilled from Marcelo's knowledge base
> (`/root/.hermes/knowledge_base/marcelo/stack/`). Human- and agent-readable on purpose
> (2026-08-16, Marcelo: "o que acha de ter um resumo explicativo que passamos ler e o agente
> também para poder sugerir as implementações") -- this is the fast, bounded reference both a
> person reviewing Conception's Step 4 "Tech stack" and the `tech_stack` AI-draft agent consult
> instead of reading ~46k lines across six source documents on every generation. It is **not** the
> canonical source: it is a summary, so it can drift if the org standard changes underneath it --
> keep it in sync by hand when those documents change (same trade-off the `tech_stack_options`
> catalog seed migration already accepted when it extracted just §12/§17/§18 of doc 02).

## Why this exists

Conception Step 4 ("Tech stack") and its "Gerar com agente" button need to ground technology
choices in tools the organization has actually adopted and can support -- not whatever a model
would suggest from general training (2026-08-16, Marcelo: "porque preciso dar a nossa base de
tecnologia a ser aplicado nos produtos. São nossas ferramentas"). `tech_stack_options`
(`backend/app/db/models/system_scope.py`) is the closed catalog picked from in the UI; this guide
is the reasoning behind why each catalog entry exists and when to reach for it, so both a human
and an agent can justify a choice instead of just naming a tool.

Full source documents, for anything this summary doesn't cover:

```text
02-UI-DESIGN-SYSTEM-AND-TECHNOLOGY-SPEC.md        §12, §13, §14, §17, §18 (this guide's primary source)
05-FRONTEND-ARCHITECTURE-AND-CODING-STANDARD.md    frontend state/architecture depth
06-BACKEND-ARCHITECTURE-AND-CODING-STANDARD.md     backend layering/architecture depth
04-DATABASE-MODELING-AND-NAMING-STANDARD.md        data modeling/naming depth
12-INFRASTRUCTURE-ENVIRONMENT-AND-IAC-STANDARD.md  deploy/infra depth (cloud-scale scenarios)
```

## Frontend

`tech_stack_options` tags every frontend row with a `platform` (2026-08-16, Marcelo: "web app,
landing page, site institucional, PWA, mobile" -- a plain "web vs. mobile" split first tried the
same day was too coarse, so the catalog's `platform` column now carries these 5 values instead of
just 2). Pick the row matching what's actually being built, not just "it's a website":

| Scenario (`platform`) | Stack | Notes |
|---|---|---|
| **web_app** -- authenticated SPA, back-office | React + TypeScript + Vite + Tailwind CSS + shadcn/ui | Default choice -- ForgeHub itself uses this. Radix (via shadcn) for accessibility/behavior, React Hook Form + Zod for forms, TanStack Query for server state. |
| **web_app** -- data-heavy screens | React + TypeScript + PrimeReact, MUI or Ant Design | Reach for a data-grid-oriented library instead of composing tables from shadcn primitives when the screen is mostly dense tables/forms. |
| **landing_page** -- single static page, no interactivity beyond a form/CTA | HTML + CSS + JS puro | No build step, no framework -- don't reach for React just to ship one page. |
| **institutional_site** -- multi-page public site needing SEO/SSR | Next.js + TypeScript + Tailwind CSS + shadcn/ui | Evolution of the web_app stack when server rendering, static generation or multi-page SEO is required. |
| **pwa** -- installable, offline-capable web app | React + TypeScript + Vite + Tailwind CSS + shadcn/ui + vite-plugin-pwa | Same web_app baseline plus a service worker/manifest via `vite-plugin-pwa` -- not a different framework, an added capability. |
| **mobile** -- native mobile app | React Native + Expo + TypeScript + NativeWind | Tamagui is the accepted alternative when a more customizable cross-platform design system is needed. |

Layering (each piece owns exactly one concern -- don't let one reimplement another's job):

```text
React + TypeScript
  ├── Tailwind CSS        → styling
  ├── shadcn/ui (Radix)   → visual components / accessibility+behavior
  ├── React Hook Form     → form state
  ├── Zod                 → validation
  └── TanStack Query      → server state / API cache
```

State placement (see doc 05 for the full standard):

```text
Local UI state      → useState / useReducer
Form state           → React Hook Form + Zod
Server state          → TanStack Query
Simple global state    → React Context
Medium global state     → Zustand
Complex global state     → Redux Toolkit
```

Never duplicate server-cached data (TanStack Query) into global state.

## Backend

| Domain | Stack | Notes |
|---|---|---|
| Core business logic, critical/transactional APIs | C#/.NET | Default for transactional systems of record. |
| BFF, WebSocket, event-driven services | Node.js | Preferred when the service is mostly I/O-bound orchestration or real-time push. |
| AI, automation, ETL, data processing | Python (FastAPI) | ForgeHub's own backend is this case. |

Selection depends on domain, criticality, integrations, security posture and team familiarity --
see doc 06 for layering (controllers/services/repositories), transaction handling and messaging
patterns; this guide only covers *which* language/framework, not *how* to structure it once chosen.

## Database

| Need | Stack | Notes |
|---|---|---|
| Default relational store | PostgreSQL | Standard choice absent a specific reason otherwise (ForgeHub's own `company_postgres`). |
| Microsoft ecosystem / existing SQL Server estate | SQL Server | Only when integrating with an environment that already standardized on it. |
| Documents with a proven need | MongoDB | Requires a demonstrated need for schema-flexible documents, not a default. |
| Cache, locks, sessions, rate limiting, ephemeral data | Redis | Complementary, not a system of record. |

See doc 04 for modeling/naming rules once PostgreSQL (or another store) is chosen.

## Deploy / infrastructure

No dedicated selection menu in doc 02 -- this catalog's `deploy_infra` layer comes from doc 12's
container/orchestration options, anchored on Docker Compose since that is ForgeHub's own
documented deploy baseline (`docs/TECHNOLOGY.md`, root `CLAUDE.md`).

| Scenario | Stack | Notes |
|---|---|---|
| Simple single-host deploy | Docker Compose (host único) | Baseline default -- what ForgeHub itself runs. |
| Multi-service/multi-node, scale or HA required | Kubernetes | Only once orchestration needs actually exist -- don't default to it. |
| Single process, no containers | VM/bare-metal + systemd | Fits a lone long-running process without the overhead of a container runtime. |
| Provider-managed, no server of your own | Serverless / PaaS gerenciado | Functions/services the cloud provider runs; trades operational control for zero infra to maintain. |

## Decision criteria (any layer)

When more than one option could fit, weigh (heavier weight = matters more): product fit,
accessibility, security, maturity — all 5; maintainability, team familiarity, testability,
customization — 4; performance, cost, adoption, lock-in — 3.

Eliminate a candidate outright if it has: discontinued maintenance, an incompatible license, an
unmitigated critical vulnerability, structural inaccessibility, browser incompatibility (frontend),
no update strategy, or an unapproved vendor dependency.

## How this feeds Conception

1. `tech_stack_options` (`backend/app/db/models/system_scope.py`) holds the pickable catalog per
   layer -- `source="org_standard"` rows were seeded from this same material (migration
   `9823e7890ae4`); `source="custom"` rows are added ad hoc from the picker ("+ Add new option").
2. The `tech_stack` AI-draft target kind (`backend/app/core/ai_draft.py`) points the agent at this
   guide (and, for deeper questions, the source documents above) plus the current catalog listing,
   and asks it to reuse an existing catalog entry's exact name when it fits the described context
   rather than paraphrasing the same tool under new wording.
