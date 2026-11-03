"""M0.8 usage-limit patterns and infrastructure failures (cycle spec §3.3, §3.4 item 3).

Pure logic, no database: run with ``pytest --noconftest``. Each runtime's
limit message -> the reset time in the timezone it names (else the host's);
near-miss strings -> no match, never a guess.
"""
import os

os.environ.setdefault("ENVIRONMENT", "test")

from datetime import datetime, timedelta, timezone  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

import pytest  # noqa: E402

from app.core.agent_availability import classify_infra_failure, parse_usage_limit  # noqa: E402
from app.main import is_agent_command_path  # noqa: E402

SP = ZoneInfo("America/Sao_Paulo")
# Run #41798 ended at 10:08:47 -03 on 2026-10-30 with this exact output.
RUN_41798 = "You've hit your 5-hour limit · resets 2:30pm (America/Sao_Paulo)"
AT_41798 = datetime(2026, 10, 30, 10, 8, 47, tzinfo=SP)


def test_claude_real_output_41798():
    assert parse_usage_limit("claude", RUN_41798, AT_41798) == datetime(2026, 10, 30, 14, 30, tzinfo=SP)


def test_claude_reset_after_midnight_without_zone_uses_host_zone():
    # 2026-10-28: Porthus stopped at 00:15 with "resets 3:30am".
    at = datetime(2026, 10, 28, 0, 15, tzinfo=SP)
    assert parse_usage_limit("claude", "You've hit your 5-hour limit · resets 3:30am", at) == \
        datetime(2026, 10, 28, 3, 30, tzinfo=SP)


def test_claude_reset_time_already_passed_today_is_tomorrow():
    at = datetime(2026, 10, 30, 23, 0, tzinfo=SP)
    assert parse_usage_limit("claude", "You've hit your limit · resets 2pm", at) == datetime(2026, 10, 31, 14, 0, tzinfo=SP)


def test_claude_named_zone_differs_from_host():
    at = datetime(2026, 10, 30, 10, 0, tzinfo=timezone.utc)
    assert parse_usage_limit("claude", "You've hit your weekly limit · resets 9am (UTC)", at) == \
        datetime(2026, 10, 31, 9, 0, tzinfo=timezone.utc)
    # A named zone that is not a zone: no match rather than the host's zone.
    assert parse_usage_limit("claude", "You've hit your limit · resets 9am (Mars/Olympus)", at) is None
    assert parse_usage_limit("claude", "You've hit your weekly limit · resets Nov 3, 9am (Europe/Lisbon)", at) == \
        datetime(2026, 11, 3, 9, 0, tzinfo=ZoneInfo("Europe/Lisbon"))


def test_claude_epoch_format():
    at = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    reset = at + timedelta(hours=2)
    assert parse_usage_limit("claude", f"Claude AI usage limit reached|{int(reset.timestamp())}", at) == reset
    past = at - timedelta(hours=1)
    assert parse_usage_limit("claude", f"Claude AI usage limit reached|{int(past.timestamp())}", at) is None


def test_codex_relative_and_clock():
    at = datetime(2026, 10, 30, 12, 0, tzinfo=timezone.utc)
    text = ("You've hit your usage limit. Upgrade to Pro (https://openai.com/chatgpt/pricing) "
            "or try again in 2 hours 13 minutes.")
    assert parse_usage_limit("codex", text, at) == at + timedelta(hours=2, minutes=13)
    assert parse_usage_limit("codex", "You've hit your usage limit. Try again in 1 day 3 hours.", at) == \
        at + timedelta(days=1, hours=3)
    local = datetime(2026, 10, 30, 12, 0, tzinfo=SP)
    assert parse_usage_limit("codex", "You've hit your usage limit. Try again at 3:39 PM.", local) == \
        datetime(2026, 10, 30, 15, 39, tzinfo=SP)


@pytest.mark.parametrize(("runtime", "text"), [
    ("claude", "The cache resets 2:30pm every day"),                  # no "hit your limit"
    ("claude", "You've hit your limit"),                               # no reset time
    ("claude", "You've hit your 5-hour limit · resets 13:30pm"),       # impossible clock
    ("claude", "You've hit your limit · resets Foo 3, 9am"),           # unknown month
    ("codex", "try again in 2 hours"),                                 # not the limit message
    ("codex", "You've hit your usage limit."),                         # no reset
    ("hermes", RUN_41798),                                             # other runtime: no pattern
    ("agy", "Quota exceeded for quota metric 'Requests'"),             # agy gives no reset time
    ("claude", ""),
    ("claude", None),
])
def test_near_misses_write_nothing(runtime, text):
    assert parse_usage_limit(runtime, text, AT_41798) is None


@pytest.mark.parametrize(("text", "error", "kind"), [
    (RUN_41798, "The agent run ended as 'failed'.", "usage_limit"),
    ("Error: 400 INVALID_ARGUMENT: Request contains an invalid argument.", None, "provider_error"),
    ("API Error: 529 {\"type\":\"error\",\"error\":{\"type\":\"overloaded_error\"}}", None, "provider_error"),
    ("Claude requested permissions to write, but you haven't granted it yet. Permission denied.", None,
     "permission_denied"),
    ("", "The agent run ended as 'timed_out'.", "timeout_no_output"),
    ("Tests fail: 3 assertions in test_x.py\nSTATUS: PARTIAL", "The agent reported STATUS: PARTIAL", None),
    ("Implemented, but the reviewer asked for changes.", None, None),
])
def test_infra_failure_classification(text, error, kind):
    assert classify_infra_failure(text, error) == kind


@pytest.mark.parametrize(("method", "path", "admitted"), [
    ("PUT", "/api/v1/agents/11111111-1111-4111-8111-111111111111/availability", True),
    ("GET", "/api/v1/agents/11111111-1111-4111-8111-111111111111/availability", True),
    ("DELETE", "/api/v1/agents/11111111-1111-4111-8111-111111111111/availability", False),
    ("PUT", "/api/v1/agents/11111111-1111-4111-8111-111111111111", False),
    ("GET", "/api/v1/missions/11111111-1111-4111-8111-111111111111/cycle", True),
    ("POST", "/api/v1/missions/11111111-1111-4111-8111-111111111111/decisions", True),
])
def test_agent_paths(method, path, admitted):
    assert is_agent_command_path(method, path) is admitted
