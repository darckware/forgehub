"""Regression coverage for the profile-owned operational verifier."""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

SCRIPTS = Path('/root/.hermes/profiles/athos/scripts')
RELEASE_SCRIPTS = Path(__file__).resolve().parents[3] / 'ops/athos'


def load_script(name):
    source = RELEASE_SCRIPTS / f'{name}.py'
    if not source.exists():
        source = SCRIPTS / f'{name}.py'
    if not source.exists():
        pytest.skip('Profile scripts are not present in this environment')
    spec = importlib.util.spec_from_file_location(f'audit_regression_{name}', source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_retired_vector_is_not_required_in_runtime_registry(monkeypatch, tmp_path):
    verifier = load_script('checklist_verifier')
    (tmp_path / 'profiles' / 'athos').mkdir(parents=True)
    monkeypatch.setattr(verifier, 'HERMES', tmp_path)
    monkeypatch.setattr(verifier, 'psql', lambda *args: 'athos|hermes\naramis|codex\nporthus|claude\ndartan|agy')
    assert verifier.check_registered_agents().ok


def backup_row(container, **overrides):
    row = dict(container=container, name=container, enabled=True, status='ok', snapshot_id='1234abcd',
               finished_at=datetime.now(timezone.utc).isoformat())
    return row | overrides


def test_backup_audit_uses_current_per_target_snapshots(monkeypatch):
    verifier = load_script('checklist_verifier')
    rows = [backup_row(container) for container in (*verifier.APPLICATION_POSTGRES, 'saedas_postgres')]
    monkeypatch.setattr(verifier, 'psql', lambda *args: '\n'.join(json.dumps(row) for row in rows))
    assert verifier.check_postgres_dumps().ok


@pytest.mark.parametrize('change', [
    {'status': 'failed'}, {'snapshot_id': None}, {'finished_at': None},
    {'finished_at': '2026-01-01T00:00:00+00:00'}, {'enabled': False},
])
def test_backup_audit_rejects_unverified_system_backup(monkeypatch, change):
    verifier = load_script('checklist_verifier')
    rows = [backup_row(container, **(change if container == 'hindsight_postgres' else {}))
            for container in (*verifier.APPLICATION_POSTGRES, 'saedas_postgres')]
    monkeypatch.setattr(verifier, 'psql', lambda *args: '\n'.join(json.dumps(row) for row in rows))
    result = verifier.check_postgres_dumps()
    assert not result.ok
    assert 'hindsight_postgres' in result.notes


def test_memory_audit_preserves_dated_historical_experiences(monkeypatch):
    verifier = load_script('checklist_verifier')
    monkeypatch.setattr(verifier, 'http_json', lambda url: {
        'total': 1, 'items': [{'id': 'historical', 'fact_type': 'experience',
                              'text': 'An old report was saved in /root/.hermes/workspaces.'}],
    })
    assert verifier.check_hindsight_obsolete().ok


def test_memory_audit_rejects_current_obsolete_facts(monkeypatch):
    verifier = load_script('checklist_verifier')
    monkeypatch.setattr(verifier, 'http_json', lambda url: {
        'total': 1, 'items': [{'id': 'current', 'fact_type': 'world',
                              'text': 'The active workspace is /root/.hermes/workspaces.'}],
    })
    assert not verifier.check_hindsight_obsolete().ok


@pytest.mark.parametrize('profile,voice', [('lara','pt-BR-FranciscaNeural'), ('maia','pt-BR-FranciscaNeural'), ('athos','pt-BR-AntonioNeural')])
def test_voice_audit_uses_channel_specific_policy(monkeypatch, tmp_path, profile, voice):
    audit = load_script('voice_runtime_audit')
    monkeypatch.setattr(audit, 'PROFILES', tmp_path)
    (tmp_path / profile).mkdir()
    config = dict(stt=dict(enabled=True, provider='local', local=dict(model='large-v3-turbo', language='pt')),
                  tts=dict(provider='edge', edge=dict(voice=voice)), voice=dict(auto_tts=False))
    (tmp_path / profile / 'config.yaml').write_text(yaml.safe_dump(config))
    assert audit.settings_drift(profile) == []


def test_voice_audit_rejects_automatic_audio_for_text(monkeypatch, tmp_path):
    audit = load_script('voice_runtime_audit')
    monkeypatch.setattr(audit, 'PROFILES', tmp_path)
    (tmp_path / 'atlas').mkdir()
    config = dict(stt=dict(enabled=True, provider='local', local=dict(model='base', language='pt')),
                  tts=dict(provider='piper', piper=dict(voice='pt_BR-jeff-medium')), voice=dict(auto_tts=True))
    (tmp_path / 'atlas' / 'config.yaml').write_text(yaml.safe_dump(config))
    assert any('auto_tts' in issue for issue in audit.settings_drift('atlas'))


def setup_backup_worker(monkeypatch, tmp_path):
    worker = load_script('backup_offsite_projects')
    monkeypatch.setattr(worker, 'STAGE_ROOT', tmp_path)
    source = tmp_path / 'source'
    source.mkdir()
    target = dict(name='sistema', paths=[str(source)], postgres_container='hindsight_postgres')
    def dump(container, dest):
        dest.mkdir(parents=True)
        (dest / 'foundation.sql').write_text('consistent dump')
    monkeypatch.setattr(worker, 'dump_postgres', dump)
    return worker, target, tmp_path / 'sistema'


def test_backup_keeps_staged_dump_when_remote_snapshot_fails(monkeypatch, tmp_path):
    worker, target, stage = setup_backup_worker(monkeypatch, tmp_path)
    def failure(*args, **kwargs):
        raise RuntimeError('Google Drive quota exceeded')
    monkeypatch.setattr(worker, 'run', failure)
    with pytest.raises(RuntimeError, match='quota'):
        worker.backup_target(target, {})
    assert [p.read_text() for p in stage.rglob('foundation.sql')] == ['consistent dump']


def test_backup_requires_a_snapshot_receipt_before_discarding_dump(monkeypatch, tmp_path):
    from types import SimpleNamespace
    worker, target, stage = setup_backup_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(worker, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=''))
    with pytest.raises(RuntimeError, match='snapshot'):
        worker.backup_target(target, {})
    assert list(stage.rglob('foundation.sql'))


