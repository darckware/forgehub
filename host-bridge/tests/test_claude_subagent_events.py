"""Claude Code stream-json -> SSE events, for runs that launch subagents.

The fixture is a real `claude --output-format stream-json --verbose` capture
(Claude Code 2.1.283) of a parent launching one backgrounded general-purpose
subagent that runs `echo 4`, trimmed to the lines the parser reads.
"""
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURE = Path(__file__).parent / "fixtures" / "claude_subagent_stream.jsonl"


def _events(monkeypatch) -> list[dict]:
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge_app = importlib.import_module("app")
    out: list[dict] = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        events, _sid, _reply = bridge_app._claude_events(json.loads(line))
        out.extend(events)
    return out


def test_launching_tool_start_describes_the_subagent(monkeypatch) -> None:
    starts = [e["tool_start"] for e in _events(monkeypatch) if "tool_start" in e]
    launch = next(s for s in starts if s["name"] == "Agent")
    assert launch["subagent"] == {"description": "soma", "subagent_type": "general-purpose"}
    assert "parent_id" not in launch


def test_subagent_steps_carry_their_parent(monkeypatch) -> None:
    events = _events(monkeypatch)
    launch_id = next(e["tool_start"]["tool_id"] for e in events if e.get("tool_start", {}).get("name") == "Agent")
    bash = next(e["tool_start"] for e in events if e.get("tool_start", {}).get("name") == "Bash")
    assert bash["parent_id"] == launch_id


def test_subagent_text_never_leaks_into_the_main_reply(monkeypatch) -> None:
    events = _events(monkeypatch)
    main_deltas = [e["delta"] for e in events if "delta" in e]
    sub_deltas = [e["subagent_delta"] for e in events if "subagent_delta" in e]
    # The subagent's own answer ("4") arrives only as a subagent_delta tagged
    # with its parent; the parent's reply keeps streaming as plain deltas.
    assert [s["text"] for s in sub_deltas] == ["4"]
    assert all(s["parent_id"] for s in sub_deltas)
    assert any("Agent 'soma' is running in the background" in d for d in main_deltas)


def test_task_lifecycle_becomes_subagent_status(monkeypatch) -> None:
    statuses = [e["subagent_status"] for e in _events(monkeypatch) if "subagent_status" in e]
    assert statuses[0]["status"] == "running" and statuses[0]["backgrounded"] is True
    assert statuses[0]["description"] == "soma"
    assert any(s.get("last_tool") == "Bash" for s in statuses)
    assert statuses[-1]["status"] == "completed"
    assert len({s["tool_id"] for s in statuses}) == 1


def test_tool_results_complete_their_steps(monkeypatch) -> None:
    events = _events(monkeypatch)
    started = {e["tool_start"]["tool_id"] for e in events if "tool_start" in e}
    completed = {e["tool_complete"]["tool_id"] for e in events if "tool_complete" in e}
    assert started and started == completed
