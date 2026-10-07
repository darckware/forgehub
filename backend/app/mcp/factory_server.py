#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp[cli]>=1.2.0,<2", "httpx>=0.27"]
# ///
"""Unified ForgeHub MCP: canonical Messages plus Software Factory tools.

The canonical Messages MCP owns its twelve tools. This module loads that
server and registers nine factory tools on the same FastMCP instance, yielding
the 21-tool ``forgehub`` catalog documented by Foundation.

Factory reads and task mutations require ``FORGEHUB_AGENT_TOKEN`` (an
``agt_`` AgentServiceCredential). Messages continues to use its narrowly
scoped bridge token. API failures are always surfaced as tool errors.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MESSAGES_SERVER_PATH = REPOSITORY_ROOT / "host-bridge" / "forgehub_messages_mcp.py"


def _load_messages_server():
    spec = importlib.util.spec_from_file_location("forgehub_messages_mcp", MESSAGES_SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load canonical Messages MCP from {MESSAGES_SERVER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


messages = _load_messages_server()
mcp = messages.mcp
BASE_URL = os.environ.get("FORGEHUB_API_URL", "http://localhost:8000").rstrip("/")


class FactoryError(Exception):
    """A safe, actionable error intended for the calling agent."""


def _agent_token() -> str:
    token = os.environ.get("FORGEHUB_AGENT_TOKEN", "").strip()
    if not token:
        raise FactoryError(
            "FORGEHUB_AGENT_TOKEN is required for Software Factory tools; "
            "configure an active agt_ AgentServiceCredential."
        )
    if not token.startswith("agt_"):
        raise FactoryError("FORGEHUB_AGENT_TOKEN must be an agt_ AgentServiceCredential.")
    return token


async def _factory_call(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
) -> Any:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{BASE_URL}{path}",
                headers={"Authorization": f"Bearer {_agent_token()}"},
                json=json,
            )
    except httpx.HTTPError as exc:
        raise FactoryError(f"ForgeHub API is unavailable: {exc}") from exc
    if response.is_error:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise FactoryError(f"ForgeHub {method} {path} failed ({response.status_code}): {detail}")
    if response.status_code == 204:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise FactoryError(f"ForgeHub {method} {path} returned invalid JSON") from exc


def _query(path: str, **params: str | None) -> str:
    values = {key: value for key, value in params.items() if value is not None}
    return f"{path}?{urlencode(values)}" if values else path


async def _latest_project_scope(project_id: str) -> dict[str, Any]:
    scopes = await _factory_call("GET", f"/api/v1/projects/{project_id}/scopes")
    if not scopes:
        raise FactoryError(f"Project {project_id} has no authorized ProjectScope.")
    return max(scopes, key=lambda scope: (scope.get("revision", 0), scope.get("created_at", "")))


@mcp.tool()
async def list_projects(status: str | None = None) -> dict[str, Any]:
    """List canonical Software Factory projects, optionally filtered by status."""
    projects = await _factory_call("GET", "/api/v1/projects")
    if status is not None:
        projects = [project for project in projects if project.get("status") == status]
    return {"projects": projects, "total": len(projects)}


@mcp.tool()
async def get_project_context(project_id: str) -> dict[str, Any]:
    """Get a Project with its Product and target ProductVersion."""
    project = await _factory_call("GET", f"/api/v1/projects/{project_id}")
    products = await _factory_call("GET", "/api/v1/products")
    version_id = project.get("product_version_id")
    for product in products:
        version = next(
            (item for item in product.get("versions", []) if item.get("id") == version_id),
            None,
        )
        if version is not None:
            return {"project": project, "product": product, "target_version": version}
    raise FactoryError(
        f"Project {project_id} references ProductVersion {version_id}, but its Product was not found."
    )


@mcp.tool()
async def list_project_screens(project_id: str) -> dict[str, Any]:
    """List screens in the latest canonical ProjectScope."""
    scope = await _latest_project_scope(project_id)
    screens = await _factory_call("GET", f"/api/v1/project-scopes/{scope['id']}/screens")
    return {"project_id": project_id, "project_scope": scope, "screens": screens}


@mcp.tool()
async def get_project_erd(project_id: str) -> dict[str, Any]:
    """Get database elements and relationships from the scope's blueprint graph."""
    scope = await _latest_project_scope(project_id)
    graph = await _factory_call(
        "GET", f"/api/v1/blueprint-revisions/{scope['blueprint_base_revision_id']}/graph"
    )
    elements = [
        row for row in graph.get("elements", [])
        if row.get("element", {}).get("family") == "database"
    ]
    element_ids = {row.get("element", {}).get("id") for row in elements}
    relations = [
        row for row in graph.get("relations", [])
        if row.get("from_element_id") in element_ids or row.get("to_element_id") in element_ids
    ]
    return {
        "project_id": project_id,
        "project_scope_id": scope["id"],
        "blueprint_revision_id": scope["blueprint_base_revision_id"],
        "elements": elements,
        "relationships": relations,
    }


