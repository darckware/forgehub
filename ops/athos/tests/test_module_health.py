"""Pure module checks reject incomplete evidence and surface every violation."""
import importlib.util
from pathlib import Path
import sys

import pytest

PATH = Path(__file__).resolve().parents[1] / 'module_health.py'
spec = importlib.util.spec_from_file_location('module_health_tests', PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


@pytest.mark.parametrize('name', ['workers','mission','factory','remote','sessions','routines'])
def test_all_checks_fail_closed_and_only_emit_counts(name):
    check = m.CHECKS[name]
    data = {key: 0 for key in check.fields}
    if name == 'workers':
        data['registered'] = 5
    assert check.evaluate(data)[0]
    for field in check.violations:
        bad = dict(data, **{field: 1})
        assert not check.evaluate(bad)[0], field
    for invalid in ({}, dict(data, **{check.fields[0]: -1}), dict(data, **{check.fields[0]: True})):
        with pytest.raises(ValueError):
            check.evaluate(invalid)
    ok, output = check.evaluate(data | {'secret': 'never output'})
    assert 'never output' not in output


def test_workers_require_all_five_observations():
    check = m.CHECKS['workers']
    assert not check.evaluate(dict(registered=4, disabled=0, unhealthy=0))[0]
    assert check.evaluate(dict(registered=5, disabled=5, unhealthy=0)) == (True, 'registered=5; disabled=5; unhealthy=0')


def test_installed_verifier_routes_module_checks_without_exposing_failures(monkeypatch):
    import json
    path = PATH.with_name('checklist_verifier.py')
    spec = importlib.util.spec_from_file_location('module_wiring_tests', path)
    v = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = v
    spec.loader.exec_module(v)
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps({'total':1,'invalid':0,'post_expiry_activity':0}))
    assert v.CHECKS['ECO-065']().ok
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps({'total':1,'invalid':0,'post_expiry_activity':1}))
    assert not v.CHECKS['ECO-065']().ok

    def unavailable(*args):
        raise RuntimeError('sensitive connection details')

    monkeypatch.setattr(v, 'psql', unavailable)
    result = v.CHECKS['ECO-065']()
    assert not result.ok
    assert 'sensitive' not in result.notes


def test_routine_evidence_counts_only_enabled_routines_in_the_last_week():
    """2026-11-13: history of disabled routines and runs older than the weekly audit window no
    longer keeps ECO-066 red forever; the records themselves are never rewritten."""
    query = m.ROUTINE_QUERY
    clause = query[query.index("'missing_evidence'"):]
    assert "r.enabled" in clause
    assert "x.occurrence_at>=now()-interval '7 days'" in clause
    demand = query[query.index("'missing_demand'"):query.index("'missing_evidence'")]
    assert "r.enabled" in demand and "interval" not in demand
    # Audit routines run Auditor batches, never a Messages task (2026-11-13).
    assert "r.kind<>'audit'" in demand


def test_routine_health_fails_on_lost_audit_runs_not_rescued_by_a_retry():
    """2026-11-13: a failed or missed audit run of an enabled audit routine in
    the last 7 days is a failure, unless its retry completed."""
    query = m.ROUTINE_QUERY
    clause = query[query.index("'failed_audit'"):]
    assert "r.kind='audit'" in clause and "x.status IN ('failed','missed')" in clause
    assert "y.retry_of_run_id=x.id AND y.status='completed'" in clause
    assert 'failed_audit' in m.CHECKS['routines'].violations
