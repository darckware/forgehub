import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('server_monitoring', Path(__file__).parents[1] / 'server_monitoring.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_rates_require_two_samples_and_handle_reset():
    r = m.Rates()
    assert r.sample('net', [100, 200], 1) == [None, None]
    assert r.sample('net', [300, 240], 3) == [100, 20]
    assert r.sample('net', [1, 2], 4) == [None, None]
    assert r.sample('net', [4, 8], 4) == [None, None]


def test_socket_ipv6_and_only_process_metadata():
    rows = m.parse_sockets('tcp ESTAB 0 0 [::1]:443 [2001:db8::1]:6543 users:(("nginx",pid=123,fd=9))\nudp UNCONN 0 0 0.0.0.0:53 0.0.0.0:*')
    assert rows[0]['remote_ip'] == '2001:db8::1'
    assert rows[0]['local_port'] == '443'
    assert rows[0]['pid'] == 123
    assert rows[0]['process'] == 'nginx'
    assert rows[1]['remote_port'] == '*'
    assert 'fd' not in rows[0]


def test_access_events_do_not_return_raw_logs():
    rows = m.parse_ssh_events([{'__REALTIME_TIMESTAMP': '1000000', 'MESSAGE': 'Failed password for invalid user jane from 192.0.2.1 port 42 ssh2 SECRET'}])
    assert rows[0]['ip'] == '192.0.2.1'
    assert rows[0]['result'] == 'failed'
    assert 'SECRET' not in str(rows)
    assert m.parse_ssh_events([{'MESSAGE': 'unrelated token=SECRET'}]) == []


def test_source_failure_is_unavailable_not_zero():
    def broken():
        raise RuntimeError('password=SECRET')
    result = m.source(broken)
    assert result['status'] == 'unavailable'
    assert result['data'] is None
    assert 'SECRET' not in str(result)


def test_directory_collection_is_cached_and_does_not_accept_paths(monkeypatch):
    c = m.Collector()
    calls = []
    monkeypatch.setattr(c, '_directories', lambda: calls.append(1) or [])
    c.directories()
    c._disk_thread.join(timeout=2)
    assert c.directories()['status'] == 'fresh'
    c.directories()
    assert len(calls) == 1
    assert set(m.DISK_ROOTS) == {'/root/project', '/root/db', '/root/backup', '/root/.hermes', '/root/.cache', '/var/log'}


def test_blocked_source_does_not_stall_snapshot_or_accumulate_work(monkeypatch):
    import threading
    import time
    c = m.Collector()
    c.deadline = 0.03
    release = threading.Event()
    calls = []
    def blocked():
        calls.append(1)
        release.wait(timeout=2)
        return []
    for name in ('memory', 'network', 'connections', 'filesystems', 'access', 'services', 'containers'):
        monkeypatch.setattr(c, name, lambda: [])
    monkeypatch.setattr(c, 'processes', blocked)
    monkeypatch.setattr(c, 'directories', lambda: {})
    try:
        start = time.monotonic()
        first = c.collect()
        assert time.monotonic() - start < .3
        assert first['processes']['status'] == 'unavailable'
        assert first['memory']['status'] == 'fresh'
        c.sampled_at = 0
        c.collect()
        assert len(calls) == 1
    finally:
        release.set()
        c.pool.shutdown(wait=True)


def test_sessions_use_portable_who_without_dns_lookup(monkeypatch):
    def fake_command(args, **kwargs):
        if args == ['who']:
            return 'operator pts/1 2026-10-27 00:00 (192.0.2.20)\n'
        if args[0] == 'journalctl':
            return ''
        raise ValueError('unsupported command')
    monkeypatch.setattr(m, 'command', fake_command)
    access = m.Collector().access()
    assert access['sessions']['status'] == 'fresh'
    assert access['sessions']['data'][0]['source'] == '192.0.2.20'
    assert access['ssh_events']['status'] == 'unavailable'


def test_old_samples_are_not_reported_as_live_rates():
    rates = m.Rates()
    rates.sample('net', [10, 20], 1)
    assert rates.sample('net', [710, 1420], 71) == [None, None]
    assert rates.sample('net', [730, 1460], 73) == [10, 20]
