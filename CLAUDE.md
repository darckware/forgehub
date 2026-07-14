# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this product is

ForgeHub is a control plane for planning, governing, and executing software projects with AI agents: product/version/project registration, pipeline stages with mandatory artifacts and approval gates, planning items (features/bugs/etc.) broken into tasks, task executions by agents, and an audit trail tying every entity back to a product version. It replaces the previous "Hermes Agent Forge" naming throughout the codebase, UI, and docs.

Full domain model and business rules: `docs/PRD.md` (vision, journeys, definition of done) and `docs/SPEC.md` (entities, business rules, acceptance criteria — see especially §6 for the per-domain rule list referenced from model/route docstrings).

Core invariant from the PRD: no feature, bug, task, skill, execution, or artifact may exist without linkage to product, version, project, planning, pipeline, owner, status, audit trail, and validation criteria. Most tables exist to keep that traceability chain unbroken, not just to store data.

## Canonical stack (confirmed, supersedes SPEC.md §2/§3.2)

`docs/SPEC.md` describes a C#/ASP.NET Core + Dapper backend. That is **stale** — the implemented backend stack matches `docs/TECHNOLOGY.md`:

- Backend: Python 3.11, FastAPI, SQLAlchemy (async) + asyncpg, Alembic migrations, OAuth2 password flow + JWT, pytest + httpx for tests.
- Frontend: React 18 + Vite, TypeScript, shadcn/ui (Tailwind + Radix primitives, via `class-variance-authority`/`clsx`/`tailwind-merge`) + Framer Motion, TanStack Query + Zustand, React Hook Form + Zod, Vitest + React Testing Library.
- Datastore: PostgreSQL (pgvector/pg16), shared instance `company_postgres` on port 5433, database `forgehub`, schema `company` (**every** table — models set `MetaData(schema=settings.POSTGRES_SCHEMA)` in `backend/app/db/base.py`, never `public`). ForgeHub does not run its own Postgres container; `database/postgres-company/docker-compose.yml` only re-documents/recreates the externally-managed container definition (see its trailing comment — do not blindly `docker compose up` there without checking config drift, Kanboard depends on the same container). Full topology: `docs/DB_README.md` and `/root/.hermes/foundation/governance/POSTGRESQL_TOPOLOGY.md`. The other instance, `foundation_postgres` (port 5432), is reserved for internal Hermes/Foundation data — never put ForgeHub application data there.
- Integrations already provisioned in `.env`: Postgres connection (`company_postgres:5433/forgehub`), Kanboard (URL/user/token).

When implementing, follow `docs/TECHNOLOGY.md` over `docs/SPEC.md` wherever they conflict (backend language/framework, directory layout). `docs/SPEC.md` remains the source of truth for the domain model, business rules, and acceptance criteria — only its tech-stack sections (§2, §3.2) and its directory layout (§10) are superseded.

## Commands

All commands assume `.env` at the repo root (Postgres + Kanboard credentials) is present.

**Fast iteration (recommended day-to-day — no Docker rebuild per change):**
```bash
./dev.sh            # backend :8001 (uvicorn --reload) + frontend :5173 (vite dev, hot-reload)
./dev.sh status       # what's currently up
./dev.sh stop         # stop both
./dev.sh restart      # stop + start
```
Deliberately on different ports than the Docker deploy (8000/4173) so both can run at once.
Auto-checks `.env`/`backend/.venv`/`frontend/node_modules` and creates/installs what's missing.
Won't kill a process it didn't start; stop targets whoever's actually listening on the port
(`lsof -tiTCP:<port> -sTCP:LISTEN`), not a captured PID — `uvicorn --reload` and `npm run dev`'s
wrapper both fork workers with a different pid than `$!` captures. Use this for verification
(pytest/tsc still apply); only run the Docker command below when a deploy is actually requested.

**Run the full stack (Docker) — only when a deploy is explicitly requested:**
```bash
docker compose up -d --build
curl http://localhost:8000/health        # → {"status":"ok"}
open http://localhost:4173               # frontend (served via `serve`, built dist)
```

