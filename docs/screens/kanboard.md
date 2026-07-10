# Screen: Kanboard

## Route & Purpose

Route: `/kanboard` (`frontend/src/App.tsx:21,53` — `import KanboardPage from "@/pages/kanboard"` and `<Route path="kanboard" element={<KanboardPage />} />`).
Component: `frontend/src/pages/kanboard/index.tsx`.

This screen does not implement any ForgeHub domain functionality. It is a full-bleed iframe that embeds the externally-hosted Kanboard application (a third-party Kanban board tool) inside the ForgeHub shell, so a user can use Kanboard without leaving the ForgeHub UI. The entire component is 9 lines.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/kanboard/index.tsx` | Whole screen. Renders a single `<iframe>` pointed at the Kanboard URL inside a bordered, rounded, viewport-height container (`h-[calc(100vh-7rem)]`). No props, no local state, no imports beyond the implicit JSX runtime. |

No sub-components, no hooks, no UI primitives from `src/components/ui/` are used on this screen.

## Data & API Calls

| Data shown | Source hook | Endpoint | Method |
|---|---|---|---|
| Entire Kanboard application UI (boards, cards, etc.) | None — no TanStack Query hook | N/A — `<iframe src={KANBOARD_URL}>` loads the external Kanboard web app directly in the browser (`kanboard/index.tsx:6`) | N/A (browser-level `GET` of the iframe document, not mediated by ForgeHub's `apiClient`/`api.ts`) |

This is **an embedded external tool**, not a ForgeHub backend domain. There is no `frontend/src/hooks/useKanboard.ts` and no `backend/app/api/routes/kanboard.py`. A repo-wide search (`grep -rn "kanboard" backend/ -i`) found only an incidental mention in `backend/app/api/routes/vault.py:4` (a docstring comparing Obsidian's embeddability to ForgeRouter/Kanboard) — there is no Kanboard route, schema, or model in the backend. ForgeHub's backend never proxies or talks to Kanboard's API.

The iframe URL is resolved client-side only:
```ts
const KANBOARD_URL = (import.meta.env.VITE_KANBOARD_URL as string | undefined) ?? "http://localhost:8081";
```
(`kanboard/index.tsx:1`). `VITE_KANBOARD_URL` is declared in `frontend/src/vite-env.d.ts:6` as an optional env var; it is not set in `docker-compose.yml` (checked — only `VITE_API_URL` is set there for the frontend build, `docker-compose.yml:64`), so in the current Docker setup the fallback `http://localhost:8081` is always used.

## Actions Available

None beyond whatever interactions Kanboard itself exposes inside the iframe (out of scope — that's Kanboard's own UI, not ForgeHub code). ForgeHub's wrapper page offers no buttons, filters, or controls of its own.

## States

No loading, empty, or error states are handled by this component. There is:
- No check for whether the iframe successfully loaded.
- No fallback UI if Kanboard is unreachable (the iframe would simply show the browser's own "can't connect" page inside the bordered box, or appear blank).
- No loading spinner while the iframe's document is fetched.

## Business Rules Surfaced Here

None — external tool integration. This screen has no relationship to any entity in `docs/DATA_MODEL.md` or rule in `docs/BUSINESS_RULES.md`. Per `CLAUDE.md`, Kanboard is explicitly called out as sharing the same `company_postgres` Postgres container as ForgeHub (for its own, separate schema/database) and having credentials provisioned in the repo-root `.env`, but none of that backend/credential wiring is touched by this frontend screen — the iframe talks straight to Kanboard's own web server, not through ForgeHub's backend or its Postgres connection.

## Dependencies

- **External: Kanboard web server**, reachable at the URL in `VITE_KANBOARD_URL` (falls back to `http://localhost:8081`). The screen is entirely non-functional (blank/broken iframe) if this isn't running or reachable from the browser.
- **Repo-root `.env`** declares `KANBOARD_URL=http://localhost:8081/jsonrpc.php`, `KANBOARD_USER=athos_agent`, and `KANBOARD_TOKEN=YOUR_KANBOARD_TOKEN_HERE` (`.env:7-9`). These are **not** the same value/purpose as the frontend's `VITE_KANBOARD_URL`: `KANBOARD_URL` here points at Kanboard's JSON-RPC API endpoint (for programmatic/API access, e.g. by agents or a future backend integration), whereas the frontend iframe just needs Kanboard's plain web UI base URL. Nothing in the current codebase (frontend or backend) reads `KANBOARD_URL`, `KANBOARD_USER`, or `KANBOARD_TOKEN` — confirmed via repo-wide search; they exist in `.env` but are unused by any application code at present, and `KANBOARD_TOKEN` is still the placeholder value `YOUR_KANBOARD_TOKEN_HERE`.
- No ForgeHub backend route, database table, or hook is involved.

## Notes / Improvement Opportunities

- `frontend/src/pages/kanboard/index.tsx`: no error/empty state at all — if Kanboard is down, unreachable, or blocks iframe embedding (e.g. via `X-Frame-Options`/CSP), the user just sees a blank or browser-error iframe with no ForgeHub-level messaging, unlike the Dashboard screen's cards which show explicit "Failed to reach..." text (see `docs/screens/dashboard.md`).
- The `.env` variables `KANBOARD_URL`, `KANBOARD_USER`, `KANBOARD_TOKEN` (JSON-RPC API credentials, `.env:7-9`) appear to be provisioned for a future backend-side Kanboard integration (e.g. syncing planning items/tasks to Kanboard cards) that does not exist yet — currently dead configuration from the application's point of view. Worth flagging if a real Kanboard sync is ever planned, since the credential shape (JSON-RPC endpoint + user + token) implies server-to-server calls, not iframe embedding.
- `KANBOARD_TOKEN=YOUR_KANBOARD_TOKEN_HERE` in `.env` is an unfilled placeholder, consistent with it being unused.
- This page is structurally identical to `frontend/src/pages/forgerouter/index.tsx` (same iframe-wrapper pattern, same fallback-localhost-URL style) — confirms this is a deliberate, repeated "embed external tool via iframe" pattern in the app (also used for ForgeRouter), not a one-off.
- No `title`-based accessibility concerns beyond the iframe's `title="Kanboard"` attribute (`kanboard/index.tsx:6`), which is present and reasonable.
