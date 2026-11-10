# ruff: noqa: F811
"""Formal acceptance uses the existing governed decision and real dossier bytes."""
import hashlib
import uuid

import pytest_asyncio
from sqlalchemy import delete, select

from app.core import mission_documents
from app.db.base import AsyncSessionLocal
from app.db.models.artifact import ArtifactVersion
from app.db.models.governance import ApprovalDecisionRecord, ApprovalRequest, PolicyEvaluation
from app.db.models.mission import ProjectMission
from app.db.models.project import Project
from app.tests.test_mission_cycle import cw, _orch_headers, _verified_execution, _key  # noqa: F401
from app.tests.test_mission_dispatch import world, runner  # noqa: F401
from app.tests.test_mission_base import _member, _criterion, _transition
from app.tests.test_mission_planning_records import _doc
from app.tests.test_task_baseline_guard import _mission


@pytest_asyncio.fixture
async def accepted_delivery(cw, tmp_path, monkeypatch):
    monkeypatch.setattr(mission_documents, "MISSION_DOCS_ROOT", tmp_path)
    mission = await _mission(cw)
    task = await mission.task("Reviewed delivery")
    verifier = await cw.agent("verifier")
    await _member(mission.project_id, verifier, role="reviewer", can_review=True)
    criterion = await _criterion(mission.project_id, verifier, task_ids=[task.id])
    await mission.baseline([task.id])
    execution = await _verified_execution(task, f"db:project_task:{task.id}")
    orch = await _orch_headers(cw, mission)
    async with cw.client(orch) as client:
        review = await client.post(f"/api/v1/missions/{mission.project_id}/tasks/{task.id}:request-review",
            json={"execution_id": str(execution), "reviewer_agent_id": str(verifier), "idempotency_key": _key(cw)})
    assert review.status_code in (200, 201), review.text
    verifier_h = await cw.agent_token(verifier, None)
    async with cw.client(verifier_h) as client:
        result = await client.patch(f"/api/v1/orchestration/reviews/{review.json()['review_id']}",
            json={"status": "approved", "feedback": "Independent evidence checked"})
    assert result.status_code == 200, result.text
    async with cw.client() as client:
        result = await client.patch(f"/api/v1/tasks/{task.id}", json={"status": "done"})
    assert result.status_code == 200, result.text
    async with cw.client(verifier_h) as client:
        result = await client.post(f"/api/v1/missions/{mission.project_id}/criteria/{criterion}:decide",
            json={"status": "proven", "evidence_ref": f"db:project_task:{task.id}",
                  "reason": "Independent criteria verified", "idempotency_key": _key(cw)})
    assert result.status_code == 200, result.text
    assert (await _transition(cw, mission.project_id, "verifying")).status_code == 200
    content = b"Reviewed immutable mission dossier"
    digest = hashlib.sha256(content).hexdigest()
    version = await _doc(cw, checksum=f"sha256:{digest}")
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, mission.project_id)
        relative = f"missions/{mission_documents.project_slug(project.name)}/DOSSIE-DE-VALIDACAO.md"
        (await db.get(ArtifactVersion, version)).location_uri = relative
        await db.commit()
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    async with cw.client() as client:
        result = await client.post(f"/api/v1/missions/{mission.project_id}/dossier",
            json={"artifact_version_id": str(version), "file_sha256": digest})
    assert result.status_code == 201, result.text
    assert (await _transition(cw, mission.project_id, "awaiting_acceptance")).status_code == 200
    yield mission, orch, path, digest
    async with AsyncSessionLocal() as db:
        (await db.get(ProjectMission, mission.project_id)).acceptance_request_id = None
        requests = select(ApprovalRequest.id).where(ApprovalRequest.target_type == "mission_dossier",
                                                   ApprovalRequest.target_id == mission.project_id)
        await db.execute(delete(ApprovalDecisionRecord).where(ApprovalDecisionRecord.approval_request_id.in_(requests)))
        await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id.in_(requests)))
        await db.execute(delete(PolicyEvaluation).where(PolicyEvaluation.target_type == "mission_dossier",
                                                       PolicyEvaluation.target_id == mission.project_id))
        await db.commit()


async def test_acceptance_request_requires_awaiting_acceptance(cw):
    mission = await _mission(cw)
    async with cw.client() as client:
        result = await client.post(f"/api/v1/missions/{mission.project_id}/acceptance:request",
                                   json={"idempotency_key": _key(cw)})
    assert result.status_code == 409, result.text


async def _request(cw, delivery):
    mission, orch, _, _ = delivery
    async with cw.client(orch) as client:
        result = await client.post(f"/api/v1/missions/{mission.project_id}/acceptance:request",
                                   json={"idempotency_key": _key(cw)})
    assert result.status_code == 201, result.text
    return result.json()["approval_request_id"]


async def test_only_human_accepts_exact_delivery_and_replay_is_bound(cw, accepted_delivery):
    mission, orch, _, digest = accepted_delivery
    request_id = await _request(cw, accepted_delivery)
    url = f"/api/v1/governed/approval-requests/{request_id}:decide"
    body = {"decision": "approved", "comments": "Accepted verified delivery", "idempotency_key": _key(cw)}
    async with cw.client(orch) as client:
        refused = await client.post(url, json=body)
    assert refused.status_code == 403, refused.text
    async with cw.client() as client:
        decided = await client.post(url, json=body)
        assert decided.status_code == 200, decided.text
        replay = await client.post(url, json=body)
        assert replay.status_code == 200 and replay.json()["id"] == decided.json()["id"]
        changed = await client.post(url, json={**body, "decision": "rejected"})
        assert changed.status_code == 409, changed.text
    async with AsyncSessionLocal() as db:
        row = await db.get(ProjectMission, mission.project_id)
        assert row.state == "completed" and str(row.acceptance_request_id) == request_id
        assert (await db.get(Project, mission.project_id)).status == "completed"
        assert (await db.get(ApprovalRequest, uuid.UUID(request_id))).target_hash == digest


async def test_changed_dossier_refuses_acceptance(cw, accepted_delivery):
    request_id = await _request(cw, accepted_delivery)
    accepted_delivery[2].write_bytes(b"changed after acceptance request")
    async with cw.client() as client:
        response = await client.post(f"/api/v1/governed/approval-requests/{request_id}:decide",
            json={"decision": "approved", "comments": "Attempt", "idempotency_key": _key(cw)})
    assert response.status_code == 409, response.text
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectMission, accepted_delivery[0].project_id)).state == "awaiting_acceptance"


async def test_rejected_delivery_returns_to_active(cw, accepted_delivery):
    request_id = await _request(cw, accepted_delivery)
    async with cw.client() as client:
        response = await client.post(f"/api/v1/governed/approval-requests/{request_id}:decide",
            json={"decision": "changes_requested", "comments": "Correct the approved scope", "idempotency_key": _key(cw)})
    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as db:
        assert (await db.get(ProjectMission, accepted_delivery[0].project_id)).state == "active"


async def test_changed_task_contract_refuses_acceptance(cw, accepted_delivery):
    from app.core.mission_plan import mission_scope_tasks
    request_id = await _request(cw, accepted_delivery)
    async with AsyncSessionLocal() as db:
        tasks = await mission_scope_tasks(db, accepted_delivery[0].project_id)
        next(iter(tasks.values())).description = "Different delivery contract after submission"
        await db.commit()
    async with cw.client() as client:
        response = await client.post(f"/api/v1/governed/approval-requests/{request_id}:decide",
            json={"decision": "approved", "comments": "Attempt", "idempotency_key": _key(cw)})
    assert response.status_code == 409, response.text
