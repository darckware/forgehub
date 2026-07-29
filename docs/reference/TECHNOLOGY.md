# Tecnologia do ForgeHub

## Backend
- **Linguagem**: Python 3.11
- **Framework**: FastAPI (async, OpenAPI automatic)
- **Servidor HTTP**: Uvicorn/Gunicorn
- **Banco de Dados**: PostgreSQL 15 (Docker Compose)  
  - Conexão via SQLAlchemy + asyncpg
  - Migrations com Alembic
- **Autenticação**: OAuth2 password flow + JWT
- **Testes**: pytest + httpx (async)
- **CI/CD**: GitHub Actions, Docker multi‑stage builds

## Frontend
- **Linguagem**: TypeScript
- **Framework**: React 18 + Vite (fast dev server)
- **UI Kit**: shadcn/ui (Tailwind CSS + Radix UI primitives)
- **State Management**: TanStack Query + Zustand
- **Form handling**: React Hook Form + Zod (schema validation)
- **Styling**: Tailwind CSS 3 + class‑variance‑authority (CVA)
- **Testing**: Vitest + React Testing Library
- **Storybook**: UI component catalogue

## Infraestrutura

## Metodologia de desenvolvimento
- **Processo Ágil**: Scrum com sprints de 1‑2 semanas + Kanban nativo no ForgeHub (Kanboard descontinuado).
- **Planejamento**: Domain‑Driven Design (DDD) + Event‑Storming para definir bounded contexts.
- **Implementação**: Test‑Driven Development (TDD) – pytest + httpx no backend; Vitest + React Testing Library no frontend.
- **CI/CD**: GitHub Actions com lint (ruff/flake8, eslint/prettier), type‑check (mypy, tsc), testes automatizados e builds Docker multi‑stage.
- **Revisão de Código**: Pull‑Request workflow com checklist de segurança, qualidade e UI/UX.
- **Entrega**: Deploy canário/blue‑green via Docker Compose, health‑checks e rollback automático.
- **Monitoramento**: Sentry + OpenTelemetry (frontend); loguru + Prometheus/Grafana (backend).
- **Definition of Done**: testes cobertos ≥ 80 %, lint aprovado, documentação atualizada, deploy em staging concluído.
- **Branching**: GitHub Flow (feature branches → PR → merge).
- **Retrospectiva**: sprint retro para ajustar débito técnico e performance.

## Infraestrutura
- **Banco de dados**: instância compartilhada `company_postgres` (porta `5433`), database `forgehub`, schema `company` — o ForgeHub não roda Postgres próprio. Ver `docs/reference/DB_README.md`.
- **Docker Compose**
  - `backend` service – FastAPI app, conecta em `company_postgres:5433/forgehub`
  - `frontend` service – Vite dev server, proxy to backend
- **Env vars** (`.env`)
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_SCHEMA`
  - `DATABASE_URL=postgresql+asyncpg://...`
  - `JWT_SECRET`, `API_URL`

## Organização do código
```
forgehub/
├─ backend/
│  ├─ app/
│  │  ├─ api/          # rotas FastAPI
│  │  ├─ core/         # configs, dependências
│  │  ├─ db/           # models SQLAlchemy + migrations
│  │  └─ tests/
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  │  ├─ components/  # UI primitives (shadcn)
│  │  ├─ pages/       # rotas React Router
│  │  ├─ hooks/       # TanStack Query wrappers
│  │  └─ ...
│  └─ Dockerfile
└─ docker-compose.yml
```