"""Metadata health checks exercise verdicts without querying host state or secrets."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SPEC = importlib.util.spec_from_file_location('health_verifier', Path(__file__).parents[1] / 'checklist_verifier.py')
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)


def metrics(**changes):
    return dict(total=10, failed=0, overdue=0, missing_deadlines=0,
                unchecked_due=0, feedback_overdue=0, queued_due=0) | changes


@pytest.mark.parametrize('field', ['overdue', 'missing_deadlines', 'unchecked_due', 'feedback_overdue'])
def test_messages_fail_for_owed_work_even_with_no_recent_dispatches(monkeypatch, field):
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps(metrics(total=0, queued_due=1, **{field: 1})))
    result = v.check_messages_health()
    assert not result.ok
    assert field in result.notes
    assert 'unavailable' not in result.notes.lower()


def test_messages_report_checked_queue_without_treating_capacity_wait_as_failure(monkeypatch):
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps(metrics(queued_due=8)))
    result = v.check_messages_health()
    assert result.ok
    assert 'queued_due=8' in result.notes


def test_failure_rate_is_still_preserved(monkeypatch):
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps(metrics(failed=3)))
    assert not v.check_messages_health().ok


@pytest.mark.parametrize('payload', ['{}', 'not json', json.dumps(metrics(total=1, failed=2))])
def test_messages_invalid_metrics_never_pass(monkeypatch, payload):
    monkeypatch.setattr(v, 'psql', lambda *args: payload)
    assert not v.check_messages_health().ok


def test_activity_missing_authenticated_delivery_fails(monkeypatch):
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps({'active_profiles': 3, 'recently_executed': 1, 'missing_delivery': 1}))
    result = v.check_outbound_hooks()
    assert not result.ok
    assert 'missing_delivery=1' in result.notes


def test_idle_profiles_are_explicit_and_no_config_or_credentials_are_read(monkeypatch):
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps({'active_profiles': 3, 'recently_executed': 0, 'missing_delivery': 0}))
    monkeypatch.setattr(Path, 'read_text', lambda *args, **kwargs: pytest.fail('must not read profile configs'))
    result = v.check_outbound_hooks()
    assert result.ok
    assert 'idle=3' in result.notes


def test_no_activity_inventory_is_not_a_success(monkeypatch):
    monkeypatch.setattr(v, 'psql', lambda *args: json.dumps({'active_profiles': 0, 'recently_executed': 0, 'missing_delivery': 0}))
    assert not v.check_outbound_hooks().ok


def _hindsight(monkeypatch, facts):
    def fake(url, *a, **k):
        term = url.split('q=', 1)[1].split('&', 1)[0]
        from urllib.parse import unquote_plus
        hits = [f for f in facts if unquote_plus(term) in f['text']]
        return {'items': hits, 'total': len(hits)}
    monkeypatch.setattr(v, 'http_json', fake)


def test_eco027_ignores_facts_that_describe_the_retirement(monkeypatch):
    _hindsight(monkeypatch, [
        {'fact_type': 'world', 'text': 'O sistema migrou de `/root/.hermes/workspaces` para profiles/*/workspace.'},
        {'fact_type': 'world', 'text': 'O Hindsight continha dois fatos com a referência obsoleta `/root/.hermes/workspaces`.'},
        {'fact_type': 'experience', 'text': 'Evidência em /root/.hermes/workspaces/hephaestus/x.md'},
    ])
    assert v.check_hindsight_obsolete().ok


def test_eco027_still_fails_on_a_current_assertion(monkeypatch):
    _hindsight(monkeypatch, [
        {'fact_type': 'world', 'text': 'Os workspaces dos agentes ficam em /root/.hermes/workspaces.'},
    ])
    result = v.check_hindsight_obsolete()
    assert not result.ok and '/root/.hermes/workspaces:1' in result.notes


@pytest.mark.parametrize('text', [
    'não é legado: use /root/.hermes/workspaces',
    'Legacy-free layout: agents use /root/.hermes/workspaces',
    'ECO-027 ok; workspaces are in /root/.hermes/workspaces',
])
def test_eco027_bare_words_do_not_hide_a_current_assertion(monkeypatch, text):
    _hindsight(monkeypatch, [{'fact_type': 'world', 'text': text}])
    assert not v.check_hindsight_obsolete().ok


AUDIT_ROUTINES = [
    {"frequency": "daily", "schedule": "0 19 * * *", "timezone": "America/Sao_Paulo", "enabled": True},
    {"frequency": "weekly", "schedule": "0 19 * * 0", "timezone": "America/Sao_Paulo", "enabled": True},
    {"frequency": "monthly", "schedule": "0 19 1 * *", "timezone": "America/Sao_Paulo", "enabled": True},
    {"frequency": "quarterly", "schedule": "0 19 1 1,4,7,10 *", "timezone": "America/Sao_Paulo", "enabled": True},
]
LEGACY_CRON = {"name": "ecosystem-weekly-audit", "enabled": True, "script": "ecosystem_weekly_audit.sh",
               "schedule": {"expr": "0 19 * * 0"}}


@pytest.mark.parametrize("value,expected", [("daily", "daily"), ("quarterly", "quarterly"), ("", "weekly"),
                                            ("hourly", "weekly"), (None, "weekly")])
def test_check_interval_records_the_auditor_tier(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("FORGEHUB_AUDIT_FREQUENCY", raising=False)
    else:
        monkeypatch.setenv("FORGEHUB_AUDIT_FREQUENCY", value)
    assert v.check_interval() == expected


def test_eco023_accepts_the_four_audit_routines_without_the_cron(monkeypatch):
    monkeypatch.setattr(v, "load_jobs", lambda: [])
    monkeypatch.setattr(v, "psql", lambda *args: json.dumps(AUDIT_ROUTINES))
    result = v.check_weekly_audit()
    assert result.ok and "routines" in result.notes


def test_eco023_flags_the_legacy_cron_still_enabled_but_passes(monkeypatch):
    monkeypatch.setattr(v, "load_jobs", lambda: [LEGACY_CRON])
    monkeypatch.setattr(v, "psql", lambda *args: json.dumps(AUDIT_ROUTINES))
    result = v.check_weekly_audit()
    assert result.ok and "disable it" in result.notes


def test_eco023_falls_back_to_the_legacy_cron_until_routines_are_enabled(monkeypatch):
    monkeypatch.setattr(v, "load_jobs", lambda: [LEGACY_CRON])
    monkeypatch.setattr(v, "psql", lambda *args: json.dumps([dict(AUDIT_ROUTINES[0], enabled=False)]))
    result = v.check_weekly_audit()
    assert result.ok and "legacy cron" in result.notes


def test_eco023_fails_with_neither_schedule(monkeypatch):
    def unreadable(*args):
        raise RuntimeError("column audit_frequency does not exist")

    monkeypatch.setattr(v, "load_jobs", lambda: [])
    monkeypatch.setattr(v, "psql", unreadable)
    result = v.check_weekly_audit()
    assert not result.ok and "unreadable" in result.notes


def test_audit_routine_problems_name_each_tier():
    drifted = [dict(AUDIT_ROUTINES[0], schedule="0 20 * * *"), dict(AUDIT_ROUTINES[1], enabled=False)]
    problems = v.audit_routine_problems(drifted)
    assert problems == ["daily: schedule 0 20 * * * America/Sao_Paulo", "weekly: routine disabled",
                        "monthly: no routine", "quarterly: no routine"]


def test_eco023_does_not_count_a_paused_legacy_cron(monkeypatch):
    monkeypatch.setattr(v, "load_jobs", lambda: [dict(LEGACY_CRON, state="paused")])
    monkeypatch.setattr(v, "psql", lambda *args: json.dumps(AUDIT_ROUTINES))
    result = v.check_weekly_audit()
    assert result.ok and "disable it" not in result.notes
    monkeypatch.setattr(v, "psql", lambda *args: json.dumps([]))
    assert not v.check_weekly_audit().ok
