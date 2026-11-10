"""A cancellation request is not evidence that the runtime has terminated."""
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_cancel_preserves_running_identity_until_process_exit(monkeypatch):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    run = {"run_id": "cancel-test", "status": "running", "pid": 123,
           "process": SimpleNamespace(pid=123), "finished_at": None}
    monkeypatch.setattr(bridge, "_agent_runs", {"cancel-test": run})
    monkeypatch.setattr(bridge, "_persist_agent_run", lambda *_: None)
    monkeypatch.setattr(bridge.os, "killpg", lambda *_: None)  # process ignores TERM
    response = asyncio.run(bridge.cancel_agent_run("cancel-test", "test-token"))
    assert response["status"] == "running"
    assert response["cancel_requested"] is True
    assert run["finished_at"] is None
    assert run["process"].pid == 123


def test_monitor_confirms_requested_cancellation_only_after_exit(monkeypatch):
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    run = {"run_id": "cancel-test", "status": "running", "cancel_requested": True}
    monkeypatch.setattr(bridge, "_agent_runs", {"cancel-test": run})
    monkeypatch.setattr(bridge, "_persist_agent_run", lambda *_: None)
    proc = SimpleNamespace(pid=123, returncode=-15, communicate=lambda **kw: ("partial", ""))
    bridge._monitor_agent_run("cancel-test", proc, 30)
    assert run["status"] == "cancelled"
    assert run["finished_at"] is not None
    assert run["output"] == "partial"


def test_a_real_term_resistant_child_is_not_reported_cancelled_early(monkeypatch):
    import subprocess
    monkeypatch.setenv("FORGEHUB_BRIDGE_TOKEN", "test-token")
    bridge = importlib.import_module("app")
    proc = subprocess.Popen([sys.executable, "-u", "-c",
        "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('ready',flush=True);time.sleep(30)"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        assert proc.stdout.readline().strip() == "ready"
        run = {"run_id": "real-cancel-test", "status": "running", "pid": proc.pid,
               "process": proc, "finished_at": None}
        monkeypatch.setattr(bridge, "_agent_runs", {"real-cancel-test": run})
        monkeypatch.setattr(bridge, "_persist_agent_run", lambda *_: None)
        response = asyncio.run(bridge.cancel_agent_run("real-cancel-test", "test-token"))
        assert proc.poll() is None
        assert response["status"] == "running" and run["finished_at"] is None
        proc.kill()
        bridge._monitor_agent_run("real-cancel-test", proc, 2)
        assert run["status"] == "cancelled" and run["finished_at"] is not None
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
