import importlib.util
from pathlib import Path

import pytest
import yaml

spec = importlib.util.spec_from_file_location('vault_profiles', Path(__file__).resolve().parents[1] / 'migrate_forgehub_vault_profiles.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

CONFIG = '''mcp_servers:
  forgehub:
    command: uv
    args:
      - run
      - /app/forgehub.py
    env:
      FORGEHUB_AGENT_TOKEN: agt_fake_credential
      FORGEHUB_AGENT_SLUG: maia
    tools:
      include:
        - personal_contacts_list
  moodle:
    command: /usr/local/bin/node
    args:
      - /app/moodle.ts
    env:
      MCP_PHASE: write
other: unchanged
'''


def test_only_wraps_the_two_mcp_servers_and_removes_plaintext_token():
    updated = module.rewrite_config(CONFIG, 'maia')
    parsed = yaml.safe_load(updated)
    assert 'agt_fake_credential' not in updated
    assert parsed['other'] == 'unchanged'
    assert parsed['mcp_servers']['forgehub']['args'] == [module.HELPER, 'maia', 'uv', 'run', '/app/forgehub.py']
    assert parsed['mcp_servers']['forgehub']['tools']['include'] == ['personal_contacts_list']
    assert parsed['mcp_servers']['moodle']['env']['FORGEHUB_URL'] == 'http://127.0.0.1:8000'


def test_rejects_an_unexpected_mcp_layout():
    with pytest.raises((ValueError, StopIteration)):
        module.rewrite_config(CONFIG.replace('    args:\n', '    unexpected: value\n    args:\n', 1), 'maia')
