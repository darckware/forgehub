"""Task-bound agent artifacts over ForgeHub's bridge, using the machine login."""
from pathlib import PurePosixPath

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes import host_execution as host
from app.api.schemas.remote_file_transfer import RemoteFileTransferCreate, RemoteFileTransferOut
from app.core.config import settings
from app.core.deps import ActorPrincipal, get_maintenance_agent
from app.core.maintenance_proposals import refuse_literal_secret
from app.core.remote_authority import require_agent_access_active, require_direct, require_remote_task_credential
from app.db.base import get_db
from app.db.models.agent import Agent
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent

router = APIRouter(prefix='/api/v1/remote-files/agent', tags=['remote-access'])


def local_transfer_roots(demand: AgentDemand, agent_id) -> list[str]:
    """Only a recorded task directory and an isolated directory of this exact run.

    The bridge resolves realpaths and rejects broad roots/configuration paths.
    Never accept roots from an agent request or derive them from its file path.
    """
    run_id = demand.agent_run_id
    if not run_id or PurePosixPath(run_id).name != run_id or run_id in {'.', '..'}:
        raise HTTPException(403, 'Active task run required for file transfers')
    roots = [f'/var/lib/forgehub/transfers/{agent_id}/{run_id}']
    if demand.working_path:
        roots.insert(0, demand.working_path)
    return roots


async def _transfer(payload, direction, principal, db):
    await require_agent_access_active(db)
    for value in (payload.reason, payload.local_path, payload.remote_path):
        refuse_literal_secret(value)
    servers, _ = await host.resolve_targets(db, [payload.machine_id], [])
    server = servers[0]
    agent = await db.get(Agent, principal.principal_id)
    if not agent or not agent.direct_access_allowed:
        raise HTTPException(403, {'code': 'AGENT_NOT_LISTED', 'message': 'You are not on the direct access list'})
    demand_id = await host._check_against_task(db, agent, payload, None, servers, principal=principal)
    demand = await db.get(AgentDemand, demand_id)
    require_remote_task_credential(principal, demand)
    await require_direct(db, agent.id, servers)
    if server.os_family == 'windows':
        raise HTTPException(501, 'File transfer requires POSIX sh and GNU coreutils; Windows is not supported')
    readiness = await host._agent_readiness(db)
    if not readiness.get(server.id, (False, ''))[0]:
        raise HTTPException(409, {'code': 'LOGIN_NOT_READY', 'message': 'ForgeHub has no working machine login'})
    roots = local_transfer_roots(demand, agent.id)
    await require_agent_access_active(db, lock=True)
    await require_direct(db, agent.id, servers, lock=True)
    metadata = {'agent_id': str(agent.id), 'agent': agent.name, 'demand_id': str(demand.id),
                'message_number': demand.number, 'direction': direction, 'reason': payload.reason.strip(),
                'local_path': payload.local_path, 'remote_path': payload.remote_path, 'overwrite': payload.overwrite}
    # Record the authorized start before crossing the bridge; a lost connection
    # still leaves evidence and never records keys or file contents.
    db.add(AuditEvent(entity_type='server', entity_id=server.id, event_type='file_transfer_started',
                      actor=principal.display_name, payload=metadata))
    await db.commit()
    body = {'direction': direction, 'local_path': payload.local_path, 'remote_path': payload.remote_path,
            'overwrite': payload.overwrite, 'roots': roots, 'host': server.ip_address, 'user': server.remote_user,
            'port': server.ssh_port or 22, 'key_ref': server.ssh_key_ref,
            'key_path': None if server.ssh_key_ref else server.ssh_key_path}
    try:
        async with httpx.AsyncClient(timeout=630) as client:
            response = await client.post(f'{settings.CHAT_BRIDGE_URL}/v1/remote-files/transfer', json=body,
                                        headers={'X-Bridge-Token': settings.CHAT_BRIDGE_TOKEN})
        if response.status_code != 200:
            # Bridge output is deliberately not forwarded or audited: even an
            # unexpected SSH error must not disclose file contents or key data.
            raise HTTPException(response.status_code if response.status_code in {400, 403, 404, 409, 413, 501, 502, 504} else 502,
                                'File transfer refused or interrupted; check paths, size and overwrite')
        result = RemoteFileTransferOut(machine_id=server.id, direction=direction, local_path=payload.local_path,
            remote_path=payload.remote_path, overwrite=payload.overwrite, **response.json())
    except (httpx.HTTPError, ValueError):
        db.add(AuditEvent(entity_type='server', entity_id=server.id, event_type='file_transfer_failed',
                          actor=principal.display_name, payload={**metadata, 'result': 'bridge_or_verification_failure'}))
        await db.commit()
        raise HTTPException(502, 'File transfer interrupted or verification failed') from None
    except HTTPException as exc:
        db.add(AuditEvent(entity_type='server', entity_id=server.id, event_type='file_transfer_failed',
                          actor=principal.display_name, payload={**metadata, 'status_code': exc.status_code}))
        await db.commit()
        raise
    db.add(AuditEvent(entity_type='server', entity_id=server.id, event_type='file_transfer_succeeded',
                      actor=principal.display_name, payload={**metadata, 'size': result.size, 'sha256': result.sha256}))
    await db.commit()
    return result


@router.post('/upload', response_model=RemoteFileTransferOut)
async def upload_remote_file(payload: RemoteFileTransferCreate,
    principal: ActorPrincipal = Depends(get_maintenance_agent), db: AsyncSession = Depends(get_db)):
    return await _transfer(payload, 'upload', principal, db)


@router.post('/download', response_model=RemoteFileTransferOut)
async def download_remote_file(payload: RemoteFileTransferCreate,
    principal: ActorPrincipal = Depends(get_maintenance_agent), db: AsyncSession = Depends(get_db)):
    return await _transfer(payload, 'download', principal, db)
