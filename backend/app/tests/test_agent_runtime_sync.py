"""Tests for the filesystem-driven runtime sync (app/core/agent_runtime_sync.py).

This is the "real" sync, as opposed to hermes_sync's doc-driven one: it decides
what an agent *runs* from evidence on disk. The behaviour worth protecting is
the conservatism -- it fills a missing runtime, never overwrites one, and
reports anything it cannot reconcile instead of guessing.

Pure filesystem, no DB: the route layer applies whatever a plan says.
"""
import pytest

from app.core import agent_profile_files, agent_runtime_sync


@pytest.fixture
def fake_host(monkeypatch, tmp_path):
    """A host layout under tmp_path: Hermes profiles plus the external runtime
    homes, all redirected so no test ever reads the real /root."""
    profiles = tmp_path / "profiles"
    (profiles / "kairos").mkdir(parents=True)
    (profiles / "athos").mkdir()
    claude_home = tmp_path / "dot-claude"
    claude_home.mkdir()

    monkeypatch.setattr(agent_profile_files, "HERMES_PROFILES_ROOT", str(profiles))
    monkeypatch.setattr(agent_profile_files, "HOST_PATH_MOUNTS", ())
    monkeypatch.setattr(agent_profile_files, "HOST_ROOT_MOUNT", str(tmp_path / "nonexistent"))
    monkeypatch.setattr(
        agent_profile_files,
        "RUNTIME_DEFAULT_HOMES",
        {"claude": str(claude_home), "codex": str(tmp_path / "dot-codex")},
    )
    return tmp_path


def test_detects_hermes_from_the_profile_directory(fake_host):
    """The Kairos case: registered with no runtime, but its profile directory
    is right there on disk."""
    plan = agent_runtime_sync.plan_for_agent(
        agent_id="1", agent_name="Kairos", profile_slug="kairos",
        runtime_type=None, home_path=None,
    )
    assert plan.detected.runtime_type == "hermes"
    assert "kairos exists" in plan.detected.evidence
    assert plan.fill_runtime_type == "hermes"
    assert plan.issues == []


def test_detects_external_runtime_from_its_home(fake_host):
    plan = agent_runtime_sync.plan_for_agent(
        agent_id="2", agent_name="Porthos", profile_slug="porthos",
        runtime_type="claude", home_path=None,
    )
    assert plan.detected.runtime_type == "claude"
    # Already registered: nothing to fill, nothing to complain about.
    assert plan.fill_runtime_type is None
    assert plan.issues == []


def test_runtime_home_that_does_not_exist_is_not_claimed(fake_host):
    """codex is in the runtime table but its home was never created here."""
    plan = agent_runtime_sync.plan_for_agent(
        agent_id="3", agent_name="Aramis", profile_slug="aramis",
        runtime_type=None, home_path=None,
    )
    assert plan.detected.runtime_type is None
    assert plan.fill_runtime_type is None
    assert any("nothing on disk" in issue for issue in plan.issues)


def test_existing_runtime_is_never_overwritten(fake_host):
    """A registered runtime decides the real command line used to execute the
    agent -- a mismatch is reported, not silently 'fixed'."""
    plan = agent_runtime_sync.plan_for_agent(
        agent_id="4", agent_name="Athos", profile_slug="athos",
        runtime_type="claude", home_path=None,
    )
    assert plan.detected.runtime_type == "hermes"
    assert plan.fill_runtime_type is None
    assert any("left as is" in issue for issue in plan.issues)


def test_unreachable_home_is_reported(fake_host):
    plan = agent_runtime_sync.plan_for_agent(
        agent_id="5", agent_name="Ghost", profile_slug="ghost",
        runtime_type="hermes", home_path="/nowhere/at/all",
    )
    assert plan.detected.home_resolved is False
    assert any("not reachable" in issue for issue in plan.issues)


def test_agent_with_nothing_on_disk_gets_an_explicit_issue(fake_host):
    plan = agent_runtime_sync.plan_for_agent(
        agent_id="6", agent_name="Nobody", profile_slug=None,
        runtime_type=None, home_path=None,
    )
    assert plan.fill_runtime_type is None
    assert plan.issues


def test_unregistered_profiles_are_listed_not_created(fake_host):
    """A profile directory nobody claims is reported for a human to judge --
    inventing an agent row here would make a scratch dir look like a member
    of the roster."""
    assert agent_runtime_sync.list_profile_dirs() == ["athos", "kairos"]
    assert agent_runtime_sync.unregistered_profiles({"athos"}) == ["kairos"]
    assert agent_runtime_sync.unregistered_profiles({"athos", "kairos"}) == []


def test_detection_reports_the_mcp_config_it_would_read(fake_host):
    plan = agent_runtime_sync.plan_for_agent(
        agent_id="7", agent_name="Kairos", profile_slug="kairos",
        runtime_type=None, home_path=None,
    )
    assert plan.detected.mcp_config_path.endswith("/kairos/config.yaml")
    # Not created in this fixture: reported as absent, not as an error.
    assert plan.detected.mcp_config_exists is False
