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
async def get_product_evolution_history(product_id: str) -> dict[str, Any]:
    """Get Product versions plus every Project that belongs to those versions."""
    product = await _factory_call("GET", f"/api/v1/products/{product_id}")
    projects = await _factory_call("GET", "/api/v1/projects")
    version_ids = {version.get("id") for version in product.get("versions", [])}
    product_projects = [
        project for project in projects if project.get("product_version_id") in version_ids
    ]
    return {"product": product, "projects": product_projects}


if __name__ == "__main__":
    mcp.run()
