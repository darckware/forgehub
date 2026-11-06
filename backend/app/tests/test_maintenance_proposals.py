"""Real FastAPI/Postgres governance, with a simulated remote bridge."""
import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, String
from app.api.routes import host_execution as host
from app.core import host_exec_runner
from app.core.security import create_access_token
from app.db.base import AsyncSessionLocal
from app.db.models.agent import Agent, AgentServiceCredential
from app.db.models.demand import AgentDemand
from app.db.models.governance import AuditEvent, AuthorityDelegation
from app.db.models.host_execution import HostExecution
from app.db.models.maintenance_proposal import MaintenanceProposal
from app.db.models.notification import Notification
from app.db.models.server import Server
from app.db.models.user import User
from app.main import app
ORIGINAL_BRIDGE_EXEC = host_exec_runner.call_bridge_exec
A='/api/v1/host-executions/agent/proposals'
H='/api/v1/maintenance-proposals'

@pytest_asyncio.fixture
async def ctx(monkeypatch):
    tag=uuid.uuid4().hex; token='agt_'+tag; other_token='agt_other_'+tag
    async with AsyncSessionLocal() as db:
        admin=User(username='proposal-admin-'+tag,hashed_password='unused',is_admin=True)
        agent=Agent(name='proposal-agent-'+tag,agent_type='executor')
        other=Agent(name='proposal-other-'+tag,agent_type='executor')
        s=Server(name='proposal-target-'+tag,ip_address='192.0.2.42',remote_user='test',os_family='linux')
        b=Server(name='proposal-outside-'+tag,ip_address='192.0.2.43',remote_user='test',os_family='linux')
        db.add_all([admin,agent,other,s,b]);await db.flush()
        task=AgentDemand(from_agent='test',from_agent_id=agent.id,target_agent_id=agent.id,subject='test',body='test',origin_type='task')
        foreign=AgentDemand(from_agent='test',from_agent_id=other.id,target_agent_id=other.id,subject='other',body='test',origin_type='task')
        db.add_all([task,foreign]);await db.flush();now=datetime.now(timezone.utc)
        delegation=AuthorityDelegation(grantor_user_id=admin.id,grantee_type='agent',grantee_id=agent.id,allowed_actions=['remote_access.execute'],servers=[str(s.id)],host_groups=[],max_risk='high',valid_from=now-timedelta(minutes=1),expires_at=now+timedelta(hours=1))
        db.add(delegation)
        for ag,tok in [(agent,token),(other,other_token)]:
            db.add(AgentServiceCredential(agent_id=ag.id,label='test',token_hash=hashlib.sha256(tok.encode()).hexdigest()))
        await db.commit()
    async def readiness(db):return {s.id:(True,'complete'),b.id:(True,'complete')}
    monkeypatch.setattr(host,'_agent_readiness',readiness)
    async def remote(*args):return dict(exit_code=0,stdout='ok token=never-show-this',stderr='',duration_ms=1,failure=None)
    monkeypatch.setattr(host_exec_runner,'call_bridge_exec',remote)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
        c=SimpleNamespace(client=client,agent=agent,other=other,admin=admin,server=s,outside=b,task=task,foreign=foreign,delegation=delegation,agent_headers={'Authorization':'Bearer '+token},other_headers={'Authorization':'Bearer '+other_token},admin_headers={'Authorization':'Bearer '+create_access_token(admin.username)},body=dict(message_number=task.number,server_ids=[str(s.id)],shell='sh',content='echo ok',risk='change',timeout_seconds=30,requires_elevation=False,reason='Install requested tool',expected_effect='Tool available',rollback='Remove tool'))
        yield c
    for pending in list(host_exec_runner._running.values()):await pending
    async with AsyncSessionLocal() as db:
        proposal_ids=select(MaintenanceProposal.id).where(MaintenanceProposal.agent_id==agent.id)
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(proposal_ids)))
        keys=select('maintenance-proposal:created:'+MaintenanceProposal.id.cast(String)).where(MaintenanceProposal.agent_id==agent.id)
        await db.execute(delete(Notification).where(Notification.event_key.in_(keys)))
        await db.execute(delete(MaintenanceProposal).where(MaintenanceProposal.agent_id==agent.id))
        execution_ids=select(HostExecution.id).where(HostExecution.agent_id==agent.id)
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(execution_ids)))
        await db.execute(delete(HostExecution).where(HostExecution.agent_id==agent.id))
        await db.execute(delete(AuthorityDelegation).where(AuthorityDelegation.grantee_id==agent.id))
        await db.execute(delete(AgentServiceCredential).where(AgentServiceCredential.agent_id.in_([agent.id,other.id])))
        demand_ids=select(AgentDemand.id).where(AgentDemand.target_agent_id.in_([agent.id,other.id]))
        await db.execute(delete(AuditEvent).where(AuditEvent.entity_id.in_(demand_ids)))
        await db.execute(delete(AgentDemand).where(AgentDemand.target_agent_id.in_([agent.id,other.id])))
        await db.execute(delete(Server).where(Server.id.in_([s.id,b.id])))
        await db.execute(delete(Agent).where(Agent.id.in_([agent.id,other.id])))
        await db.execute(delete(User).where(User.id==admin.id));await db.commit()

