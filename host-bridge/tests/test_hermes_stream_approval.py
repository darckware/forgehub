"""The stream must use Hermes's approval context API for each turn."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def test_stream_id_is_not_emitted_before_hermes_import_completes(monkeypatch, tmp_path):
    stream_path = Path(__file__).resolve().parents[1] / "hermes_stream.py"
    spec = importlib.util.spec_from_file_location("hermes_stream_import_test", stream_path)
    stream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stream)

    # Hermes can restart this script while importing cli to finish a source
    # update. An ID announced before that restart belongs to the old process.
    cli = ModuleType("cli")
    monkeypatch.setitem(sys.modules, "cli", cli)
    events = []
    monkeypatch.setattr(stream, "_emit", events.append)
    monkeypatch.setattr(sys, "argv", ["hermes_stream.py", "--profile-home", str(tmp_path), "--message", "Oi"])
    monkeypatch.chdir(tmp_path)

    stream.main()

    assert all("stream_id" not in event for event in events)
    assert events[-1].get("error", "").startswith("import failed:")


def test_stream_binds_approval_session_with_current_hermes_api(monkeypatch, tmp_path):
    stream_path = Path(__file__).resolve().parents[1] / "hermes_stream.py"
    spec = importlib.util.spec_from_file_location("hermes_stream_approval_test", stream_path)
    stream = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stream)

    events = []
    approval = ModuleType("tools.approval")
    approval.register_gateway_notify = lambda key, callback: events.append(("register", key))
    approval.unregister_gateway_notify = lambda key: events.append(("unregister", key))
    context = ModuleType("tools.approval_context")
    context.set_current_session_key = lambda key: events.append(("set", key)) or "session-token"
    context.reset_current_session_key = lambda token: events.append(("reset", token))
    tools_package = ModuleType("tools")
    tools_package.__path__ = []
    monkeypatch.setitem(sys.modules, "tools", tools_package)
    monkeypatch.setitem(sys.modules, "tools.approval", approval)
    monkeypatch.setitem(sys.modules, "tools.approval_context", context)

    class FakeCLI:
        def __init__(self, resume=None):
            self.agent = SimpleNamespace(run_conversation=lambda **kwargs: {"final_response": "Olá"})
            self.conversation_history = []
            self.session_id = "session-123"

        def _init_agent(self):
            return True

    cli = ModuleType("cli")
    cli.HermesCLI = FakeCLI
    cli._looks_like_slash_command = lambda message: False
    commands = ModuleType("hermes_cli.commands")
    commands.resolve_command = lambda name: None
    hermes_cli = ModuleType("hermes_cli")
    hermes_cli.__path__ = []
    monkeypatch.setitem(sys.modules, "cli", cli)
    monkeypatch.setitem(sys.modules, "hermes_cli", hermes_cli)
    monkeypatch.setitem(sys.modules, "hermes_cli.commands", commands)

    monkeypatch.setattr(stream, "_emit", events.append)
    monkeypatch.setattr(stream, "_start_approval_listener", lambda key: None)
    monkeypatch.setattr(sys, "argv", ["hermes_stream.py", "--profile-home", str(tmp_path), "--message", "Oi"])
    monkeypatch.chdir(tmp_path)

    stream.main()

    assert any(isinstance(event, dict) and event.get("done") for event in events)
    stream_id = events[0]["stream_id"]
    assert ("register", stream_id) in events
    assert ("set", stream_id) in events
    assert ("reset", "session-token") in events
    assert ("unregister", stream_id) in events
