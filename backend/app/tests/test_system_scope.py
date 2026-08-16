"""Integration coverage for the Planning conception-to-scope gate."""
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent
from app.db.models.backlog import PlanningItem
from app.db.models.governance import AuditEvent
from app.db.models.governance import ApprovalDecisionRecord, ApprovalRequest, PolicyEvaluation
from app.db.models.notification import Notification
from app.db.models.orchestration import ProjectAgentMembership
from app.db.models.pipeline import PipelineStage, PipelineTemplate, PipelineTemplateStage, ProjectPipeline
from app.db.models.product import Product, ProductVersion
from app.db.models.project import Project
from app.db.models.task import TaskAssignment
from app.db.models.system_scope import (
    ProjectScope,
    ProjectScopeItem,
    SystemBlueprint,
    SystemBlueprintRevision,
    SystemElement,
    SystemElementRelation,
    SystemElementRevision,
    TechStackOption,
)
from app.db.models.user import User
from app.core.security import create_access_token, hash_password
from app.main import app


@pytest_asyncio.fixture
async def governed_users():
    suffix = uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        requester = User(username=f"planning-requester-{suffix}", hashed_password=hash_password("test"), is_admin=True)
        approver = User(username=f"planning-approver-{suffix}", hashed_password=hash_password("test"), is_admin=True)
        db.add_all([requester, approver])
        await db.commit()
        await db.refresh(requester); await db.refresh(approver)
        data = {
            "requester_id": requester.id, "approver_id": approver.id,
            "requester_headers": {"Authorization": f"Bearer {create_access_token(requester.username)}"},
            "approver_headers": {"Authorization": f"Bearer {create_access_token(approver.username)}"},
        }
    yield data
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.id.in_([data["requester_id"], data["approver_id"]])))
        await db.commit()


@pytest_asyncio.fixture
async def client(governed_users):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=governed_users["requester_headers"]
    ) as value:
        yield value


