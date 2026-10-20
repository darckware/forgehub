# Nexo Client Monitoring Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the foundation for Nexo client monitoring in ForgeHub: the `Client`/`Workstation`/
`Irregularity` domain, the ingestion endpoint that turns Nexo Remote Agent reports into
Irregularities, an `agent_unreachable` staleness sweep, and the Irregularities screen.

**Architecture:** A new `clients` domain module (`db/models/client.py`, `api/schemas/client.py`,
`api/routes/client.py`) following this codebase's established domain-module pattern (UUID PK,
`TimestampMixin`, `String` + `CheckConstraint` instead of native enums, cross-domain FKs as plain
strings). The ingestion endpoint authenticates by a per-`Workstation` device token (SHA-256
hashed, same boundary as `Agent.forgerouter_api_key_encrypted`/`AgentServiceCredential.token_hash`)
rather than the existing JWT/`agt_`-prefixed principal path, since a device token identifies a
`Workstation`, not a `User`/`Agent`. Rule evaluation is a pure function over the ingested report
body, producing zero or more `Irregularity` rows plus a `Notification` each (reusing the existing
bell — no parallel notification mechanism). A second async poll loop (same pattern as
`demand.py`'s existing `_dispatch_completion_poll_loop`) detects workstations that stopped
reporting.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (async) + asyncpg, Alembic, pytest + httpx
(against the real `company_postgres` DB, no mocking) — backend only. Frontend: React 18 + Vite +
TypeScript, TanStack Query, shadcn/ui, following the existing per-domain page+hook pairing.

**Spec:** `docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md` §1-4 (this plan covers
the domain model, ingestion, and Irregularities screen only — §5 Nexo network administration, §6
installer/download area, and §7 report generation are separate follow-up plans, per that spec's
own multi-subsystem scope).

## Global Constraints

- UUID primary keys, Python-side `uuid.uuid4` default — never autoincrement, never server-side
  `gen_random_uuid()` (per `db/base.py`).
- Every model gets `TimestampMixin` for `created_at`/`updated_at` — never redeclare them.
- Status/kind fields are plain `String` + `CheckConstraint`, never native Postgres ENUM.
- Cross-domain FKs are string-form (`ForeignKey("company.<table>.id")`), never an import of
  another domain's model module.
- The raw device token is returned to the caller exactly once, at issuance — every other read
  returns only a boolean/hash-presence indicator, same convention as
  `Server.private_key_stored`/`Agent.forgerouter_api_key_configured`.
- `SchemaVersion` mismatch on an ingested report is a 400, not a silent best-effort parse — the
  Nexo Remote Agent's payload contract (`internal/collector/report.go` in `/root/project/nexo`,
  post the final-review fix wave) is versioned specifically so this endpoint can enforce that.

---

### Task 1: `Client`, `Workstation`, `Irregularity` models + migration

**Files:**
- Create: `backend/app/db/models/client.py`
- Modify: `backend/app/db/models/__init__.py` (import the three new models so Alembic's
  autogenerate and every other domain's cross-FK resolution sees them)
- Modify: `backend/app/db/models/profile.py` (`MODULES` list — add `"clients"`)
- Create: `backend/alembic/versions/<hash>_add_client_workstation_irregularity.py` (via
  `alembic revision --autogenerate`)
- Test: `backend/app/tests/test_client.py`

**Interfaces:**
- Produces: `Client`, `Workstation`, `Irregularity` ORM classes (table names `clients`,
  `workstations`, `irregularities`), and the tuple constants
  `SUPPORT_PLANS = ("4h", "8h", "12h")`, `OS_KINDS = ("linux", "windows")`,
  `IRREGULARITY_RULE_KEYS = ("disk_space_low", "backup_stale", "unauthorized_remote_tool",
  "critical_service_down", "collection_failed", "agent_unreachable")`,
  `IRREGULARITY_SEVERITIES = ("info", "warning", "critical")`,
  `IRREGULARITY_STATUSES = ("open", "acknowledged", "resolved")` — every later task in this plan
  imports these exact names.

```python
# backend/app/db/models/client.py
"""Client/Workstation/Irregularity domain -- the Nexo monitoring foundation.

A Client is a company Marcelo supports (e.g. Clube de Tiro Gatling). A
Workstation is one machine of theirs running the Nexo Remote Agent,
identified to the ingestion endpoint by a per-device token (never the raw
token stored -- only its SHA-256 hash, same boundary as
Agent.forgerouter_api_key_encrypted / AgentServiceCredential.token_hash).
An Irregularity is one rule violation surfaced from an ingested report; see
docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md sections 2-3
for the full rule table and lifecycle.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

SUPPORT_PLANS = ("4h", "8h", "12h")
OS_KINDS = ("linux", "windows")
IRREGULARITY_RULE_KEYS = (
    "disk_space_low",
    "backup_stale",
    "unauthorized_remote_tool",
    "critical_service_down",
    "collection_failed",
    "agent_unreachable",
)
IRREGULARITY_SEVERITIES = ("info", "warning", "critical")
IRREGULARITY_STATUSES = ("open", "acknowledged", "resolved")


class Client(Base, TimestampMixin):
    __tablename__ = "clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_plan: Mapped[str | None] = mapped_column(String(20), nullable=True)
    headscale_tag: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"support_plan IS NULL OR support_plan IN {SUPPORT_PLANS}",
            name="ck_clients_support_plan",
        ),
    )


class Workstation(Base, TimestampMixin):
    __tablename__ = "workstations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.clients.id", ondelete="CASCADE"), nullable=False
    )
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # SHA-256 hex digest of the raw device token. The raw token is shown to
    # the caller exactly once, at issuance -- never stored, never returned
    # by any read endpoint. See Server.private_key_encrypted's docstring
    # for the sibling "store a durable copy, decrypted, never leak on read"
    # boundary; this one is simpler still because a device token is a
    # bearer secret, not something ForgeHub ever needs to reconstruct.
    device_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    device_token_issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    device_token_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_report_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_agent_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        CheckConstraint(f"os_kind IN {OS_KINDS}", name="ck_workstations_os_kind"),
    )


class Irregularity(Base, TimestampMixin):
    __tablename__ = "irregularities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workstation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.workstations.id", ondelete="CASCADE"), nullable=False
    )
    rule_key: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"rule_key IN {IRREGULARITY_RULE_KEYS}", name="ck_irregularities_rule_key"),
        CheckConstraint(f"severity IN {IRREGULARITY_SEVERITIES}", name="ck_irregularities_severity"),
        CheckConstraint(f"status IN {IRREGULARITY_STATUSES}", name="ck_irregularities_status"),
    )
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_client.py`)

