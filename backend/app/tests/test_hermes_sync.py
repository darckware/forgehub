"""Hermes roster eligibility tests.

Directory presence is evidence that a profile can be read, not authority to
reactivate an archived role.  These tests protect the Foundation registry as
the boundary between a profile directory and an active roster member.
"""

from pathlib import Path

from app.core import hermes_sync


def _write_registry(path: Path) -> None:
    path.write_text(
        """# Registry

| Profile | Agent | Layer | Role | Telegram required |
|---|---|---|---|---|
| `athos` | Athos | Governance | Orchestrator | yes |
| `atlas` | Atlas | Governance | Planning | yes |
""",
        encoding="utf-8",
    )


def test_active_provisioned_profiles_require_directory_and_registry_entry(
    tmp_path: Path, monkeypatch,
) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    for slug in ("athos", "atlas", "archimedes", "lara"):
        (profiles / slug).mkdir()

    registry = tmp_path / "ECOSYSTEM_AGENTS.md"
    _write_registry(registry)
    monkeypatch.setattr(hermes_sync, "PROFILES_DIR", profiles)
    monkeypatch.setattr(hermes_sync, "ECOSYSTEM_AGENTS_PATH", registry)

    assert hermes_sync.list_active_provisioned_profiles() == ["athos", "atlas"]


def test_active_provisioned_profiles_do_not_register_documented_missing_directory(
    tmp_path: Path, monkeypatch,
) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "athos").mkdir()

    registry = tmp_path / "ECOSYSTEM_AGENTS.md"
    _write_registry(registry)
    monkeypatch.setattr(hermes_sync, "PROFILES_DIR", profiles)
    monkeypatch.setattr(hermes_sync, "ECOSYSTEM_AGENTS_PATH", registry)

    assert hermes_sync.list_active_provisioned_profiles() == ["athos"]
