"""Execute the actual initializer with an in-memory telemetry writer.

Extract only the async function AST so this pure lifecycle test neither loads
application credentials/settings nor creates a database connection.
"""
import ast
import asyncio
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / 'backend/app/core/worker_observation.py'


def initializer(rows):
    tree = ast.parse(SOURCE.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == 'initialize_worker_observations')

    async def start(name, enabled, *, starting=False):
        rows[name] = {'enabled': enabled, 'status': 'starting' if enabled else 'disabled'}

    namespace = {'_start': start, 'WORKER_INTERVALS': {
        'scheduled-dispatch-poll':30, 'feedback-poll':120, 'routine-poll':60,
        'mission-cycle-poll':60, 'machine-status-poll':900,
    }}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['initialize_worker_observations']


def test_non_owner_preserves_stale_active_worker_evidence():
    stale = {'enabled':True, 'status':'running', 'last_success_at':'stale-owner-evidence'}
    rows = {'feedback-poll':dict(stale)}
    asyncio.run(initializer(rows)(background_enabled=False, mission_enabled=False))
    assert rows == {'feedback-poll':stale}


def test_non_owner_does_not_create_disabled_rows_when_evidence_is_missing():
    rows = {}
    asyncio.run(initializer(rows)(background_enabled=False, mission_enabled=False))
    assert rows == {}


def test_owner_registers_all_workers_and_explicitly_disabled_mission_feature():
    rows = {}
    asyncio.run(initializer(rows)(background_enabled=True, mission_enabled=False))
    assert len(rows) == 5
    assert rows['mission-cycle-poll'] == {'enabled':False, 'status':'disabled'}
    assert rows['feedback-poll'] == {'enabled':True, 'status':'starting'}
