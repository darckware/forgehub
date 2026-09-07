# Nexo Network Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ForgeHub becomes the single control plane for Nexo's Headscale network isolation: every
`Client` gets its own overlay tag (default-deny between clients), and an admin can selectively
grant/revoke direct communication between two `Workstation`s of the *same* client, auditable and
reversible, with ForgeHub's database as the single source of truth the live Headscale policy is
always re-derived from.

**Architecture:** A new `core/headscale_client.py` module is the only thing that ever talks to
Headscale — entirely through the host-bridge's existing `/v1/exec` (shell out to the `headscale`
CLI) and `/v1/fs/write` (write the rendered policy file), the same pattern `system_control.py`
already uses for git/backup operations this backend container can't reach directly. Every
tag-provisioning or peer-grant change triggers a **full re-render of the entire Headscale ACL
policy from the current database state** and pushes it in one shot (`headscale policy set --file
...`) — never an incremental patch — so the database and the live policy can never structurally
drift apart. A new `WorkstationPeerGrant` table records every grant/revoke (never deleted, only
`revoked_at`-stamped) and every change is written to the existing `AuditEvent` audit trail. The
frontend gets a minimal Clients list + detail page (neither existed before this plan — Plan 1 built
only the backend CRUD) with a pairwise matrix panel for the peer-grant toggles.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (async) + asyncpg, Alembic, pytest + httpx
(against the real `company_postgres` DB; host-bridge calls faked via `monkeypatch.setattr(module.httpx,
"AsyncClient", FakeBridgeClient)`, the established pattern in `test_system_control.py` — no live
Headscale is reachable in this environment, and none should be called from a test). Frontend:
React 18 + Vite + TypeScript, TanStack Query, shadcn/ui.

**Spec:** `docs/architecture/NEXO_CLIENT_MONITORING_AND_NETWORK_ADMIN.md` §5 (this plan implements
that section only — §6 installer/download area and §7 report generation remain separate,
not-yet-started plans per that spec's own scope split).

## Global Constraints

- Headscale is reached **only** through the host-bridge (`settings.CHAT_BRIDGE_URL` +
  `X-Bridge-Token: settings.CHAT_BRIDGE_TOKEN`), via `POST /v1/exec` (`{"command": "..."}` →
  `{"stdout", "stderr", "exit_code"}`) and `PUT /v1/fs/write` (`{"path", "content"}`) — never a
  direct network call to Headscale itself.
- Every policy-affecting change (new `Client` tag, new/revoked `WorkstationPeerGrant`) triggers a
  **full re-render of the whole ACL policy from the database**, never an incremental patch to the
  live file.
- `WorkstationPeerGrant` rows are **never deleted** — revoking sets `revoked_at`, preserving the
  audit trail of who granted/revoked and when.
- A peer grant spanning two different `Client`s is rejected with 400 — this is the one invariant
  the whole feature exists to enforce, checked at the route layer before any write.
- Every grant/revoke writes an `AuditEvent` (`entity_type="workstation_peer_grant"`).
- Client tags follow the exact format `tag:cliente-<slug>`, where `<slug>` is the client's name,
  lowercased, non-alphanumeric runs collapsed to a single `-`, stripped of leading/trailing `-`.

---

### Task 1: `WorkstationPeerGrant` model, migration, and settings

**Files:**
- Modify: `backend/app/db/models/client.py` (add `WorkstationPeerGrant`)
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/core/config.py` (add `HEADSCALE_ACL_POLICY_PATH` setting)
- Create: `backend/alembic/versions/<hash>_add_workstation_peer_grant.py`
- Test: `backend/app/tests/test_workstation_peer_grant.py`

**Interfaces:**
- Produces: `WorkstationPeerGrant` ORM class (table `workstation_peer_grants`) — Task 4's routes
  import this directly. `settings.HEADSCALE_ACL_POLICY_PATH: str` — Task 2's `push_policy` reads
  this.

```python
# addition to backend/app/db/models/client.py
class WorkstationPeerGrant(Base, TimestampMixin):
    """An explicit, auditable permission for two Workstations of the SAME
    Client to talk directly over the Headscale overlay -- default is no
    lateral traffic at all between any two Workstations, even of the same
    client; this is the one mechanism that opens a specific pair. Never
    deleted -- revoking sets revoked_at, preserving who granted/revoked and
    when. Canonical pair ordering (workstation_a_id is always the
    lexicographically-smaller UUID) is enforced at the route layer, not
    here, so (A,B) and (B,A) never both exist as separate rows."""
    __tablename__ = "workstation_peer_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workstation_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.workstations.id", ondelete="CASCADE"), nullable=False
    )
    workstation_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.workstations.id", ondelete="CASCADE"), nullable=False
    )
    granted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("company.users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("workstation_a_id", "workstation_b_id", name="uq_workstation_peer_grants_pair"),
    )
```

Add `UniqueConstraint` to the existing `sqlalchemy` import line at the top of `client.py` if not
already imported (check the file's current import line first).

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_workstation_peer_grant.py`)

