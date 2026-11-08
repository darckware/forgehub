"""Authority policy tests without database or host access."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.api.schemas.direct_access import DirectAgentConfigure
from app.core.remote_authority import direct_access_for, direct_coverage_expands


def access(**overrides):
    return SimpleNamespace(**{"servers": [], "all_machines": False, "allow_elevation": False,
                           "expires_at": datetime.now(timezone.utc) + timedelta(hours=1), **overrides})


def test_configuration_defaults_are_all_without_expiry_or_elevation():
    payload = DirectAgentConfigure()
    assert payload.all_machines is True
    assert payload.duration_hours == 0
    assert payload.allow_elevation is False
    assert payload.reason is None and payload.purpose is None


@pytest.mark.parametrize('hours', [-1, 2, 25])
def test_configuration_rejects_other_durations(hours):
    with pytest.raises(ValidationError):
        DirectAgentConfigure(duration_hours=hours)


def test_all_covers_a_machine_created_after_configuration():
    row = access(all_machines=True)
    assert direct_access_for([row], uuid.uuid4()) is row
    assert direct_access_for([row], uuid.uuid4(), elevation=True) is None


def test_empty_and_snapshot_scopes_never_expand():
    selected, other = uuid.uuid4(), uuid.uuid4()
    row = access()
    assert direct_access_for([row], selected) is None
    row.servers = [str(selected)]
    assert direct_access_for([row], selected) is row
    assert direct_access_for([row], other) is None


def test_confirmation_only_when_coverage_expands():
    first, second = uuid.uuid4(), uuid.uuid4()
    old = access()
    old.servers = [str(first)]
    assert not direct_coverage_expands(old, False, [first])
    assert direct_coverage_expands(old, False, [first, second])
    assert direct_coverage_expands(old, True, [])
    old.all_machines = True
    assert not direct_coverage_expands(old, False, [second])
    assert direct_coverage_expands(None, True, [])


def test_retention_defaults_to_90_days():
    from app.core.config import settings
    assert settings.HOST_OUTPUT_RETENTION_DAYS == 90


def test_task_credential_is_bound_to_the_exact_dispatch():
    from fastapi import HTTPException
    from app.core import remote_authority
    agent_id = uuid.uuid4()
    task = SimpleNamespace(dispatch_status='running', agent_run_id='run-1', target_agent_id=agent_id)
    principal = SimpleNamespace(principal_id=agent_id, credential_label='dispatch:run-1')
    remote_authority.require_remote_task_credential(principal, task)
    principal.credential_label = 'dispatch:run-2'
    with pytest.raises(HTTPException) as exc:
        remote_authority.require_remote_task_credential(principal, task)
    assert exc.value.detail['code'] == 'TASK_CREDENTIAL_MISMATCH'