```python
"""Client/Workstation/Irregularity model smoke test -- confirms the tables
exist with the expected columns and constraints, against the real DB."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation


@pytest.mark.asyncio
async def test_create_client_workstation_irregularity():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}", headscale_tag=f"tag:cliente-{uuid.uuid4().hex[:8]}")
        db.add(client)
        await db.flush()

        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.flush()

        irregularity = Irregularity(
            workstation_id=workstation.id,
            rule_key="disk_space_low",
            severity="warning",
            detail="disk / at 92%",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(irregularity)
        await db.commit()

        try:
            fetched = (await db.execute(
                select(Irregularity).where(Irregularity.id == irregularity.id)
            )).scalar_one()
            assert fetched.status == "open"
            assert fetched.rule_key == "disk_space_low"
        finally:
            await db.delete(irregularity)
            await db.delete(workstation)
            await db.delete(client)
            await db.commit()


@pytest.mark.asyncio
async def test_irregularity_rejects_invalid_rule_key():
    from sqlalchemy.exc import IntegrityError

    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.flush()

        db.add(Irregularity(
            workstation_id=workstation.id,
            rule_key="not_a_real_rule",
            severity="warning",
            detail="x",
            detected_at=datetime.now(timezone.utc),
        ))
        with pytest.raises(IntegrityError):
            await db.commit()

        await db.rollback()
        await db.delete(workstation)
        await db.delete(client)
        await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest app/tests/test_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db.models.client'`

- [ ] **Step 3: Create `backend/app/db/models/client.py`** with the exact content above.

- [ ] **Step 4: Wire the new models into `db/models/__init__.py`**

Add the same-style import line the file already uses for every other domain (check the file's
existing pattern — e.g. `from app.db.models.server import Server, ServerService` — and add the
matching line: `from app.db.models.client import Client, Irregularity, Workstation`).

- [ ] **Step 5: Add `"clients"` to `MODULES` in `backend/app/db/models/profile.py`**

```python
MODULES = [
    "product", "projects", "pipeline", "backlog", "tasks", "agents",
    "artifacts", "governance", "forgerouter", "obsidian",
    "foundation", "crons", "deploy", "database", "users", "profiles",
    "clients",
]
```

- [ ] **Step 6: Generate and apply the migration**

Run: `cd backend && alembic revision --autogenerate -m "add client workstation irregularity"`

Inspect the generated file: confirm it creates all three tables with the exact columns/constraints
above and does **not** touch any unrelated table (autogenerate against a live schema can pick up
unrelated drift — if it does, hand-trim the migration to only this task's tables, per this
codebase's own established practice of reviewing autogenerated migrations before applying).

Run: `alembic upgrade head`

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && pytest app/tests/test_client.py -v`
Expected: PASS (both tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/models/client.py backend/app/db/models/__init__.py \
        backend/app/db/models/profile.py backend/alembic/versions/*_add_client_workstation_irregularity.py \
        backend/app/tests/test_client.py
git commit -m "feat(clients): add Client/Workstation/Irregularity domain models"
```

---

### Task 2: `Client` CRUD (schemas + routes)

**Files:**
- Create: `backend/app/api/schemas/client.py`
- Create: `backend/app/api/routes/client.py`
- Modify: `backend/app/main.py` (register the router)
- Test: `backend/app/tests/test_client_routes.py`

**Interfaces:**
- Consumes: `Client` (Task 1).
- Produces: `router` (prefix `/api/v1/clients`) exported from `api/routes/client.py`, mounted in
  `main.py`; Pydantic `ClientCreate`/`ClientUpdate`/`ClientOut` schemas Task 3 and later tasks
  reference when building a `Workstation`'s parent-client response fields.

```python
# backend/app/api/schemas/client.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ClientBase(BaseModel):
    name: str
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    support_plan: str | None = None
    notes: str | None = None


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    support_plan: str | None = None
    notes: str | None = None


class ClientOut(ClientBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    headscale_tag: str | None
    created_at: datetime
    updated_at: datetime
```

```python
# backend/app/api/routes/client.py
"""Client domain -- companies Marcelo supports with Nexo-monitored workstations.

Endpoints:
  GET    /api/v1/clients       -- list all
  POST   /api/v1/clients       -- create
  GET    /api/v1/clients/{id}  -- get one
  PUT    /api/v1/clients/{id}  -- update
  DELETE /api/v1/clients/{id}  -- delete

Headscale tag provisioning (spec section 5) is deliberately NOT part of this
task -- headscale_tag stays nullable and unset here; a later plan wires
POST here to also call the Headscale ACL adapter.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client import ClientCreate, ClientOut, ClientUpdate
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.client import Client
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


@router.get("", response_model=list[ClientOut])
async def list_clients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).order_by(Client.name))
    return result.scalars().all()


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    client = Client(**payload.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return client


@router.put("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    await db.commit()
    await db.refresh(client)
    return client


@router.delete("/{client_id}", status_code=204)
async def delete_client(
    client_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    await db.delete(client)
    await db.commit()
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_client_routes.py`)

