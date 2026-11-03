"""Initial M0 rehearsal: test environment and mission membership guards."""
import uuid

import pytest

from app.core.config import assert_test_database_target, settings
from app.core.mission_documents import project_slug
from app.mcp import factory_server
from app.tests.test_mission_mcp import _key, docs_root, mcp_as, mw  # noqa: F401


@pytest.mark.asyncio
async def test_mission_rehearsal_membership(mw, mcp_as, docs_root, monkeypatch):  # noqa: F811
    assert settings.ENVIRONMENT == "test"
    assert_test_database_target(settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB,
                                settings.POSTGRES_USER)
    monkeypatch.setattr(settings, "MISSION_TOOLS_ENABLED", True)
    product_id, version_id = await mw.version()
    coordinator = await mw.agent("coordinator", runtime="hermes")
    executor = await mw.agent("executor", runtime="codex")
    reviewer = await mw.agent("reviewer", runtime="agy")
    documentation = await mw.agent("documentation", runtime="hermes")
    mcp_as(await mw.token(coordinator, product_id=product_id))
    name = f"mission-test-{uuid.uuid4().hex}"
    created = await factory_server.create_internal_project(str(version_id), name, _key())
    assert created["mission_state"] == "draft"
    project_id = created["project_id"]
    mcp_as(await mw.token(coordinator, project_id=uuid.UUID(project_id)))
    for operation, code in (
        ({"op": "add", "agent_id": str(executor), "role": "developer", "can_approve": True},
         "CAN_APPROVE_NOT_FOR_AGENTS"),
        ({"op": "add", "agent_id": str(documentation), "role": "developer"},
         "CODE_ROLE_REQUIRES_EXTERNAL_RUNTIME"),
        ({"op": "release", "agent_id": str(coordinator)}, "LAST_COORDINATOR"),
    ):
        with pytest.raises(factory_server.FactoryError, match=code):
            await factory_server.manage_project_members(project_id, [operation], _key())
    members = await factory_server.manage_project_members(project_id, [
        {"op": "add", "agent_id": str(executor), "role": "developer"},
        {"op": "add", "agent_id": str(reviewer), "role": "reviewer", "can_review": True},
        {"op": "add", "agent_id": str(documentation), "role": "documentation"},
    ], _key())
    assert members["replayed"] is False

    # Step 7: the documentation member attaches a file inside this mission.
    slug = project_slug(name)
    doc_path = f"missions/{slug}/notes.md"
    path = docs_root / doc_path
    path.parent.mkdir(parents=True)
    path.write_text("Rehearsal notes", encoding="utf-8")
    mcp_as(await mw.token(documentation, project_id=uuid.UUID(project_id)))
    attached = await factory_server.attach_project_document(project_id, "project", project_id, doc_path, _key())
    assert attached["link_created"] is True
    with pytest.raises(factory_server.FactoryError, match="DOC_PATH_NOT_ALLOWED"):
        await factory_server.attach_project_document(project_id, "project", project_id,
                                                     f"missions/{slug}/../{slug}/notes.md", _key())
