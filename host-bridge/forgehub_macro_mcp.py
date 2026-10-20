#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp[cli]>=1.2.0", "httpx>=0.27"]
# ///
"""MCP server exposing ForgeHub's Web Automation routines ("macros") as tools.

Wraps the existing `/api/v1/workspace-browser/routines*` endpoints
(backend/app/api/routes/workspace_browser.py, backend model
backend/app/db/models/web_automation.py) so a Hermes agent can run a
product's saved macro against the shared Workspace CDP browser -- the same
session its own native `browser_*` toolset already drives via `cdp_url`
(see the `browser:` section of the agent's config.yaml) -- instead of
freehand clicking. Prefer a saved routine when one exists for the task;
it is deterministic and was recorded once against the real DOM.

Auth: FORGEHUB_AGENT_TOKEN must be an `agt_`-prefixed AgentServiceCredential
token (minted via POST /api/v1/governed/agent-credentials) for the calling
agent. The global RequireAuthMiddleware in backend/app/main.py only accepts
agent tokens on an explicit path allowlist, which includes
/api/v1/workspace-browser/ and /api/v1/products.
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("FORGEHUB_API_URL", "http://localhost:8001").rstrip("/")
AGENT_TOKEN = os.environ["FORGEHUB_AGENT_TOKEN"]

mcp = FastMCP("forgehub-macros")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, headers={"Authorization": f"Bearer {AGENT_TOKEN}"}, timeout=120.0)


async def _find_product(client: httpx.AsyncClient, product: str) -> dict:
    response = await client.get("/api/v1/products")
    response.raise_for_status()
    products = response.json()
    match = next((p for p in products if p["name"].strip().lower() == product.strip().lower()), None)
    if match is None:
        names = ", ".join(p["name"] for p in products) or "(none registered)"
        raise ValueError(f"No product named {product!r}. Registered products: {names}")
    return match


async def _find_routine(client: httpx.AsyncClient, product_id: str, routine_name: str) -> dict:
    response = await client.get("/api/v1/workspace-browser/routines", params={"product_id": product_id})
    response.raise_for_status()
    routines = response.json()
    match = next((r for r in routines if r["name"].strip().lower() == routine_name.strip().lower()), None)
    if match is None:
        names = ", ".join(r["name"] for r in routines) or "(none saved)"
        raise ValueError(f"No routine named {routine_name!r} for this product. Saved routines: {names}")
    return match


@mcp.tool()
async def list_web_automation_routines(product: str) -> str:
    """List the saved Web Automation routines ("macros") for a ForgeHub product, by product name."""
    async with _client() as client:
        product_row = await _find_product(client, product)
        response = await client.get("/api/v1/workspace-browser/routines", params={"product_id": product_row["id"]})
        response.raise_for_status()
        routines = response.json()
    if not routines:
        return f"No Web Automation routines saved for product {product_row['name']!r}."
    lines = [f"Routines for {product_row['name']!r}:"]
    for routine in routines:
        lines.append(f"- {routine['name']} ({len(routine['steps'])} step(s)): {routine.get('description') or 'no description'}")
    return "\n".join(lines)


@mcp.tool()
async def run_web_automation_routine(product: str, routine_name: str) -> str:
    """Run a saved Web Automation routine ("macro") against the shared Workspace browser.

    This drives the exact same CDP session shown in ForgeHub's Web App pane.
    Prefer this over freehand browser_* clicking whenever a routine already
    exists for the task -- it is deterministic and was recorded once against
    the real DOM, so it does not depend on guessing selectors live.
    """
    async with _client() as client:
        product_row = await _find_product(client, product)
        routine_row = await _find_routine(client, product_row["id"], routine_name)
        response = await client.post(f"/api/v1/workspace-browser/routines/{routine_row['id']}:run")
        response.raise_for_status()
        result = response.json()
    lines = [f"Routine {routine_row['name']!r} finished with status: {result['status']}"]
    for step in result["steps"]:
        lines.append(f"  {step['index']}. {step['action']}: {step['outcome']} ({step['status']})")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
