"""Application coverage comes from one validated, versioned manifest."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('target_verifier', ROOT / 'checklist_verifier.py')
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)


def manifest():
    return json.loads((ROOT / 'audit_targets.json').read_text())


def test_manifest_covers_real_filenest_and_saedas_targets():
    targets = v.validate_target_manifest(manifest())
    by_name = {item['name']: item for item in targets}
    assert {'filenest','saedas','forgehub','forgerouter','forgevault','hindsight','coreti','darckware'} == set(by_name)
    assert by_name['filenest']['postgres'] == ['filenest-db-1']
    assert by_name['saedas']['endpoints'][0]['url'] == 'http://127.0.0.1:3200/'


@pytest.mark.parametrize('missing', ['filenest', 'saedas'])
def test_manifest_rejects_removing_required_application_coverage(missing):
    data = manifest()
    data['applications'] = [item for item in data['applications'] if item['name'] != missing]
    with pytest.raises(ValueError, match='Required application coverage is missing'):
        v.validate_target_manifest(data)


@pytest.mark.parametrize('change', ['duplicate','empty','credentials','test_target','unknown_schema','missing_owner','invalid_status'])
def test_invalid_or_secret_bearing_targets_are_rejected(change):
    data = copy.deepcopy(manifest())
    if change == 'duplicate':
        data['applications'].append(copy.deepcopy(data['applications'][0]))
    elif change == 'empty':
        data['applications'] = []
    elif change == 'credentials':
        data['applications'][0]['endpoints'][0]['url'] = 'http://user:password@127.0.0.1:8000/'
    elif change == 'test_target':
        data['applications'][0]['containers'] = ['forgehub_test_backend']
    elif change == 'unknown_schema':
        data['schema_version'] = 2
    elif change == 'missing_owner':
        data['applications'][0].pop('owner')
    elif change == 'invalid_status':
        data['applications'][0]['endpoints'][0]['expected'] = [999]
    with pytest.raises(ValueError):
        v.validate_target_manifest(data)


def test_a_missing_inventory_does_not_fall_back_to_old_six_applications(monkeypatch):
    monkeypatch.setattr(v, 'TARGET_MANIFEST', ROOT / 'does-not-exist.json')
    with pytest.raises(FileNotFoundError):
        v.application_targets()
