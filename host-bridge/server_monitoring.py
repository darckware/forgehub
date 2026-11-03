"""Bounded, read-only host metadata. No command, path or log content from callers."""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import threading
import time

DISK_ROOTS = ('/root/project', '/root/db', '/root/backup', '/root/.hermes', '/root/.cache', '/var/log')
LIMIT = 100


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    return re.sub(r'[\x00-\x1f\x7f]', '', str(value))[:160]


def command(args, timeout=2):
    env = None
    if args[:2] == ['systemctl', '--user']:
        env = dict(os.environ, XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}')
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=True, env=env)
    if len(result.stdout) > 2_000_000:
        raise ValueError('output_limit')
    return result.stdout


def source(fn):
    try:
        return {'status': 'fresh', 'collected_at': now(), 'error': None, 'data': fn()}
    except Exception as exc:
        # Exception strings/stderr can contain secrets. Only disclose a stable class.
        return {'status': 'unavailable', 'collected_at': now(), 'error': type(exc).__name__, 'data': None}


class Rates:
    def __init__(self):
        self.previous = {}

    def sample(self, key, counters, at):
        previous = self.previous.get(key)
        self.previous[key] = (at, counters)
        if not previous or at <= previous[0] or at - previous[0] > 60:
            return [None] * len(counters)
        return [(value - old) / (at - previous[0]) if value >= old else None
                for value, old in zip(counters, previous[1])]


def endpoint(value):
    host, _, port = value.rpartition(':')
    return host.strip('[]'), port


def parse_sockets(output):
    rows = []
    for line in output.splitlines():
        fields = line.split(None, 6)
        if len(fields) < 6:
            continue
        local_ip, local_port = endpoint(fields[4])
        remote_ip, remote_port = endpoint(fields[5])
        match = re.search(r'\("([^"]+)",pid=(\d+)', fields[6] if len(fields) > 6 else '')
        rows.append({'protocol': fields[0], 'state': fields[1], 'local_ip': clean(local_ip),
                     'local_port': clean(local_port), 'remote_ip': clean(remote_ip), 'remote_port': clean(remote_port),
                     'pid': int(match[2]) if match else None, 'process': clean(match[1]) if match else None})
    return rows


def parse_ssh_events(events):
    rows = []
    for event in events:
        match = re.search(r'(Accepted \S+|Failed \S+) for (?:invalid user )?(\S+) from (\S+)', str(event.get('MESSAGE', '')))
        if not match:
            continue
        try:
            ip = str(ipaddress.ip_address(match[3]))
        except ValueError:
            continue
        timestamp = event.get('__REALTIME_TIMESTAMP')
        rows.append({'at': datetime.fromtimestamp(int(timestamp) / 1e6, timezone.utc).isoformat() if timestamp else None,
                     'result': 'accepted' if match[1].startswith('Accepted') else 'failed',
                     'user': clean(match[2]), 'ip': ip})
    return rows