```python
"""Client CRUD route tests -- real DB, real ASGI app, no mocking."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.user import User
from app.main import app


async def _admin_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.is_admin.is_(True)).limit(1))
        admin = result.scalar_one_or_none()
        assert admin is not None, "expected at least one admin user to exist for this test"
        return create_access_token({"sub": admin.username})


@pytest.mark.asyncio
async def test_create_get_list_delete_client():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    name = f"Test Client {uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/clients", json={"name": name}, headers=headers)
        assert create_resp.status_code == 201, create_resp.text
        client_id = create_resp.json()["id"]

        try:
            get_resp = await client.get(f"/api/v1/clients/{client_id}")
            assert get_resp.status_code == 200
            assert get_resp.json()["name"] == name

            list_resp = await client.get("/api/v1/clients")
            assert list_resp.status_code == 200
            assert any(c["id"] == client_id for c in list_resp.json())
        finally:
            delete_resp = await client.delete(f"/api/v1/clients/{client_id}", headers=headers)
            assert delete_resp.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest app/tests/test_client_routes.py -v`
Expected: FAIL — `ModuleNotFoundError` (schemas/routes don't exist yet).

- [ ] **Step 3: Create `backend/app/api/schemas/client.py` and `backend/app/api/routes/client.py`**
  with the exact content above.

- [ ] **Step 4: Register the router in `backend/app/main.py`**

Add `from app.api.routes import client as client_routes` alongside the other route imports, and
`app.include_router(client_routes.router)` alongside the other `include_router` calls (match the
existing file's import/registration style exactly — check its current imports section before
editing, since it's a long file with an established grouping).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest app/tests/test_client_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/schemas/client.py backend/app/api/routes/client.py backend/app/main.py \
        backend/app/tests/test_client_routes.py
git commit -m "feat(clients): add Client CRUD routes"
```

---

### Task 3: `Workstation` CRUD + device token issue/revoke

**Files:**
- Modify: `backend/app/api/schemas/client.py` (add Workstation schemas)
- Create: `backend/app/api/routes/workstation.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/tests/test_workstation_routes.py`

**Interfaces:**
- Consumes: `Client`, `Workstation` (Task 1); `get_current_admin` (existing, `core/deps.py`).
- Produces: `router` (prefix `/api/v1/workstations`); a `hash_device_token(raw: str) -> str`
  helper (SHA-256 hex digest, `hashlib.sha256(raw.encode()).hexdigest()`) that Task 4's ingestion
  endpoint imports to verify an incoming `X-Device-Token` header against
  `Workstation.device_token_hash` — define it once here, in `core/security.py` if that file
  already holds comparable hashing helpers (check it first), otherwise as a small module-level
  function in this route file, imported by Task 4.

```python
# additions to backend/app/api/schemas/client.py
class WorkstationCreate(BaseModel):
    client_id: uuid.UUID
    os_kind: str


class WorkstationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    hostname: str | None
    os_kind: str
    device_token_issued_at: datetime
    device_token_revoked_at: datetime | None
    last_report_at: datetime | None
    last_seen_agent_version: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def device_token_active(self) -> bool:
        return self.device_token_revoked_at is None


class WorkstationTokenIssued(BaseModel):
    """Returned exactly once, at issuance -- the only response that ever
    carries the raw token."""
    workstation: WorkstationOut
    device_token: str
```

```python
# backend/app/api/routes/workstation.py
"""Workstation domain -- Nexo-monitored devices, one per Client.

Endpoints:
  GET    /api/v1/workstations                 -- list all (optionally ?client_id=)
  POST   /api/v1/workstations                 -- create + issue device token (shown once)
  GET    /api/v1/workstations/{id}             -- get one
  DELETE /api/v1/workstations/{id}             -- delete
  POST   /api/v1/workstations/{id}/token:reissue -- revoke old token, issue a new one (shown once)
  POST   /api/v1/workstations/{id}/token:revoke  -- revoke without issuing a replacement
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client import (
    WorkstationCreate,
    WorkstationOut,
    WorkstationTokenIssued,
)
from app.core.deps import get_current_admin
from app.db.base import get_db
from app.db.models.client import Client, Workstation
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/workstations", tags=["workstations"])


def _generate_device_token() -> str:
    # "nxw_" prefix (Nexo Workstation) mirrors this codebase's existing
    # "agt_" convention for agent service credentials -- lets the auth
    # layer in a future task tell token kinds apart on sight if ever needed.
    return f"nxw_{secrets.token_urlsafe(32)}"


def hash_device_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.get("", response_model=list[WorkstationOut])
async def list_workstations(
    client_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Workstation)
    if client_id is not None:
        query = query.where(Workstation.client_id == client_id)
    result = await db.execute(query.order_by(Workstation.created_at))
    return result.scalars().all()


@router.post("", response_model=WorkstationTokenIssued, status_code=201)
async def create_workstation(
    payload: WorkstationCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    if not await db.get(Client, payload.client_id):
        raise HTTPException(404, "Client not found")

    raw_token = _generate_device_token()
    workstation = Workstation(
        client_id=payload.client_id,
        os_kind=payload.os_kind,
        device_token_hash=hash_device_token(raw_token),
        device_token_issued_at=datetime.now(timezone.utc),
    )
    db.add(workstation)
    await db.commit()
    await db.refresh(workstation)
    return WorkstationTokenIssued(workstation=workstation, device_token=raw_token)


@router.get("/{workstation_id}", response_model=WorkstationOut)
async def get_workstation(workstation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")
    return workstation


@router.delete("/{workstation_id}", status_code=204)
async def delete_workstation(
    workstation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")
    await db.delete(workstation)
    await db.commit()


@router.post("/{workstation_id}/token:reissue", response_model=WorkstationTokenIssued)
async def reissue_workstation_token(
    workstation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")

    raw_token = _generate_device_token()
    workstation.device_token_hash = hash_device_token(raw_token)
    workstation.device_token_issued_at = datetime.now(timezone.utc)
    workstation.device_token_revoked_at = None
    await db.commit()
    await db.refresh(workstation)
    return WorkstationTokenIssued(workstation=workstation, device_token=raw_token)


@router.post("/{workstation_id}/token:revoke", response_model=WorkstationOut)
async def revoke_workstation_token(
    workstation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    workstation = await db.get(Workstation, workstation_id)
    if not workstation:
        raise HTTPException(404, "Workstation not found")
    workstation.device_token_revoked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(workstation)
    return workstation
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_workstation_routes.py`)

```python
"""Workstation CRUD + token lifecycle route tests -- real DB, no mocking."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes.workstation import hash_device_token
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client
from app.db.models.user import User
from app.main import app


async def _admin_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.is_admin.is_(True)).limit(1))
        admin = result.scalar_one_or_none()
        assert admin is not None
        return create_access_token({"sub": admin.username})


