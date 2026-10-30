"""M0.2c §6: the mission dispatch body is built only from the allowlist
(MCP_MISSION_TOOLS_SPEC.md §6, §9.6).

Fictitious canaries are planted where the builder must never look: a personal
note (Maia), a client name snapshot on the product (Lara), a Knowledge Base
file, another task's text and result, and a non-objective section of the
brief. None may reach the demand body nor the prompt given to the (simulated)
runner. Test database only; the Docs tree is a temporary directory.
"""
import uuid

import pytest
from sqlalchemy import select, text

from app.core import mission_documents
from app.core.mission_dispatch import MISSION_CONTEXT_MAX_BYTES, objective_section
from app.db.base import AsyncSessionLocal
from app.db.models.artifact import ArtifactVersion
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent
from app.db.models.mission import ProjectMission
from app.db.models.personal import PersonalNote
from app.db.models.product import Product
from app.db.models.task import ProjectTask, TaskDependency
from app.tests.test_mission_base import _criterion, _task
from app.tests import test_mission_dispatch as m02c
from app.tests.test_task_baseline_guard import _code, _executions, _mission, _update

# The same fixtures as test_mission_dispatch (simulated runner, mission switch on).
runner = m02c.runner
world = m02c.world


def _canary(kind: str) -> str:
    return f"CANARY-{kind}-{uuid.uuid4()}"


async def _dispatch(world, task_id):
    async with world.client() as client:
        return await client.post(f"/api/v1/tasks/{task_id}/dispatch", json={})


async def _demand(response) -> AgentDemand:
    async with AsyncSessionLocal() as db:
        return await db.get(AgentDemand, uuid.UUID(response.json()["demand_id"]))


async def _brief_file(tmp_path, monkeypatch, mission, content: str) -> None:
    monkeypatch.setattr(mission_documents, "MISSION_DOCS_ROOT", tmp_path)
    async with AsyncSessionLocal() as db:
        brief_id = (await db.get(ProjectMission, mission.project_id)).brief_artifact_id
        version = (await db.execute(select(ArtifactVersion).where(ArtifactVersion.artifact_id == brief_id))).scalar_one()
        path = tmp_path / "missions" / f"m02c-{uuid.uuid4().hex[:6]}" / "BRIEF.md"
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        version.location_uri = str(path.relative_to(tmp_path))
        await db.commit()


@pytest.mark.asyncio
async def test_canaries_absent(world, runner, tmp_path, monkeypatch):
    mission = await _mission(world)
    maia, lara, kb, other, brief_secret = (_canary(k) for k in ("MAIA", "LARA", "KB", "OTHER", "BRIEF"))
    async with AsyncSessionLocal() as db:
        note = PersonalNote(title="m02c fictitious note", content=f"recado {maia}")
        db.add(note)
        product = await db.get(Product, world.product_id)
        product.darckware_client_name = lara
        await db.commit()
        note_id = note.id
    kb_file = tmp_path / "knowledge_base" / "fixture.md"
    kb_file.parent.mkdir(parents=True)
    kb_file.write_text(f"KB fixture {kb}", encoding="utf-8")
    await _brief_file(tmp_path, monkeypatch, mission,
                      f"# Brief\n\n## Contexto\n{brief_secret}\n\n## Objetivo\nEntregar o fluxo X.\n\n## Riscos\n{brief_secret}\n")
    sibling = await mission.task("sibling", description=f"sibling text {other}")
    async with AsyncSessionLocal() as db:
        db.add(AgentDemand(from_agent="test", subject="m02c sibling result", body=other, origin_type="task",
                           origin_id=sibling.id, dispatch_status="completed", dispatch_result=other,
                           working_path="/srv/forgehub-test/m02c"))
        await db.commit()
    await _update(ProjectTask, sibling.id, status="done")
    task = await mission.task("guarded", description="the real work")
    async with AsyncSessionLocal() as db:
        db.add(TaskDependency(task_id=task.id, depends_on_task_id=sibling.id))
        await db.commit()
    await _criterion(mission.project_id, mission.executor, task_ids=[task.id])
    await mission.baseline([sibling.id, task.id])
    try:
        response = await _dispatch(world, task.id)
        assert response.status_code == 200, response.text
        demand = await _demand(response)
        for canary in (maia, lara, kb, other, brief_secret):
            assert canary not in demand.body
            assert all(canary not in prompt for prompt in runner.prompts)
        assert "Entregar o fluxo X." in demand.body and "#" in demand.body and "sibling (done)" in demand.body
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM company.personal_notes WHERE id = :id"), {"id": note_id})
            await db.commit()


