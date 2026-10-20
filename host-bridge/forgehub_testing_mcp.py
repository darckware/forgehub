#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp[cli]>=1.2.0", "httpx>=0.27"]
# ///
"""MCP server exposing ForgeHub's background app testing as a tool.

Wraps `/api/v1/workspace-browser/routines/{id}:run-background` +
`/test-runs/{id}` (backend/app/api/routes/workspace_browser.py, models in
backend/app/db/models/web_automation.py) -- same pattern as
forgehub_macro_mcp.py, but for `mode="background"` runs: an isolated,
throwaway CDP Chromium instance the operator does not need to watch,
distinct from the shared Workspace Browser `run_web_automation_routine`
drives.

**Prefer the deterministic `/testar` slash command when the operator is
present in the chat** (see ChatPane.tsx's LOCAL_SLASH_COMMANDS + plan's
Fase 4) -- it dispatches straight from the client via apiClient and never
depends on this tool being loaded in the agent's active toolset. This
tool exists for the organic, best-effort path ("hey, test the app") and
inherits the known MCP-discovery gap documented in the plan's "Risco
explícito" section: if the ForgeHub gateway did not load this toolset for
the turn, the agent simply cannot call it -- there is nothing this file
can do about that from inside the tool itself.

Auth: FORGEHUB_AGENT_TOKEN must be an `agt_`-prefixed AgentServiceCredential
token (minted via POST /api/v1/governed/agent-credentials) for the calling
agent. The global RequireAuthMiddleware in backend/app/main.py only accepts
agent tokens on an explicit path allowlist, which includes
/api/v1/workspace-browser/ and /api/v1/products.
"""
import asyncio
import os

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("FORGEHUB_API_URL", "http://localhost:8001").rstrip("/")
AGENT_TOKEN = os.environ["FORGEHUB_AGENT_TOKEN"]

# Poll for a short while and return whatever we have -- never block the
# agent's turn indefinitely. A still-running test is reported as such,
# with the test_run id so the operator (or a follow-up call) can check
# the Systems Hub / test-runs endpoint later.
POLL_INTERVAL_SECONDS = 3.0
DEFAULT_TIMEOUT_SECONDS = 90
TERMINAL_STATUSES = {"passed", "failed", "error"}

mcp = FastMCP("forgehub-testing")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=BASE_URL, headers={"Authorization": f"Bearer {AGENT_TOKEN}"}, timeout=30.0)


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


def _format_run(run: dict) -> str:
    lines = [f"Test run {run['id']} -- status: {run['status']} (mode: {run['mode']})"]
    if run.get("report"):
        lines.append(run["report"])
    if run.get("error"):
        lines.append(f"Error: {run['error']}")
    shots = run.get("screenshot_paths") or []
    if shots:
        lines.append(f"{len(shots)} screenshot(s) captured.")
    return "\n".join(lines)


@mcp.tool()
async def test_application(product: str, routine_name: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Test a product's live application in the background, using a saved
    Web Automation routine (create/enable one in ForgeHub's Systems Hub
    "Background tests" tab first -- this tool does not invent steps).

    Runs against an isolated, throwaway browser instance -- does not
    interfere with anything visible in the shared Workspace Browser.
    Polls up to `timeout_seconds` (default 90s); if the run is still going
    when the timeout is reached, returns its id so progress can be checked
    later via ForgeHub's Systems Hub instead of blocking the conversation.
    """
    async with _client() as client:
        product_row = await _find_product(client, product)
        routine_row = await _find_routine(client, product_row["id"], routine_name)
        if not routine_row.get("background_test_enabled"):
            return (
                f"Routine {routine_row['name']!r} is not enabled for background testing yet. "
                "Enable it in ForgeHub's Systems Hub, \"Background tests\" tab, then try again."
            )

        dispatch = await client.post(
            f"/api/v1/workspace-browser/routines/{routine_row['id']}:run-background",
            json={"mode": "background"},
        )
        dispatch.raise_for_status()
        run = dispatch.json()

        elapsed = 0.0
        while run["status"] not in TERMINAL_STATUSES and elapsed < timeout_seconds:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
            poll = await client.get(f"/api/v1/workspace-browser/test-runs/{run['id']}")
            poll.raise_for_status()
            run = poll.json()

    if run["status"] not in TERMINAL_STATUSES:
        return (
            f"Test run {run['id']} is still {run['status']} after {int(elapsed)}s -- "
            "still running. Check ForgeHub's Systems Hub, \"Background tests\" tab, "
            f"or call this tool again later to see the final result (test_run #{run['id']})."
        )
    return _format_run(run)


if __name__ == "__main__":
    mcp.run()