**Backend, local dev (manual, if not using dev.sh):**
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Backend migrations (Alembic, async, schema `company`):**
```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "<message>"   # picks up new models via app/db/models/__init__.py
```

**Backend tests (pytest + httpx, hits the real `company_postgres` DB — no mocking):**
```bash
cd backend
pytest                                  # all tests
pytest app/tests/test_product.py        # single domain
pytest app/tests/test_product.py::test_create_get_list_product   # single test
```
Tests use `httpx.AsyncClient` with `ASGITransport` against the real FastAPI `app` and the real async session from `app/db/base.py`. There is no test-DB isolation/transaction rollback — each test creates its own rows (usually with a UUID-suffixed unique name) and explicitly deletes them in a `finally`/cleanup helper. Tests require migrations to have been applied first (tables must exist).

**Frontend, local dev:**
```bash
cd frontend
npm install
npm run dev          # vite dev server, port 5173, proxies to VITE_API_URL (default http://localhost:8000)
npm run build         # tsc -b && vite build
npm run preview       # serves the production build, port 4173 (matches docker-compose)
npm test               # vitest, jsdom environment, setup file at src/test/setup.ts
```

## Architecture

### Backend: domain-module pattern

The backend is organized as independent **domain modules**, each touching exactly three layers under `backend/app/`:

```
db/models/<domain>.py     SQLAlchemy ORM models for that domain's tables
api/schemas/<domain>.py   Pydantic request/response schemas
api/routes/<domain>.py    APIRouter with the domain's full CRUD surface
```

Domains: `product`, `project`, `pipeline`, `backlog`, `task`, `agent`, `artifact`, `governance`, `demand` (the Inbox — see below), `prompt_commands`, plus `foundation`, `system_control`, `hindsight` (all three host-bridge proxy domains — no DB table of their own, see below) and `auth` (placeholder — see below).

Key conventions, binding for any new domain code (stated in docstrings across `db/base.py` and the model files — read one model file like `db/models/product.py` before adding to a domain):

- **UUID primary keys, Python-side default.** Always `mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)`. Never autoincrement ints or server-side `gen_random_uuid()` — IDs must exist before flush/commit.
- **`TimestampMixin`** (in `db/base.py`) gives every model `created_at`/`updated_at` for free — don't redeclare them.
- **Cross-domain foreign keys are string-form and lazy.** A domain never imports another domain's model module to declare an FK; it writes `ForeignKey("company.<table>.id")` as a plain string. This avoids import-order coupling between domain modules. All domain modules get imported together (and thus all FKs resolved) centrally in `app/db/models/__init__.py`, which Alembic's `env.py` also imports for autogenerate.
- **Polymorphic references use (entity_type, entity_id), not a FK** — e.g. `governance.Approval`/`AuditEvent` target many different table types and deliberately skip a real FK (see `db/models/governance.py` docstring).
- **Status/enum-like fields are plain `String` + a `CheckConstraint`**, not native Postgres ENUM types — keeps migrations simple, avoids `ALTER TYPE` churn. The allowed value tuple lives next to the model (e.g. `PRODUCT_VERSION_STATUSES` in `db/models/product.py`) and is re-validated at the route layer.
- **Business rules live at the API layer, not as DB constraints**, whenever they require a second statement or cross-row checks (e.g. "every product must have ≥1 version" — enforced in `create_product`/`delete_version` in `api/routes/product.py`, not a constraint). Route docstrings cite the specific SPEC.md §6 rule they implement — check there before changing CRUD behavior.
- **Routes own their full path.** Every `api/routes/<domain>.py` exports a module-level `router = APIRouter(prefix="/api/v1/<resource>", tags=[...])`; `app/main.py` only does `app.include_router(...)` and never adds prefixes itself.
- **Settings are centralized.** `app/core/config.py`'s `settings` object (pydantic-settings, loads repo-root `.env`) is the only place reading env vars — `db/base.py`, `core/security.py`, and `alembic/env.py` all import `settings` rather than touching `os.environ` directly.

### Backend: non-domain pieces

