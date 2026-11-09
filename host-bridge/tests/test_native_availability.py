import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_availability import observe_codex_availability

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def setup_sample(home, *, age=30, primary=20, secondary=10, auth_age=600, kind="token_count"):
    home.mkdir(exist_ok=True)
    auth = home / "auth.json"
    auth.write_text("credential-content-must-never-be-read")
    stamp = (NOW - timedelta(seconds=auth_age)).timestamp()
    os.utime(auth, (stamp, stamp))
    sessions = home / "sessions" / "2026" / "11" / "08"
    sessions.mkdir(parents=True, exist_ok=True)
    limits = {"primary": {"used_percent": primary, "window_minutes": 300},
              "secondary": {"used_percent": secondary, "window_minutes": 10080}}
    row = {"timestamp": (NOW - timedelta(seconds=age)).isoformat(), "type": "event_msg",
           "payload": {"type": kind, "rate_limits": limits}}
    (sessions / "rollout-test.jsonl").write_text(json.dumps(row) + "\n")


def test_fresh_official_windows_are_available(tmp_path):
    setup_sample(tmp_path)
    result = observe_codex_availability(tmp_path, NOW)
    assert result["available"] is True
    assert result["observed_at"] == (NOW - timedelta(seconds=30)).isoformat()
    assert set(result) == {"available", "observed_at", "reason"}


@pytest.mark.parametrize("kwargs,expected", [({"primary": 100}, False), ({"secondary": 100}, False),
    ({"age": 3600}, None), ({"auth_age": 10}, None), ({"secondary": None}, None),
    ({"kind": "assistant_message"}, None), ({"age": -60}, None)])
def test_rejects_unsafe_observations(tmp_path, kwargs, expected):
    setup_sample(tmp_path, **kwargs)
    assert observe_codex_availability(tmp_path, NOW)["available"] is expected


def test_no_auth_or_other_home_cannot_clear_limit(tmp_path):
    assert observe_codex_availability(tmp_path, NOW)["available"] is None


def test_symlink_transcript_outside_home_is_ignored(tmp_path):
    home = tmp_path / "home"
    setup_sample(home)
    transcript = next((home / "sessions").rglob("*.jsonl"))
    external = tmp_path / "external.jsonl"
    transcript.rename(external)
    transcript.symlink_to(external)
    assert observe_codex_availability(home, NOW)["available"] is None


def test_newer_unknown_observation_supersedes_positive_sample(tmp_path):
    setup_sample(tmp_path)
    path = next((tmp_path / "sessions").rglob("*.jsonl"))
    latest = {"timestamp": (NOW - timedelta(seconds=5)).isoformat(), "type": "event_msg",
              "payload": {"type": "token_count", "rate_limits": {"primary": {"used_percent": 5}}}}
    with path.open("a") as handle:
        handle.write(json.dumps(latest) + "\n")
    assert observe_codex_availability(tmp_path, NOW)["available"] is None


def test_credentials_are_only_statted_never_read(tmp_path, monkeypatch):
    setup_sample(tmp_path)
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert path.name != "auth.json"
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    assert observe_codex_availability(tmp_path, NOW)["available"] is True


def test_ambiguous_identical_windows_cannot_clear_limit(tmp_path):
    setup_sample(tmp_path)
    path = next((tmp_path / "sessions").rglob("*.jsonl"))
    event = json.loads(path.read_text())
    event["payload"]["rate_limits"]["secondary"]["window_minutes"] = 300
    path.write_text(json.dumps(event) + "\n")
    assert observe_codex_availability(tmp_path, NOW)["available"] is None


def test_fresh_sample_survives_large_historical_session_tail_budget(tmp_path):
    setup_sample(tmp_path)
    sessions = tmp_path / "sessions"
    fresh = next(sessions.rglob("*.jsonl"))
    fresh_stamp = NOW.timestamp()
    os.utime(fresh, (fresh_stamp, fresh_stamp))
    for index in range(10):
        history = sessions / f"rollout-old-{index}.jsonl"
        history.write_bytes(b"historical-transcript-data\n" * 11000)
        old_stamp = (NOW - timedelta(days=1)).timestamp()
        os.utime(history, (old_stamp, old_stamp))
    result = observe_codex_availability(tmp_path, NOW)
    assert result["available"] is True