def test_backup_cleans_staging_after_verified_snapshot(monkeypatch, tmp_path):
    from types import SimpleNamespace
    worker, target, stage = setup_backup_worker(monkeypatch, tmp_path)
    monkeypatch.setattr(worker, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(
        dict(message_type='summary', snapshot_id='12345678abcdef'))))
    assert worker.backup_target(target, {})['snapshot_id'] == '12345678'
    assert not stage.exists()


def test_failed_retry_preserves_previous_consistent_dump(monkeypatch, tmp_path):
    worker, target, stage = setup_backup_worker(monkeypatch, tmp_path)
    def failure(*args, **kwargs):
        raise RuntimeError('remote quota')
    monkeypatch.setattr(worker, 'run', failure)
    with pytest.raises(RuntimeError):
        worker.backup_target(target, {})
    retained = list(stage.rglob('foundation.sql'))
    assert len(retained) == 1
    monkeypatch.setattr(worker, 'dump_postgres', failure)
    with pytest.raises(RuntimeError):
        worker.backup_target(target, {})
    assert retained[0].read_text() == 'consistent dump'


def test_repeated_upload_failures_keep_two_complete_attempts_with_stable_path(monkeypatch, tmp_path):
    worker, target, stage = setup_backup_worker(monkeypatch, tmp_path)
    paths = []
    def failure(command, **kwargs):
        paths.append([value for value in command if value.startswith(str(stage))])
        raise RuntimeError('remote quota')
    monkeypatch.setattr(worker, 'run', failure)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            worker.backup_target(target, {})
    assert paths == [[str(stage / 'current')]] * 3
    assert len(list(stage.rglob('foundation.sql'))) == 2
    assert (stage / 'current/COMPLETE').is_file()
    assert (stage / 'previous/COMPLETE').is_file()


def test_success_preserves_manual_recovery_copies(monkeypatch, tmp_path):
    from types import SimpleNamespace
    worker, target, stage = setup_backup_worker(monkeypatch, tmp_path)
    manual = stage / 'manual-recovery'
    manual.mkdir(parents=True)
    (manual / 'foundation.sql').write_text('manual backup')
    monkeypatch.setattr(worker, 'run', lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(
        dict(message_type='summary', snapshot_id='12345678abcdef'))))
    worker.backup_target(target, {})
    assert (manual / 'foundation.sql').read_text() == 'manual backup'