- **`auth.py` is an explicit placeholder.** It checks credentials against a single hardcoded dev user from `settings.DEV_USER_USERNAME`/`DEV_USER_PASSWORD` — there is no real Users/Auth domain yet (out of scope per PRD/SPEC at this stage). Its docstring asks that a future real implementation keep the same contract (`POST /api/v1/auth/token`, `OAuth2PasswordRequestForm` in, `{access_token, token_type}` out).
- **`foundation.py` is mostly a filesystem-only router**, with one deliberate exception. It reads from filesystem mounts (`/vault/Agents`, `/profiles`) to expose Hermes Foundation agent metadata (SOUL.md, sub-agents, skills, MEMORY.md) over HTTP. It also owns the per-profile `hermes cron` job stores (`<profile>/cron/jobs.json`): the list endpoint reports unparsable stores via `store_errors` (a corrupted store silently stops every cron in that profile — never swallow that) and refreshes a `.jobs.json.good` recovery snapshot on each clean read. SKILL.md read/write for the Skills page lives here too (`/foundation/skills/{name}/content`). Its **`/scripts` endpoint is the one place this router touches the database**: `_audit_check_script_refs` queries the `audit` domain's `audit_checks` table (enabled checks only) so a script invoked solely by an Auditor check's command — no corresponding cron job — isn't wrongly reported as `"unused"` (2026-07-09); `_foundation_registry_script_names` extends the same idea to the `foundation_scripts` table (the Foundation page's Scripts registry, `foundation_script.py`'s own domain) so a script documented by a Hermes/Foundation governance doc (`doc_path` set, or hand-registered) also counts as referenced even with no cron job, no Auditor check, and no systemd/ad hoc trigger ForgeHub can see (2026-07-11 — see `docs/SCRIPTS_AND_CRONS.md`'s §3 for the incident: `worker.sh`/`kanboard-cleanup.sh`/`send_demand.sh`/`health_check.sh` kept showing as "Old/unused scripts" in System Control's Cleanup card despite being registered there). `_list_scripts` reads every profile's `scripts/` dir off the event loop via `asyncio.to_thread` and returns the raw file content alongside the list so `system_control.py`'s cleanup-scan can reuse it (hashing for duplicates) instead of re-reading every script from disk a second time; script identity there is keyed by `(profile, filename)`, not filename alone, since two profiles can each have a same-named script.
- **`demand.py` is the Inbox** — ForgeHub's "console de desenvolvimento" intake: any agent (via the bridge-token `/demands/submit`) or the logged-in user (via the JWT `/demands`, backing both the chat's `/demanda` command and the Inbox page's "Nova nota" compose dialog) files a note here, which a human then reads and converts. `core/conversions.py`'s `CONVERT_TARGETS` has 7 targets: `task`/`doc`/`artifact`/`knowledge_base` (the original four) plus `planning_item`, `project_doc`, and `quick_task` (project-scoped — create a planning item, a project-linked doc, or a planning item + task together in one call, since a task can never exist without a planning item per the core traceability invariant). Every new demand also inserts a `Notification(source="system")` so arrivals surface in the existing bell, and `POST /demands/{id}/notify-telegram` forwards a demand through the host-bridge's cross-channel messaging proxy (see below). `demand_attachments` stores uploaded files under the same `/docs` mount `docs.py` writes to.
- **`system_control.py` and `hindsight.py` are host-bridge proxy domains, like `foundation.py`** — no DB table of their own. `system_control.py` surfaces this repo's git status/last-commit and triggers a compressed `/root/.hermes` backup, both via host-bridge (`/v1/exec`, `/v1/system/hermes-backup`) since the backend container has neither a git checkout of the host repo nor a `git` binary. `hindsight.py` surfaces Hermes' Hindsight memory-daemon status/logs (`/v1/hindsight/status`) and two admin-gated mutations: `/restart` (docker restart) and `/clear-log` (truncates whichever log file the status view reads — these processes never rotate their own logs).
- **Chat streaming is a 3-hop SSE proxy** (browser → nginx → `chat.py` → host-bridge on port 8910 → `hermes_stream.py` subprocess). Two hard-won rules: frontend fetches must be same-origin (`VITE_API_URL || window.location.origin` — a hardcoded localhost fallback breaks every call from LAN/tunnel origins), and silent periods are covered by `: ping` SSE comments (proxies kill byte-silent connections ~100s; agent turns think for minutes). A stream that ends without `done` must persist the partial reply + tool steps and surface an explicit error — never end silently (the turn "vanishes" from the UI). The bridge runs under systemd (`forgehub-chat-bridge.service`), restart with systemctl, not docker. Those mounts come from `docker-compose.yml`'s bind mounts of `/root/.hermes/knowledge_base/vault` and `/root/.hermes/profiles` — this router will 404/return empty data if run outside that container or without equivalent local mounts.
- **The host-bridge (`host-bridge/app.py`) also proxies Hermes' cross-channel messaging gateway** — `POST /v1/messages/send` shells out to `host-bridge/send_message.py` (a `HERMES_PYTHON` subprocess, same pattern as `hermes_stream.py`, since the bridge's own process doesn't have Hermes' `tools`/`gateway` packages on its `sys.path`) to forward a message via `send_message_tool` to Telegram/Discord/Slack/etc. Target format `"platform:chat_id"`, or just `"platform"` to resolve the configured home channel (`~/.hermes/config.yaml`, `hermes config set <PLATFORM>_HOME_CHANNEL <chat_id>` if unset). `demand.py`'s `/notify-telegram` is the only current caller.
- **`docker-compose.yml`** puts both containers on the single external `foundation_network` (renamed from `hermes_foundation_pg_default` on 2026-07-03), shared with `company_postgres`, `foundation_postgres`, Kanboard and Hindsight. There is no ForgeHub-only network (the old `forgehub_default` was removed): backend needs the shared net to reach `company_postgres`, and the frontend's nginx proxies `/api` to `http://forgehub-backend:8000` by container name, so it sits on the same network. `foundation_network` is created manually (`docker network create foundation_network`) and referenced as `external: true` by every compose that uses it.

