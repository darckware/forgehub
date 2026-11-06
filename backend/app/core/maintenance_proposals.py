"""Immutable script fingerprint and readable-content checks."""
import hashlib
import json
import re

from fastapi import HTTPException

_ELEVATION = re.compile(r"\b(sudo|su|doas|pkexec|docker|podman|runas)\b|Start-Process\b[^\n]*-Verb\s+['\"]?RunAs", re.I)
_SECRET = re.compile(
    r"-----BEGIN [^\n]*PRIVATE KEY-----|\b(?:agt_|sk-|ghp_|github_pat_)[a-zA-Z0-9_-]{12,}"
    r"|\bBearer\s+[a-zA-Z0-9._/-]+"
    r"|\btskey-[A-Za-z0-9-]{8,}"
    r"|\bnet\s+user\s+\S+\s+(?!/|\$|['\"]\$)[^\s]+"
    r"|ConvertTo-SecureString\s+(?:-String\s+)?(?!\$|['\"]\$)[^\s]+"
    r"|sshpass\s+-p\s*(?!\$|['\"]\$)[^\s]+"
    r"|https?://[^/\s:]+:[^@/\s]+@"
    r"|(?:password|passwd|pwd|token|api[_-]?key|secret)\s*[:=]\s*['\"]?(?!\$|\{|\s|['\"]?\$)[^\s'\";]+", re.I)


def validate_content(content: str, requires_elevation: bool):
    if _SECRET.search(content):
        raise HTTPException(422, "Possible literal secret: use a vault_secret parameter")
    if _ELEVATION.search(content) and not requires_elevation:
        raise HTTPException(422, "Elevation must be declared with requires_elevation=true")


def refuse_literal_secret(text: str):
    if _SECRET.search(text):
        raise HTTPException(422, {"code": "LITERAL_SECRET", "message": (
            "Possible literal secret: a direct command can't carry one. "
            "Use a library script with a vault_secret parameter")})


def looks_elevated(command: str) -> bool:
    return bool(_ELEVATION.search(command))


def content_hash(fields):
    # Parameter bindings are included too: changing a vault reference needs new approval.
    data = {key: fields[key] for key in ('content', 'shell', 'risk', 'timeout_seconds', 'requires_elevation')}
    data['server_ids'] = sorted(str(i) for i in fields['server_ids'])
    data['parameters'] = fields.get('parameters', [])
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def proposal_hash(proposal):
    return content_hash({key: getattr(proposal, key) for key in
        ('content', 'shell', 'server_ids', 'risk', 'timeout_seconds', 'requires_elevation', 'parameters')})


async def record_execution_finish(db, execution_id):
    """Only a definite result ends a claim. Interrupted/unknown output never retries."""
    from sqlalchemy import select
    from app.db.models.maintenance_proposal import MaintenanceProposal
    from app.db.models.host_execution import HostExecutionResult
    from app.db.models.governance import AuditEvent
    p = await db.scalar(select(MaintenanceProposal).where(MaintenanceProposal.execution_id == execution_id,
        MaintenanceProposal.status == 'claimed').with_for_update())
    if p is None:
        return
    results = (await db.scalars(select(HostExecutionResult).where(HostExecutionResult.execution_id == execution_id))).all()
    if not results or any(r.status not in ('succeeded', 'failed') or r.failure in ('interrupted', 'timeout', 'unreachable', 'bridge') for r in results):
        return
    # No exit code means the bridge cannot establish what happened remotely.
    if any(r.exit_code is None for r in results):
        return
    p.status = 'succeeded' if all(r.status == 'succeeded' for r in results) else 'failed'
    db.add(AuditEvent(entity_type='maintenance_proposal', entity_id=p.id, event_type=p.status,
        actor=f'agent:{p.agent_id}', payload={'content_hash': p.content_hash,
            'agent_demand_id': str(p.agent_demand_id), 'execution_id': str(execution_id)}))
