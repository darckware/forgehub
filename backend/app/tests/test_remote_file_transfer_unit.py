"""Transfer authorization orchestration with an in-memory DB boundary (no DB IO)."""
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.routes import remote_file_transfer as route  # noqa: E402
from app.api.schemas.remote_file_transfer import RemoteFileTransferCreate  # noqa: E402
from app.core.deps import ActorPrincipal  # noqa: E402
from app.db.models.agent import Agent  # noqa: E402


class MemoryDB:
    def __init__(self, agent, demand):
        self.agent, self.demand = agent, demand
        self.events = []
        self.spec = None

    async def get(self, model, identifier):
        return self.agent if model is Agent else self.demand

    async def execute(self, statement):
        # host._check_against_task requests demand then its optional scope audit.
        text = str(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: self.demand if 'agent_demands' in text else self.spec)

    def add(self, event):
        self.events.append(event)

    async def commit(self):
        pass


@pytest.fixture
def domain(monkeypatch, tmp_path):
    agent_id, machine_id, task_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    agent = SimpleNamespace(id=agent_id, name='worker', direct_access_allowed=True)
    demand = SimpleNamespace(id=task_id, number=123, target_agent_id=agent_id, origin_type='task',
        status='read', dispatch_status='running', agent_run_id='run-123', working_path=str(tmp_path),
        completed_at=None)
    server = SimpleNamespace(id=machine_id, os_family='linux', ip_address='linux-target.test',
        remote_user='test', ssh_port=22, ssh_key_ref=None, ssh_key_path=None)
    db = MemoryDB(agent, demand)
    async def targets(*args):
        return [server], []
    async def active(*args, **kwargs):
        pass
    async def readiness(*args):
        return {machine_id: (True, '')}
    monkeypatch.setattr(route.host, 'resolve_targets', targets)
    monkeypatch.setattr(route.host, '_agent_readiness', readiness)
    monkeypatch.setattr(route, 'require_agent_access_active', active)
    monkeypatch.setattr(route, 'require_direct', active)
    principal = ActorPrincipal('agent', agent_id, 'worker', credential_label='dispatch:run-123')
    payload = RemoteFileTransferCreate(machine_id=machine_id, local_path=str(tmp_path / 'artifact'),
        remote_path='/tmp/artifact', reason='deliver test artifact', message_number=123)
    return db, principal, payload, server


def test_roots_do_not_come_from_agent_file_path():
    demand = SimpleNamespace(agent_run_id='abc', working_path='/srv/project')
    assert route.local_transfer_roots(demand, 'agent') == ['/srv/project', '/var/lib/forgehub/transfers/agent/abc']
    demand.agent_run_id = '../../escape'
    with pytest.raises(HTTPException):
        route.local_transfer_roots(demand, 'agent')


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['not_listed', 'finished', 'other_agent', 'wrong_run', 'windows', 'paused', 'no_access', 'out_of_task_scope'])
async def test_refusals_never_contact_bridge(domain, condition, monkeypatch):
    db, principal, payload, server = domain
    if condition == 'not_listed':
        db.agent.direct_access_allowed = False
    elif condition == 'finished':
        db.demand.dispatch_status = 'completed'
    elif condition == 'other_agent':
        db.demand.target_agent_id = uuid.uuid4()
    elif condition == 'wrong_run':
        db.demand.agent_run_id = 'another-run'
    elif condition == 'windows':
        server.os_family = 'windows'
    elif condition == 'out_of_task_scope':
        db.spec = SimpleNamespace(payload={'server_ids': [str(uuid.uuid4())]})
        server.name = 'outside'
    else:
        async def refused(*args, **kwargs):
            raise HTTPException(403, 'paused' if condition == 'paused' else 'no access')
        monkeypatch.setattr(route, 'require_agent_access_active' if condition == 'paused' else 'require_direct', refused)
    def forbidden_client(*args, **kwargs):
        pytest.fail('Unauthorized transfer contacted bridge')
    monkeypatch.setattr(route.httpx, 'AsyncClient', forbidden_client)
    with pytest.raises(HTTPException) as error:
        await route._transfer(payload, 'upload', principal, db)
    assert error.value.status_code in {403, 409, 501}
    assert not db.events


@pytest.mark.asyncio
async def test_success_history_contains_metadata_(domain, monkeypatch):
    db, principal, payload, server = domain
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, *, json, headers):
            assert 'content' not in json
            assert json['host'] == 'linux-target.test'
            assert json['roots'][0] == db.demand.working_path
            return SimpleNamespace(status_code=200, json=lambda: {'size': 4, 'sha256': 'a' * 64})
    monkeypatch.setattr(route.httpx, 'AsyncClient', lambda **kwargs: Client())
    result = await route._transfer(payload, 'upload', principal, db)
    assert result.size == 4
    assert [e.event_type for e in db.events] == ['file_transfer_started', 'file_transfer_succeeded']
    assert db.events[-1].payload['sha256'] == 'a' * 64
    assert db.events[-1].payload['overwrite'] is False


@pytest.mark.asyncio
async def test_bridge_error_does_not_expose_untrusted_details(domain, monkeypatch):
    db, principal, payload, _ = domain
    class Client:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, *args, **kwargs):
            return SimpleNamespace(status_code=409, text='sensitive SSH details and file content')
    monkeypatch.setattr(route.httpx, 'AsyncClient', lambda **kwargs: Client())
    with pytest.raises(HTTPException) as error:
        await route._transfer(payload, 'download', principal, db)
    assert error.value.status_code == 409
    assert 'sensitive' not in error.value.detail
    assert [e.event_type for e in db.events] == ['file_transfer_started', 'file_transfer_failed']
    assert 'sensitive' not in str(db.events[-1].payload)
