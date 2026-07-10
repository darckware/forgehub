# Screen: Dashboard

## Route & Purpose

Route: `/` (index route, `frontend/src/App.tsx:30` — `<Route index element={<Dashboard />} />`).
Component: `frontend/src/pages/Dashboard.tsx`.

Landing screen of the app. It does not surface any ForgeHub domain data (no products, projects, pipelines, tasks, etc.) — it is an operational/observability view of the local development environment: installed CLI tool versions and host system resource usage. Heading text is static: "Dashboard" / "Welcome to ForgeHub." (`Dashboard.tsx:8-9`).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/Dashboard.tsx` | Page shell; renders a 2-column grid (`md:grid-cols-2`) with the two cards below. No local state, no data fetching itself. |
| `frontend/src/components/ToolVersionsCard.tsx` | Card listing installed/latest versions of 4 monitored CLIs (Hermes, Claude Code, Codex, Antigravity), with manual "check now", per-tool "Update", and an automatic-sync on/off toggle. |
| `frontend/src/components/SystemStatsCard.tsx` | Card showing host memory and disk usage (progress bars) and network interface RX/TX byte counters. Read-only, auto-refreshing. |
| `frontend/src/components/ui/badge.tsx`, `frontend/src/components/ui/card.tsx`, `frontend/src/components/ui/button.tsx` | shadcn/ui primitives used for layout/status rendering. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Per-tool installed/latest version, update-available flag, last error (Hermes/Claude/Codex/Antigravity) | `useToolVersions()` (`frontend/src/hooks/useToolVersions.ts:43-48`) | `/api/v1/tool-versions` (`backend/app/api/routes/toolversions.py:126-131`) | GET |
| Automatic-sync on/off state | `useToolSyncSetting()` (`useToolVersions.ts:66-71`) | `/api/v1/tool-versions/sync` (`toolversions.py:173-175`) | GET |
| Memory used/total/percent, disk used/total/percent, network interface + RX/TX bytes | `useSystemStats()` (`frontend/src/hooks/useSystemStats.ts:39-47`) | `/api/v1/system-stats` (`backend/app/api/routes/systemstats.py:17-28`) | GET |

Mutations triggered from this screen:

| Action | Hook | Backend endpoint | Method |
|---|---|---|---|
| "Check now" (force version check) | `useCheckToolVersions()` (`useToolVersions.ts:50-56`) | `/api/v1/tool-versions/check` | POST |
| Toggle automatic sync | `useSetToolSyncSetting()` (`useToolVersions.ts:73-79`) | `/api/v1/tool-versions/sync` | PUT |
| "Update" a given tool | `useUpdateTool()` (`useToolVersions.ts:58-64`) | `/api/v1/tool-versions/{tool}/update` | POST |

Backend-side wiring (not visible in the frontend but relevant to understanding the data source):
- `tool-versions` GET reads a DB cache (`tool_version_status` table, model `backend/app/db/models/toolversions.py`) so the page has something to render without a host round-trip; `/check` and `/update` proxy live to the host bridge (`host-bridge/app.py`'s `/v1/tool-versions*`) and persist the result. A background poll (`backend/app/main.py:85-99`, every 900s when sync is enabled) refreshes the same cache independently of this screen being open.
- `system-stats` GET has **no DB model** — it is a pure live proxy to the host bridge's `/v1/system-stats` on every request (`systemstats.py:1-7,17-28`). `useSystemStats` additionally polls it client-side every 15s (`useSystemStats.ts:43-46`, `refetchInterval: 15_000`).
- Both backend routes call the host bridge over HTTP with header `X-Bridge-Token: settings.CHAT_BRIDGE_TOKEN` and URL `settings.CHAT_BRIDGE_URL` (`toolversions.py:42-43`, `systemstats.py:21-23`). If the bridge container (`forgehub-chat-bridge` per the UI's own error text) is unreachable, the backend returns `502 Bad Gateway`.

## Actions Available

- **Check now** (`ToolVersionsCard.tsx:48-62`, refresh icon button) — forces an immediate version check of all 4 tools via the host bridge; spinner shown while `checkVersions.isPending`.
- **Toggle automatic sync** (`ToolVersionsCard.tsx:63-77`, Wifi/WifiOff icon button) — flips the background poll's persisted enabled/disabled state.
- **Update** (`ToolVersionsCard.tsx:124-137`, per-tool button) — only rendered when `version.update_available` is true; runs the tool's real update command on the host, then refreshes that tool's status row. Disabled (shows spinner) while that specific tool is updating (`updatingTool` local state, `ToolVersionsCard.tsx:34,38-41`).

`SystemStatsCard` exposes no interactive actions — it is read-only, refreshed automatically every 15 seconds.

## States

**ToolVersionsCard:**
- Loading: spinner + "Loading..." row while `useToolVersions` is pending (`ToolVersionsCard.tsx:88-93`).
- Per-tool status badges: "Update available" (warning, shows latest version), "Up to date" (success), "Check failed" (destructive, with `last_error` as tooltip), or "Not checked" (outline) — `ToolVersionsCard.tsx:113-123`.
- Error: a single inline message is shown if either `checkVersions.isError` or `updateTool.isError`, with two different copies depending on which one failed (`ToolVersionsCard.tsx:81-87`). There is no per-row "empty" state distinct from "Not checked".

**SystemStatsCard:**
- Loading: spinner + "Loading..." while `isLoading` (`SystemStatsCard.tsx:84-89`).
- Error: inline destructive text "Failed to reach the host bridge..." when `isError` (`SystemStatsCard.tsx:90-94`).
- Success: renders memory/disk usage bars (color-coded by `barColor()` — green <75%, amber 75-89%, red ≥90%, `SystemStatsCard.tsx:12-16`) and the network row.
- No explicit "empty" state (the bridge always returns all three sub-objects when it responds 200).

## Business Rules Surfaced Here

None directly enforced here. This screen does not touch any entity covered by `docs/BUSINESS_RULES.md` (Product, Pipeline, Planning, Execution, Skill, Traceability, Governance) — it has no DB-backed domain model relationship to product/version/project/pipeline/owner/audit trail. The only "rule"-like behavior is operational and local to this domain: the tool-versions cache is read-cheap (GET never hits the host) while `/check` and `/update` always hit the host bridge live (`toolversions.py:126-131` vs `134-170`).

## Dependencies

- **`tool-versions` domain** (non-core, infra/observability) — `backend/app/db/models/toolversions.py`, `backend/app/api/routes/toolversions.py`. Not part of the Product/Project/Pipeline/Backlog/Task/Agent/Artifact/Governance domain set described in `docs/DATA_MODEL.md`.
- **`system-stats` domain** (non-core) — `backend/app/api/routes/systemstats.py`. No DB model at all.
- **External: host-bridge service** (`host-bridge/app.py`, referenced as `forgehub-chat-bridge` in error copy) — both cards are non-functional (loading or error state) if this service is down, since neither backend route can serve real data without it.

## Notes / Improvement Opportunities

- `ToolVersionsCard.tsx:81-87`: the combined error banner only distinguishes "check failed" vs "update failed" by which mutation's `isError` flag is set, not by inspecting the actual failing tool — if a user has both a failed check and a failed update pending across renders, only the check-failed message would show (it's checked first in the ternary).
- `SystemStatsCard.tsx`: no manual refresh control (unlike `ToolVersionsCard`'s "Check now") — the user must wait up to 15s for `refetchInterval` or reload the page.
- `useSystemStats.ts` has no `isError`-driven retry/backoff configuration visible in the hook itself; relies on TanStack Query defaults.
- Antigravity is excluded from the periodic background poll (`backend/app/main.py:96`, `toolversions.py:34-39`) because checking it requires actually running `agy update` rather than a read-only version check; this is invisible on the Dashboard UI itself — a user has no way to tell from this screen that Antigravity's "Not checked"/stale badge state behaves differently from the other three tools until they read the backend comment.
- Dashboard.tsx itself has no error boundary — if either card's underlying hook throws synchronously (vs. surfacing via React Query's `isError`), there's no page-level fallback beyond what TanStack Query manages per-hook.