async def _make_client() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.commit()
        await db.refresh(client)
        return client.id


@pytest.mark.asyncio
async def test_create_workstation_issues_token_once_then_reissue_revoke():
    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    client_id = await _make_client()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        create_resp = await http.post(
            "/api/v1/workstations",
            json={"client_id": str(client_id), "os_kind": "linux"},
            headers=headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        body = create_resp.json()
        raw_token = body["device_token"]
        workstation_id = body["workstation"]["id"]
        assert raw_token.startswith("nxw_")

        get_resp = await http.get(f"/api/v1/workstations/{workstation_id}")
        assert get_resp.status_code == 200
        assert "device_token" not in get_resp.json()

        reissue_resp = await http.post(
            f"/api/v1/workstations/{workstation_id}/token:reissue", headers=headers
        )
        assert reissue_resp.status_code == 200
        new_raw_token = reissue_resp.json()["device_token"]
        assert new_raw_token != raw_token
        assert hash_device_token(new_raw_token) != hash_device_token(raw_token)

        revoke_resp = await http.post(
            f"/api/v1/workstations/{workstation_id}/token:revoke", headers=headers
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["device_token_revoked_at"] is not None

        delete_resp = await http.delete(f"/api/v1/workstations/{workstation_id}", headers=headers)
        assert delete_resp.status_code == 204

    async with AsyncSessionLocal() as db:
        client = await db.get(Client, client_id)
        await db.delete(client)
        await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest app/tests/test_workstation_routes.py -v`
Expected: FAIL — module/route not found.

- [ ] **Step 3: Add the schemas to `client.py` and create `workstation.py`** with the exact
  content above.

- [ ] **Step 4: Register the router in `main.py`**

`from app.api.routes import workstation as workstation_routes`, then
`app.include_router(workstation_routes.router)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest app/tests/test_workstation_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/schemas/client.py backend/app/api/routes/workstation.py backend/app/main.py \
        backend/app/tests/test_workstation_routes.py
git commit -m "feat(clients): add Workstation CRUD and device token lifecycle"
```

---

### Task 4: Ingestion endpoint — rule engine + `Irregularity`/`Notification` creation

**Files:**
- Create: `backend/app/api/schemas/agent_report.py`
- Create: `backend/app/core/irregularity_rules.py`
- Create: `backend/app/api/routes/agent_report.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/tests/test_agent_report_ingestion.py`

**Interfaces:**
- Consumes: `Workstation` (Task 1), `hash_device_token` (Task 3), `Notification` (existing,
  `db/models/notification.py`).
- Produces: `evaluate_report(report: AgentReportIn) -> list[RuleFinding]` (pure function, no DB
  access — testable standalone) and the mounted `POST /api/v1/agent-reports` route.

```python
# backend/app/api/schemas/agent_report.py
"""Mirrors the Nexo Remote Agent's `collector.Report` JSON shape exactly
(internal/collector/report.go in /root/project/nexo, post the final-review
fix wave: DiskUsage is a list, CollectionErrors/Hostname/OS/AgentVersion/
SchemaVersion all exist). Field names match Go's JSON tags, not Go's
exported field names."""
from pydantic import BaseModel


class ServiceStatusIn(BaseModel):
    name: str
    status: str  # "running" | "stopped" | "unknown"


class SoftwareMatchIn(BaseModel):
    name: str


class DiskUsageIn(BaseModel):
    path: str
    used_percent: float


class SystemMetricsIn(BaseModel):
    cpu_percent: float
    mem_percent: float
    disk_usage: list[DiskUsageIn] = []


class BackupStatusIn(BaseModel):
    path: str
    newest_file: str
    newest_mtime: str
    stale: bool


class AgentReportIn(BaseModel):
    collected_at: str
    system: SystemMetricsIn
    listening_ports: list[int] = []
    services: list[ServiceStatusIn] = []
    unauthorized_software: list[SoftwareMatchIn] = []
    backup: BackupStatusIn
    collection_errors: list[str] = []
    hostname: str = ""
    os: str = ""
    agent_version: str = ""
    schema_version: int
```

```python
# backend/app/core/irregularity_rules.py
"""Pure rule evaluation over an ingested Nexo Remote Agent report -- no DB
access here, so this is unit-testable without the ingestion route or a
database at all. See docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md
section 3.2 for the rule table this implements."""
from dataclasses import dataclass

from app.api.schemas.agent_report import AgentReportIn

SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RuleFinding:
    rule_key: str
    severity: str
    detail: str


def evaluate_report(report: AgentReportIn) -> list[RuleFinding]:
    findings: list[RuleFinding] = []

    for disk in report.system.disk_usage:
        if disk.used_percent > 90:
            findings.append(RuleFinding(
                rule_key="disk_space_low",
                severity="warning",
                detail=f"{disk.path} at {disk.used_percent:.1f}%",
            ))

    if report.backup.stale:
        findings.append(RuleFinding(
            rule_key="backup_stale",
            severity="warning",
            detail=f"newest backup file {report.backup.newest_file or '(none found)'} "
                    f"at {report.backup.newest_mtime}",
        ))

    if report.unauthorized_software:
        names = ", ".join(m.name for m in report.unauthorized_software)
        findings.append(RuleFinding(
            rule_key="unauthorized_remote_tool",
            severity="critical",
            detail=f"unauthorized software detected: {names}",
        ))

    for service in report.services:
        if service.status == "stopped":
            findings.append(RuleFinding(
                rule_key="critical_service_down",
                severity="critical",
                detail=f"service {service.name} is stopped",
            ))

    if report.collection_errors:
        findings.append(RuleFinding(
            rule_key="collection_failed",
            severity="warning",
            detail="; ".join(report.collection_errors),
        ))

    return findings
```

```python
# backend/app/api/routes/agent_report.py
"""Nexo Remote Agent ingestion endpoint.

POST /api/v1/agent-reports -- authenticated by the X-Device-Token header
(hashed and matched against Workstation.device_token_hash; a revoked or
unknown token is 401). Never reachable by a User/Agent JWT/agt_ principal
-- this is a separate, narrower auth boundary than get_actor_principal,
scoped to exactly one Workstation.
"""
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.api.schemas.agent_report import AgentReportIn
from app.core.irregularity_rules import SUPPORTED_SCHEMA_VERSION, evaluate_report
from app.db.base import AsyncSessionLocal
from app.db.models.client import Irregularity, Workstation
from app.db.models.notification import Notification

router = APIRouter(prefix="/api/v1/agent-reports", tags=["agent-reports"])


@router.post("", status_code=202)
async def ingest_agent_report(
    report: AgentReportIn,
    x_device_token: str | None = Header(default=None),
):
    if not x_device_token:
        raise HTTPException(401, "X-Device-Token header required")
    if report.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise HTTPException(
            400, f"unsupported schema_version {report.schema_version}, expected {SUPPORTED_SCHEMA_VERSION}"
        )

    token_hash = hashlib.sha256(x_device_token.encode()).hexdigest()

    async with AsyncSessionLocal() as db:
        workstation = (await db.execute(
            select(Workstation).where(Workstation.device_token_hash == token_hash)
        )).scalar_one_or_none()
        if workstation is None or workstation.device_token_revoked_at is not None:
            raise HTTPException(401, "invalid or revoked device token")

        workstation.last_report_at = datetime.now(timezone.utc)
        if report.hostname:
            workstation.hostname = report.hostname
        if report.agent_version:
            workstation.last_seen_agent_version = report.agent_version

        findings = evaluate_report(report)
        for finding in findings:
            existing_open = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation.id,
                    Irregularity.rule_key == finding.rule_key,
                    Irregularity.status == "open",
                )
            )).scalar_one_or_none()
            if existing_open is not None:
                continue

            irregularity = Irregularity(
                workstation_id=workstation.id,
                rule_key=finding.rule_key,
                severity=finding.severity,
                detail=finding.detail,
                detected_at=datetime.now(timezone.utc),
            )
            db.add(irregularity)
            await db.flush()

            db.add(Notification(
                source="system",
                severity=finding.severity if finding.severity != "critical" else "error",
                title=f"Irregularidade: {finding.rule_key} ({workstation.hostname or workstation.id})",
                message=finding.detail,
                event_key=f"irregularity:{irregularity.id}",
                occurred_at=datetime.now(timezone.utc),
            ))

        await db.commit()

    return {"accepted": True, "findings": len(findings)}
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_agent_report_ingestion.py`)

```python
"""Ingestion endpoint tests -- real DB, no mocking. Covers: unknown token
rejected, valid token + clean report accepted with no findings, a
disk-space-low report creates exactly one open Irregularity + Notification,
re-ingesting the same violation does not duplicate the Irregularity, and a
schema_version mismatch is rejected."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation
from app.main import app

CLEAN_REPORT = {
    "collected_at": "2026-09-06T00:00:00Z",
    "system": {"cpu_percent": 10.0, "mem_percent": 20.0, "disk_usage": [{"path": "/", "used_percent": 30.0}]},
    "listening_ports": [],
    "services": [],
    "unauthorized_software": [],
    "backup": {"path": "/backup", "newest_file": "/backup/x.tar", "newest_mtime": "2026-09-05T00:00:00Z", "stale": False},
    "collection_errors": [],
    "hostname": "test-host",
    "os": "linux",
    "agent_version": "dev",
    "schema_version": 1,
}


async def _make_workstation() -> tuple[uuid.UUID, uuid.UUID, str]:
    from app.api.routes.workstation import hash_device_token

    raw_token = f"nxw_test_{uuid.uuid4().hex}"
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=hash_device_token(raw_token),
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.commit()
        return client.id, workstation.id, raw_token


async def _cleanup(client_id: uuid.UUID):
    async with AsyncSessionLocal() as db:
        client = await db.get(Client, client_id)
        if client:
            await db.delete(client)
            await db.commit()


@pytest.mark.asyncio
async def test_ingest_rejects_unknown_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        resp = await http.post(
            "/api/v1/agent-reports", json=CLEAN_REPORT, headers={"X-Device-Token": "nxw_bogus"}
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_clean_report_creates_no_irregularity():
    client_id, workstation_id, token = await _make_workstation()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.post(
                "/api/v1/agent-reports", json=CLEAN_REPORT, headers={"X-Device-Token": token}
            )
            assert resp.status_code == 202, resp.text
            assert resp.json()["findings"] == 0

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(Irregularity.workstation_id == workstation_id)
            )).scalars().all()
            assert rows == []
    finally:
        await _cleanup(client_id)


@pytest.mark.asyncio
async def test_ingest_disk_space_low_creates_one_irregularity_and_dedupes():
    client_id, workstation_id, token = await _make_workstation()
    dirty_report = {**CLEAN_REPORT, "system": {**CLEAN_REPORT["system"], "disk_usage": [{"path": "/", "used_percent": 95.0}]}}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            first = await http.post("/api/v1/agent-reports", json=dirty_report, headers={"X-Device-Token": token})
            assert first.status_code == 202
            assert first.json()["findings"] == 1

            second = await http.post("/api/v1/agent-reports", json=dirty_report, headers={"X-Device-Token": token})
            assert second.status_code == 202
            # dedupe: still reported as "0 new findings created" is NOT what
            # this asserts -- the endpoint reports raw rule matches, not rows
            # created. What matters is exactly one open Irregularity exists.

        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "disk_space_low",
                )
            )).scalars().all()
            assert len(rows) == 1
            assert rows[0].status == "open"
    finally:
        await _cleanup(client_id)


@pytest.mark.asyncio
async def test_ingest_rejects_schema_version_mismatch():
    client_id, _workstation_id, token = await _make_workstation()
    bad_report = {**CLEAN_REPORT, "schema_version": 999}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.post("/api/v1/agent-reports", json=bad_report, headers={"X-Device-Token": token})
            assert resp.status_code == 400
    finally:
        await _cleanup(client_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest app/tests/test_agent_report_ingestion.py -v`
Expected: FAIL — module/route not found.

- [ ] **Step 3: Create the three new files** with the exact content above.

- [ ] **Step 4: Register the router in `main.py`**

`from app.api.routes import agent_report as agent_report_routes`, then
`app.include_router(agent_report_routes.router)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest app/tests/test_agent_report_ingestion.py -v`
Expected: PASS (all four cases)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/schemas/agent_report.py backend/app/core/irregularity_rules.py \
        backend/app/api/routes/agent_report.py backend/app/main.py \
        backend/app/tests/test_agent_report_ingestion.py
git commit -m "feat(clients): add Nexo agent report ingestion endpoint and rule engine"
```

---

### Task 5: `agent_unreachable` staleness sweep

**Files:**
- Modify: `backend/app/core/irregularity_rules.py` (add a threshold constant)
- Create: `backend/app/core/workstation_staleness.py`
- Modify: `backend/app/main.py` (register the poll loop, same pattern as `demand.py`'s existing
  loops)
- Test: `backend/app/tests/test_workstation_staleness.py`

**Interfaces:**
- Consumes: `Workstation`, `Irregularity` (Task 1), `Notification` (existing).
- Produces: `run_workstation_staleness_sweep(db) -> int` (returns count of new irregularities
  raised — testable directly against a real DB without needing the poll loop itself running).

```python
# backend/app/core/workstation_staleness.py
"""Detects a Workstation that stopped reporting -- an agent cannot report
its own absence, so this has to be a server-side sweep. See
docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md section 3.3."""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.client import Irregularity, Workstation
from app.db.models.notification import Notification

logger = logging.getLogger(__name__)

# Nexo's Report does not currently send its own report_interval, so a fixed
# conservative threshold is used until that's added to the agent payload
# (noted as a follow-up in the spec). 15 minutes covers the documented
# default report_interval (5m) at 3x with margin.
STALENESS_THRESHOLD = timedelta(minutes=15)


async def run_workstation_staleness_sweep(db: AsyncSession) -> int:
    cutoff = datetime.now(timezone.utc) - STALENESS_THRESHOLD
    stale_workstations = (await db.execute(
        select(Workstation).where(
            Workstation.device_token_revoked_at.is_(None),
            Workstation.last_report_at.is_not(None),
            Workstation.last_report_at < cutoff,
        )
    )).scalars().all()

    raised = 0
    for workstation in stale_workstations:
        existing_open = (await db.execute(
            select(Irregularity).where(
                Irregularity.workstation_id == workstation.id,
                Irregularity.rule_key == "agent_unreachable",
                Irregularity.status == "open",
            )
        )).scalar_one_or_none()
        if existing_open is not None:
            continue

        irregularity = Irregularity(
            workstation_id=workstation.id,
            rule_key="agent_unreachable",
            severity="critical",
            detail=f"no report since {workstation.last_report_at.isoformat()}",
            detected_at=datetime.now(timezone.utc),
        )
        db.add(irregularity)
        await db.flush()

        db.add(Notification(
            source="system",
            severity="error",
            title=f"Agente inacessível: {workstation.hostname or workstation.id}",
            message=irregularity.detail,
            event_key=f"irregularity:{irregularity.id}",
            occurred_at=datetime.now(timezone.utc),
        ))
        raised += 1

    await db.commit()
    return raised
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_workstation_staleness.py`)

```python
"""Staleness sweep tests -- real DB, no mocking."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.workstation_staleness import run_workstation_staleness_sweep
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation


