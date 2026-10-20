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


def test_parse_profile_identity_reads_plain_and_bold_keys(tmp_path, monkeypatch):
    from app.core import hermes_sync

    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "IDENTITY.md").write_text("# IDENTITY\n- Name: Athos\n- Mission: govern\n")
    (tmp_path / "bold").mkdir()
    (tmp_path / "bold" / "IDENTITY.md").write_text(
        "# IDENTITY.md\n\n- **Name:** Daedalus\n- **Layer:** Engineering\n"
        "- **Role:** Engineering lead\n- **Mission:** Lead engineering without coding.\n- **Avatar:**\n"
    )
    monkeypatch.setattr(hermes_sync, "PROFILES_DIR", tmp_path)
    assert hermes_sync.parse_profile_identity("plain")["mission"] == "govern"
    bold = hermes_sync.parse_profile_identity("bold")
    assert bold == {"name": "Daedalus", "layer": "Engineering", "role": "Engineering lead",
                    "mission": "Lead engineering without coding."}
