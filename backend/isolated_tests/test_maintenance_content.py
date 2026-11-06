import pytest
from fastapi import HTTPException
from app.core.maintenance_proposals import validate_content, content_hash

@pytest.mark.parametrize('command', ['sudo apt install x', 'su root', 'doas true', 'pkexec true', 'docker run x', 'podman run x', 'runas /user:admin cmd', 'Start-Process cmd -Verb RunAs'])
def test_undeclared_elevation_is_refused(command):
    with pytest.raises(HTTPException) as exc:
        validate_content(command, False)
    assert exc.value.status_code == 422

@pytest.mark.parametrize('content', ['-----BEGIN OPENSSH PRIVATE KEY-----', 'TOKEN="abc123"', 'password=literal', 'Authorization: Bearer abcdef', 'agt_abcdefghijklmnopqrstuv'])
def test_literal_secrets_are_refused(content):
    with pytest.raises(HTTPException) as exc:
        validate_content(content, True)
    assert exc.value.status_code == 422

def test_hash_covers_every_execution_input():
    fields = dict(content='echo ok', shell='sh', server_ids=['B','A'], risk='change', timeout_seconds=60, requires_elevation=False, parameters=[])
    original = content_hash(fields)
    assert content_hash({**fields, 'server_ids': ['A','B']}) == original
    for key, value in dict(content='echo other', shell='powershell', server_ids=['A'], risk='destructive', timeout_seconds=61, requires_elevation=True, parameters=[{'name':'KEY', 'vault_secret':'TEST'}]).items():
        assert content_hash({**fields, key:value}) != original