@pytest.mark.asyncio
async def test_stale_workstation_raises_one_irregularity_and_dedupes():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
            last_report_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        db.add(workstation)
        await db.commit()
        workstation_id, client_id_ = workstation.id, client.id

    try:
        async with AsyncSessionLocal() as db:
            raised = await run_workstation_staleness_sweep(db)
            assert raised >= 1

        async with AsyncSessionLocal() as db:
            raised_again = await run_workstation_staleness_sweep(db)
            # already-open irregularity for this workstation -- no duplicate
            rows = (await db.execute(
                select(Irregularity).where(
                    Irregularity.workstation_id == workstation_id,
                    Irregularity.rule_key == "agent_unreachable",
                )
            )).scalars().all()
            assert len(rows) == 1
    finally:
        async with AsyncSessionLocal() as db:
            client = await db.get(Client, client_id_)
            await db.delete(client)
            await db.commit()


@pytest.mark.asyncio
async def test_fresh_workstation_raises_nothing():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id,
            os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
            last_report_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.commit()
        client_id = client.id

    try:
        async with AsyncSessionLocal() as db:
            rows_before = (await db.execute(select(Irregularity))).scalars().all()
            await run_workstation_staleness_sweep(db)
            rows_after = (await db.execute(select(Irregularity))).scalars().all()
            assert len(rows_after) == len(rows_before)
    finally:
        async with AsyncSessionLocal() as db:
            client = await db.get(Client, client_id)
            await db.delete(client)
            await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest app/tests/test_workstation_staleness.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `backend/app/core/workstation_staleness.py`** with the exact content above.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest app/tests/test_workstation_staleness.py -v`
Expected: PASS (both cases)

- [ ] **Step 5: Register the poll loop in `main.py`**

Find `demand.py`'s existing `_dispatch_completion_poll_loop`/`_incubation_maturation_poll_loop`
registration in `main.py` (an `asyncio.create_task` in the app's startup/lifespan handler) and add
a sibling loop calling `run_workstation_staleness_sweep` every 5 minutes, following that exact
pattern (its own `try/except` per iteration so one failure doesn't kill the loop, its own
`asyncio.sleep`, registered as its own task so it fails independently of the other loops).

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/workstation_staleness.py backend/app/main.py \
        backend/app/tests/test_workstation_staleness.py
git commit -m "feat(clients): add agent_unreachable staleness sweep"
```

