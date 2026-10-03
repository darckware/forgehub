"""External runtimes receive their identity with every dispatch (the bridge
passes only the task text, and ~/.claude/CLAUDE.md is shared with every
operator session, so it can't say "you are Porthus")."""
from app.core import agent_runs
from app.core.agent_profile_files import IDENTITY_PREAMBLE_MAX_CHARS, external_identity_preamble
from app.db.models.agent import Agent


def _agent(tmp_path, runtime="codex", name="Aramis"):
    return Agent(name=name, runtime_type=runtime, profile_slug=name.lower(), home_path=str(tmp_path))


def test_preamble_carries_identity_and_soul(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("# IDENTITY\n- **Name:** Aramis\n- **Mission:** backend")
    (tmp_path / "SOUL.md").write_text("Precise, test-first.")
    preamble = external_identity_preamble(_agent(tmp_path))
    assert preamble.startswith("<agent-identity>\nYou are Aramis")
    assert "**Mission:** backend" in preamble and "Precise, test-first." in preamble
    assert preamble.endswith("</agent-identity>")


def test_no_preamble_for_hermes_or_missing_files(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("x")
    assert external_identity_preamble(_agent(tmp_path, runtime="hermes", name="Athos")) is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert external_identity_preamble(_agent(empty)) is None


def test_preamble_is_bounded(tmp_path):
    (tmp_path / "SOUL.md").write_text("a" * (IDENTITY_PREAMBLE_MAX_CHARS * 2))
    assert len(external_identity_preamble(_agent(tmp_path))) < IDENTITY_PREAMBLE_MAX_CHARS + 200


async def test_dispatch_prepends_identity(tmp_path, monkeypatch):
    (tmp_path / "IDENTITY.md").write_text("- **Name:** Porthus")
    sent = {}

    class FakeResponse:
        status_code = 202

        def raise_for_status(self):
            return None

        def json(self):
            return {"run_id": "r1"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json, headers):
            sent.update(json)
            return FakeResponse()

    monkeypatch.setattr(agent_runs.httpx, "AsyncClient", FakeClient)
    await agent_runs.dispatch_agent_run("r1", _agent(tmp_path, runtime="claude", name="Porthus"), "Revise o PR.", "/root")
    assert sent["prompt"].startswith("<agent-identity>\nYou are Porthus")
    assert sent["prompt"].endswith("Revise o PR.")
