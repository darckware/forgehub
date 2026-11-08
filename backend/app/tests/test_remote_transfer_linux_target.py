"""Real bridge file bytes over SSH, with the API's task/run authorization.

Only the isolated linux-target.test container is addressed. HTTP transport to
the bridge is in-process; SSH, hashes, atomic publication and DB history are real.
"""
import hashlib
import sys
from pathlib import Path

import httpx
import pytest

from app.api.routes import remote_file_transfer as route
from app.core import host_exec_runner
from app.db.base import AsyncSessionLocal
from app.db.models.demand import AgentDemand
from app.db.models.server import Server
from app.tests.test_direct_access import (  # noqa: F401
    ORIGINAL_BRIDGE_EXEC, command, ctx, finished, opened,
)


@pytest.mark.asyncio
async def test_linux_target_upload_execute_download_history(ctx, tmp_path, monkeypatch):  # noqa: F811 -- imported pytest fixture
    c = ctx
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / 'host-bridge'))
    import remote_file_transfer as bridge
    import remote_fs

    key = (root / 'test-env/.env.test').resolve().parent / 'linux-target/id_ed25519'
    assert key.is_file(), 'Isolated SSH fixture key required'
    target = remote_fs.SshTarget('172.25.0.14', 'darckware', 22, str(key))
    original_args = remote_fs.ssh_args
    monkeypatch.setattr(remote_fs, '_CONTROL_DIR', str(tmp_path / 'control'))
    monkeypatch.setattr(remote_fs, 'ssh_args', lambda value: [
        *original_args(value)[:1], '-F', '/dev/null', '-o', f'UserKnownHostsFile={tmp_path / "known_hosts"}',
        '-o', 'ControlMaster=no', '-o', 'ControlPath=none',
        *original_args(value)[1:],
    ])
    remote = f'/tmp/forgehub-transfer-{c.agent.id}.txt'
    source, downloaded = tmp_path / 'artifact.txt', tmp_path / 'download.txt'
    source.write_bytes(b'ForgeHub isolated transfer acceptance\n')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    code, login, error = await remote_fs.run(target, 'id -un')
    assert code == 0, error
    assert login.strip() == b'darckware'
    async with AsyncSessionLocal() as db:
        task = await db.get(AgentDemand, c.task.id)
        task.working_path = str(tmp_path)
        server = await db.get(Server, c.lab.id)
        server.ip_address, server.remote_user = 'linux-target.test', 'darckware'
        server.ssh_key_path = '/test-linux-target/id_ed25519'
        await db.commit()
    await opened(c)
    original_client = httpx.AsyncClient

    class BridgeClient:
        def __init__(self, **kwargs):
            self.client = original_client(**kwargs)

        async def __aenter__(self):
            await self.client.__aenter__()
            return self

        async def __aexit__(self, *args):
            return await self.client.__aexit__(*args)

        async def post(self, url, **kwargs):
            if not url.endswith('/v1/remote-files/transfer'):
                return await self.client.post(url, **kwargs)
            body = kwargs['json']
            local = bridge.safe_local_path(body['local_path'], body['roots'])
            try:
                result = await bridge.transfer_file(target, body['direction'], local, body['remote_path'], body['overwrite'])
                return httpx.Response(200, json=result)
            except bridge.HTTPException as exc:
                return httpx.Response(exc.status_code, json={'detail': exc.detail})

    monkeypatch.setattr(route.httpx, 'AsyncClient', BridgeClient)
    monkeypatch.setattr(host_exec_runner, 'call_bridge_exec', ORIGINAL_BRIDGE_EXEC)
    payload = {'machine_id': str(c.lab.id), 'message_number': c.task.number,
               'local_path': str(source), 'remote_path': remote, 'reason': 'Test artifact delivery'}
    try:
        upload = await c.client.post('/api/v1/remote-files/agent/upload', json=payload, headers=c.agent_h)
        assert upload.status_code == 200, upload.text
        assert upload.json()['sha256'] == digest
        conflict = await c.client.post('/api/v1/remote-files/agent/upload', json=payload, headers=c.agent_h)
        assert conflict.status_code == 409
        execution = await c.client.post('/api/v1/host-executions/agent/commands',
            json=command(c, command=f'sha256sum {remote}'), headers=c.agent_h)
        assert execution.status_code == 201, execution.text
        await finished(c, execution.json()['id'])
        result = await c.client.get('/api/v1/host-executions/agent/' + execution.json()['id'], headers=c.agent_h)
        assert digest in result.json()['results'][0]['stdout']
        download = await c.client.post('/api/v1/remote-files/agent/download',
            json={**payload, 'local_path': str(downloaded)}, headers=c.agent_h)
        assert download.status_code == 200, download.text
        assert download.json()['sha256'] == digest
        assert downloaded.read_bytes() == source.read_bytes()
        history = (await c.client.get(f'/api/v1/servers/{c.lab.id}/maintenance', headers=c.admin_h)).json()
        transfers = [e for e in history if e.get('transfer_sha256') == digest]
        assert {e['transfer_direction'] for e in transfers} == {'upload', 'download'}
        assert all(e['message_number'] == c.task.number and e['status'] == 'succeeded' for e in transfers)
    finally:
        await remote_fs.run(target, 'rm -f -- "$1"', remote)