async def proposed(c):
    r=await c.client.post(A,json=c.body,headers=c.agent_headers);assert r.status_code==201,r.text;return r.json()
async def approved(c):
    p=await proposed(c)
    r=await c.client.post(H+'/'+p['id']+'/decision',json={'decision':'approved','content_hash':p['content_hash']},headers=c.admin_headers)
    assert r.status_code==200,r.text;return r.json()
async def execute(c,p,**overrides):
    return await c.client.post(A+'/'+p['id']+'/run',json={'message_number':p['message_number'],'content_hash':p['content_hash'],**overrides},headers=c.agent_headers)

@pytest.mark.asyncio
async def test_complete_cycle_and_single_use(ctx):
    c=ctx;p=await approved(c)
    assert datetime.fromisoformat(p['expires_at'])-datetime.fromisoformat(p['approved_at'])==timedelta(hours=24)
    r=await execute(c,p);assert r.status_code==200,r.text
    eid=r.json()['id'];task=host_exec_runner._running.get(uuid.UUID(eid))
    if task:await task
    got=await c.client.get(A+'/'+p['id'],params={'message_number':p['message_number']},headers=c.agent_headers)
    assert got.json()['status']=='succeeded';assert got.json()['execution_id']==eid
    output=await c.client.get('/api/v1/host-executions/agent/'+eid,headers=c.agent_headers)
    assert 'never-show-this' not in output.text
    history=await c.client.get(f'/api/v1/servers/{c.server.id}/maintenance',headers=c.admin_headers)
    assert any(x['execution_id']==eid for x in history.json())
    async with AsyncSessionLocal() as db:
        events=(await db.scalars(select(AuditEvent).where(AuditEvent.entity_id==uuid.UUID(p['id'])))).all()
        assert {e.event_type for e in events}=={'created','approved','claimed','succeeded'}
        assert all(e.payload['content_hash']==p['content_hash'] for e in events)
        assert all(e.actor.startswith(('agent:','user:')) for e in events)
    assert (await execute(c,p)).status_code==409

