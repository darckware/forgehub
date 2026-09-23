# Repository Guidelines

## Project Structure & Module Organization

ForgeHub is split into a FastAPI backend and a React/Vite frontend. Backend code lives in `backend/app/`: domain models in `db/models/`, Pydantic schemas in `api/schemas/`, routes in `api/routes/`, and tests in `app/tests/`. Alembic migrations are in `backend/alembic/versions/`. Frontend source is in `frontend/src/`, with shared API and utilities in `src/lib/` and test setup in `src/test/setup.ts`. Product and architecture docs live in `docs/`.

## Build, Test, and Development Commands

- `./dev.sh`: start development servers with hot-reload (backend on :8001, frontend on :5172).
- `./dev.sh status` / `./dev.sh stop` / `./dev.sh restart`: inspect and manage dev servers.
- `./scripts/build.sh`: build versioned images with commit and build metadata.
- `./scripts/deploy.sh`: build and deploy the full stack with traceable version metadata.
- `cd backend && uvicorn app.main:app --reload --port 8000`: run the API locally.
- `cd backend && alembic upgrade head`: apply database migrations.
- `cd backend && pytest`: run backend tests.
- `cd backend && ruff check app`: run the configured Python linter.
- `cd frontend && npm install`: install frontend dependencies.
- `cd frontend && npm run dev`: start the Vite dev server.
- `cd frontend && npm run build`: type-check and build the frontend.
- `cd frontend && npm test`: run Vitest tests.

## Coding Style & Naming Conventions

Backend code targets Python 3.13. Follow the domain-module pattern: matching `db/models/<domain>.py`, `api/schemas/<domain>.py`, and `api/routes/<domain>.py` files when applicable. Use UUID primary keys, `TimestampMixin`, string-form cross-domain foreign keys, and route-level business-rule validation. Ruff enforces Pyflakes plus `B904`; do not broaden lint scope without team agreement.

Frontend code uses TypeScript, React 18, Tailwind, shadcn/ui, TanStack Query, and Zustand. Keep API calls centralized through `frontend/src/lib/api.ts`. Use PascalCase for components, `useX` for hooks, and domain-oriented folders under `src/pages/`.

## Testing Guidelines

Backend tests use pytest with async support and `httpx.AsyncClient` against the real FastAPI app and database. Create unique test data and clean it up explicitly. Name tests `test_<behavior>` and place them in `backend/app/tests/`. Frontend tests use Vitest with jsdom and React Testing Library; keep setup in `frontend/src/test/setup.ts`.

## Commit & Pull Request Guidelines

Recent commits use short, imperative, scope-prefixed messages such as `Chat: survive long turns` or `Crons: surface corrupted stores`. Keep subjects specific and user-facing. Pull requests should describe the change, list verification commands run, link related issues or docs, and include screenshots for visible UI changes.

## Security & Configuration Tips

Keep secrets in the repo-root `.env`; do not commit credentials. ForgeHub application data belongs in the shared `company` schema on `company_postgres`, not `public` or `foundation_postgres`. Prefer `docs/TECHNOLOGY.md` for implemented stack details when it conflicts with older spec sections.