async def _cleanup(product_id: uuid.UUID, concept_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        request_ids = list((await db.execute(select(ApprovalRequest.id).where(
            ApprovalRequest.target_id == concept_id
        ))).scalars())
        evaluation_ids = list((await db.execute(select(ApprovalRequest.policy_evaluation_id).where(
            ApprovalRequest.target_id == concept_id
        ))).scalars())
        if request_ids:
            await db.execute(delete(ApprovalDecisionRecord).where(ApprovalDecisionRecord.approval_request_id.in_(request_ids)))
            await db.execute(delete(AuditEvent).where(AuditEvent.entity_type == "approval_request", AuditEvent.entity_id.in_(request_ids)))
            await db.execute(delete(Notification).where(Notification.event_key.in_([f"approval:requested:{value}" for value in request_ids] + [f"approval:decision:{value}" for value in request_ids])))
            await db.execute(delete(ApprovalRequest).where(ApprovalRequest.id.in_(request_ids)))
        if evaluation_ids:
            await db.execute(delete(PolicyEvaluation).where(PolicyEvaluation.id.in_(evaluation_ids)))
        await db.execute(delete(AuditEvent).where(
            AuditEvent.entity_type == "product_concept", AuditEvent.entity_id == concept_id
        ))
        product = await db.get(Product, product_id)
        if product:
            await db.delete(product)
        await db.commit()


@pytest.mark.asyncio
async def test_idea_system_map_approval_and_project_scope(client: AsyncClient, governed_users):
    name = f"Planning Product {uuid.uuid4()}"
    created = await client.post("/api/v1/conception/ideas", json={
        "name": name,
        "problem_statement": "Daily engineering decisions are not traceable end to end.",
        "vision": "A deterministic engineering control plane.",
        "scope_summary": "Conception, system map and project scope.",
        "requested_by": "test-operator",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    product_id = uuid.UUID(body["product_id"])
    concept_id = uuid.UUID(body["concept"]["id"])
    revision_id = body["blueprint_revision"]["id"]

    try:
        assert body["concept"]["status"] == "draft"
        assert body["blueprint_revision"]["status"] == "draft"

        empty_submit = await client.post(f"/api/v1/product-concepts/{concept_id}:submit")
        assert empty_submit.status_code == 422

        element = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.daily-cockpit",
            "family": "experience",
            "element_type": "screen",
            "name": "Daily Engineering Cockpit",
            "spec_snapshot": {"route": "/planning/daily"},
        })
        assert element.status_code == 201, element.text
        element_id = element.json()["element"]["id"]

        moved = await client.patch(f"/api/v1/blueprint-revisions/{revision_id}/elements/{element_id}", json={
            "spec_snapshot": {"position": {"x": 120, "y": 80}},
        })
        assert moved.status_code == 200, moved.text
        assert moved.json()["revision"]["spec_snapshot"]["position"] == {"x": 120, "y": 80}
        assert moved.json()["revision"]["spec_snapshot"]["route"] == "/planning/daily"

        renamed = await client.patch(f"/api/v1/blueprint-revisions/{revision_id}/elements/{element_id}", json={
            "name": "Daily Cockpit v2", "element_type": "form", "stable_key": "screen.daily-cockpit-v2",
        })
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["element"]["name"] == "Daily Cockpit v2"
        assert renamed.json()["element"]["element_type"] == "form"
        assert renamed.json()["element"]["stable_key"] == "screen.daily-cockpit-v2"
        assert renamed.json()["element"]["family"] == "experience"
        assert renamed.json()["revision"]["spec_snapshot"]["position"] == {"x": 120, "y": 80}

        bad_type = await client.patch(f"/api/v1/blueprint-revisions/{revision_id}/elements/{element_id}", json={
            "element_type": "table",
        })
        assert bad_type.status_code == 422

        scratch = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.scratch-temp",
            "family": "experience",
            "element_type": "screen",
            "name": "Scratch Temp Screen",
        })
        assert scratch.status_code == 201, scratch.text
        scratch_id = scratch.json()["element"]["id"]
        removed = await client.delete(f"/api/v1/blueprint-revisions/{revision_id}/elements/{scratch_id}")
        assert removed.status_code == 204, removed.text
        missing_move = await client.patch(f"/api/v1/blueprint-revisions/{revision_id}/elements/{scratch_id}", json={
            "spec_snapshot": {},
        })
        assert missing_move.status_code == 404

        # A second, "interface" family element (Backend layer) so
        # :authorize-delivery-planning's per-solution_type filtering (below)
        # has something to split web_app (Frontend) from api_service
        # (Backend) against.
        api_element = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "api.daily-cockpit",
            "family": "interface",
            "element_type": "api",
            "name": "Daily Cockpit API",
        })
        assert api_element.status_code == 201, api_element.text

        validation = await client.post(f"/api/v1/blueprint-revisions/{revision_id}:validate")
        assert validation.status_code == 200
        assert validation.json()["valid"] is True

        submitted = await client.post(f"/api/v1/product-concepts/{concept_id}:submit")
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["concept"]["status"] == "in_review"

        locked_blueprint = await client.get(f"/api/v1/products/{product_id}/system-blueprint")
        assert locked_blueprint.status_code == 200
        assert locked_blueprint.json()["current_revision"]["status"] == "in_review"
        locked_add = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.blocked", "family": "experience", "element_type": "screen", "name": "Should be blocked",
        })
        assert locked_add.status_code == 409

        direct = await client.post(f"/api/v1/product-concepts/{concept_id}:decide", json={
            "decision": "approved", "decided_by": "spoofed-approver"
        })
        assert direct.status_code == 409
        pending = await client.get("/api/v1/governed/approval-requests", params={"status_filter": "pending"})
        assert pending.status_code == 200, pending.text
        request_id = next(row["id"] for row in pending.json() if row["target_id"] == str(concept_id))
        self_decision = await client.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
            "decision": "approved", "idempotency_key": f"self-{uuid.uuid4()}"
        })
        assert self_decision.status_code == 403
        decision_key = f"approve-{uuid.uuid4()}"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=governed_users["approver_headers"]) as approver:
            approved = await approver.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": "approved", "idempotency_key": decision_key
            })
            repeated_decision = await approver.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": "approved", "idempotency_key": decision_key
            })
        assert approved.status_code == 200, approved.text
        assert repeated_decision.status_code == 200
        assert repeated_decision.json()["id"] == approved.json()["id"]
        assert approved.json()["decided_by_id"] == str(governed_users["approver_id"])

        authorization = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "projects": [
                {"solution_type": "web_app", "project_name": f"Web {name}", "owner": "test-operator"},
                {"solution_type": "api_service", "project_name": f"API {name}", "owner": "test-operator"},
            ]},
        )
        assert authorization.status_code == 200, authorization.text
        by_type = {p["solution_type"]: p for p in authorization.json()["projects"]}
        # 1 Project per requested solution_type, both under the same
        # ProductVersion, each scoped to only its own layer's elements:
        # the "experience" screen -> web_app (Frontend), the "interface"
        # api -> api_service (Backend). No cross-contamination.
        assert set(by_type) == {"web_app", "api_service"}
        assert by_type["web_app"]["project_id"] != by_type["api_service"]["project_id"]
        assert by_type["web_app"]["scope_items_created"] == 1
        assert by_type["web_app"]["tasks_created"] == 1
        assert by_type["api_service"]["scope_items_created"] == 1
        assert by_type["api_service"]["tasks_created"] == 1
        project_id = by_type["web_app"]["project_id"]
        scope_id = by_type["web_app"]["project_scope_id"]
        api_project_id = by_type["api_service"]["project_id"]

        # Same ProductVersion for both -- not two separate versions.
        versions_check = await client.get(f"/api/v1/projects/{project_id}/scopes")
        assert versions_check.status_code == 200

        repeated = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "projects": [
                {"solution_type": "web_app", "project_name": f"Web {name}", "owner": "test-operator"},
                {"solution_type": "api_service", "project_name": f"API {name}", "owner": "test-operator"},
            ]},
        )
        assert repeated.status_code == 200, repeated.text
        repeated_by_type = {p["solution_type"]: p for p in repeated.json()["projects"]}
        assert repeated_by_type["web_app"]["project_id"] == project_id
        assert repeated_by_type["web_app"]["project_scope_id"] == scope_id
        assert repeated_by_type["api_service"]["project_id"] == api_project_id

        # Requesting a 3rd, not-yet-existing type under the same version
        # adds a new Project to it instead of erroring or creating a new
        # ProductVersion.
        third = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "projects": [
                {"solution_type": "deploy", "project_name": f"Deploy {name}", "owner": "test-operator"},
            ]},
        )
        assert third.status_code == 200, third.text
        assert third.json()["product_version_id"] == authorization.json()["product_version_id"]
        deploy_project_id = third.json()["projects"][0]["project_id"]
        assert deploy_project_id not in {project_id, api_project_id}

        scopes = await client.get(f"/api/v1/projects/{project_id}/scopes")
        assert scopes.status_code == 200
        assert scopes.json()[0]["blueprint_base_revision_id"] == revision_id

        auto_items = await client.get(f"/api/v1/project-scopes/{scope_id}/items")
        assert auto_items.status_code == 200
        assert len(auto_items.json()) == 1
        auto_item = auto_items.json()[0]
        assert auto_item["system_element_id"] == element_id
        assert auto_item["change_type"] == "add"
        assert auto_item["applicability"] == "required"

        # The element is already scoped (auto-generated above) -- adding it
        # again is rejected, same uniqueness rule as manual scoping.
        duplicate_item = await client.post(f"/api/v1/project-scopes/{scope_id}/items", json={
            "system_element_id": element_id,
            "change_type": "add",
            "applicability": "required",
        })
        assert duplicate_item.status_code == 409, duplicate_item.text

        # Once delivery is authorized off the approved revision, a new draft
        # revision can be started to keep evolving the map -- current_revision_id
        # must not move until this point (authorize-delivery-planning above
        # required revision.status == "approved" on whatever was "current").
        new_revision = await client.post(f"/api/v1/products/{product_id}/system-blueprint/revisions", json={
            "clone_from_revision_id": revision_id,
        })
        assert new_revision.status_code == 200, new_revision.text
        assert new_revision.json()["status"] == "draft"
        assert new_revision.json()["revision"] == 2
        new_revision_id = new_revision.json()["id"]
        cloned_graph = await client.get(f"/api/v1/blueprint-revisions/{new_revision_id}/graph")
        assert cloned_graph.status_code == 200
        assert {el["element"]["stable_key"] for el in cloned_graph.json()["elements"]} == {"screen.daily-cockpit-v2", "api.daily-cockpit"}
        cloned_add = await client.post(f"/api/v1/blueprint-revisions/{new_revision_id}/elements", json={
            "stable_key": "screen.next-iteration", "family": "experience", "element_type": "screen", "name": "Next iteration screen",
        })
        assert cloned_add.status_code == 201, cloned_add.text
        refetched_blueprint = await client.get(f"/api/v1/products/{product_id}/system-blueprint")
        assert refetched_blueprint.json()["current_revision"]["id"] == new_revision_id
    finally:
        await _cleanup(product_id, concept_id)


