"""ECO-073: Lara and Maia reach only the ForgeHub tools of the servers marked for them on the screen."""
import importlib.util
from pathlib import Path
import sys

SPEC = importlib.util.spec_from_file_location('ext_verifier', Path(__file__).parents[1] / 'checklist_verifier.py')
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)
SERVER_MAP = v._load_server_map(Path(__file__).parents[3] / 'backend/app/mcp/server_map.py')


def test_inside_the_marked_servers_passes():
    reachable = {'lara': {'send_agent_message', 'list_projects'}, 'maia': {'check_agent_inbox', 'personal_contacts_list'}}
    marked = {'lara': ['forgehub_factory'], 'maia': ['forgehub_factory', 'forgehub_personal']}
    assert v.external_agent_findings(reachable, marked, SERVER_MAP) == []


def test_a_tool_outside_is_reported():
    reachable = {'lara': {'send_agent_message', 'restart_deploy_container'}, 'maia': {'check_agent_inbox'}}
    marked = {'lara': ['forgehub_factory'], 'maia': []}
    findings = v.external_agent_findings(reachable, marked, SERVER_MAP)
    assert findings == ['lara: reaches 1 ForgeHub tool(s) outside its marked servers: restart_deploy_container']


def test_the_whole_catalog_or_no_screen_row_is_reported():
    findings = v.external_agent_findings({'lara': None, 'maia': set()}, {'lara': ['forgehub_factory']}, SERVER_MAP)
    assert findings == ['lara: reaches the whole ForgeHub catalog (no tools.include on its forgehub MCP)',
                        'maia: no row on the Agentes e MCP do ForgeHub screen']
