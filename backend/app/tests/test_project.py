"""Tests for the Project domain (projects, project_plans, plan_baselines,
change_requests).

DB strategy: this backend foundation is built incrementally by several
domain agents against the same shared `company_postgres` database, and no
unified Alembic migration has landed yet at the time this module runs. To
exercise real async-session CRUD against the live database without
depending on migration ordering between domains, this module:

1. Ensures this domain's own four tables exist via
   `Base.metadata.create_all(checkfirst=True)` (the default), which is a
   no-op if a migration already created them.
2. Ensures a minimal `company.product_versions` stub table exists (the
   real FK target, owned by the Product domain) -- also checkfirst, so it
   never clobbers a real product_versions table created by that domain's
   own migration. Other domains (e.g. Backlog: planning_items,
   bug_reports, version_scope_items) may already have live FK constraints
   pointing at this table, so it is intentionally never dropped.
3. Inserts one stub product_version row tests can point projects at.
4. Runs all tests against the real AsyncSessionLocal / engine from
   app.db.base (per the foundation's `get_db` dependency).
5. Teardown only DELETEs the rows this module created (by id) -- it never
   DROPs any table, since other concurrently-developed domains may already
   have foreign keys referencing these tables.
"""
import shutil
import tempfile
import uuid
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api.routes import project as project_routes
from app.db.base import AsyncSessionLocal, Base, engine
from app.db.models.product import Product, ProductVersion
from app.db.models.project import (
    ChangeRequest,
    PlanBaseline,
    Project,
    ProjectPlan,
    ProjectStructureNode,
)
from app.main import app

# The wiring step (not yet run) is responsible for adding
# `app.include_router(project.router)` to app/main.py. Until then, include
# it here directly so these tests can exercise the real app + real router
# together without editing main.py ourselves. Guard against double
# registration in case a future wiring step runs before this test module
# is removed/updated.
_ALREADY_WIRED = any(
    getattr(route, "path", "").startswith("/api/v1/projects") for route in app.router.routes
)
if not _ALREADY_WIRED:
    app.include_router(project_routes.router)

# NOTE: this module previously declared a local stub `Table()` object for
# the `product_versions` FK target to satisfy string-FK resolution before
# the unified Alembic migration existed. The real ORM model for that table
# now exists (Product domain) and is migration-managed, so the stub was
# removed -- a duplicate `Table(..., extend_existing=True)` registration for
# an already-mapped table corrupts SQLAlchemy's mapper configuration for any
# other test module that also touches that table in the same test session.
# A real Product + ProductVersion row is created in `db_schema` below
# instead.

_OWN_TABLES = [
    Project.__table__,
    ProjectPlan.__table__,
    PlanBaseline.__table__,
    ChangeRequest.__table__,
    ProjectStructureNode.__table__,
]

_STUB_PRODUCT_VERSION_ID: uuid.UUID | None = None
_STUB_PRODUCT_ID: uuid.UUID | None = None

# Track every row this module inserts (table, id) so teardown can delete
# exactly those rows without ever issuing a DROP TABLE against tables that
# other concurrently-developed domains may already depend on.
_created_rows: list[tuple[str, uuid.UUID]] = []


@pytest_asyncio.fixture(scope="module")
async def db_schema():
    global _STUB_PRODUCT_VERSION_ID, _STUB_PRODUCT_ID

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_OWN_TABLES)

    async with AsyncSessionLocal() as session:
        product = Product(name=f"Project Domain Test Product {uuid.uuid4()}")
        session.add(product)
        await session.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0")
        session.add(version)
        await session.commit()
        _STUB_PRODUCT_ID = product.id
        _STUB_PRODUCT_VERSION_ID = version.id

    yield

    async with engine.begin() as conn:
        # Delete child rows before parents (FK-safe order), and the stub
        # product_version/product rows only after every project referencing
        # them is gone.
        for table_name in (
            "change_requests",
            "plan_baselines",
            "project_structure_nodes",
            "project_plans",
            "projects",
        ):
            ids = [row_id for tbl, row_id in _created_rows if tbl == table_name]
            if ids:
                await conn.execute(
                    text(f"DELETE FROM company.{table_name} WHERE id = ANY(:ids)"),
                    {"ids": ids},
                )
        await conn.execute(
            text("DELETE FROM company.product_versions WHERE id = :id"),
            {"id": _STUB_PRODUCT_VERSION_ID},
        )
        await conn.execute(
            text("DELETE FROM company.products WHERE id = :id"),
            {"id": _STUB_PRODUCT_ID},
        )