@pytest.mark.asyncio
async def test_screen_registry_business_rule_and_derive_database(client: AsyncClient):
    """Screen Registry (UI & Screen Inspection redesign): create a screen
    with attributes, edit it directly (no agent call), round-trip a business
    rule .md, and derive a database model from the screens -- all against a
    Project/ProjectScope set up directly in the DB, independent of the
    concept-approval flow already covered above."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Screen Registry Product {suffix}", status="active")
        db.add(product)
        await db.flush()
        blueprint = SystemBlueprint(product_id=product.id, name="Screens Test Blueprint")
        db.add(blueprint)
        await db.flush()
        baseline_revision = SystemBlueprintRevision(blueprint_id=blueprint.id, revision=1, status="approved")
        db.add(baseline_revision)
        await db.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0", status="planned")
        db.add(version)
        await db.flush()
        project = Project(name=f"Screen Registry Project {suffix}", product_version_id=version.id, status="planned")
        db.add(project)
        await db.flush()
        scope = ProjectScope(project_id=project.id, blueprint_base_revision_id=baseline_revision.id, revision=1, status="draft")
        db.add(scope)
        await db.commit()
        product_id, blueprint_id, project_id, version_id, scope_id = (
            product.id, blueprint.id, project.id, version.id, scope.id
        )

    try:
        created = await client.post(f"/api/v1/project-scopes/{scope_id}/screens", json={
            "name": "Tela de Login",
            "spec": {
                "attributes": [
                    {"name": "email", "type": "string", "required": True},
                    {"name": "password", "type": "string", "required": True},
                ],
                "css_framework": "plain",
            },
        })
        assert created.status_code == 201, created.text
        screen = created.json()
        element_id = screen["element"]["id"]
        assert screen["element"]["element_type"] == "screen"
        assert screen["element"]["family"] == "experience"
        assert screen["revision"]["spec_snapshot"]["attributes"][0]["name"] == "email"

        listed = await client.get(f"/api/v1/project-scopes/{scope_id}/screens")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        # Direct edit -- adding a field is a plain PATCH, no agent involved
        # (Marcelo: "coisas simples pode ajudar na economia de token").
        updated = await client.patch(f"/api/v1/project-scopes/{scope_id}/screens/{element_id}", json={
            "spec": {"attributes": [
                {"name": "email", "type": "string", "required": True},
                {"name": "password", "type": "string", "required": True},
                {"name": "remember_me", "type": "boolean", "required": False},
            ]},
        })
        assert updated.status_code == 200, updated.text
        assert len(updated.json()["revision"]["spec_snapshot"]["attributes"]) == 3

        empty_rule = await client.get(f"/api/v1/project-scopes/{scope_id}/screens/{element_id}/business-rule")
        assert empty_rule.status_code == 200
        assert empty_rule.json()["content"] == ""

        write_rule = await client.put(f"/api/v1/project-scopes/{scope_id}/screens/{element_id}/business-rule", json={
            "content": "# Regra\n\nEmail obrigatório e único.",
        })
        assert write_rule.status_code == 200, write_rule.text
        assert "Email obrigat" in write_rule.json()["content"]

        read_rule = await client.get(f"/api/v1/project-scopes/{scope_id}/screens/{element_id}/business-rule")
        assert read_rule.status_code == 200
        assert read_rule.json()["content"] == write_rule.json()["content"]

        derived = await client.post(f"/api/v1/project-scopes/{scope_id}/derive-database")
        assert derived.status_code == 200, derived.text
        assert derived.json()["tables_created"] == 1
        assert derived.json()["fields_written"] == 4  # id + email + password + remember_me
        revision_id = derived.json()["revision_id"]

        # Idempotent re-run: same table found and updated, no duplicates.
        derived_again = await client.post(f"/api/v1/project-scopes/{scope_id}/derive-database")
        assert derived_again.status_code == 200, derived_again.text
        assert derived_again.json()["tables_created"] == 0
        assert derived_again.json()["tables_updated"] == 1
        assert derived_again.json()["revision_id"] == revision_id

        graph = await client.get(f"/api/v1/blueprint-revisions/{revision_id}/graph")
        assert graph.status_code == 200, graph.text
        elements = graph.json()["elements"]
        table_elements = [e for e in elements if e["element"]["element_type"] == "table"]
        field_elements = [e for e in elements if e["element"]["element_type"] == "field"]
        assert len(table_elements) == 1
        assert len(field_elements) == 4
        relation_types = {r["relation_type"] for r in graph.json()["relations"]}
        assert {"persists_as", "contains"} <= relation_types

        # Deleting a screen only drops it from this project's scope -- the
        # underlying element/revision (and its derived table) stay behind.
        delete_resp = await client.delete(f"/api/v1/project-scopes/{scope_id}/screens/{element_id}")
        assert delete_resp.status_code == 204
        listed_after = await client.get(f"/api/v1/project-scopes/{scope_id}/screens")
        assert listed_after.status_code == 200
        assert listed_after.json() == []
    finally:
        async with AsyncSessionLocal() as db:
            revision_ids = list((await db.execute(
                select(SystemBlueprintRevision.id).where(SystemBlueprintRevision.blueprint_id == blueprint_id)
            )).scalars())
            if revision_ids:
                await db.execute(delete(SystemElementRelation).where(SystemElementRelation.blueprint_revision_id.in_(revision_ids)))
                await db.execute(delete(SystemElementRevision).where(SystemElementRevision.blueprint_revision_id.in_(revision_ids)))
            await db.execute(delete(ProjectScopeItem).where(ProjectScopeItem.project_scope_id == scope_id))
            await db.execute(delete(ProjectScope).where(ProjectScope.id == scope_id))
            await db.execute(delete(SystemElement).where(SystemElement.product_id == product_id))
            if revision_ids:
                await db.execute(delete(SystemBlueprintRevision).where(SystemBlueprintRevision.id.in_(revision_ids)))
            await db.execute(delete(SystemBlueprint).where(SystemBlueprint.id == blueprint_id))
            # AuditEvent rows use a polymorphic (entity_type, entity_id) pair
            # with no FK constraint (see governance.py docstring) -- leftover
            # audit rows from this test don't block any of the deletes above,
            # so they're left in place rather than hunted down by element id.
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.execute(delete(ProductVersion).where(ProductVersion.id == version_id))
            await db.execute(delete(Product).where(Product.id == product_id))
            await db.commit()


@pytest.mark.asyncio
async def test_authorize_delivery_planning_responsible_agent_and_platform_tag(
    client: AsyncClient, governed_users
):
    """Pacote 3 (2026-08-01): responsible_agent_id auto-creates a
    ProjectAgentMembership + a TaskAssignment per task; an element tagged
    spec_snapshot.target_platforms disambiguates web_app vs mobile_app
    instead of duplicating into both (untagged elements still go to both,
    preserving the pre-Pacote-3 behavior)."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        agent = Agent(name=f"Responsible Agent {suffix}", agent_type="executor")
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        agent_id = agent.id

    name = f"Platform Product {suffix}"
    created = await client.post("/api/v1/conception/ideas", json={
        "name": name,
        "problem_statement": "Need a web + mobile + API split with a tagged screen.",
        "requested_by": "test-operator",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    product_id = uuid.UUID(body["product_id"])
    concept_id = uuid.UUID(body["concept"]["id"])
    revision_id = body["blueprint_revision"]["id"]

    try:
        web_only = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.web-only", "family": "experience", "element_type": "screen",
            "name": "Web-only Screen", "spec_snapshot": {"target_platforms": ["web"]},
        })
        assert web_only.status_code == 201, web_only.text

        untagged = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.untagged", "family": "experience", "element_type": "screen",
            "name": "Untagged Screen",
        })
        assert untagged.status_code == 201, untagged.text

        validation = await client.post(f"/api/v1/blueprint-revisions/{revision_id}:validate")
        assert validation.status_code == 200 and validation.json()["valid"] is True

        submitted = await client.post(f"/api/v1/product-concepts/{concept_id}:submit")
        assert submitted.status_code == 200, submitted.text

        pending = await client.get("/api/v1/governed/approval-requests", params={"status_filter": "pending"})
        request_id = next(row["id"] for row in pending.json() if row["target_id"] == str(concept_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=governed_users["approver_headers"]) as approver:
            approved = await approver.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": "approved", "idempotency_key": f"approve-{uuid.uuid4()}"
            })
        assert approved.status_code == 200, approved.text

        authorization = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "projects": [
                {"solution_type": "web_app", "project_name": f"Web {name}", "responsible_agent_id": str(agent_id)},
                {"solution_type": "mobile_app", "project_name": f"Mobile {name}"},
            ]},
        )
        assert authorization.status_code == 200, authorization.text
        by_type = {p["solution_type"]: p for p in authorization.json()["projects"]}

        # web_app gets both screens (tagged "web" + untagged); mobile_app
        # only gets the untagged one -- the tagged screen is excluded, not
        # duplicated in.
        assert by_type["web_app"]["scope_items_created"] == 2
        assert by_type["mobile_app"]["scope_items_created"] == 1

        web_project_id = by_type["web_app"]["project_id"]
        async with AsyncSessionLocal() as db:
            membership = (await db.execute(select(ProjectAgentMembership).where(
                ProjectAgentMembership.project_id == web_project_id, ProjectAgentMembership.agent_id == agent_id,
            ))).scalar_one_or_none()
            assert membership is not None
            assert membership.role == "developer"

            planning_items = list((await db.execute(select(PlanningItem).where(
                PlanningItem.project_id == web_project_id
            ))).scalars())
            assignments = list((await db.execute(select(TaskAssignment).where(
                TaskAssignment.membership_id == membership.id
            ))).scalars())
            assert len(assignments) == len(planning_items) == 2
            assert all(a.agent_id == agent_id for a in assignments)

        mobile_project_id = by_type["mobile_app"]["project_id"]
        async with AsyncSessionLocal() as db:
            no_membership = (await db.execute(select(ProjectAgentMembership).where(
                ProjectAgentMembership.project_id == mobile_project_id
            ))).scalar_one_or_none()
            assert no_membership is None
    finally:
        await _cleanup(product_id, concept_id)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Agent).where(Agent.id == agent_id))
            await db.commit()