---

### Task 6: `Irregularity` list + resolve routes

**Files:**
- Modify: `backend/app/api/schemas/client.py` (add Irregularity schemas)
- Create: `backend/app/api/routes/irregularity.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/tests/test_irregularity_routes.py`

**Interfaces:**
- Consumes: `Irregularity`, `Workstation`, `Client` (Task 1); `get_current_user`/`get_current_admin`
  (existing).
- Produces: `router` (prefix `/api/v1/irregularities`) — the endpoint Task 9's frontend hook calls.

```python
# additions to backend/app/api/schemas/client.py
class IrregularityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workstation_id: uuid.UUID
    rule_key: str
    severity: str
    detail: str
    status: str
    detected_at: datetime
    resolved_at: datetime | None
    resolved_by_user_id: uuid.UUID | None


class IrregularityResolve(BaseModel):
    status: str  # "acknowledged" | "resolved"
```

```python
# backend/app/api/routes/irregularity.py
"""Irregularities screen backend.

Endpoints:
  GET   /api/v1/irregularities                    -- list, filterable
  PATCH /api/v1/irregularities/{id}                -- change status (ack/resolve)
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.client import IrregularityOut, IrregularityResolve
from app.core.deps import get_current_user
from app.db.base import get_db
from app.db.models.client import IRREGULARITY_STATUSES, Irregularity
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/irregularities", tags=["irregularities"])


@router.get("", response_model=list[IrregularityOut])
async def list_irregularities(
    status_filter: str | None = None,
    severity: str | None = None,
    workstation_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Irregularity)
    if status_filter is not None:
        query = query.where(Irregularity.status == status_filter)
    if severity is not None:
        query = query.where(Irregularity.severity == severity)
    if workstation_id is not None:
        query = query.where(Irregularity.workstation_id == workstation_id)
    result = await db.execute(query.order_by(Irregularity.detected_at.desc()))
    return result.scalars().all()


@router.patch("/{irregularity_id}", response_model=IrregularityOut)
async def update_irregularity_status(
    irregularity_id: uuid.UUID,
    payload: IrregularityResolve,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.status not in IRREGULARITY_STATUSES:
        raise HTTPException(400, f"status must be one of {IRREGULARITY_STATUSES}")

    irregularity = await db.get(Irregularity, irregularity_id)
    if not irregularity:
        raise HTTPException(404, "Irregularity not found")

    irregularity.status = payload.status
    if payload.status == "resolved":
        irregularity.resolved_at = datetime.now(timezone.utc)
        irregularity.resolved_by_user_id = current_user.id
    await db.commit()
    await db.refresh(irregularity)
    return irregularity
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_irregularity_routes.py`)

