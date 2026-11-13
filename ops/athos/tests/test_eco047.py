"""ECO-047 fixtures replace only host commands and public HTTP probes."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

SPEC = importlib.util.spec_from_file_location("eco047_verifier", Path(__file__).resolve().parents[1] / "checklist_verifier.py")
v = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = v
SPEC.loader.exec_module(v)

UFW = '''Status: active
Default: deny (incoming), allow (outgoing), deny (routed)

To                         Action      From
--                         ------      ----
8910                       ALLOW IN    127.0.0.1
8910/tcp on lo             ALLOW IN    Anywhere
8910/tcp                   ALLOW IN    172.19.0.0/16 # bridge
8910/tcp (v6) on lo        ALLOW IN    Anywhere (v6)
'''


def host(monkeypatch, sockets="", firewall=UFW, ss_code=0, ufw_code=0, public_open=None):
    def run(args, **kwargs):
        if args[0] == "hostname":
            value = "100.105.235.114 203.0.113.1" if args[1] == "-I" else "test-host"
            return subprocess.CompletedProcess(args, 0, value, "")
        is_ss = args[0] == "ss"
        return subprocess.CompletedProcess(args, ss_code if is_ss else ufw_code,
                                           sockets if is_ss else firewall, "command failed")
    monkeypatch.setattr(v, "run", run)
    monkeypatch.setattr(v, "_url_status", lambda url, expected: v.fail(url) if url == public_open else v.ok(url))


def socket(address, *owners):
    processes = ','.join(f'("{name}",pid=42,fd=3)' for name in owners)
    return f'LISTEN 0 4096 {address} 0.0.0.0:* users:({processes})\n'


@pytest.mark.parametrize('address,owners', [
    ('100.105.235.114:22', ('sshd', 'systemd')),
    ('100.105.235.114:37770', ('tailscaled',)),
    ('100.105.235.114:49123', ('tailscaled',)),
    ('100.105.235.114%tailscale0:37770', ('tailscaled',)),
    *[(f'100.105.235.114:{port}', ('docker-proxy',)) for port in (3000, 8020, 21115, 21116, 21117)],
    ('0.0.0.0:8910', ('python',)),
])
def test_approved_listeners(monkeypatch, address, owners):
    host(monkeypatch, socket(address, *owners))
    assert v.check_public_interfaces().ok


@pytest.mark.parametrize('address,owners', [
    ('100.105.235.114:22', ('python',)),
    ('100.105.235.114:37770', ('node',)),
    ('100.105.235.114:37770', ()),
    ('100.105.235.114:22', ('sshd', 'python')),
    ('100.105.235.114:21118', ('docker-proxy',)),
    ('100.105.235.114:21115', ('python',)),
    *[(f'{ip}:21116', ('hbbs',)) for ip in ('0.0.0.0', '[::]', '*')],
    ('0.0.0.0:22', ('sshd',)),
    ('0.0.0.0:37770', ('tailscaled',)),
])
def test_unapproved_application_or_wildcard_fails(monkeypatch, address, owners):
    host(monkeypatch, socket(address, *owners))
    assert not v.check_public_interfaces().ok


@pytest.mark.parametrize('firewall,code', [
    ('Status: inactive', 0), (UFW, 1),
    (UFW.replace('deny (incoming)', 'allow (incoming)'), 0),
    (UFW + '8910/tcp                   ALLOW IN    Anywhere\n', 0),
    (UFW + '8910/tcp                   ALLOW IN    Anywhere # 172.19.0.0/16\n', 0),
    (UFW + '8910/tcp (v6)              ALLOW IN    Anywhere (v6)\n', 0),
    (UFW + 'Anywhere                   ALLOW IN    Anywhere\n', 0),
    (UFW + '8000:9000/tcp              ALLOW IN    Anywhere\n', 0),
    ('Status: active\nDefault: deny (incoming)\n', 0),
])
def test_bridge_requires_proven_firewall_restriction(monkeypatch, firewall, code):
    host(monkeypatch, socket('0.0.0.0:8910', 'python'), firewall, ufw_code=code)
    assert not v.check_public_interfaces().ok


@pytest.mark.parametrize('domain', ['forgehub.darckware.net', 'forgevault.darckware.net', 'darckware.net'])
@pytest.mark.parametrize('path', ['/docs', '/redoc', '/openapi.json'])
def test_public_documentation_still_fails(monkeypatch, domain, path):
    url = f'https://{domain}{path}'
    host(monkeypatch, public_open=url)
    assert not v.check_public_interfaces().ok


def test_ss_failure_is_not_accepted(monkeypatch):
    host(monkeypatch, ss_code=1)
    assert not v.check_public_interfaces().ok


@pytest.mark.parametrize('rule', [
    '8911/tcp                   ALLOW IN    Anywhere',
    '8910/tcp                   DENY IN     Anywhere',
    '8000:9000/udp              ALLOW IN    Anywhere',
])
def test_unrelated_or_deny_rules_do_not_invalidate_bridge(monkeypatch, rule):
    host(monkeypatch, socket('0.0.0.0:8910', 'python'), UFW + rule + '\n')
    assert v.check_public_interfaces().ok


@pytest.mark.parametrize('address,owners', [
    ('8.8.8.8:8020', ('docker-proxy',)),
    ('[2606:4700:4700::1111]:8020', ('docker-proxy',)),
    ('[::ffff:0.0.0.0]:8910', ('python',)),
    ('[::ffff:8.8.8.8]:8020', ('docker-proxy',)),
    ('100.105.235.115:21116', ('docker-proxy',)),
    ('[fd7a:115c:a1e0::1]:21116', ('docker-proxy',)),
    ('100.105.235.114:3000', ('python',)),
    ('100.105.235.114:8020', ()),
    ('invalid:21116', ('docker-proxy',)),
    ('[fd7a:115c:a1e0::2501:ebce]%tailscale0:63157', ('tailscaled',)),
    ('100.105.235.115:22', ('sshd',)),
    ('[fd7a:115c:a1e0::1]:22', ('sshd',)),
    ('[::ffff:100.105.235.114]:49123', ('tailscaled',)),
    ('[::ffff:100.105.235.114]:21116', ('docker-proxy',)),
])
def test_merge_preserves_live_listener_rejections(monkeypatch, address, owners):
    host(monkeypatch, socket(address, *owners))
    result = v.check_public_interfaces()
    assert not result.ok
    assert address in result.notes
    assert 'process=' in result.notes


def test_scoped_ipv6_has_a_baseline_finding_instead_of_a_parse_error(monkeypatch):
    host(monkeypatch, socket('[fd7a:115c:a1e0::2501:ebce]%tailscale0:63157', 'tailscaled'))
    result = v.check_public_interfaces()
    assert not result.ok
    assert 'Tailscale bind, no authorized baseline' in result.notes
    assert 'unparseable' not in result.notes


def test_merge_preserves_live_evidence_context(monkeypatch):
    host(monkeypatch)
    result = v.check_public_interfaces()
    assert result.ok
    assert 'host=test-host' in result.notes
    assert 'external reachability NOT verified' in result.notes


def test_many_findings_keep_context_and_omission_count(monkeypatch):
    host(monkeypatch, ''.join(socket(f'0.0.0.0:{port}', 'python') for port in range(22000, 22100)))
    result = v.check_public_interfaces()
    assert not result.ok
    assert len(result.notes) <= 4000
    assert 'host=test-host' in result.notes
    assert '80 findings omitted' in result.notes