@pytest.mark.asyncio
async def test_manifest_lists_every_source(world, runner, tmp_path, monkeypatch):
    mission = await _mission(world)
    await _brief_file(tmp_path, monkeypatch, mission, "## Objective\nShip it.\n")
    before = await mission.task("before")
    await _update(ProjectTask, before.id, status="done")
    task = await mission.task("manifest", plan_brief="step by step")
    async with AsyncSessionLocal() as db:
        db.add(TaskDependency(task_id=task.id, depends_on_task_id=before.id))
        await db.commit()
    await _criterion(mission.project_id, mission.executor, task_ids=[task.id])
    await mission.baseline([before.id, task.id])
    response = await _dispatch(world, task.id)
    assert response.status_code == 200, response.text
    async with AsyncSessionLocal() as db:
        audit = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task.id, AuditEvent.event_type == "task.dispatched"))).scalar_one()
    manifest = audit.payload["context_manifest"]
    assert {"project_task", "mission", "plan_baseline_item", "brief_objective", "mission_acceptance_criterion",
            "task_dependency", "project_agent_membership", "working_path", "instructions"} <= {
        entry["source"] for entry in manifest}
    assert all(len(entry["hash"]) == 64 for entry in manifest)
    assert next(e for e in manifest if e["source"] == "project_task")["id"] == str(task.id)


@pytest.mark.asyncio
async def test_context_too_large_refused(world, runner):
    mission = await _mission(world)
    task = await mission.task("huge", plan_brief="x" * (MISSION_CONTEXT_MAX_BYTES + 1))
    await mission.baseline([task.id])
    response = await _dispatch(world, task.id)
    assert response.status_code == 422 and _code(response) == "CONTEXT_TOO_LARGE", response.text
    assert response.json()["detail"]["size_bytes"] > MISSION_CONTEXT_MAX_BYTES
    # Never truncated, never half-dispatched.
    assert await _executions(task.id) == 0 and runner.runs == []


@pytest.mark.asyncio
async def test_common_task_body_unchanged(world, runner):
    project = await world.common_project()
    task = await _task(project["id"], "common", description="plain description", plan_brief="plain plan")
    agent = await world.agent("common")
    async with world.client() as client:
        await client.patch(f"/api/v1/projects/{project['id']}",
                           json={"working_directory_path": "/srv/forgehub-test/m02c-common"})
        response = await client.post(f"/api/v1/tasks/{task.id}/dispatch", json={"target_agent_id": str(agent)})
    assert response.status_code == 200, response.text
    demand = await _demand(response)
    async with AsyncSessionLocal() as db:
        number = (await db.get(ProjectTask, task.id)).number
    assert demand.body == "\n\n".join([
        f"Task #{number}: common", "plain description", "Plano/abordagem:\nplain plan",
        "Tipo: feature | Prioridade: medium | Status atual: planned",
        "Ao concluir, declare a evidência numa linha própria no formato "
        "'EVIDENCE: <ref>', onde <ref> é um dos:\n"
        "- file:<caminho relativo ao projeto> (arquivo que você criou/alterou)\n"
        "- git:<sha> (commit que contém a mudança)\n"
        "- db:<entity_type>:<uuid> (registro real que você criou, ex: db:project:...)\n"
        "Sem essa linha, a execução fica pendente de verificação manual.",
    ])
    async with AsyncSessionLocal() as db:
        audit = (await db.execute(select(AuditEvent).where(
            AuditEvent.entity_id == task.id, AuditEvent.event_type == "task.dispatched"))).scalar_one()
    assert "context_manifest" not in audit.payload


def test_objective_section_only():
    brief = "# B\n## Objetivo\nA\n### Detalhe\nB\n## Riscos\nC\n"
    assert objective_section(brief) == "A\n### Detalhe\nB"
    assert objective_section("# B\n## Escopo\nnada") is None
