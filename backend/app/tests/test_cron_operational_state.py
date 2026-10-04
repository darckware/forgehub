"""Operational script state exposed by Foundation cron jobs."""

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes import foundation
from app.core.cron_script_state import classify_script


def test_cron_job_reports_profile_script_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profiles = tmp_path / "profiles"
    scripts = profiles / "athos" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "ready.sh").write_text("#!/bin/sh\n")
    (scripts / "broken.sh").symlink_to("absent.sh")
    unreadable = scripts / "unreadable.sh"
    unreadable.write_text("#!/bin/sh\n")
    unreadable.chmod(0)
    monkeypatch.setattr(foundation, "PROFILES_DIR", profiles)

    for name, expected in [
        ("ready.sh", "ok"),
        ("absent.sh", "missing"),
        ("broken.sh", "broken"),
        ("unreadable.sh", "broken"),
        (None, "none"),
    ]:
        job = foundation._raw_job_to_out({"profile": "athos", "name": "ordinary", "script": name})
        assert job.script_state == expected
        assert classify_script(None) == "none"


def test_audit_job_is_tagged():
    audit = foundation._raw_job_to_out({"profile": "athos", "name": "ecosystem-weekly-audit"})
    other_profile = foundation._raw_job_to_out({"profile": "atlas", "name": "ecosystem-weekly-audit"})
    other_name = foundation._raw_job_to_out({"profile": "athos", "name": "different"})
    assert audit.is_audit_job is True
    assert other_profile.is_audit_job is False
    assert other_name.is_audit_job is False


@pytest.mark.asyncio
async def test_script_content_rejects_legacy_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    profiles = tmp_path / "profiles"
    scripts = profiles / "athos" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "ready.sh").write_text("echo ready\n")
    monkeypatch.setattr(foundation, "PROFILES_DIR", profiles)

    for location in ("central", "main", "profile"):
        with pytest.raises(HTTPException) as error:
            await foundation.get_script_content(location, "ready.sh")
        assert error.value.status_code == 404
    result = await foundation.get_script_content("athos", "ready.sh")
    assert result.content == "echo ready\n"
