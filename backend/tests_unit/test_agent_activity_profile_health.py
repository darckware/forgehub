"""Profile health on the Agent Activity board (core/agent_activity._profile_issues).

`has_profile` is only set by the Hermes Foundation sync, so an external
runtime (claude/codex/agy) must be judged by its runtime home on disk --
otherwise Porthus/Aramis/Dartan always read "Profile metadata is not
registered" even though their home exists.
"""
from app.core.agent_activity import _profile_issues
from app.db.models.agent import Agent


def _agent(**fields) -> Agent:
    return Agent(name="Test", profile_slug="test", **fields)


def test_hermes_agent_with_profile_is_healthy():
    assert _profile_issues(_agent(runtime_type="hermes", has_profile=True)) == []


def test_external_runtime_with_existing_home_is_healthy(tmp_path):
    agent = _agent(runtime_type="claude", has_profile=False, home_path=str(tmp_path))
    assert _profile_issues(agent) == []


def test_external_runtime_with_missing_home_reports_the_path(tmp_path):
    missing = tmp_path / "gone"
    agent = _agent(runtime_type="codex", has_profile=False, home_path=str(missing))
    assert _profile_issues(agent) == [f"Runtime home not found: {missing}"]


def test_unknown_runtime_without_profile_keeps_the_original_warning():
    agent = _agent(runtime_type=None, has_profile=False)
    assert _profile_issues(agent) == ["Profile metadata is not registered"]
