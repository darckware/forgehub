# PostgreSQL Topology Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy `company_postgres` and `foundation_postgres` instances with dedicated `forgehub_postgres`, `forgerouter_postgres`, and `hindsight_postgres` instances without losing application data.

**Architecture:** ForgeHub owns database `forgehub` on port 5433, ForgeRouter owns database `forgerouter` on port 5434, and Hindsight/Foundation owns database `foundation` on port 5432. Each instance has its own named Docker volume and joins the shared `foundation_network`.

**Tech Stack:** Docker Compose, PostgreSQL 16 with pgvector, pg_dump/pg_restore, FastAPI configuration.

**Spec:** User-approved topology in the current maintenance session.

## Global Constraints

- Preserve verified dumps before stopping or deleting any database container.
- Do not migrate or restore the discontinued `kanboard` database.
- Keep rollback possible by retaining the legacy bind-mounted data directories.
- Verify database connectivity, schemas, application health, and row counts before completion.

---

### Task 1: Define the three PostgreSQL instances

**Files:**
- Create: `database/docker-compose.yml`
- Modify: `database/postgres-company/docker-compose.yml`

- [ ] Add one service and one persistent volume for each approved instance.
- [ ] Validate the Compose configuration with `docker compose config`.

### Task 2: Update ForgeHub and Hindsight connections

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/api/routes/database.py`
- Modify: `.env.example`

- [ ] Replace legacy instance names with the approved names.
- [ ] Give ForgeRouter its own connection settings.
- [ ] Run backend configuration tests.

### Task 3: Migrate the live development data

- [ ] Dump `forgehub`, `forgerouter`, and `foundation` in custom format.
- [ ] Stop the legacy database containers without deleting bind-mounted data.
- [ ] Start the three new instances.
- [ ] Restore one database into each destination with ownership normalized.
- [ ] Validate schemas, sizes, and representative row counts.

### Task 4: Restart and verify the stack

- [ ] Start ForgeRouter with its new database URL.
- [ ] Start ForgeHub and Hindsight.
- [ ] Verify container health and HTTP health endpoints.
- [ ] Confirm the discontinued `kanboard` database is absent from the new topology.