```python
"""Irregularity list/resolve route tests -- real DB, no mocking."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Irregularity, Workstation
from app.db.models.user import User
from app.main import app


async def _user_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        assert user is not None
        return create_access_token({"sub": user.username})


@pytest.mark.asyncio
async def test_list_and_resolve_irregularity():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        workstation = Workstation(
            client_id=client.id, os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(workstation)
        await db.flush()
        irregularity = Irregularity(
            workstation_id=workstation.id, rule_key="backup_stale", severity="warning",
            detail="test", detected_at=datetime.now(timezone.utc),
        )
        db.add(irregularity)
        await db.commit()
        irregularity_id, client_id = irregularity.id, client.id

    try:
        token = await _user_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            list_resp = await http.get("/api/v1/irregularities", params={"status_filter": "open"})
            assert list_resp.status_code == 200
            assert any(i["id"] == str(irregularity_id) for i in list_resp.json())

            resolve_resp = await http.patch(
                f"/api/v1/irregularities/{irregularity_id}",
                json={"status": "resolved"},
                headers=headers,
            )
            assert resolve_resp.status_code == 200
            body = resolve_resp.json()
            assert body["status"] == "resolved"
            assert body["resolved_at"] is not None
            assert body["resolved_by_user_id"] is not None
    finally:
        async with AsyncSessionLocal() as db:
            client = await db.get(Client, client_id)
            await db.delete(client)
            await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest app/tests/test_irregularity_routes.py -v`
Expected: FAIL — module/route not found.

- [ ] **Step 3: Add the schemas and create `irregularity.py`** with the exact content above.

- [ ] **Step 4: Register the router in `main.py`**

`from app.api.routes import irregularity as irregularity_routes`, then
`app.include_router(irregularity_routes.router)`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest app/tests/test_irregularity_routes.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/schemas/client.py backend/app/api/routes/irregularity.py backend/app/main.py \
        backend/app/tests/test_irregularity_routes.py
git commit -m "feat(clients): add Irregularity list and resolve routes"
```

---

### Task 7: Frontend hooks — `useClients`, `useWorkstations`, `useIrregularities`

**Files:**
- Create: `frontend/src/hooks/useClients.ts`
- Create: `frontend/src/hooks/useWorkstations.ts`
- Create: `frontend/src/hooks/useIrregularities.ts`
- Test: `frontend/src/hooks/useIrregularities.test.ts`

**Interfaces:**
- Consumes: `apiClient` (existing, `lib/api.ts`).
- Produces: `Client`/`Workstation`/`Irregularity` TypeScript interfaces and
  `useClients`/`useCreateClient`/`useWorkstations`/`useCreateWorkstation`/`useIrregularities`/
  `useUpdateIrregularityStatus` hooks — Task 8's pages import these exact names.

Follow `frontend/src/hooks/useServers.ts`'s exact structure (read it again as the direct template
before writing this file): a TypeScript interface per response shape, a `useQuery` hook per list/
get, a `useMutation` hook per write with `queryClient.invalidateQueries` on success.

```typescript
// frontend/src/hooks/useIrregularities.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface Irregularity {
  id: string;
  workstation_id: string;
  rule_key: string;
  severity: "info" | "warning" | "critical";
  detail: string;
  status: "open" | "acknowledged" | "resolved";
  detected_at: string;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
}

