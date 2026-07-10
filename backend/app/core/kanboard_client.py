"""Thin client for Kanboard's JSON-RPC 2.0 API.

ForgeHub's "Kanboard" page (frontend/src/pages/kanboard/index.tsx) is just
an <iframe> embed -- this module is the actual data integration: it lets
ProjectTask rows be pushed to a real Kanboard project as cards, so a task
worked on in ForgeHub shows up on the board its team already watches.

Settings (app/core/config.py): KANBOARD_URL/KANBOARD_USER/KANBOARD_TOKEN/
KANBOARD_PROJECT_ID. KANBOARD_URL must be reachable from inside this
container (the `kanboard` hostname on the shared
foundation_network docker network), not `localhost`.
"""
import httpx

from app.core.config import settings


class KanboardError(RuntimeError):
    """Raised when Kanboard's JSON-RPC API returns an error envelope."""


async def _call(method: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            settings.KANBOARD_URL,
            auth=(settings.KANBOARD_USER, settings.KANBOARD_TOKEN),
            json={"jsonrpc": "2.0", "method": method, "id": 1, "params": params},
        )
        response.raise_for_status()
        payload = response.json()
    if "error" in payload:
        raise KanboardError(f"Kanboard {method} failed: {payload['error']}")
    return payload["result"]


async def get_user_by_name(username: str) -> int | None:
    """Return the Kanboard user id for the given username, or None if not found."""
    try:
        users = await _call("getAllUsers", {})
        if not isinstance(users, list):
            return None
        for user in users:
            if user.get("username") == username or user.get("name") == username:
                return int(user["id"])
    except Exception:
        pass
    return None


async def create_task(
    title: str,
    description: str,
    column_id: int,
    owner_id: int | None = None,
    date_started: int | None = None,
    project_id: int | None = None,
) -> int:
    """Creates a card in the configured Kanboard project and returns its id."""
    params: dict = {
        "title": title,
        "description": description,
        "project_id": project_id or settings.KANBOARD_PROJECT_ID,
        "column_id": column_id,
    }
    if owner_id is not None:
        params["owner_id"] = owner_id
    if date_started is not None:
        params["date_started"] = date_started
    task_id = await _call("createTask", params)
    return int(task_id)


async def update_task(
    task_id: int,
    title: str,
    description: str,
    owner_id: int | None = None,
    date_started: int | None = None,
) -> None:
    params: dict = {"id": task_id, "title": title, "description": description}
    if owner_id is not None:
        params["owner_id"] = owner_id
    if date_started is not None:
        params["date_started"] = date_started
    await _call("updateTask", params)


async def move_task_to_column(task_id: int, column_id: int, project_id: int | None = None) -> None:
    # moveTaskPosition requires (project_id, task_id, column_id, position,
    # swimlane_id) -- position=1 puts it at the top of the column, the
    # board's own drag-and-drop ordering is not something ForgeHub tracks.
    await _call(
        "moveTaskPosition",
        {
            "project_id": project_id or settings.KANBOARD_PROJECT_ID,
            "task_id": task_id,
            "column_id": column_id,
            "position": 1,
            "swimlane_id": 1,
        },
    )


async def get_task(task_id: int) -> dict:
    """Returns the Kanboard task dict for the given id (includes column_id)."""
    return await _call("getTask", {"task_id": task_id})


async def close_task(task_id: int) -> None:
    """Closes (archives) a task in Kanboard. Kanboard closeTask returns true/false."""
    await _call("closeTask", {"task_id": task_id})


def task_url(task_id: int) -> str:
    return f"{settings.KANBOARD_PUBLIC_URL}/task/{task_id}"


# ---------------------------------------------------------------------------
# Project management
# ---------------------------------------------------------------------------

# Canonical column names mirroring the ForgeHub reference project (id=8).
REFERENCE_COLUMNS = [
    "Backlog", "Ready", "In Progress", "Review",
    "Testing", "Blocked", "Done", "Close", "Canceled",
]

# ForgeHub task status → Kanboard column title.
STATUS_TO_COLUMN_TITLE: dict[str, str] = {
    "planned":     "Backlog",
    "assigned":    "Ready",
    "in_progress": "In Progress",
    "blocked":     "Blocked",
    "done":        "Done",
    "deployed":    "Close",
    "cancelled":   "Canceled",
}


async def get_columns(project_id: int) -> list[dict]:
    result = await _call("getColumns", {"project_id": project_id})
    return result if isinstance(result, list) else []


async def create_project(name: str, description: str = "") -> int:
    return int(await _call("createProject", {"name": name, "description": description}))


async def remove_column(column_id: int) -> None:
    await _call("removeColumn", {"column_id": column_id})


async def add_column(project_id: int, title: str) -> int:
    return int(await _call("addColumn", {"project_id": project_id, "title": title}))


async def create_project_with_columns(name: str, description: str = "") -> tuple[int, dict[str, int]]:
    """Create a Kanboard project replicating the ForgeHub reference column structure.

    Returns (kanboard_project_id, {column_title: column_id}) for storage on Product.
    """
    project_id = await create_project(name, description)
    for col in await get_columns(project_id):
        try:
            await remove_column(int(col["id"]))
        except Exception:
            pass
    col_map: dict[str, int] = {}
    for title in REFERENCE_COLUMNS:
        col_map[title] = await add_column(project_id, title)
    return project_id, col_map


async def get_column_id_for_status(
    product_column_ids: dict | None,
    task_status: str,
) -> int:
    """Return the Kanboard column id for a task status.

    Uses the per-product column map when available; falls back to the global
    reference project's hardcoded IDs.
    """
    col_title = STATUS_TO_COLUMN_TITLE.get(task_status, "Backlog")
    if product_column_ids:
        col_id = product_column_ids.get(col_title)
        if col_id:
            return int(col_id)
    fallback = {
        "Backlog": 40, "Ready": 41, "In Progress": 42, "Review": 43,
        "Testing": 44, "Blocked": 45, "Done": 46, "Close": 47, "Canceled": 48,
    }
    return fallback.get(col_title, 40)