@mcp.tool()
async def list_planning_items(project_id: str, status: str | None = None) -> dict[str, Any]:
    """List canonical planning items for a Project."""
    items = await _factory_call(
        "GET", _query("/api/v1/planning-items", project_id=project_id, status_filter=status)
    )
    return {"project_id": project_id, "planning_items": items, "count": len(items)}


@mcp.tool()
async def list_project_tasks(
    project_id: str,
    planning_item_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """List execution tasks for a Project with optional canonical filters."""
    tasks = await _factory_call(
        "GET",
        _query(
            "/api/v1/tasks",
            project_id=project_id,
            planning_item_id=planning_item_id,
            status_filter=status,
        ),
    )
    return {"project_id": project_id, "tasks": tasks, "count": len(tasks)}


@mcp.tool()
async def update_task_status(
    task_id: str,
    status: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """Update a task through agent-authorized planning.execution.manage."""
    payload: dict[str, Any] = {"status": status}
    if summary:
        payload["description"] = summary
    task = await _factory_call("PATCH", f"/api/v1/tasks/{task_id}", json=payload)
    return {"success": True, "task": task}


@mcp.tool()
async def report_governance_blocker(
    project_id: str,
    planning_item_id: str,
    reason: str,
    development_request_id: str | None = None,
) -> dict[str, Any]:
    """Create a canonical Messages record for operator governance review.

    This does not forge an approval or silently mutate the planning item.
    """
    sender = messages._resolve_agent(None)
    payload: dict[str, Any] = {
        "from_agent": sender,
        "subject": f"Governance blocker for planning item {planning_item_id}",
        "body": reason,
        "project_id": project_id,
        "development_request_id": development_request_id,
        "origin_type": "incubation",
        "channel": "factory",
        "channel_ref": f"planning-item:{planning_item_id}",
        "requires_response": True,
    }
    message = await messages._call("POST", "/api/v1/demands/submit", json=payload)
    return {
        "success": True,
        "project_id": project_id,
        "planning_item_id": planning_item_id,
        "message_id": message.get("id"),
        "message_number": message.get("number"),
        "canonical_path": f"/demands?message={message.get('id')}",
    }


@mcp.tool()
async def create_conception_idea(
    name: str,
    problem_statement: str,
    vision: str | None = None,
    scope_summary: str | None = None,
    project_description: str | None = None,
    working_directory_path: str | None = None,
    requested_by: str | None = None,
) -> dict[str, Any]:
    """Capture a new conception idea (Phase 1), creating a Product, Concept and Blueprint."""
    payload: dict[str, Any] = {
        "name": name,
        "problem_statement": problem_statement,
        "vision": vision,
        "scope_summary": scope_summary,
        "project_description": project_description,
        "working_directory_path": working_directory_path,
        "requested_by": requested_by,
    }
    result = await _factory_call("POST", "/api/v1/conception/ideas", json=payload)
    return {"success": True, "result": result}


@mcp.tool()
async def save_concept_document(
    concept_id: str,
    filename: str,
    content: str,
    category: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Save or attach a markdown/documentation file to a Concept (Phase 1 - Documentation)."""
    payload: dict[str, Any] = {
        "content": content,
        "category": category,
        "description": description,
    }
    doc = await _factory_call("PUT", f"/api/v1/product-concepts/{concept_id}/documents/{filename}", json=payload)
    return {"success": True, "document": doc}


@mcp.tool()
async def authorize_project_delivery(
    concept_id: str,
    version: str,
    projects: list[dict[str, Any]],
) -> dict[str, Any]:
    """Authorize projects and create versioned project deliverables from an approved concept."""
    payload: dict[str, Any] = {
        "version": version,
        "projects": projects,
    }
    result = await _factory_call("POST", f"/api/v1/product-concepts/{concept_id}:authorize-delivery-planning", json=payload)
    return {"success": True, "authorized": result}


@mcp.tool()
async def ensure_project_scope(project_id: str) -> dict[str, Any]:
    """Ensure that an active Project Scope exists for the given project."""
    scope = await _factory_call("POST", f"/api/v1/projects/{project_id}/ensure-scope")
    return {"success": True, "project_scope": scope}


@mcp.tool()
async def add_project_screen(
    project_scope_id: str,
    name: str,
    description: str | None = None,
    route: str | None = None,
    attributes: list[dict[str, Any]] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add a screen specification to the project scope (Phase 2 - Designer & Wireframes)."""
    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "spec": {
            "route": route,
            "attributes": attributes or [],
            "actions": actions or [],
        },
    }
    screen = await _factory_call("POST", f"/api/v1/project-scopes/{project_scope_id}/screens", json=payload)
    return {"success": True, "screen": screen}


@mcp.tool()
async def save_screen_prototype_html(
    project_scope_id: str,
    screen_element_id: str,
    html_content: str,
) -> dict[str, Any]:
    """Save an interactive HTML prototype or business rule for a screen."""
    payload: dict[str, Any] = {"content": html_content}
    rule = await _factory_call(
        "PUT",
        f"/api/v1/project-scopes/{project_scope_id}/screens/{screen_element_id}/business-rule",
        json=payload,
    )
    return {"success": True, "prototype": rule}


@mcp.tool()
async def derive_database_model(project_scope_id: str) -> dict[str, Any]:
    """Derive ERD database tables and fields automatically from the project screens."""
    result = await _factory_call("POST", f"/api/v1/project-scopes/{project_scope_id}/derive-database")
    return {"success": True, "derived_database": result}


@mcp.tool()
async def create_database_table(
    project_scope_id: str,
    name: str,
    description: str | None = None,
    initial_columns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a database table element and its columns in the project scope."""
    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "initial_columns": initial_columns or [{"name": "id", "sql_type": "uuid", "is_pk": True}],
    }
    table = await _factory_call("POST", f"/api/v1/project-scopes/{project_scope_id}/tables", json=payload)
    return {"success": True, "table": table}


@mcp.tool()
async def create_planning_item(
    project_id: str,
    title: str,
    item_type: str = "feature",
    description: str | None = None,
    priority: str = "medium",
) -> dict[str, Any]:
    """Create a new canonical planning item for a project backlog (Phase 3)."""
    payload: dict[str, Any] = {
        "project_id": project_id,
        "title": title,
        "item_type": item_type,
        "description": description,
        "priority": priority,
    }
    item = await _factory_call("POST", "/api/v1/planning-items", json=payload)
    return {"success": True, "planning_item": item}


@mcp.tool()
async def create_project_task(
    planning_item_id: str,
    title: str,
    description: str | None = None,
    priority: str = "medium",
    due_date: str | None = None,
) -> dict[str, Any]:
    """Create an execution task linked to a planning item (Phase 4 - Tarefas)."""
    payload: dict[str, Any] = {
        "planning_item_id": planning_item_id,
        "title": title,
        "description": description,
        "priority": priority,
        "due_date": due_date,
    }
    task = await _factory_call("POST", "/api/v1/tasks", json=payload)
    return {"success": True, "task": task}


@mcp.tool()
async def release_planning_for_execution(
    planning_item_id: str,
    agent_id: str,
) -> dict[str, Any]:
    """Release a planning item through Governance Gate into active execution with assigned agent (Phase 5)."""
    payload: dict[str, Any] = {
        "status": "in_progress",
        "assigned_agent_id": agent_id,
    }
    item = await _factory_call("PUT", f"/api/v1/planning-items/{planning_item_id}", json=payload)
    return {"success": True, "planning_item": item}


@mcp.tool()
async def create_product_version(
    product_id: str,
    version: str,
    release_notes: str | None = None,
) -> dict[str, Any]:
    """Create a new ProductVersion for version tracking and closure (Phase 7)."""
    payload: dict[str, Any] = {
        "version": version,
        "status": "planned",
        "release_notes": release_notes,
    }
    ver = await _factory_call("POST", f"/api/v1/products/{product_id}/versions", json=payload)
    return {"success": True, "version": ver}


@mcp.tool()
async def close_version_and_publish(
    version_id: str,
    release_notes: str | None = None,
) -> dict[str, Any]:
    """Publish a product version and lock its projects permanently (Phase 7 - Fechamento de Versão)."""
    if release_notes:
        await _factory_call("PUT", f"/api/v1/products/versions/{version_id}", json={"release_notes": release_notes})
    version = await _factory_call("POST", f"/api/v1/products/versions/{version_id}:publish")
    return {"success": True, "published_version": version}


if __name__ == "__main__":
    mcp.run()