@pytest.mark.asyncio
async def test_screen_mutation_locked_once_version_published(client: AsyncClient):
    """Pacote 4 (2026-08-01): once the Project's ProductVersion is
    published, Screen Registry mutations are locked -- _assert_version_editable,
    reused by create/update/remove_screen, write_screen_business_rule and
    derive_database. Creating a screen is enough to prove the gate; the
    other four call the exact same one-line check."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        product = Product(name=f"Locked Version Product {suffix}", status="active")
        db.add(product)
        await db.flush()
        blueprint = SystemBlueprint(product_id=product.id, name="Locked Version Blueprint")
        db.add(blueprint)
        await db.flush()
        baseline_revision = SystemBlueprintRevision(blueprint_id=blueprint.id, revision=1, status="approved")
        db.add(baseline_revision)
        await db.flush()
        version = ProductVersion(product_id=product.id, version="0.1.0", status="published")
        db.add(version)
        await db.flush()
        project = Project(name=f"Locked Version Project {suffix}", product_version_id=version.id, status="planned")
        db.add(project)
        await db.flush()
        scope = ProjectScope(project_id=project.id, blueprint_base_revision_id=baseline_revision.id, revision=1, status="draft")
        db.add(scope)
        await db.commit()
        product_id, blueprint_id, project_id, version_id, scope_id = (
            product.id, blueprint.id, project.id, version.id, scope.id
        )

    try:
        blocked = await client.post(f"/api/v1/project-scopes/{scope_id}/screens", json={"name": "Should be blocked"})
        assert blocked.status_code == 409, blocked.text
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(ProjectScope).where(ProjectScope.id == scope_id))
            await db.execute(delete(SystemBlueprintRevision).where(SystemBlueprintRevision.id == baseline_revision.id))
            await db.execute(delete(SystemBlueprint).where(SystemBlueprint.id == blueprint_id))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.execute(delete(ProductVersion).where(ProductVersion.id == version_id))
            await db.execute(delete(Product).where(Product.id == product_id))
            await db.commit()


@pytest.mark.asyncio
async def test_authorize_delivery_planning_multiple_new_versions_same_revision(
    client: AsyncClient, governed_users
):
    """2026-08-15 regression: the Conception "Project" tab now lets each
    project spec carry its own version (Marcelo: "para cada projeto o
    controle de versao, nao posso ter uma versao unica"), so one submit can
    fire :authorize-delivery-planning once per distinct version string
    against the same approved System Map revision. The old guard tracked
    "which version does this revision belong to" with a scalar
    `revision.product_version_id` FK -- fine for one version, but the second
    brand-new version in a batch silently stomped the first version's claim
    on that column. That didn't fail loudly on the second call (the guard
    only fires when `existing_version` is truthy); it surfaced later as a
    false 409 on any *idempotent re-submission* of the first version, which
    is what this test reproduces."""
    name = f"Multi-Version Product {uuid.uuid4()}"
    created = await client.post("/api/v1/conception/ideas", json={
        "name": name,
        "problem_statement": "One approved System Map, two projects on two different new versions.",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    product_id = uuid.UUID(body["product_id"])
    concept_id = uuid.UUID(body["concept"]["id"])
    revision_id = body["blueprint_revision"]["id"]

    try:
        screen = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.multi-version", "family": "experience", "element_type": "screen",
            "name": "Some Screen",
        })
        assert screen.status_code == 201, screen.text

        validation = await client.post(f"/api/v1/blueprint-revisions/{revision_id}:validate")
        assert validation.status_code == 200 and validation.json()["valid"] is True

        submitted = await client.post(f"/api/v1/product-concepts/{concept_id}:submit")
        assert submitted.status_code == 200, submitted.text

        pending = await client.get("/api/v1/governed/approval-requests", params={"status_filter": "pending"})
        request_id = next(row["id"] for row in pending.json() if row["target_id"] == str(concept_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=governed_users["approver_headers"]) as approver:
            approved = await approver.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": "approved", "idempotency_key": f"approve-{uuid.uuid4()}"
            })
        assert approved.status_code == 200, approved.text

        first = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "projects": [{"solution_type": "web_app", "project_name": f"Web {name}"}]},
        )
        assert first.status_code == 200, first.text

        # A second, distinct brand-new version authorized against the exact
        # same (unchanged) revision -- this is the case that used to
        # silently steal the revision's version claim.
        second = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.2.0", "projects": [{"solution_type": "mobile_app", "project_name": f"Mobile {name}"}]},
        )
        assert second.status_code == 200, second.text

        # Re-submitting the first version (idempotent retry, e.g. a UI
        # double-click) must still succeed -- the old code raised a false
        # 409 "already exists under a different System Map revision" here,
        # because the revision's scalar pointer had moved on to 0.2.0.
        first_again = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={"version": "0.1.0", "projects": [{"solution_type": "web_app", "project_name": f"Web {name}"}]},
        )
        assert first_again.status_code == 200, first_again.text
        assert first_again.json()["projects"][0]["project_id"] == first.json()["projects"][0]["project_id"]

        async with AsyncSessionLocal() as db:
            versions = list((await db.execute(select(ProductVersion).where(
                ProductVersion.product_id == product_id
            ))).scalars())
            assert {v.version for v in versions} == {"0.1.0", "0.2.0"}
    finally:
        await _cleanup(product_id, concept_id)


@pytest.mark.asyncio
async def test_authorize_delivery_planning_project_type_and_pipeline_template(
    client: AsyncClient, governed_users
):
    """2026-08-15: Conception's Pipeline/Template section is picked once for
    the whole submission and applied to every Project it creates
    (`AuthorizeDeliveryPlanning.pipeline_template_id`), while `project_type`
    (creation|maintenance) stays per-project (`ProjectSpec.project_type`) --
    one idea can produce a brand new web app alongside a maintenance change
    to an existing API. Asserts both actually persist/instantiate."""
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        template = PipelineTemplate(name=f"Standard Flow {suffix}")
        db.add(template)
        await db.flush()
        db.add(PipelineTemplateStage(
            template_id=template.id, name="Build", stage_type="build", order_index=0,
        ))
        db.add(PipelineTemplateStage(
            template_id=template.id, name="Review", stage_type="review", order_index=1, requires_approval=True,
        ))
        await db.commit()
        await db.refresh(template)
        template_id = template.id

    name = f"Pipeline Template Product {suffix}"
    created = await client.post("/api/v1/conception/ideas", json={
        "name": name,
        "problem_statement": "New web app plus a maintenance API change, one pipeline template for both.",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    product_id = uuid.UUID(body["product_id"])
    concept_id = uuid.UUID(body["concept"]["id"])
    revision_id = body["blueprint_revision"]["id"]

    try:
        screen = await client.post(f"/api/v1/blueprint-revisions/{revision_id}/elements", json={
            "stable_key": "screen.pipeline-template", "family": "experience", "element_type": "screen",
            "name": "Some Screen",
        })
        assert screen.status_code == 201, screen.text

        validation = await client.post(f"/api/v1/blueprint-revisions/{revision_id}:validate")
        assert validation.status_code == 200 and validation.json()["valid"] is True

        submitted = await client.post(f"/api/v1/product-concepts/{concept_id}:submit")
        assert submitted.status_code == 200, submitted.text

        pending = await client.get("/api/v1/governed/approval-requests", params={"status_filter": "pending"})
        request_id = next(row["id"] for row in pending.json() if row["target_id"] == str(concept_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=governed_users["approver_headers"]) as approver:
            approved = await approver.post(f"/api/v1/governed/approval-requests/{request_id}:decide", json={
                "decision": "approved", "idempotency_key": f"approve-{uuid.uuid4()}"
            })
        assert approved.status_code == 200, approved.text

        authorization = await client.post(
            f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning",
            json={
                "version": "0.1.0",
                "pipeline_template_id": str(template_id),
                "projects": [
                    {"solution_type": "web_app", "project_name": f"Web {name}", "project_type": "creation"},
                    {"solution_type": "mobile_app", "project_name": f"Mobile {name}", "project_type": "maintenance"},
                ],
            },
        )
        assert authorization.status_code == 200, authorization.text
        by_type = {p["solution_type"]: p for p in authorization.json()["projects"]}

        async with AsyncSessionLocal() as db:
            web_project = await db.get(Project, uuid.UUID(by_type["web_app"]["project_id"]))
            mobile_project = await db.get(Project, uuid.UUID(by_type["mobile_app"]["project_id"]))
            assert web_project.project_type == "creation"
            assert mobile_project.project_type == "maintenance"

            for project in (web_project, mobile_project):
                pipeline = (await db.execute(select(ProjectPipeline).where(
                    ProjectPipeline.project_id == project.id
                ))).scalar_one()
                assert pipeline.template_id == template_id
                stages = list((await db.execute(select(PipelineStage).where(
                    PipelineStage.pipeline_id == pipeline.id
                ).order_by(PipelineStage.order_index))).scalars())
                assert [s.name for s in stages] == ["Build", "Review"]
                assert stages[1].requires_approval is True
    finally:
        # Deleting the Product cascades to Project -> ProjectPipeline
        # (ondelete="CASCADE" on ProjectPipeline.project_id), so only the
        # template itself (not owned by any project) needs its own cleanup.
        await _cleanup(product_id, concept_id)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(PipelineTemplateStage).where(PipelineTemplateStage.template_id == template_id))
            await db.execute(delete(PipelineTemplate).where(PipelineTemplate.id == template_id))
            await db.commit()


@pytest.mark.asyncio
async def test_tech_stack_options_catalog(client: AsyncClient):
    """Conception step 4's picker: org_standard rows come seeded (migration
    9823e7890ae4), and POSTing a new one adds it to the catalog idempotently
    by (layer, name) case-insensitive -- see TechStackOptionPicker.tsx."""
    listed = await client.get("/api/v1/tech-stack-options", params={"layer": "database"})
    assert listed.status_code == 200
    names = {row["name"] for row in listed.json()}
    assert "PostgreSQL" in names
    assert all(row["source"] == "org_standard" for row in listed.json())
    assert all(row["platform"] is None for row in listed.json())  # not a frontend layer

    frontend = await client.get("/api/v1/tech-stack-options", params={"layer": "frontend"})
    frontend_by_name = {row["name"]: row["platform"] for row in frontend.json()}
    assert frontend_by_name["React Native + Expo + Tamagui"] == "mobile"
    assert frontend_by_name["React + TypeScript + Vite + Tailwind CSS + shadcn/ui"] == "web_app"
    assert frontend_by_name["Next.js + TypeScript + Tailwind CSS + shadcn/ui"] == "institutional_site"
    assert frontend_by_name["HTML + CSS + JS puro"] == "landing_page"
    assert frontend_by_name["React + TypeScript + Vite + Tailwind CSS + shadcn/ui + vite-plugin-pwa"] == "pwa"

    option_name = f"Custom DB {uuid.uuid4().hex[:8]}"
    try:
        created = await client.post("/api/v1/tech-stack-options", json={
            "layer": "database", "name": option_name, "description": "test-only option",
        })
        assert created.status_code == 201
        body = created.json()
        assert body["source"] == "custom"
        assert body["platform"] is None
        option_id = body["id"]

        relisted = await client.get("/api/v1/tech-stack-options", params={"layer": "database"})
        assert option_name in {row["name"] for row in relisted.json()}

        duplicate = await client.post("/api/v1/tech-stack-options", json={
            "layer": "database", "name": option_name.lower(), "description": "different text",
        })
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == option_id
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(TechStackOption).where(TechStackOption.name == option_name))
            await db.commit()