```python
"""WorkstationPeerGrant model smoke test -- confirms the table exists with
the expected columns and constraint, against the real DB."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation, WorkstationPeerGrant


@pytest.mark.asyncio
async def test_create_and_revoke_peer_grant():
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        ws_a = Workstation(
            client_id=client.id, os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        ws_b = Workstation(
            client_id=client.id, os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(ws_a)
        db.add(ws_b)
        await db.flush()

        grant = WorkstationPeerGrant(
            workstation_a_id=ws_a.id,
            workstation_b_id=ws_b.id,
            granted_at=datetime.now(timezone.utc),
        )
        db.add(grant)
        await db.commit()

        try:
            fetched = (await db.execute(
                select(WorkstationPeerGrant).where(WorkstationPeerGrant.id == grant.id)
            )).scalar_one()
            assert fetched.revoked_at is None

            fetched.revoked_at = datetime.now(timezone.utc)
            await db.commit()

            revoked = (await db.execute(
                select(WorkstationPeerGrant).where(WorkstationPeerGrant.id == grant.id)
            )).scalar_one()
            assert revoked.revoked_at is not None
        finally:
            await db.delete(grant)
            await db.delete(ws_a)
            await db.delete(ws_b)
            await db.delete(client)
            await db.commit()


@pytest.mark.asyncio
async def test_duplicate_pair_rejected_by_unique_constraint():
    from sqlalchemy.exc import IntegrityError

    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        ws_a = Workstation(
            client_id=client.id, os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        ws_b = Workstation(
            client_id=client.id, os_kind="linux",
            device_token_hash=uuid.uuid4().hex,
            device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(ws_a)
        db.add(ws_b)
        await db.flush()

        db.add(WorkstationPeerGrant(
            workstation_a_id=ws_a.id, workstation_b_id=ws_b.id,
            granted_at=datetime.now(timezone.utc),
        ))
        await db.commit()

        db.add(WorkstationPeerGrant(
            workstation_a_id=ws_a.id, workstation_b_id=ws_b.id,
            granted_at=datetime.now(timezone.utc),
        ))
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        await db.execute(select(Workstation))  # keep session usable after rollback
        from sqlalchemy import delete
        await db.execute(delete(WorkstationPeerGrant).where(
            WorkstationPeerGrant.workstation_a_id == ws_a.id
        ))
        await db.delete(ws_a)
        await db.delete(ws_b)
        await db.delete(client)
        await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_workstation_peer_grant.py -v`
Expected: FAIL — `ImportError: cannot import name 'WorkstationPeerGrant'`

- [ ] **Step 3: Add `WorkstationPeerGrant` to `client.py`** with the exact content above. Confirm
  `UniqueConstraint` is imported (add it to the existing `from sqlalchemy import ...` line if not).

- [ ] **Step 4: Wire it into `db/models/__init__.py`**

Find the existing import line for this domain (`from app.db.models.client import Client,
Irregularity, Workstation`) and add `WorkstationPeerGrant` to it.

- [ ] **Step 5: Add the new setting to `backend/app/core/config.py`**

Find `BACKUP_ROOT` (or a similarly-scoped host-path setting) in the `Settings` class and add a
sibling field near it:

```python
    # Host filesystem path (via the host-bridge) where Headscale reads its
    # file-mode ACL policy from -- see core/headscale_client.py. Matches
    # infra/headscale/config.prod.yaml.example's `policy.path` in the Nexo
    # repo; overridable here since that path is an operational default, not
    # a credential.
    HEADSCALE_ACL_POLICY_PATH: str = "/etc/headscale/acl-policy.hujson"
```

- [ ] **Step 6: Generate and apply the migration**

Run: `cd backend && alembic revision --autogenerate -m "add workstation peer grant"`

Inspect the generated file: confirm it creates only `workstation_peer_grants` with the exact
columns/constraint above. Hand-trim if autogenerate captured unrelated drift.