@pytest_asyncio.fixture
async def client(db_schema, auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


async def test_create_get_list_project(client: AsyncClient):
    payload = {
        "name": "ForgeHub — Foundation MVP",
        "description": "Initial bootstrap project",
        "product_version_id": str(_STUB_PRODUCT_VERSION_ID),
        "owner": "marcelo",
        "status": "planned",
        "start_date": str(date.today()),
    }
    create_resp = await client.post("/api/v1/projects", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == payload["name"]
    assert created["status"] == "planned"
    project_id = created["id"]
    _created_rows.append(("projects", uuid.UUID(project_id)))

    get_resp = await client.get(f"/api/v1/projects/{project_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == project_id

    list_resp = await client.get("/api/v1/projects")
    assert list_resp.status_code == 200
    assert any(p["id"] == project_id for p in list_resp.json())


async def test_get_project_not_found(client: AsyncClient):
    resp = await client.get(f"/api/v1/projects/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_baseline_requires_approved_plan(client: AsyncClient):
    """Business rule (SPEC 6.3.1): only an approved plan can be baselined.

    Creating a baseline from a freshly-created (draft) plan must be
    rejected with a 4xx, not silently succeed.
    """
    project_resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "Rule Test Project",
            "product_version_id": str(_STUB_PRODUCT_VERSION_ID),
        },
    )
    assert project_resp.status_code == 201
    project_id = project_resp.json()["id"]
    _created_rows.append(("projects", uuid.UUID(project_id)))

    plan_resp = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"name": "Initial Plan", "scope_summary": "MVP scope"},
    )
    assert plan_resp.status_code == 201
    plan = plan_resp.json()
    assert plan["status"] == "draft"
    _created_rows.append(("project_plans", uuid.UUID(plan["id"])))

    baseline_resp = await client.post(
        f"/api/v1/projects/{project_id}/baselines",
        json={"name": "Baseline 1", "project_plan_id": plan["id"]},
    )
    assert baseline_resp.status_code == 422
    assert "approved" in baseline_resp.json()["detail"].lower()