class Collector:
    def __init__(self, proc=Path('/proc')):
        self.proc = proc
        self.rates = Rates()
        self.lock = threading.Lock()
        self.disk_lock = threading.Lock()
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=6, thread_name_prefix='monitor')
        self.snapshot = None
        self.sampled_at = 0
        self.disk_at = float("-inf")
        self.deadline = 7.0
        self.inflight = {}
        self.disk_result = {'status': 'collecting', 'collected_at': None, 'error': None, 'data': None}
        self._disk_thread = None

    def memory(self):
        mem = {k: int(v.split()[0]) * 1024 for k, v in (line.split(':', 1) for line in (self.proc / 'meminfo').read_text().splitlines())}
        total, available = mem['MemTotal'], mem['MemAvailable']
        return {'total_bytes': total, 'available_bytes': available, 'used_bytes': total - available,
                'cache_bytes': mem.get('Cached', 0) + mem.get('SReclaimable', 0),
                'swap_total_bytes': mem['SwapTotal'], 'swap_used_bytes': mem['SwapTotal'] - mem['SwapFree'],
                'percent_used': round(100 * (total - available) / total, 1), 'cpu_count': os.cpu_count(),
                'load': list(os.getloadavg())}

    def processes(self):
        rows, skipped = [], 0
        at, hz = time.monotonic(), os.sysconf('SC_CLK_TCK')
        page = os.sysconf('SC_PAGE_SIZE')
        previous_keys = set()
        for path in self.proc.iterdir():
            if not path.name.isdigit():
                continue
            if len(rows) >= 10000:
                skipped += 1
                continue
            try:
                raw = (path / 'stat').read_text()
                end = raw.rindex(')')
                stat = raw[end + 2:].split()
                pid = int(path.name)
                key = f'pid:{pid}:{stat[19]}'  # starttime prevents PID-reuse spikes
                previous_keys.add(key)
                io = {k: int(v) for k, v in (line.split(':', 1) for line in (path / 'io').read_text().splitlines())}
                cpu, read, write = self.rates.sample(key, [int(stat[11]) + int(stat[12]), io['read_bytes'], io['write_bytes']], at)
                uid = path.stat().st_uid
                try:
                    user = pwd.getpwuid(uid).pw_name
                except KeyError:
                    user = str(uid)
                cgroup = (path / 'cgroup').read_text()
                container = re.search(r'(?:docker[-/])([a-f0-9]{64})', cgroup)
                service = re.findall(r'/([^/\n]+\.service)', cgroup)
                rows.append({'pid': pid, 'name': clean(raw[raw.index('(') + 1:end]), 'user': clean(user),
                             'memory_bytes': max(0, int(stat[21])) * page,
                             'cpu_percent': round(cpu / hz * 100, 1) if cpu is not None else None,
                             'read_bytes_sec': read, 'write_bytes_sec': write,
                             'container_id': container[1][:12] if container else None,
                             'service': clean(service[-1]) if service else None})
            except (OSError, ValueError, IndexError, KeyError):
                skipped += 1
        # Avoid retaining dead process metadata/counters indefinitely.
        for key in list(self.rates.previous):
            if key.startswith('pid:') and key not in previous_keys:
                del self.rates.previous[key]
        return {'total': len(rows), 'skipped': skipped, 'truncated': len(rows) > 20 or skipped > 0,
                'by_memory': sorted(rows, key=lambda p: p['memory_bytes'], reverse=True)[:20],
                'by_cpu': sorted(rows, key=lambda p: p['cpu_percent'] or 0, reverse=True)[:20],
                'by_write': sorted(rows, key=lambda p: p['write_bytes_sec'] or 0, reverse=True)[:20]}

    def network(self):
        rows, at = [], time.monotonic()
        for line in (self.proc / 'net/dev').read_text().splitlines()[2:]:
            name, values = line.split(':', 1)
            values = values.split()
            rx, tx = int(values[0]), int(values[8])
            rx_rate, tx_rate = self.rates.sample('net:' + name.strip(), [rx, tx], at)
            rows.append({'interface': clean(name.strip()), 'rx_bytes': rx, 'tx_bytes': tx,
                         'rx_bytes_sec': rx_rate, 'tx_bytes_sec': tx_rate,
                         'rx_errors': int(values[2]), 'tx_errors': int(values[10]),
                         'rx_dropped': int(values[3]), 'tx_dropped': int(values[11])})
        return rows[:100]

    def connections(self):
        rows = parse_sockets(command(['ss', '-H', '-n', '-t', '-u', '-a', '-p']))
        # Show established traffic before listeners, then deterministic endpoint order.
        rows.sort(key=lambda r: (r['state'] != 'ESTAB', r['remote_ip'], r['local_port']))
        return {'total': len(rows), 'truncated': len(rows) > LIMIT, 'items': rows[:LIMIT]}

    def filesystems(self):
        rows, seen = [], set()
        for line in (self.proc / 'mounts').read_text().splitlines():
            device, mount, fs = line.split()[:3]
            mount = mount.replace('\\040', ' ')
            if fs not in {'ext4', 'ext3', 'xfs', 'btrfs', 'zfs', 'vfat'} or device in seen:
                continue
            seen.add(device)
            try:
                s = os.statvfs(mount)
                rows.append({'mount': clean(mount), 'device': clean(device), 'total_bytes': s.f_blocks * s.f_frsize,
                             'used_bytes': (s.f_blocks - s.f_bfree) * s.f_frsize, 'free_bytes': s.f_bavail * s.f_frsize,
                             'percent_used': round(100 * (s.f_blocks - s.f_bfree) / s.f_blocks, 1) if s.f_blocks else None,
                             'inodes_percent': round(100 * (s.f_files - s.f_ffree) / s.f_files, 1) if s.f_files else None})
            except OSError:
                continue
        if not rows:
            raise OSError('no_filesystems')
        return rows[:30]

    def _directories(self):
        rows = []
        for root in DISK_ROOTS:
            path = Path(root)
            if path.is_symlink() or not path.exists():
                rows.append({'path': root, 'bytes': None, 'status': 'unavailable'})
                continue
            try:
                output = command(['du', '-s', '-x', '-B1', '--', root], timeout=8)
                rows.append({'path': root, 'bytes': int(output.split()[0]), 'status': 'fresh'})
            except Exception:
                rows.append({'path': root, 'bytes': None, 'status': 'unavailable'})
        return sorted(rows, key=lambda r: r['bytes'] or 0, reverse=True)

    def docker_logs(self):
        ids = command(['docker', 'ps', '-a', '-q', '--no-trunc']).splitlines()
        ids = [value for value in ids if re.fullmatch(r'[a-f0-9]{64}', value)]
        if not ids:
            return {'items': [], 'truncated': False}
        # Format explicitly excludes Env, Args and other sensitive inspect fields.
        output = command(['docker', 'inspect', '--format', '{{json .Id}} {{json .Name}} {{json .LogPath}} {{json .HostConfig.LogConfig.Type}}', *ids[:100]], timeout=4)
        rows = []
        decoder = json.JSONDecoder()
        for line in output.splitlines()[:100]:
            values, rest = [], line
            while rest.strip():
                value, end = decoder.raw_decode(rest.lstrip())
                values.append(value)
                rest = rest.lstrip()[end:]
            if len(values) != 4:
                continue
            cid, name, log_path, driver = values
            size = None
            if log_path:
                path = Path(log_path)
                # Only stat Docker-owned log files under the expected container root.
                expected = Path('/var/lib/docker/containers') / cid
                try:
                    if path.resolve().is_relative_to(expected):
                        files = [path, *list(path.parent.glob(path.name + '.*'))[:100]]
                        size = sum(p.stat().st_size for p in files if p.is_file() and not p.is_symlink())
                except OSError:
                    pass
            rows.append({'container': clean(name.lstrip('/')), 'driver': clean(driver), 'bytes': size})
        return {'items': sorted(rows, key=lambda r: r['bytes'] or 0, reverse=True), 'truncated': len(ids) > 100}

    def directories(self):
        with self.disk_lock:
            if time.monotonic() - self.disk_at >= 300 and not (self._disk_thread and self._disk_thread.is_alive()):
                def scan():
                    result = source(lambda: {'items': self._directories(), 'docker_logs': source(self.docker_logs)})
                    with self.disk_lock:
                        self.disk_result = result
                        self.disk_at = time.monotonic()
                self._disk_thread = threading.Thread(target=scan, daemon=True, name='monitor-disk')
                self._disk_thread.start()
            return {**self.disk_result, 'refreshing': bool(self._disk_thread and self._disk_thread.is_alive())}

    def access(self):
        def sessions():
            rows = []
            for line in command(['who']).splitlines()[:100]:
                fields = line.split()
                if len(fields) >= 4:
                    rows.append({'user': clean(fields[0]), 'terminal': clean(fields[1]),
                                 'since': clean(' '.join(fields[2:4])), 'source': clean(fields[-1].strip('()')) if len(fields) > 4 else None})
            return rows
        def events():
            output = command(['journalctl', '-u', 'ssh.service', '-u', 'sshd.service', '--since', '-1h', '-n', '200', '--no-pager', '-o', 'json'])
            events = [json.loads(line) for line in output.splitlines() if line.startswith('{')]
            # A successful empty journal is not proof the SSH source is configured.
            if not events:
                raise LookupError('no_journal_evidence')
            return {'items': parse_ssh_events(events)[-50:], 'window_minutes': 60, 'truncated': len(events) >= 200}
        return {'sessions': source(sessions), 'ssh_events': source(events), 'application_events': {'status': 'unavailable', 'data': None, 'collected_at': None, 'error': 'not_instrumented'}}

    def services(self):
        def units(user=False):
            args = ['systemctl'] + (['--user'] if user else [])
            names = ['hermes-gateway.service'] if user else ['forgehub-chat-bridge.service', 'tailscaled.service', 'cloudflared.service']
            # show succeeds for missing units, whose LoadState is explicitly reported.
            output = command(args + ['show', '--no-pager', '--property=Id,LoadState,ActiveState,SubState'] + names)
            rows = []
            for block in output.strip().split('\n\n'):
                data = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
                rows.append({'name': clean(data.get('Id', 'unknown')), 'scope': 'user' if user else 'system',
                             'load': data.get('LoadState'), 'state': data.get('ActiveState'), 'substate': data.get('SubState')})
            return rows
        return {'system': source(units), 'user': source(lambda: units(True))}

    def containers(self):
        # Stats expose counters and names only. Never docker inspect Env/Args.
        text = command(['docker', 'stats', '--no-stream', '--format', '{{json .}}'], timeout=4)
        rows = []
        for line in text.splitlines()[:100]:
            item = json.loads(line)
            rows.append({key: clean(item.get(key, '')) for key in ('ID', 'Name', 'CPUPerc', 'MemUsage', 'MemPerc', 'BlockIO', 'NetIO', 'PIDs')})
        status_text = command(['docker', 'ps', '-a', '--format', '{{json .}}'])
        states = []
        for line in status_text.splitlines()[:100]:
            item = json.loads(line)
            states.append({key: clean(item.get(key, '')) for key in ('ID', 'Names', 'State', 'Status')})
        return {'usage': rows, 'states': states, 'truncated': len(status_text.splitlines()) > 100}

    def collect(self):
        with self.lock:
            if self.snapshot and time.monotonic() - self.sampled_at < 10:
                return self.snapshot
            methods = ('memory', 'processes', 'network', 'connections', 'filesystems', 'access', 'services', 'containers')
            for name in methods:
                if name not in self.inflight:
                    self.inflight[name] = self.pool.submit(source, getattr(self, name))
            concurrent.futures.wait(list(self.inflight.values()), timeout=self.deadline)
            snapshot = {'collected_at': now()}
            for name in methods:
                future = self.inflight[name]
                if future.done():
                    snapshot[name] = future.result()
                    del self.inflight[name]
                else:
                    snapshot[name] = {'status': 'unavailable', 'collected_at': now(), 'error': 'collection_timeout', 'data': None}
            snapshot['directories'] = self.directories()
            self.snapshot, self.sampled_at = snapshot, time.monotonic()
            return snapshot


collector = Collector()