Run: `alembic upgrade head`

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_workstation_peer_grant.py -v`
Expected: PASS (both tests)

- [ ] **Step 8: Commit**

```bash
git add backend/app/db/models/client.py backend/app/db/models/__init__.py \
        backend/app/core/config.py \
        backend/alembic/versions/*_add_workstation_peer_grant.py \
        backend/app/tests/test_workstation_peer_grant.py
git commit -m "feat(clients): add WorkstationPeerGrant model and Headscale policy path setting"
```

---

### Task 2: `core/headscale_client.py` — policy rendering + host-bridge adapter

**Files:**
- Create: `backend/app/core/headscale_client.py`
- Test: `backend/app/tests/test_headscale_client.py`

**Interfaces:**
- Consumes: `settings.CHAT_BRIDGE_URL`/`CHAT_BRIDGE_TOKEN`/`HEADSCALE_ACL_POLICY_PATH` (existing +
  Task 1); `Client`, `Workstation`, `WorkstationPeerGrant` (Task 1).
- Produces: `slugify_client_name(name: str) -> str`, `render_policy(client_tags: list[str],
  peer_pairs: list[PeerPairIPs]) -> str`, `async def list_node_ips() -> dict[str, str]` (hostname
  → overlay IP), `async def rebuild_and_push_policy(db: AsyncSession) -> None` — Task 3 (client
  creation) and Task 4 (grant create/revoke) both call `rebuild_and_push_policy` as their one
  integration point; nothing else in this plan calls `render_policy`/`list_node_ips`/`push_policy`
  directly.

```python
# backend/app/core/headscale_client.py
"""The only module that ever talks to Headscale. Every interaction goes
through the host-bridge (settings.CHAT_BRIDGE_URL) -- this backend
container has no network path to Headscale and no `headscale` binary,
exactly the same constraint api/routes/system_control.py already solves
for git via /v1/exec. Headscale itself is reached only via its own CLI
(`headscale ... -o json`), never an HTTP/gRPC API call -- confirmed against
Nexo's real integration tests (test/integration/02_admin_user_test.go,
04_enrollment_test.go), which use the identical `headscale <subcommand>
-o json` shape this module reproduces.

Every policy-affecting change re-renders the ENTIRE ACL policy from the
current database state and pushes it in one shot (`headscale policy set
--file ...`) -- never an incremental patch. This makes "what the database
says is granted" and "what Headscale is actually enforcing" structurally
unable to drift apart: there is no diff logic to have a bug in.
"""
import json
import re
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.client import Client, Workstation, WorkstationPeerGrant


@dataclass(frozen=True)
class PeerPairIPs:
    alias_a: str
    ip_a: str
    alias_b: str
    ip_b: str


def slugify_client_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "cliente"


async def _bridge(method: str, path: str, *, timeout_seconds: float = 30.0, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        resp = await client.request(
            method,
            f"{settings.CHAT_BRIDGE_URL}{path}",
            headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
            **kwargs,
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Host-bridge error: {resp.text[:500]}")
    return resp.json()


async def _headscale_exec(*args: str) -> str:
    import shlex
    command = "headscale " + " ".join(shlex.quote(a) for a in args)
    data = await _bridge("POST", "/v1/exec", json={"command": command})
    if data["exit_code"] != 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(data["stderr"] or "").strip() or "headscale command failed",
        )
    return (data["stdout"] or "").strip()


async def list_node_ips() -> dict[str, str]:
    """hostname -> first IPv4 overlay address, per `headscale nodes list -o json`."""
    out = await _headscale_exec("nodes", "list", "-o", "json")
    nodes = json.loads(out) if out else []
    result: dict[str, str] = {}
    for node in nodes:
        name = node.get("given_name") or node.get("name")
        ips = node.get("ip_addresses") or []
        ipv4 = next((ip for ip in ips if "." in ip), None)
        if name and ipv4:
            result[name] = ipv4
    return result


def render_policy(client_tags: list[str], peer_pairs: list[PeerPairIPs]) -> str:
    tag_owners = {tag: ["marcelo@"] for tag in client_tags}
    grants = [
        {"src": ["group:admins"], "dst": [tag], "ip": ["*"]}
        for tag in client_tags
    ]
    hosts = {}
    for pair in peer_pairs:
        hosts[pair.alias_a] = pair.ip_a
        hosts[pair.alias_b] = pair.ip_b
        grants.append({"src": [pair.alias_a], "dst": [pair.alias_b], "ip": ["*"]})

    policy = {
        "groups": {"group:admins": ["marcelo@"]},
        "tagOwners": tag_owners,
        "hosts": hosts,
        "grants": grants,
    }
    return json.dumps(policy, indent=2)


async def push_policy(hujson: str) -> None:
    await _bridge("PUT", "/v1/fs/write", json={"path": settings.HEADSCALE_ACL_POLICY_PATH, "content": hujson})
    await _headscale_exec("policy", "set", "--file", settings.HEADSCALE_ACL_POLICY_PATH)


async def rebuild_and_push_policy(db: AsyncSession) -> None:
    """The single integration point every policy-affecting route calls.
    Reads current DB state, resolves live overlay IPs for any active peer
    grant, renders the whole policy, and pushes it."""
    client_tags = [
        tag for (tag,) in (await db.execute(
            select(Client.headscale_tag).where(Client.headscale_tag.is_not(None))
        )).all()
    ]

    active_grants = (await db.execute(
        select(WorkstationPeerGrant).where(WorkstationPeerGrant.revoked_at.is_(None))
    )).scalars().all()

    peer_pairs: list[PeerPairIPs] = []
    if active_grants:
        node_ips = await list_node_ips()
        workstation_ids = {g.workstation_a_id for g in active_grants} | {g.workstation_b_id for g in active_grants}
        workstations = (await db.execute(
            select(Workstation).where(Workstation.id.in_(workstation_ids))
        )).scalars().all()
        ws_by_id = {ws.id: ws for ws in workstations}

        for grant in active_grants:
            ws_a = ws_by_id.get(grant.workstation_a_id)
            ws_b = ws_by_id.get(grant.workstation_b_id)
            if ws_a is None or ws_b is None or not ws_a.hostname or not ws_b.hostname:
                continue
            ip_a = node_ips.get(ws_a.hostname)
            ip_b = node_ips.get(ws_b.hostname)
            if not ip_a or not ip_b:
                continue
            peer_pairs.append(PeerPairIPs(
                alias_a=f"ws-{ws_a.id}", ip_a=ip_a,
                alias_b=f"ws-{ws_b.id}", ip_b=ip_b,
            ))

    hujson = render_policy(client_tags, peer_pairs)
    await push_policy(hujson)
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_headscale_client.py`)

```python
"""core/headscale_client.py tests. render_policy/slugify are pure and
tested directly with no bridge involved; list_node_ips/push_policy/
rebuild_and_push_policy are tested against a FakeBridgeClient that
intercepts httpx.AsyncClient, the same pattern test_system_control.py
already uses -- no live Headscale is reachable in this environment and
none should be called."""
import json
import uuid
from datetime import datetime, timezone

import pytest

from app.core import headscale_client as hc
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation, WorkstationPeerGrant


def test_slugify_client_name():
    assert hc.slugify_client_name("Clube de Tiro Gatling") == "clube-de-tiro-gatling"
    assert hc.slugify_client_name("  Multi   Space!! ") == "multi-space"
    assert hc.slugify_client_name("---") == "cliente"


def test_render_policy_no_grants():
    result = hc.render_policy(["tag:cliente-a", "tag:cliente-b"], [])
    policy = json.loads(result)
    assert policy["tagOwners"] == {"tag:cliente-a": ["marcelo@"], "tag:cliente-b": ["marcelo@"]}
    assert policy["hosts"] == {}
    assert {"src": ["group:admins"], "dst": ["tag:cliente-a"], "ip": ["*"]} in policy["grants"]
    assert not any("ws-" in str(g.get("src", [])) for g in policy["grants"])


def test_render_policy_with_peer_grant():
    pair = hc.PeerPairIPs(alias_a="ws-a", ip_a="100.64.0.1", alias_b="ws-b", ip_b="100.64.0.2")
    result = hc.render_policy(["tag:cliente-a"], [pair])
    policy = json.loads(result)
    assert policy["hosts"] == {"ws-a": "100.64.0.1", "ws-b": "100.64.0.2"}
    assert {"src": ["ws-a"], "dst": ["ws-b"], "ip": ["*"]} in policy["grants"]


class FakeBridgeClient:
    calls: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, headers=None, json=None, params=None, **kwargs):
        FakeBridgeClient.calls.append((method, url, json))
        if url.endswith("/v1/exec"):
            command = (json or {}).get("command", "")
            if "nodes list" in command:
                return _ok(__import__("json").dumps([
                    {"given_name": "ws-host-a", "ip_addresses": ["100.64.0.1", "fd7a::1"]},
                    {"given_name": "ws-host-b", "ip_addresses": ["100.64.0.2"]},
                ]))
            if "policy set" in command:
                return _ok("")
            return _ok("")
        if url.endswith("/v1/fs/write"):
            return _ok("")
        raise AssertionError(f"unexpected bridge call: {url}")


def _ok(stdout: str):
    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {"stdout": stdout, "stderr": "", "exit_code": 0}
    return _Resp()


@pytest.mark.asyncio
async def test_list_node_ips(monkeypatch):
    monkeypatch.setattr(hc.httpx, "AsyncClient", FakeBridgeClient)
    result = await hc.list_node_ips()
    assert result == {"ws-host-a": "100.64.0.1", "ws-host-b": "100.64.0.2"}


@pytest.mark.asyncio
async def test_rebuild_and_push_policy_resolves_active_grant_ips(monkeypatch):
    FakeBridgeClient.calls = []
    monkeypatch.setattr(hc.httpx, "AsyncClient", FakeBridgeClient)

    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}", headscale_tag=f"tag:cliente-{uuid.uuid4().hex[:8]}")
        db.add(client)
        await db.flush()
        ws_a = Workstation(
            client_id=client.id, os_kind="linux", hostname="ws-host-a",
            device_token_hash=uuid.uuid4().hex, device_token_issued_at=datetime.now(timezone.utc),
        )
        ws_b = Workstation(
            client_id=client.id, os_kind="linux", hostname="ws-host-b",
            device_token_hash=uuid.uuid4().hex, device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(ws_a)
        db.add(ws_b)
        await db.flush()
        grant = WorkstationPeerGrant(
            workstation_a_id=ws_a.id, workstation_b_id=ws_b.id, granted_at=datetime.now(timezone.utc),
        )
        db.add(grant)
        await db.commit()

        try:
            await hc.rebuild_and_push_policy(db)

            write_calls = [c for c in FakeBridgeClient.calls if c[1].endswith("/v1/fs/write")]
            assert len(write_calls) == 1
            pushed_policy = json.loads(write_calls[0][2]["content"])
            assert client.headscale_tag in pushed_policy["tagOwners"]
            assert f"ws-{ws_a.id}" in pushed_policy["hosts"]
            assert pushed_policy["hosts"][f"ws-{ws_a.id}"] == "100.64.0.1"

            set_calls = [c for c in FakeBridgeClient.calls if "policy set" in (c[2] or {}).get("command", "")]
            assert len(set_calls) == 1
        finally:
            await db.delete(grant)
            await db.delete(ws_a)
            await db.delete(ws_b)
            await db.delete(client)
            await db.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_headscale_client.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create `backend/app/core/headscale_client.py`** with the exact content above.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_headscale_client.py -v`
Expected: PASS (all 5 cases)

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/headscale_client.py backend/app/tests/test_headscale_client.py
git commit -m "feat(clients): add Headscale host-bridge adapter and full-policy renderer"
```

---

### Task 3: Wire Client-tag auto-provisioning into `create_client`

**Files:**
- Modify: `backend/app/api/routes/client.py`
- Test: `backend/app/tests/test_client_routes.py` (add one test)

**Interfaces:**
- Consumes: `slugify_client_name`, `rebuild_and_push_policy` (Task 2).

- [ ] **Step 1: Write the failing test** (append to `test_client_routes.py`)

```python
@pytest.mark.asyncio
async def test_create_client_provisions_headscale_tag(monkeypatch):
    from app.core import headscale_client as hc

    pushed = {}

    async def fake_rebuild(db):
        pushed["called"] = True

    monkeypatch.setattr("app.api.routes.client.rebuild_and_push_policy", fake_rebuild)

    token = await _admin_token()
    headers = {"Authorization": f"Bearer {token}"}
    name = f"Tagged Client {uuid.uuid4()}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post("/api/v1/clients", json={"name": name}, headers=headers)
        assert create_resp.status_code == 201, create_resp.text
        body = create_resp.json()
        assert body["headscale_tag"] == f"tag:cliente-{hc.slugify_client_name(name)}"
        assert pushed.get("called") is True

        delete_resp = await client.delete(f"/api/v1/clients/{body['id']}", headers=headers)
        assert delete_resp.status_code == 204
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_client_routes.py -v -k provisions`
Expected: FAIL — `headscale_tag` is still `None`.

- [ ] **Step 3: Modify `create_client` in `client.py`**

Read the current `create_client` function first (from Plan 1). Add the tag assignment and policy
push after the commit:

```python
from app.core.headscale_client import rebuild_and_push_policy, slugify_client_name

@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    payload: ClientCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    client = Client(**payload.model_dump())
    if payload.support_plan is not None and payload.support_plan not in SUPPORT_PLANS:
        raise HTTPException(400, f"support_plan must be one of {SUPPORT_PLANS}")
    client.headscale_tag = f"tag:cliente-{slugify_client_name(client.name)}"
    db.add(client)
    await db.commit()
    await db.refresh(client)
    await rebuild_and_push_policy(db)
    return client
```

(Keep the existing `support_plan` validation from the prior plan's fix wave exactly as it is — the
snippet above shows it only so the insertion point relative to `client.headscale_tag =` is clear;
do not duplicate the check if it is already present in a different position in the real file.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_client_routes.py -v`
Expected: PASS (all cases, including the new one)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/client.py backend/app/tests/test_client_routes.py
git commit -m "feat(clients): auto-provision Headscale tag on client creation"
```

---

### Task 4: `WorkstationPeerGrant` create/revoke routes + audit logging

**Files:**
- Create: `backend/app/api/schemas/peer_grant.py`
- Create: `backend/app/api/routes/peer_grant.py`
- Modify: `backend/app/main.py`
- Test: `backend/app/tests/test_peer_grant_routes.py`

**Interfaces:**
- Consumes: `WorkstationPeerGrant` (Task 1), `rebuild_and_push_policy` (Task 2), `AuditEvent`
  (existing, `db/models/governance.py`), `get_current_admin` (existing).
- Produces: `router` (prefix `/api/v1/peer-grants`) — Task 6's frontend hook calls this.

```python
# backend/app/api/schemas/peer_grant.py
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PeerGrantCreate(BaseModel):
    workstation_a_id: uuid.UUID
    workstation_b_id: uuid.UUID


class PeerGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workstation_a_id: uuid.UUID
    workstation_b_id: uuid.UUID
    granted_by_user_id: uuid.UUID | None
    granted_at: datetime
    revoked_at: datetime | None
```

```python
# backend/app/api/routes/peer_grant.py
"""Selective same-client peer access between two Workstations -- default
is no lateral traffic at all, even within one client; this is the one
mechanism that opens a specific pair, always audited and always reversible.

Endpoints:
  GET    /api/v1/peer-grants?client_id=   -- list grants for a client's workstations
  POST   /api/v1/peer-grants              -- create (rejects cross-client pairs)
  POST   /api/v1/peer-grants/{id}:revoke   -- revoke (never deletes the row)
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.peer_grant import PeerGrantCreate, PeerGrantOut
from app.core.deps import get_current_admin
from app.core.headscale_client import rebuild_and_push_policy
from app.db.base import get_db
from app.db.models.client import Workstation, WorkstationPeerGrant
from app.db.models.governance import AuditEvent
from app.db.models.user import User

router = APIRouter(prefix="/api/v1/peer-grants", tags=["peer-grants"])


def _canonical_pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


@router.get("", response_model=list[PeerGrantOut])
async def list_peer_grants(client_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    workstation_ids = (await db.execute(
        select(Workstation.id).where(Workstation.client_id == client_id)
    )).scalars().all()
    if not workstation_ids:
        return []
    result = await db.execute(
        select(WorkstationPeerGrant).where(
            or_(
                WorkstationPeerGrant.workstation_a_id.in_(workstation_ids),
                WorkstationPeerGrant.workstation_b_id.in_(workstation_ids),
            )
        )
    )
    return result.scalars().all()


@router.post("", response_model=PeerGrantOut, status_code=201)
async def create_peer_grant(
    payload: PeerGrantCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    ws_a = await db.get(Workstation, payload.workstation_a_id)
    ws_b = await db.get(Workstation, payload.workstation_b_id)
    if ws_a is None or ws_b is None:
        raise HTTPException(404, "Workstation not found")
    if ws_a.client_id != ws_b.client_id:
        raise HTTPException(400, "Both workstations must belong to the same Client")
    if ws_a.id == ws_b.id:
        raise HTTPException(400, "Cannot grant a workstation peer access to itself")

    a_id, b_id = _canonical_pair(ws_a.id, ws_b.id)
    existing = (await db.execute(
        select(WorkstationPeerGrant).where(
            WorkstationPeerGrant.workstation_a_id == a_id,
            WorkstationPeerGrant.workstation_b_id == b_id,
            WorkstationPeerGrant.revoked_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    grant = WorkstationPeerGrant(
        workstation_a_id=a_id,
        workstation_b_id=b_id,
        granted_by_user_id=admin.id,
        granted_at=datetime.now(timezone.utc),
    )
    db.add(grant)
    await db.flush()

    db.add(AuditEvent(
        entity_type="workstation_peer_grant",
        entity_id=grant.id,
        event_type="granted",
        actor=admin.username,
        payload={"workstation_a_id": str(a_id), "workstation_b_id": str(b_id)},
    ))
    await db.commit()
    await db.refresh(grant)
    await rebuild_and_push_policy(db)
    return grant


@router.post("/{grant_id}:revoke", response_model=PeerGrantOut)
async def revoke_peer_grant(
    grant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    grant = await db.get(WorkstationPeerGrant, grant_id)
    if grant is None:
        raise HTTPException(404, "Peer grant not found")
    if grant.revoked_at is not None:
        return grant

    grant.revoked_at = datetime.now(timezone.utc)
    await db.flush()

    db.add(AuditEvent(
        entity_type="workstation_peer_grant",
        entity_id=grant.id,
        event_type="revoked",
        actor=admin.username,
        payload={"workstation_a_id": str(grant.workstation_a_id), "workstation_b_id": str(grant.workstation_b_id)},
    ))
    await db.commit()
    await db.refresh(grant)
    await rebuild_and_push_policy(db)
    return grant
```

- [ ] **Step 1: Write the failing test** (`backend/app/tests/test_peer_grant_routes.py`)

```python
"""Peer grant route tests -- real DB, host-bridge faked via monkeypatch
(no live Headscale reachable in this environment)."""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.client import Client, Workstation
from app.db.models.governance import AuditEvent
from app.db.models.user import User
from app.main import app


async def _admin_token() -> str:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.is_admin.is_(True)).limit(1))
        admin = result.scalar_one_or_none()
        assert admin is not None
        return create_access_token(admin.username)


async def _make_client_with_two_workstations(other_client: bool = False):
    async with AsyncSessionLocal() as db:
        client = Client(name=f"Test Client {uuid.uuid4()}")
        db.add(client)
        await db.flush()
        other = None
        if other_client:
            other = Client(name=f"Other Client {uuid.uuid4()}")
            db.add(other)
            await db.flush()
        ws_a = Workstation(
            client_id=client.id, os_kind="linux", hostname="ws-a",
            device_token_hash=uuid.uuid4().hex, device_token_issued_at=datetime.now(timezone.utc),
        )
        ws_b = Workstation(
            client_id=(other.id if other else client.id), os_kind="linux", hostname="ws-b",
            device_token_hash=uuid.uuid4().hex, device_token_issued_at=datetime.now(timezone.utc),
        )
        db.add(ws_a)
        db.add(ws_b)
        await db.commit()
        return client.id, ws_a.id, ws_b.id, (other.id if other else None)


async def _cleanup(*client_ids):
    async with AsyncSessionLocal() as db:
        for cid in client_ids:
            if cid is None:
                continue
            c = await db.get(Client, cid)
            if c:
                await db.delete(c)
        await db.commit()


@pytest.mark.asyncio
async def test_create_and_revoke_peer_grant_within_same_client(monkeypatch):
    pushed = {"count": 0}

    async def fake_rebuild(db):
        pushed["count"] += 1

    monkeypatch.setattr("app.api.routes.peer_grant.rebuild_and_push_policy", fake_rebuild)

    client_id, ws_a_id, ws_b_id, _ = await _make_client_with_two_workstations()
    try:
        token = await _admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            create_resp = await http.post(
                "/api/v1/peer-grants",
                json={"workstation_a_id": str(ws_a_id), "workstation_b_id": str(ws_b_id)},
                headers=headers,
            )
            assert create_resp.status_code == 201, create_resp.text
            grant_id = create_resp.json()["id"]
            assert create_resp.json()["revoked_at"] is None
            assert pushed["count"] == 1

            list_resp = await http.get("/api/v1/peer-grants", params={"client_id": str(client_id)})
            assert list_resp.status_code == 200
            assert any(g["id"] == grant_id for g in list_resp.json())

            revoke_resp = await http.post(f"/api/v1/peer-grants/{grant_id}:revoke", headers=headers)
            assert revoke_resp.status_code == 200
            assert revoke_resp.json()["revoked_at"] is not None
            assert pushed["count"] == 2

        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            events = (await db.execute(
                select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(grant_id))
            )).scalars().all()
            assert {e.event_type for e in events} == {"granted", "revoked"}
    finally:
        await _cleanup(client_id)


@pytest.mark.asyncio
async def test_create_peer_grant_rejects_cross_client_pair(monkeypatch):
    async def fake_rebuild(db):
        pass

    monkeypatch.setattr("app.api.routes.peer_grant.rebuild_and_push_policy", fake_rebuild)

    client_id, ws_a_id, ws_b_id, other_id = await _make_client_with_two_workstations(other_client=True)
    try:
        token = await _admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            resp = await http.post(
                "/api/v1/peer-grants",
                json={"workstation_a_id": str(ws_a_id), "workstation_b_id": str(ws_b_id)},
                headers=headers,
            )
            assert resp.status_code == 400
    finally:
        await _cleanup(client_id, other_id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_peer_grant_routes.py -v`
Expected: FAIL — module/route not found.

- [ ] **Step 3: Create the two files above** with the exact content shown.

- [ ] **Step 4: Register the router in `main.py`**

Add `from app.api.routes import peer_grant as peer_grant_routes` alphabetically to the import
block and `app.include_router(peer_grant_routes.router)` near the other `clients`/`workstations`
routers, matching the established style.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_peer_grant_routes.py -v`
Expected: PASS (both cases)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/schemas/peer_grant.py backend/app/api/routes/peer_grant.py backend/app/main.py \
        backend/app/tests/test_peer_grant_routes.py
git commit -m "feat(clients): add WorkstationPeerGrant create/revoke routes with audit logging"
```

---

### Task 5: Frontend hook — `usePeerGrants`

**Files:**
- Create: `frontend/src/hooks/usePeerGrants.ts`
- Test: `frontend/src/hooks/usePeerGrants.test.ts`

**Interfaces:**
- Consumes: `apiClient` (existing).
- Produces: `PeerGrant` interface, `usePeerGrants(clientId)`, `useCreatePeerGrant()`,
  `useRevokePeerGrant()` — Task 6's Client detail page imports these exact names.

```typescript
// frontend/src/hooks/usePeerGrants.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

export interface PeerGrant {
  id: string;
  workstation_a_id: string;
  workstation_b_id: string;
  granted_by_user_id: string | null;
  granted_at: string;
  revoked_at: string | null;
}

export function usePeerGrants(clientId: string) {
  return useQuery({
    queryKey: ["peer-grants", clientId],
    queryFn: () => apiClient.get<PeerGrant[]>("/api/v1/peer-grants", { params: { client_id: clientId } }),
    enabled: Boolean(clientId),
  });
}

export function useCreatePeerGrant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ workstationAId, workstationBId }: { workstationAId: string; workstationBId: string }) =>
      apiClient.post<PeerGrant>("/api/v1/peer-grants", {
        workstation_a_id: workstationAId,
        workstation_b_id: workstationBId,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["peer-grants"] });
    },
  });
}

export function useRevokePeerGrant() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (grantId: string) => apiClient.post<PeerGrant>(`/api/v1/peer-grants/${grantId}:revoke`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["peer-grants"] });
    },
  });
}
```

- [ ] **Step 1: Write `usePeerGrants.ts`** with the exact content above.

- [ ] **Step 2: Write a test verifying the query is disabled with no clientId and enabled with one**

Find an existing hook test with the `renderHook`/`QueryClientProvider` pattern (e.g.
`useIrregularities.test.ts`, added in the prior plan) and copy its exact wrapper setup. Assert
`usePeerGrants("")`'s underlying query never fires (`apiClient.get` not called), and
`usePeerGrants("some-id")` calls `apiClient.get` with `{params: {client_id: "some-id"}}`.

- [ ] **Step 3: Run the test**

Run: `cd frontend && npx vitest run usePeerGrants`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/usePeerGrants.ts frontend/src/hooks/usePeerGrants.test.ts
git commit -m "feat(clients): add usePeerGrants frontend hook"
```

---

### Task 6: Clients list page + Client detail page with peer-grant matrix panel

**Files:**
- Create: `frontend/src/pages/clients/index.tsx`
- Create: `frontend/src/pages/clients/[id].tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/navSections.ts`
- Modify: `frontend/src/i18n/locales/en/common.json`, `frontend/src/i18n/locales/pt-BR/common.json`

**Interfaces:**
- Consumes: `useClients`/`useCreateClient` (existing, from Plan 1), `useWorkstations` (existing),
  `usePeerGrants`/`useCreatePeerGrant`/`useRevokePeerGrant` (Task 5).

- [ ] **Step 1: Build the Clients list page**, following `frontend/src/pages/servers/index.tsx`'s
  established structure (table + "Novo cliente" create dialog using `useCreateClient`, each row
  linking to `/clients/{id}`). This is a plain CRUD list — no matrix panel here.

- [ ] **Step 2: Build the Client detail page**, following `frontend/src/pages/agent/[id].tsx`'s
  established multi-panel detail-page structure (read that file first — it already has more than
  one card/panel on a single entity's detail view, the closest existing template for what this page
  needs). Panels:
  1. Client info (name, contact fields, support plan, `headscale_tag` shown read-only).
  2. Workstations list for this client (`useWorkstations(clientId)`, from Plan 1).
  3. **"Comunicação entre estações"** panel: a pairwise matrix. For N workstations, render an N×N
     grid (or, simpler and equally correct, a flat list of every unordered pair) where each
     cell/row shows the pair's two hostnames and a toggle. A pair with an active (non-revoked)
     `PeerGrant` (from `usePeerGrants(clientId)`, matched by `workstation_a_id`/`workstation_b_id`
     against the pair, checking both orderings since the API canonicalizes internally but the
     frontend must not assume which workstation the API stored as "a") shows the toggle ON and
     calls `useRevokePeerGrant()` on click; an ungranted pair shows it OFF and calls
     `useCreatePeerGrant()`. Wrap the toggle action in `ConfirmDialog` only for the revoke
     direction (granting is the safe, reversible default action; revoking removes an
     already-working communication path — treat it with the same destructive-action care as a
     delete). No bulk "allow all" control — every grant is one deliberate pair, per spec §5.2.

- [ ] **Step 3: Register both routes** in `App.tsx`, following the existing
  `<Route path="servers" .../>`/`<Route path="clients/:id" .../>`-style pattern (check the file's
  actual route definitions first — some detail routes use `:id`, confirm the exact param name
  convention already in use, e.g. `project/[id].tsx`'s route registration).

- [ ] **Step 4: Add a "Clientes"/"Clients" nav entry** to `navSections.ts`, with `module:
  "clients"` (the RBAC module Plan 1 already added — do not use `"servers"`, the mistake caught and
  fixed in Plan 1's final review). Place it in whichever existing section is the closest semantic
  fit (likely alongside the Irregularities entry from Plan 1, in "Operations").

- [ ] **Step 5: Add the i18n keys** (`nav.clients` or similar) to both locale files, following the
  exact style of the `nav.irregularities` keys Plan 1 already added.

- [ ] **Step 6: Manual verification** — start `./dev.sh`, confirm the Clients list page loads with
  no console error, create a test client through the UI, open its detail page, confirm the
  Workstations panel and the (initially empty, since a fresh client has 0-1 workstations so no
  pairs exist) peer-grant panel render without error. If time/tooling allows, register two
  workstations for the same test client (via `curl` against the existing `POST
  /api/v1/workstations` endpoint, since no workstation-creation UI exists yet — that's explicitly
  deferred to the installer/download-area plan) and confirm a pair now appears in the matrix and
  toggling it on/off actually calls the peer-grant endpoints (check the Network tab or backend
  logs — a live Headscale push will fail in this dev environment since no `headscale` binary is
  installed on this host; confirm the failure is a clean, visible error rather than a silent no-op,
  and note this limitation explicitly in the report rather than claiming full verification).
  Clean up the test client afterward.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/clients/index.tsx frontend/src/pages/clients/\[id\].tsx \
        frontend/src/App.tsx frontend/src/components/layout/navSections.ts \
        frontend/src/i18n/locales/en/common.json frontend/src/i18n/locales/pt-BR/common.json
git commit -m "feat(clients): add Clients list and detail page with peer-grant matrix panel"
```

---

## Self-Review Notes

- **Spec coverage:** §5.1 (Client → tag provisioning) → Task 3; §5.2 (peer grants, audit,
  never-delete) → Tasks 1/4; the host-bridge integration mechanism and full-render-and-push
  strategy resolved in this plan's own spec update → Task 2; the "Comunicação entre estações" UI
  → Task 6.
- **Placeholder scan:** every step has complete code or a precisely-scoped manual-verification
  instruction (Task 6 Step 6 explicitly bounds what can and cannot be verified in this environment,
  rather than leaving it vague).
- **Type consistency:** `WorkstationPeerGrant` (Task 1) is the exact ORM type Task 4's routes use;
  `rebuild_and_push_policy`/`slugify_client_name` (Task 2) are the exact functions Tasks 3-4 import;
  `PeerGrantOut` (Task 4) field-for-field matches the frontend `PeerGrant` interface (Task 5).
- **No live Headscale dependency introduced:** every test that would otherwise need a real
  Headscale instance fakes the host-bridge's `httpx.AsyncClient` instead, matching this codebase's
  own established convention for bridge-calling routes (`test_system_control.py`'s
  `FakeBridgeClient`) — confirmed this environment has no `headscale` binary reachable via the real
  host-bridge, so this is not a shortcut but the only viable test strategy.