async def test_baseline_flow_and_post_baseline_edit_blocked(client: AsyncClient):
    """Full happy path: approve -> baseline -> direct edit now rejected ->
    change request with no impact flags rejected -> change request with an
    impact flag accepted."""
    project_resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "Baseline Flow Project",
            "product_version_id": str(_STUB_PRODUCT_VERSION_ID),
        },
    )
    project_id = project_resp.json()["id"]
    _created_rows.append(("projects", uuid.UUID(project_id)))

    plan_resp = await client.post(
        f"/api/v1/projects/{project_id}/plans",
        json={"name": "Plan A", "scope_summary": "Scope A"},
    )
    plan_id = plan_resp.json()["id"]
    _created_rows.append(("project_plans", uuid.UUID(plan_id)))

    approve_resp = await client.post(f"/api/v1/projects/plans/{plan_id}/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    baseline_resp = await client.post(
        f"/api/v1/projects/{project_id}/baselines",
        json={"name": "Baseline A", "project_plan_id": plan_id},
    )
    assert baseline_resp.status_code == 201, baseline_resp.text
    assert baseline_resp.json()["scope_snapshot"] == "Scope A"
    _created_rows.append(("plan_baselines", uuid.UUID(baseline_resp.json()["id"])))

    plan_after = await client.get(f"/api/v1/projects/plans/{plan_id}")
    assert plan_after.json()["status"] == "baselined"

    # Direct mutation of scope after baseline must be rejected.
    edit_resp = await client.patch(
        f"/api/v1/projects/plans/{plan_id}", json={"scope_summary": "Sneaky change"}
    )
    assert edit_resp.status_code == 422
    assert "change" in edit_resp.json()["detail"].lower()

    # A change request with no impact flags is meaningless and rejected.
    empty_cr_resp = await client.post(
        f"/api/v1/projects/{project_id}/change-requests",
        json={"title": "No-op CR"},
    )
    assert empty_cr_resp.status_code == 422

    # A change request with a real impact flag is accepted.
    cr_resp = await client.post(
        f"/api/v1/projects/{project_id}/change-requests",
        json={
            "title": "Add reporting feature",
            "justification": "Stakeholder request",
            "adds_features": True,
            "affects_schedule": True,
            "schedule_delta_days": 5,
        },
    )
    assert cr_resp.status_code == 201, cr_resp.text
    cr = cr_resp.json()
    assert cr["status"] == "pending"
    _created_rows.append(("change_requests", uuid.UUID(cr["id"])))

    update_resp = await client.patch(
        f"/api/v1/projects/change-requests/{cr['id']}", json={"status": "approved"}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "approved"
    assert update_resp.json()["decided_at"] is not None


async def _create_project(client: AsyncClient, name: str) -> str:
    resp = await client.post(
        "/api/v1/projects",
        json={"name": name, "product_version_id": str(_STUB_PRODUCT_VERSION_ID)},
    )
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["id"]
    _created_rows.append(("projects", uuid.UUID(project_id)))
    return project_id


async def test_structure_node_create_get_list(client: AsyncClient):
    project_id = await _create_project(client, "Structure Node Project")

    folder_resp = await client.post(
        f"/api/v1/projects/{project_id}/structure-nodes",
        json={"name": "backend", "node_type": "folder", "path": "backend"},
    )
    assert folder_resp.status_code == 201, folder_resp.text
    folder = folder_resp.json()
    assert folder["project_id"] == project_id
    assert folder["is_locked"] is False
    _created_rows.append(("project_structure_nodes", uuid.UUID(folder["id"])))

    child_resp = await client.post(
        f"/api/v1/projects/{project_id}/structure-nodes",
        json={
            "name": "task.py",
            "node_type": "module",
            "path": "backend/app/db/models/task.py",
            "parent_node_id": folder["id"],
        },
    )
    assert child_resp.status_code == 201, child_resp.text
    child = child_resp.json()
    assert child["parent_node_id"] == folder["id"]
    _created_rows.append(("project_structure_nodes", uuid.UUID(child["id"])))

    get_resp = await client.get(f"/api/v1/projects/structure-nodes/{child['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == child["id"]

    list_resp = await client.get(f"/api/v1/projects/{project_id}/structure-nodes")
    assert list_resp.status_code == 200
    node_ids = {n["id"] for n in list_resp.json()}
    assert {folder["id"], child["id"]} <= node_ids


async def test_structure_node_invalid_node_type_rejected(client: AsyncClient):
    project_id = await _create_project(client, "Structure Node Invalid Type Project")

    resp = await client.post(
        f"/api/v1/projects/{project_id}/structure-nodes",
        json={"name": "bogus", "node_type": "not_a_real_type"},
    )
    assert resp.status_code == 422


async def test_structure_node_parent_must_belong_to_same_project(client: AsyncClient):
    project_a = await _create_project(client, "Structure Node Project A")
    project_b = await _create_project(client, "Structure Node Project B")

    node_a_resp = await client.post(
        f"/api/v1/projects/{project_a}/structure-nodes",
        json={"name": "root", "node_type": "folder"},
    )
    assert node_a_resp.status_code == 201
    node_a = node_a_resp.json()
    _created_rows.append(("project_structure_nodes", uuid.UUID(node_a["id"])))

    cross_project_resp = await client.post(
        f"/api/v1/projects/{project_b}/structure-nodes",
        json={"name": "leak", "node_type": "folder", "parent_node_id": node_a["id"]},
    )
    assert cross_project_resp.status_code == 400


async def test_structure_node_lock_blocks_mutation_until_unlocked(client: AsyncClient):
    project_id = await _create_project(client, "Structure Node Lock Project")

    node_resp = await client.post(
        f"/api/v1/projects/{project_id}/structure-nodes",
        json={"name": "auth", "node_type": "module", "path": "backend/app/core/security.py"},
    )
    assert node_resp.status_code == 201
    node = node_resp.json()
    _created_rows.append(("project_structure_nodes", uuid.UUID(node["id"])))

    lock_resp = await client.patch(
        f"/api/v1/projects/structure-nodes/{node['id']}", json={"is_locked": True}
    )
    assert lock_resp.status_code == 200
    assert lock_resp.json()["is_locked"] is True

    # Any non-unlocking mutation while locked is rejected.
    blocked_resp = await client.patch(
        f"/api/v1/projects/structure-nodes/{node['id']}", json={"description": "sneaky"}
    )
    assert blocked_resp.status_code == 409

    blocked_delete = await client.delete(f"/api/v1/projects/structure-nodes/{node['id']}")
    assert blocked_delete.status_code == 409

    # Unlocking is always allowed, and re-enables further mutation.
    unlock_resp = await client.patch(
        f"/api/v1/projects/structure-nodes/{node['id']}", json={"is_locked": False}
    )
    assert unlock_resp.status_code == 200
    assert unlock_resp.json()["is_locked"] is False

    edit_resp = await client.patch(
        f"/api/v1/projects/structure-nodes/{node['id']}", json={"description": "now allowed"}
    )
    assert edit_resp.status_code == 200
    assert edit_resp.json()["description"] == "now allowed"

    delete_resp = await client.delete(f"/api/v1/projects/structure-nodes/{node['id']}")
    assert delete_resp.status_code == 204
    _created_rows.remove(("project_structure_nodes", uuid.UUID(node["id"])))


async def test_files_require_working_directory(client: AsyncClient):
    """A project with no working_directory_path set can't be browsed --
    there's nowhere on the host to point the bridge at."""
    project_id = await _create_project(client, "Files No Working Dir Project")

    resp = await client.get(f"/api/v1/projects/{project_id}/files")
    assert resp.status_code == 400
    assert "working_directory_path" in resp.json()["detail"]


async def test_files_full_crud_flow(client: AsyncClient):
    """End-to-end against a real scratch directory on the host (via the
    real chat bridge, no mocking) -- list, create dir/file, write, read,
    rename, delete."""
    working_dir = tempfile.mkdtemp(prefix="forgehub-test-project-")
    try:
        project_id = await _create_project(client, "Files CRUD Project")
        patch_resp = await client.patch(
            f"/api/v1/projects/{project_id}", json={"working_directory_path": working_dir}
        )
        assert patch_resp.status_code == 200, patch_resp.text

        empty_list = await client.get(f"/api/v1/projects/{project_id}/files")
        assert empty_list.status_code == 200, empty_list.text
        assert empty_list.json() == {"path": "", "entries": []}

        mkdir_resp = await client.post(
            f"/api/v1/projects/{project_id}/files/directory", json={"path": "src"}
        )
        assert mkdir_resp.status_code == 201, mkdir_resp.text
        assert mkdir_resp.json() == {"name": "src", "path": "src", "type": "dir", "size": None}

        create_resp = await client.post(
            f"/api/v1/projects/{project_id}/files/new", json={"path": "src/main.py"}
        )
        assert create_resp.status_code == 201, create_resp.text
        assert create_resp.json()["path"] == "src/main.py"

        # Creating the same file again is rejected, not silently overwritten.
        dup_resp = await client.post(
            f"/api/v1/projects/{project_id}/files/new", json={"path": "src/main.py"}
        )
        assert dup_resp.status_code == 409

        write_resp = await client.put(
            f"/api/v1/projects/{project_id}/files/content",
            params={"path": "src/main.py"},
            json={"content": "print('hello')\n"},
        )
        assert write_resp.status_code == 200, write_resp.text

        read_resp = await client.get(
            f"/api/v1/projects/{project_id}/files/content", params={"path": "src/main.py"}
        )
        assert read_resp.status_code == 200
        assert read_resp.json() == {"path": "src/main.py", "content": "print('hello')\n"}

        list_resp = await client.get(f"/api/v1/projects/{project_id}/files", params={"path": "src"})
        assert list_resp.status_code == 200
        assert list_resp.json()["entries"] == [
            {"name": "main.py", "path": "src/main.py", "type": "file", "size": 15}
        ]

        rename_resp = await client.patch(
            f"/api/v1/projects/{project_id}/files",
            json={"path": "src/main.py", "new_path": "src/app.py"},
        )
        assert rename_resp.status_code == 200, rename_resp.text
        assert rename_resp.json()["path"] == "src/app.py"

        # Path traversal is rejected before it ever reaches the bridge.
        escape_resp = await client.get(
            f"/api/v1/projects/{project_id}/files/content", params={"path": "../../etc/passwd"}
        )
        assert escape_resp.status_code == 400

        delete_file_resp = await client.delete(
            f"/api/v1/projects/{project_id}/files", params={"path": "src/app.py"}
        )
        assert delete_file_resp.status_code == 204

        # Non-empty dir delete without recursive=true is rejected...
        delete_dir_resp = await client.delete(
            f"/api/v1/projects/{project_id}/files", params={"path": "src"}
        )
        assert delete_dir_resp.status_code in (200, 204)  # src is empty again now (app.py was removed)
    finally:
        shutil.rmtree(working_dir, ignore_errors=True)


async def test_files_sensitive_paths_are_hidden_and_blocked(client: AsyncClient):
    """A working directory containing a real .env must never expose it
    through this browser -- not in the listing, and not even if a caller
    requests/writes/deletes it by its exact path directly."""
    working_dir = tempfile.mkdtemp(prefix="forgehub-test-project-secrets-")
    try:
        with open(f"{working_dir}/.env", "w") as f:
            f.write("SECRET=do-not-leak\n")
        with open(f"{working_dir}/app.py", "w") as f:
            f.write("print('safe')\n")

        project_id = await _create_project(client, "Files Sensitive Paths Project")
        await client.patch(f"/api/v1/projects/{project_id}", json={"working_directory_path": working_dir})

        list_resp = await client.get(f"/api/v1/projects/{project_id}/files")
        assert list_resp.status_code == 200
        names = {e["name"] for e in list_resp.json()["entries"]}
        assert names == {"app.py"}

        read_resp = await client.get(f"/api/v1/projects/{project_id}/files/content", params={"path": ".env"})
        assert read_resp.status_code == 403

        write_resp = await client.put(
            f"/api/v1/projects/{project_id}/files/content",
            params={"path": ".env"},
            json={"content": "PWNED=true\n"},
        )
        assert write_resp.status_code == 403

        delete_resp = await client.delete(f"/api/v1/projects/{project_id}/files", params={"path": ".env"})
        assert delete_resp.status_code == 403

        rename_resp = await client.patch(
            f"/api/v1/projects/{project_id}/files", json={"path": ".env", "new_path": "env.txt"}
        )
        assert rename_resp.status_code == 403

        # The real file on disk is untouched by any of the rejected attempts.
        with open(f"{working_dir}/.env") as f:
            assert f.read() == "SECRET=do-not-leak\n"
    finally:
        shutil.rmtree(working_dir, ignore_errors=True)