@pytest.mark.asyncio
async def test_approval_hands_the_agent_a_new_task(ctx):
    # The proposing run is long gone when the human decides: nothing may depend on it.
    c=ctx;p=await proposed(c);assert p['message_number']==c.task.number
    async with AsyncSessionLocal() as db:
        (await db.get(AgentDemand,c.task.id)).status='archived';await db.commit()
    r=await c.client.post(H+'/'+p['id']+'/decision',json={'decision':'approved','content_hash':p['content_hash']},headers=c.admin_headers)
    assert r.status_code==200,r.text;p=r.json();assert p['message_number']!=c.task.number
    async with AsyncSessionLocal() as db:
        task=(await db.scalars(select(AgentDemand).where(AgentDemand.number==p['message_number']))).one()
        assert (task.target_agent_id,task.origin_type,task.fixed_agent)==(c.agent.id,'task',True)
        assert task.scheduled_at is not None and task.dispatch_status is None
        assert all(v in task.body for v in (p['id'],p['content_hash'],f"message_number={task.number}",f"#{c.task.number}"))
        event=(await db.scalars(select(AuditEvent).where(AuditEvent.entity_id==uuid.UUID(p['id']),AuditEvent.event_type=='approved'))).one()
        assert event.payload['origin_demand_id']==str(c.task.id)
    assert (await execute(c,p,message_number=c.task.number)).status_code in (403,409)
    r=await execute(c,p);assert r.status_code==200,r.text

@pytest.mark.asyncio
async def test_rejection_opens_no_task(ctx):
    c=ctx;p=await proposed(c)
    r=await c.client.post(H+'/'+p['id']+'/decision',json={'decision':'rejected','content_hash':p['content_hash'],'reason':'no'},headers=c.admin_headers)
    assert r.status_code==200,r.text;assert r.json()['message_number']==c.task.number
    async with AsyncSessionLocal() as db:
        assert len((await db.scalars(select(AgentDemand).where(AgentDemand.target_agent_id==c.agent.id))).all())==1

@pytest.mark.asyncio
async def test_concurrent_claim_has_one_winner(ctx):
    p=await approved(ctx);results=await asyncio.gather(execute(ctx,p),execute(ctx,p))
    assert sorted(r.status_code for r in results)==[200,409]
    async with AsyncSessionLocal() as db:
        assert len((await db.scalars(select(HostExecution).where(HostExecution.agent_id==ctx.agent.id))).all())==1

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['hash','tamper','expired','rejected','other_agent','other_task','archived','revoked','delegation_expired'])
async def test_run_refusals(ctx,kind):
    c=ctx;p=await approved(c)
    async with AsyncSessionLocal() as db:
        row=await db.get(MaintenanceProposal,uuid.UUID(p['id']))
        if kind=='tamper':row.content='echo changed'
        if kind=='expired':row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        if kind=='rejected':row.status='rejected'
        if kind=='archived':(await db.get(AgentDemand,row.agent_demand_id)).status='archived'
        if kind=='revoked':(await db.get(AuthorityDelegation,c.delegation.id)).status='revoked'
        if kind=='delegation_expired':(await db.get(AuthorityDelegation,c.delegation.id)).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        await db.commit()
    if kind=='other_agent':r=await c.client.post(A+'/'+p['id']+'/run',json={'message_number':p['message_number'],'content_hash':p['content_hash']},headers=c.other_headers)
    else:r=await execute(c,p,**({'content_hash':'0'*64} if kind=='hash' else {'message_number':c.foreign.number} if kind=='other_task' else {}))
    assert r.status_code in (403,409),r.text

@pytest.mark.asyncio
async def test_agent_cannot_decide_even_with_governance_delegation(ctx):
    c=ctx;p=await proposed(c)
    async with AsyncSessionLocal() as db:
        d=await db.get(AuthorityDelegation,c.delegation.id);d.allowed_actions=['remote_access.execute','governance.approval.decide'];await db.commit()
    r=await c.client.post(H+'/'+p['id']+'/decision',json={'decision':'approved','content_hash':p['content_hash']},headers=c.agent_headers)
    assert r.status_code in (401,403)
    r=await c.client.post(H+'/'+p['id']+'/decision',json={'decision':'approved','content_hash':'0'*64},headers=c.admin_headers);assert r.status_code==409
    async with AsyncSessionLocal() as db:assert (await db.get(MaintenanceProposal,uuid.UUID(p['id']))).status=='proposed'

