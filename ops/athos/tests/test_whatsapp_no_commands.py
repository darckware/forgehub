"""ECO-071: no WhatsApp entry accepts slash commands; one adapter per WhatsApp session."""
import importlib.util
from pathlib import Path
import sys

SPEC = importlib.util.spec_from_file_location('wa_verifier', Path(__file__).parents[1] / 'checklist_verifier.py')
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)

LOCKED = """whatsapp:
  enabled: true
  session_path: {session}
  allow_admin_from: [whatsapp-sem-comandos]
  user_allowed_commands: []
  group_allow_admin_from: [whatsapp-sem-comandos]
  group_user_allowed_commands: []
"""


def write(tmp_path, name, text):
    path = tmp_path / f'{name}.yaml'
    path.write_text(text)
    return path


def test_locked_config_passes(tmp_path):
    cfg = write(tmp_path, 'lara', LOCKED.format(session='/s/lara'))
    assert v.whatsapp_command_findings({'lara': cfg}) == []


def test_missing_admin_list_means_everyone_is_admin(tmp_path):
    cfg = write(tmp_path, 'maia', "whatsapp:\n  enabled: true\n  session_path: /s/maia\n")
    findings = v.whatsapp_command_findings({'maia': cfg})
    assert any('no whatsapp.allow_admin_from' in f for f in findings)
    assert any('no whatsapp.group_allow_admin_from' in f for f in findings)


def test_real_admin_is_reported_without_its_number(tmp_path):
    text = LOCKED.format(session='/s/lara').replace("allow_admin_from: [whatsapp-sem-comandos]\n  user", "allow_admin_from: ['5521900000000']\n  user", 1)
    findings = v.whatsapp_command_findings({'root': write(tmp_path, 'root', text)})
    assert len(findings) == 1 and 'lists 1 admin(s)' in findings[0]
    assert '5521900000000' not in findings[0]


def test_allowed_commands_are_reported(tmp_path):
    text = LOCKED.format(session='/s/x').replace("group_user_allowed_commands: []", "group_user_allowed_commands: ['/restart', yolo]")
    findings = v.whatsapp_command_findings({'x': write(tmp_path, 'x', text)})
    assert findings == ['x: whatsapp.group_user_allowed_commands allows /restart, /yolo']


def test_platforms_extra_overrides_root_block(tmp_path):
    text = LOCKED.format(session='/s/x') + "platforms:\n  whatsapp:\n    extra:\n      allow_admin_from: '5521900000000'\n"
    findings = v.whatsapp_command_findings({'x': write(tmp_path, 'x', text)})
    assert any('whatsapp.allow_admin_from lists 1 admin(s)' in f for f in findings)


def test_disabled_whatsapp_is_ignored(tmp_path):
    cfg = write(tmp_path, 'athos', "whatsapp:\n  enabled: false\n  allow_admin_from: ['5521900000000']\n")
    assert v.whatsapp_command_findings({'athos': cfg}) == []


def test_enabled_only_under_platforms_counts(tmp_path):
    cfg = write(tmp_path, 'lara', "whatsapp:\n  enabled: false\nplatforms:\n  whatsapp:\n    enabled: true\n")
    assert any('no whatsapp.allow_admin_from' in f for f in v.whatsapp_command_findings({'lara': cfg}))


def test_two_adapters_on_one_session(tmp_path):
    configs = {'root': write(tmp_path, 'root', LOCKED.format(session='/s/lara/')),
               'lara': write(tmp_path, 'lara', LOCKED.format(session='/s/lara'))}
    findings = v.whatsapp_command_findings(configs)
    assert findings == [f for f in findings if 'served by 2 adapters (root, lara)' in f] and len(findings) == 1


def test_unreadable_config_fails(tmp_path):
    findings = v.whatsapp_command_findings({'x': tmp_path / 'missing.yaml'})
    assert findings == ['x: config.yaml unreadable (FileNotFoundError)']


def test_parked_profiles_are_skipped(tmp_path, monkeypatch):
    (tmp_path / 'config.yaml').write_text(LOCKED.format(session='/s/lara'))
    parked = tmp_path / 'profiles' / 'default'
    parked.mkdir(parents=True)
    (parked / 'config.yaml').write_text("whatsapp:\n  enabled: true\n  session_path: /s/lara\n")
    (parked / 'gateway.parked').write_text('')
    monkeypatch.setattr(v, 'HERMES', tmp_path)
    assert v.whatsapp_command_findings() == []
    assert v.check_whatsapp_no_commands().ok