### Frontend: per-domain page + hook pairing

Each backend domain has a matching `frontend/src/pages/<domain>/` (typically `index.tsx` list view, `[id].tsx` detail view, `<Domain>Form.tsx`) and a `frontend/src/hooks/use<Domain>.ts` (TanStack Query hooks). Pages whose main table should scroll internally (tools, skills, notifications, database, workspace) are "full-bleed": listed in `AppLayout.tsx`'s `isFullBleed` so `<main>` gets a definite `h-screen` height — without it the `flex-1 min-h-0 → overflow-auto` chain never binds and the table overflows the viewport with no scrollbar. `src/lib/api.ts` is the single fetch wrapper everything goes through — domain hooks call `apiClient.get/post/put/patch/delete` with the exact `/api/v1/<resource>` path; never hardcode `BASE_URL` or add path segments elsewhere. `BASE_URL` comes from `VITE_API_URL` (defaults to `http://localhost:8000`).

`src/components/ui/` holds shadcn/ui primitives (button, card, input, select, table, etc.) — extend this set via the shadcn CLI/pattern rather than hand-rolling alternatives.

**Sidebar navigation** (`src/components/layout/Sidebar.tsx`) is data-driven from `src/components/layout/navSections.ts`'s `NAV_SECTIONS` — shared with `CommandPalette.tsx` (Cmd/Ctrl+K quick nav, filtered by the same `usePermission` checks) so the route list is never duplicated. Each top-level section groups by a single semantic criterion (e.g. "Agents & AI" is agent config only, "Operations" is infra/ops tooling, "Integrations" is external tool links) — when a new nav entry doesn't clearly fit an existing section, that's a signal to add a section rather than force it into a "misc" one. Section headers are independently collapsible (state in `localStorage`). The `/demands` route is labeled "Inbox" in the sidebar, not "Demandas" — see `demand.py`'s domain description above for why.

## UI library governance

Canonical UI stack is shadcn/ui + Radix + Tailwind (+ Framer Motion when justified). Any other UI library is "complementary": adopting one requires checking license, accessibility, bundle impact, maintenance, and security, and an ADR is required if it replaces the canonical stack, introduces a parallel design system, or is premium/commercial in production. Full policy: `docs/SPEC.md` §7.