export interface IrregularityFilters {
  status_filter?: string;
  severity?: string;
  workstation_id?: string;
}

export function useIrregularities(filters: IrregularityFilters = {}) {
  return useQuery({
    queryKey: ["irregularities", filters],
    queryFn: () => apiClient.get<Irregularity[]>("/api/v1/irregularities", { params: filters }),
  });
}

export function useUpdateIrregularityStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "acknowledged" | "resolved" }) =>
      apiClient.patch<Irregularity>(`/api/v1/irregularities/${id}`, { body: { status } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["irregularities"] });
    },
  });
}
```

- [ ] **Step 1: Write `useClients.ts` and `useWorkstations.ts`**, mirroring `useServers.ts`'s
  exact shape for `Client`/`ClientCreate`/`useClients`/`useCreateClient`/`useDeleteClient` and
  `Workstation`/`WorkstationCreate`/`useWorkstations`/`useCreateWorkstation`/
  `useReissueWorkstationToken`/`useRevokeWorkstationToken` respectively — matching this plan's
  backend schemas (Tasks 2-3) field for field.

- [ ] **Step 2: Write `useIrregularities.ts`** with the exact content above.

- [ ] **Step 3: Write a test verifying the query key shape** (`useIrregularities.test.ts`) —
  check an existing `*.test.ts` file under `frontend/src/hooks/` for this codebase's actual test
  setup (e.g. `useServers.test.ts` if it exists, else the nearest hook test) and mirror its
  `renderHook`/`QueryClientProvider` wrapper exactly; assert `useIrregularities({status_filter:
  "open"})`'s `queryKey` includes `{status_filter: "open"}` so a filter change actually triggers a
  refetch (TanStack Query keys this off deep-equality of the key array).

- [ ] **Step 4: Run the frontend test suite**

Run: `cd frontend && npm test -- useIrregularities`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useClients.ts frontend/src/hooks/useWorkstations.ts \
        frontend/src/hooks/useIrregularities.ts frontend/src/hooks/useIrregularities.test.ts
git commit -m "feat(clients): add Clients/Workstations/Irregularities frontend hooks"
```

---

### Task 8: Irregularities screen + sidebar entry

**Files:**
- Create: `frontend/src/pages/irregularities/index.tsx`
- Modify: `frontend/src/components/layout/navSections.ts` (add the nav entry)
- Modify: `frontend/src/App.tsx` or the router config file (wherever routes are registered — check
  its current structure before editing)

**Interfaces:**
- Consumes: `useIrregularities`, `useUpdateIrregularityStatus` (Task 7).

- [ ] **Step 1: Build the page**, following `pages/servers/index.tsx`'s established structure
  (read it again as the direct template): a filter bar (status/severity `<Select>`s, matching the
  shadcn/ui `Select` component already used elsewhere), a table/list of `Irregularity` rows each
  showing `detail`/`severity` (as a `Badge`, colored by severity — critical=destructive,
  warning=default, info=secondary, matching `Badge`'s existing variant prop usage in this
  codebase) /`detected_at`, and a "Marcar como tratada" button per row wrapped in the existing
  `ConfirmDialog` component (`components/ui/confirm-dialog.tsx`) with `disabled={mutation.isPending}`
  + a `Loader2` spinner while pending — per `CLAUDE.md`'s documented CRUD UX convention (not a new
  pattern to invent).

- [ ] **Step 2: Register the route** in whichever file defines the React Router routes (find it
  by grepping for an existing route like `path="/servers"` before adding
  `path="/irregularities"` pointing at this new page).

- [ ] **Step 3: Add the nav entry** to `navSections.ts`, in whichever existing section is closest
  in kind (likely alongside "Servers"/infra-monitoring entries — check the file's current section
  groupings per its own established semantic-grouping rule before deciding, per `CLAUDE.md`'s
  note that a new entry not clearly fitting an existing section is a signal to add a section, not
  force it into "misc").

- [ ] **Step 4: Manual verification** — per this project's `run` skill / `CLAUDE.md`'s testing
  guidance, start the dev servers (`./dev.sh`) and open `/irregularities` in a browser; confirm
  the empty state renders without error (no irregularities exist yet at this point in the plan),
  then manually insert one `Irregularity` row via the `/database` admin screen or a quick
  `psql`/Python shell insert, reload, and confirm it appears and "Marcar como tratada" works
  end-to-end against the real backend.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/irregularities/index.tsx frontend/src/components/layout/navSections.ts \
        <the route registration file>
git commit -m "feat(clients): add Irregularities screen"
```

---

## Self-Review Notes

- **Spec coverage:** §2 (Client/Workstation/Irregularity) → Task 1; §3 (ingestion, rules,
  `agent_unreachable`) → Tasks 4-5; §4 (Irregularities screen) → Tasks 7-8. §5 (Nexo network
  administration), §6 (installer/download), §7 (report generation) are explicitly out of scope
  for this plan, per the spec's own multi-subsystem note — separate follow-up plans.
- **Placeholder scan:** every step contains complete code or a precisely-scoped manual/verification
  instruction; no bare "add error handling"/"write tests for the above" left unexpanded.
- **Type consistency:** `Client`/`Workstation`/`Irregularity` (Task 1) are the exact ORM types used
  unchanged through Tasks 2-6; `hash_device_token` (Task 3) is the exact function Task 4's
  ingestion route imports; `RuleFinding`/`evaluate_report` (Task 4) signatures match how Task 4's
  route calls them; the frontend `Irregularity` interface (Task 7) field-for-field matches
  `IrregularityOut` (Task 6).
