# Screen: ForgeRouter

## Route & Purpose

Route: `/forgerouter` (`frontend/src/App.tsx:52` — `<Route path="forgerouter" element={<ForgeRouterPage />} />`).
Component: `frontend/src/pages/forgerouter/index.tsx`.

This screen is a full-bleed `<iframe>` embed of an external web UI called "ForgeRouter," reached at `VITE_FORGEROUTER_URL` (falls back to `http://localhost:2100` if unset). The entire page is 10 lines of code with no state, no data fetching, and no ForgeHub backend involvement of any kind. It is purely a navigation convenience so users don't have to leave the ForgeHub shell to reach this other tool — the same pattern used for the Kanboard screen (`frontend/src/pages/kanboard/index.tsx`) and, conceptually, the same family as the Obsidian vault browser (which embeds a server-rendered view of vault content instead of an iframe, because Obsidian itself has no web server — see `backend/app/api/routes/vault.py:1-15`).

**ForgeRouter is not a ForgeHub domain.** It is not listed among the 8 core backend domains (`product`, `project`, `pipeline`, `backlog`, `task`, `agent`, `artifact`, `governance`) and has zero presence in the ForgeHub backend, database, or API surface. Investigation found no `forgerouter` route, model, schema, or proxy anywhere in `backend/`, no entry in `docker-compose.yml`, no service named `forgerouter` anywhere in the repo, and no mention in `.env`/`.env.example`. It is also **not** reached through the chat/host bridge (`host-bridge/app.py`, `CHAT_BRIDGE_URL`) the way Dashboard's tool-versions/system-stats cards or the Terminal/Chat screens are — there is no `forgerouter`/`2100` reference anywhere in `host-bridge/app.py`. The iframe simply points the browser directly at whatever is listening on port 2100 (or the override URL), independent of the ForgeHub backend or the host bridge entirely. What process actually serves that port is outside this repo and was not found in the codebase — likely a separate, externally-run Hermes-ecosystem service ("ForgeRouter") that this repo only references by name and default port, with no further documentation of what it does.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/forgerouter/index.tsx` | Entire screen. Computes `FORGEROUTER_URL` from `import.meta.env.VITE_FORGEROUTER_URL` (default `http://localhost:2100`) and renders a single full-height/width `<iframe>` pointed at it. No imports beyond JSX/React runtime — no hooks, no UI primitives, no shadcn components. |

## Data & API Calls

| Data shown | Source hook | Endpoint | Method |
|---|---|---|---|
| Entire screen content | none — no hook, no `fetch`/`apiClient` call | N/A — content is whatever the external ForgeRouter web app at `VITE_FORGEROUTER_URL` (default `http://localhost:2100`) renders inside the iframe | N/A (browser-level `<iframe src>` navigation, not an API call) |

**This is explicitly not a ForgeHub backend domain call.** There is no `useForgeRouter` hook, no `/api/v1/...` endpoint, and no row in `src/lib/api.ts`'s usage anywhere in this file. The "API calls," if any, happen entirely inside the iframe's own document, against whatever backend ForgeRouter itself talks to — invisible to and untouched by ForgeHub's frontend or backend code.

## Actions Available

None at the ForgeHub level. The page renders no buttons, links, or controls of its own — any interactivity (forms, buttons, navigation) is whatever the embedded ForgeRouter app provides inside its own document, which is opaque to this codebase.

## States

None handled. There is no loading indicator, no empty state, and no error/fallback UI if the iframe fails to load (e.g., if nothing is listening on port 2100, or `VITE_FORGEROUTER_URL` points somewhere unreachable, or the target refuses to be framed via `X-Frame-Options`/CSP). The browser's default broken-iframe behavior (a blank panel) is all a user would see in that case — there is no code path in `index.tsx` to detect or report it.

## Business Rules Surfaced Here

None — out of ForgeHub's core domain model. ForgeRouter has no relationship to Product, Pipeline, Planning, Execution, Skill, Traceability, or Governance entities as defined in `docs/DATA_MODEL.md` / `docs/BUSINESS_RULES.md`. Nothing here touches the database, an artifact, an approval gate, or an audit trail.

## Dependencies

- **External: ForgeRouter web service**, expected to be reachable in-browser at `VITE_FORGEROUTER_URL` (build-time Vite env var) or `http://localhost:2100` by default (`frontend/src/pages/forgerouter/index.tsx:1-2`, declared in `frontend/src/vite-env.d.ts:5`). This is a direct browser-to-service connection — the ForgeHub backend is not in the request path at all (contrast with Dashboard/Terminal/Chat, which proxy through `host-bridge/app.py` via `CHAT_BRIDGE_URL`).
- No entry for this service exists in `docker-compose.yml`, `.env`, or `.env.example` in this repo — its actual deployment (container, host process, port mapping) lives entirely outside what's checked into ForgeHub. Nothing in the repository documents what ForgeRouter is/does beyond the name and default port.

## Notes / Improvement Opportunities

- `frontend/src/pages/forgerouter/index.tsx`: no `VITE_FORGEROUTER_URL` documented in `.env.example` (unlike `VITE_KANBOARD_URL`'s backing `KANBOARD_URL`, which at least has Kanboard credentials documented elsewhere in `.env.example`) — a developer reading `.env.example` alone would not discover this variable exists or what default port to expect without reading the source file.
- No iframe load-failure handling (no `onError`, no health check, no "service unreachable" message) — compare to Dashboard's `SystemStatsCard`/`ToolVersionsCard`, which both show explicit destructive-styled error text when their backend dependency is unreachable (`docs/screens/dashboard.md`). A user visiting `/forgerouter` with nothing running on port 2100 gets a silent blank pane with no indication of what's wrong or how to fix it.
- No `sandbox` or `referrerpolicy` attribute on the `<iframe>` — not necessarily wrong (same pattern as Kanboard's iframe), but worth deliberate review since it's embedding a same-origin-unrestricted third-party app surface inside the ForgeHub shell.
- The name "ForgeRouter" together with this repo's `CLAUDE.md` framing of ForgeHub as part of a broader "Hermes ecosystem" (Foundation, vault, host-bridge, Kanboard) strongly suggests ForgeRouter is a sibling Hermes-ecosystem tool (possibly an agent/task router), but this repository contains no source, README, or API contract for it — only the iframe's default URL. Anyone writing a true spec for ForgeRouter itself would need to look in a different repository/service, not ForgeHub's.
