<p align="center">
  <img src="docs/assets/forgehub-logo.svg" width="260" height="64" alt="ForgeHub" />
</p>

<p align="center">
  <strong>The control plane for planning, governing, and executing software projects with AI agents.</strong>
</p>

<p align="center">
  <a href="#key-features">Key Features</a> ·
  <a href="#tech-stack">Tech Stack</a> ·
  <a href="#getting-started">Getting Started</a> ·
  <a href="#documentation">Documentation</a>
</p>

---

## Overview

ForgeHub is a governance and execution platform for teams that build software with the help of AI agents. It ties every unit of work — from a product version down to a single task execution — back to an unbroken audit trail: product, version, project, planning item, pipeline stage, owner, status, and validation criteria.

Rather than treating agent output as a black box, ForgeHub enforces the discipline software organizations already expect from human teams: pipelines with mandatory artifacts and approval gates, planning items broken into accountable tasks, and a full record of who (or which agent) did what, when, and why it was approved.

## Key Features

- **Product & pipeline governance** — register products, versions, and projects; define pipeline stages with required artifacts and approval gates before work can advance.
- **Planning → execution traceability** — break features, bugs, and other planning items into tasks, assign them to agents, and track every execution back to its originating planning item.
- **Agent registry** — manage executor/coordinator agents, sub-agents, skills, cost rates, and capacities, synced from the Hermes Foundation agent roster.
- **Audit trail by design** — approvals and audit events are first-class entities, not an afterthought bolted onto existing tables.
- **Inbox** — a lightweight intake channel where agents or humans file notes, later converted into tasks, docs, artifacts, or planning items.
- **Operational tooling** — built-in views for cron jobs, database introspection, Hindsight memory status, and system/git control, so the same console that governs planning also gives visibility into the infrastructure running it.

## Tech Stack

| Layer | Stack |
|---|---|
| **Backend** | Python 3.11 · FastAPI · SQLAlchemy (async) + asyncpg · Alembic · OAuth2/JWT · pytest + httpx |
| **Frontend** | React 18 + Vite · TypeScript · shadcn/ui (Tailwind + Radix) + Framer Motion · TanStack Query + Zustand · React Hook Form + Zod · Vitest |
| **Datastore** | PostgreSQL (pgvector/pg16) |

See [`docs/TECHNOLOGY.md`](docs/TECHNOLOGY.md) for the full, authoritative stack reference.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js (for the Vite/React frontend)
- Docker (only required for the containerized deploy path)
- A reachable PostgreSQL instance, configured via a repo-root `.env` (see [`docs/DB_README.md`](docs/DB_README.md))

### Fast iteration (recommended for day-to-day development)

No Docker rebuild required — hot-reload on both sides:

```bash
./dev.sh            # backend on :8001 (uvicorn --reload) + frontend on :5173 (vite dev)
./dev.sh status      # check what's running
./dev.sh stop        # stop both
./dev.sh restart     # stop + start
```

`dev.sh` auto-checks for `.env`, `backend/.venv`, and `frontend/node_modules`, creating/installing whatever is missing on a fresh checkout.

### Full stack via Docker

```bash
docker compose up -d --build
curl http://localhost:8000/health   # → {"status":"ok"}
open http://localhost:4173          # frontend
```

### Database migrations

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "<message>"
```

### Running tests

```bash
# Backend (pytest + httpx, against a real database)
cd backend && pytest

# Frontend (Vitest + React Testing Library)
cd frontend && npm test
```

## Documentation

| Doc | Purpose |
|---|---|
| [`docs/PRD.md`](docs/PRD.md) | Product vision, user journeys, definition of done |
| [`docs/SPEC.md`](docs/SPEC.md) | Domain model, entities, business rules, acceptance criteria |
| [`docs/TECHNOLOGY.md`](docs/TECHNOLOGY.md) | Canonical technology stack |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Entity/relationship reference |
| [`docs/DB_README.md`](docs/DB_README.md) | Database topology and connection setup |
| [`docs/MANUAL.md`](docs/MANUAL.md) | End-user operating manual |
| `http://localhost:8000/docs` | Live FastAPI interactive API reference |

## License

Internal / proprietary — all rights reserved.