@pytest.mark.asyncio
async def test_machine_scope_and_empty_delegation(ctx):
    c=ctx;listed=await c.client.get('/api/v1/host-executions/agent/machines',headers=c.agent_headers)
    assert {m['id'] for m in listed.json()}=={str(c.server.id)}
    for fields in ({'server_ids':[str(c.outside.id)]},{'message_number':c.foreign.number},{'content':'sudo true'},{'content':'password=literal'}):
        r=await c.client.post(A,json={**c.body,**fields},headers=c.agent_headers);assert r.status_code in (403,422),r.text
    async with AsyncSessionLocal() as db:(await db.get(AuthorityDelegation,c.delegation.id)).servers=[];await db.commit()
    assert (await c.client.post(A,json=c.body,headers=c.agent_headers)).status_code==403
    assert (await c.client.get('/api/v1/host-executions/agent/machines',headers=c.agent_headers)).json()==[]

@pytest.mark.asyncio
async def test_uncertain_launch_stays_claimed(ctx):
    p=await approved(ctx)
    with patch.object(host,'launch_execution',side_effect=RuntimeError('uncertain')):
        with pytest.raises(RuntimeError):await execute(ctx,p)
    async with AsyncSessionLocal() as db:assert (await db.get(MaintenanceProposal,uuid.UUID(p['id']))).status=='claimed'
    assert (await execute(ctx,p)).status_code==409

@pytest.mark.asyncio
@pytest.mark.parametrize('authorization',[None,'Bearer agt_invalid','Bearer not-valid'])
async def test_individual_credential_required(ctx,authorization):
    r=await ctx.client.post(A,json=ctx.body,headers={'Authorization':authorization} if authorization else {})
    assert r.status_code==401


@pytest.mark.asyncio
async def test_t4a_full_proposal_cycle(ctx,monkeypatch):
    c=ctx
    import subprocess
    inspected=subprocess.run(['docker','inspect','-f','{{.State.Status}}','forgehub_test_linux_target'],capture_output=True,text=True,check=True)
    assert inspected.stdout.strip()=='running'
    async with AsyncSessionLocal() as db:
        s=await db.get(Server,c.server.id)
        s.ip_address='linux-target.test';s.remote_user='darckware';s.ssh_key_path='/test-linux-target/id_ed25519'
        await db.commit()
    monkeypatch.setattr(host_exec_runner,'call_bridge_exec',ORIGINAL_BRIDGE_EXEC)
    async def test_vault(name):
        assert name=='TEST_PROPOSAL_VALUE'
        return 'fictitious-output-secret-548'
    monkeypatch.setattr(host,'vault_reveal_name',test_vault)
    c.body.update(content='hostname; id -un; printf "%s\n" "$VALUE"', parameters=[dict(name='VALUE',label='Test value',secret=True,required=True,vault_secret='TEST_PROPOSAL_VALUE')])
    p=await approved(c);r=await execute(c,p);assert r.status_code==200,r.text
    eid=r.json()['id'];pending=host_exec_runner._running.get(uuid.UUID(eid))
    if pending:await pending
    r=await c.client.get('/api/v1/host-executions/agent/'+eid,headers=c.agent_headers)
    data=r.json();assert data['counts']['succeeded']==1,data
    assert 'darckware' in data['results'][0]['stdout']
    assert 'fictitious-output-secret-548' not in r.text
    history=await c.client.get(f'/api/v1/servers/{c.server.id}/maintenance',headers=c.admin_headers)
    assert any(x['execution_id']==eid for x in history.json())
    got=await c.client.get(A+'/'+p['id'],params={'message_number':p['message_number']},headers=c.agent_headers)
    assert got.json()['status']=='succeeded'
    async with AsyncSessionLocal() as db:
        events=(await db.scalars(select(AuditEvent).where(AuditEvent.entity_id==uuid.UUID(p['id'])))).all()
        assert {e.event_type for e in events}=={'created','approved','claimed','succeeded'}


