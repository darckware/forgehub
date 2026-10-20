"""The personal-contact tools only run inside the ForgeHub MCP, never as a server of their own."""

import os
import subprocess
import sys
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "mcp" / "personal_contacts.py"


def test_personal_contacts_cannot_start_as_separate_mcp():
    env = {**os.environ, "FORGEHUB_AGENT_SLUG": "maia"}
    result = subprocess.run(
        [sys.executable, str(MODULE)], capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode != 0
    assert "ForgeHub" in result.stderr