@pytest.mark.asyncio
@pytest.mark.parametrize('runtime',['claude','codex','agy'])
async def test_dispatch_mints_identity_for_actual_agent(ctx,runtime):
    import httpx
    from app.core.agent_runs import dispatch_agent_run
    c=ctx;c.agent.runtime_type=runtime;c.agent.profile_slug='agent-'+runtime
    captured={}
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            captured.update(kwargs['json'])
            return httpx.Response(202,json={'run_id':'test'},request=httpx.Request('POST',url))
    with patch('app.core.agent_runs.httpx.AsyncClient',Client):
        await dispatch_agent_run(str(uuid.uuid4()),c.agent,'test prompt','/srv/forgehub-test/')
    token=captured['agent_service_token']
    assert token.startswith('agt_') and token not in captured['prompt']
    async with AsyncSessionLocal() as db:
        cred=await db.scalar(select(AgentServiceCredential).where(AgentServiceCredential.token_hash==hashlib.sha256(token.encode()).hexdigest()))
        assert cred.agent_id==c.agent.id
        assert cred.expires_at>datetime.now(timezone.utc)

@pytest.mark.asyncio
async def test_scope_applies_to_library_and_requests_and_groups(ctx):
    from app.db.models.host_script import HostScript, HostScriptCategory
    from app.db.models.server import HostGroup, HostGroupMember
    c=ctx
    async with AsyncSessionLocal() as db:
        category=await db.scalar(select(HostScriptCategory).limit(1))
        script=HostScript(name='scope-'+uuid.uuid4().hex,category_id=category.id,platform='linux',risk='read',timeout_seconds=30,parameters=[],content='true',current_version=1,created_by='test',updated_by='test')
        group=HostGroup(name='scope-'+uuid.uuid4().hex)
        db.add_all([script,group]);await db.flush()
        db.add(HostGroupMember(group_id=group.id,server_id=c.server.id));await db.commit()
    try:
        outside={'script_id':str(script.id),'server_ids':[str(c.outside.id)],'reason':'test scope','message_number':c.task.number}
        assert (await c.client.post('/api/v1/host-executions/agent',json=outside,headers=c.agent_headers)).status_code==403
        request={'agent_ids':[str(c.agent.id)],'server_ids':[str(c.outside.id)],'instruction':'test scope','scripts':[]}
        assert (await c.client.post('/api/v1/host-executions/agent-requests',json=request,headers=c.admin_headers)).status_code==422
        async with AsyncSessionLocal() as db:
            d=await db.get(AuthorityDelegation,c.delegation.id);d.servers=[];d.host_groups=[str(group.id)];await db.commit()
        assert (await c.client.post(A,json=c.body,headers=c.agent_headers)).status_code==201
        listed=await c.client.get('/api/v1/host-executions/agent/machines',headers=c.agent_headers)
        assert {x['id'] for x in listed.json()}=={str(c.server.id)}
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(HostScript).where(HostScript.id==script.id))
            await db.execute(delete(HostGroup).where(HostGroup.id==group.id));await db.commit()

@pytest.mark.asyncio
async def test_project_scoped_delegation_is_checked_in_task_context(ctx):
    from app.db.models.project import Project
    c=ctx
    async with AsyncSessionLocal() as db:
        project=await db.scalar(select(Project).limit(1))
        assert project is not None, 'isolated seed project required'
        d=await db.get(AuthorityDelegation,c.delegation.id)
        from app.core.remote_authority import project_product_id
        d.project_id=project.id;d.product_id=await project_product_id(db,project)
        (await db.get(AgentDemand,c.task.id)).project_id=project.id
        await db.commit()
        assert not await host.agent_risk_ceilings(db,[c.agent.id],[c.server])
        assert c.agent.id in await host.agent_risk_ceilings(db,[c.agent.id],[c.server],project.id)
    url='/api/v1/host-executions/agent/machines'
    assert (await c.client.get(url,headers=c.agent_headers)).json()==[]
    scoped=await c.client.get(url,params={'message_number':c.task.number},headers=c.agent_headers)
    assert {m['id'] for m in scoped.json()}=={str(c.server.id)}
    p=await approved(c)
    assert (await execute(c,p)).status_code==200
