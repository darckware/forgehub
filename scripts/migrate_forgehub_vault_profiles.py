#!/usr/bin/env python3
"""Prepare or apply narrowly scoped ForgeHub Vault consumers for Maia and Athos."""
import argparse
import copy
import json
import os
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

import yaml

ROOT = Path('/root/.hermes/profiles')
HELPER = '/root/.hermes/scripts/forgehub_vault_token.py'
STAGED = Path('/tmp/forgehub-agent-vault-stage/maia')


def _server_block(lines, name):
    root = next(i for i, line in enumerate(lines) if line.rstrip() == 'mcp_servers:')
    root_end = next((i for i in range(root + 1, len(lines)) if re.match(r'^\S[^:]*:', lines[i])), len(lines))
    start = next(i for i in range(root + 1, root_end) if lines[i].rstrip() == f'  {name}:')
    end = next((i for i in range(start + 1, root_end) if re.match(r'^  \S[^:]*:', lines[i])), root_end)
    return start, end


def _replace_server(text, profile, name, source):
    lines = text.splitlines(keepends=True)
    start, end = _server_block(lines, name)
    block = lines[start:end]
    command = source['command']
    args = source.get('args', [])
    if not isinstance(command, str) or not all(isinstance(arg, str) and '\n' not in arg for arg in args):
        raise ValueError('Unsupported MCP command')
    command_index = next(i for i, line in enumerate(block) if re.match(r'^    command:', line))
    args_index = next(i for i, line in enumerate(block) if re.match(r'^    args:\s*$', line))
    if args_index != command_index + 1:
        raise ValueError('Unexpected MCP command layout')
    args_end = next((i for i in range(args_index + 1, len(block)) if re.match(r'^    [A-Za-z_][\w-]*:', block[i])), len(block))
    new_args = [HELPER, profile, command, *args]
    dumped = yaml.safe_dump(new_args, default_flow_style=False, allow_unicode=True).splitlines(keepends=True)
    replacement = ['    command: /usr/bin/python3\n', '    args:\n', *['      ' + line for line in dumped]]
    block[command_index:args_end] = replacement
    if name == 'forgehub':
        indices = [i for i, line in enumerate(block) if re.match(r'^      FORGEHUB_AGENT_TOKEN:', line)]
        if len(indices) != 1:
            raise ValueError('Unexpected ForgeHub credential layout')
        del block[indices[0]]
    else:
        env_index = next(i for i, line in enumerate(block) if re.match(r'^    env:\s*$', line))
        if 'FORGEHUB_URL' in source.get('env', {}):
            raise ValueError('Moodle ForgeHub URL already configured')
        block.insert(env_index + 1, '      FORGEHUB_URL: http://127.0.0.1:8000\n')
    return ''.join(lines[:start] + block + lines[end:]), new_args


def rewrite_config(text, profile):
    original = yaml.safe_load(text)
    expected = copy.deepcopy(original)
    for name in ('forgehub', 'moodle'):
        source = original['mcp_servers'][name]
        text, args = _replace_server(text, profile, name, source)
        expected['mcp_servers'][name]['command'] = '/usr/bin/python3'
        expected['mcp_servers'][name]['args'] = args
        if name == 'forgehub':
            del expected['mcp_servers'][name]['env']['FORGEHUB_AGENT_TOKEN']
        else:
            expected['mcp_servers'][name]['env']['FORGEHUB_URL'] = 'http://127.0.0.1:8000'
    if yaml.safe_load(text) != expected:
        raise ValueError('Profile configuration changed beyond the intended keys')
    return text


def atomic_write(path, content, mode):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.vault-config-')
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def encrypted_backup(path, destination, label):
    result = subprocess.run(
        ['systemd-creds', 'encrypt', f'--name={label}', '-', '-'],
        input=path.read_bytes(), capture_output=True, check=True, timeout=15,
    )
    atomic_write(destination, result.stdout, 0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--manifest')
    args = parser.parse_args()
    config_updates = {}
    for profile in ('maia', 'athos'):
        path = ROOT / profile / 'config.yaml'
        config_updates[path] = rewrite_config(path.read_text(), profile).encode()
    if not args.apply:
        print('Profile transformations validated; no files changed.')
        return
    if not args.manifest:
        raise ValueError('Manifest required')
    manifest = json.loads(Path(args.manifest).read_text())
    helper_source = Path(__file__).with_name('forgehub_vault_token.py')
    if not helper_source.is_file() or not all((STAGED / name).is_file() for name in ('_forgehub.py', 'contatos.py')):
        raise ValueError('Staged consumers unavailable')
    updates = {Path(HELPER): helper_source.read_bytes()}
    for profile in ('maia', 'athos'):
        secret_id = str(uuid.UUID(manifest['profiles'][profile]['secret_id']))
        metadata_path = ROOT / profile / 'forgehub-vault.json'
        if metadata_path.exists():
            raise ValueError('Vault metadata file already exists')
        updates[metadata_path] = (json.dumps({'secret_id': secret_id}) + '\n').encode()
    updates[ROOT / 'maia' / 'scripts' / '_forgehub.py'] = (STAGED / '_forgehub.py').read_bytes()
    updates[ROOT / 'maia' / 'plugins' / 'maia_whatsapp_recados' / 'contatos.py'] = (STAGED / 'contatos.py').read_bytes()
    updates.update(config_updates)
    backup = Path('/root/.hermes/state-snapshots/forgehub-vault-rotation')
    backup.mkdir(parents=True, exist_ok=False, mode=0o700)
    originals = {path: path.read_bytes() for path in updates if path.exists()}
    for index, path in enumerate(originals):
        encrypted_backup(path, backup / f'{index}.cred', f'forgehub-vault-backup-{index}')
    try:
        for path, content in updates.items():
            mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
            atomic_write(path, content, mode)
    except Exception:
        for path, content in originals.items():
            atomic_write(path, content, path.stat().st_mode & 0o777 if path.exists() else 0o600)
        for path in updates.keys() - originals.keys():
            path.unlink(missing_ok=True)
        raise
    print('Vault-backed profile consumers installed; encrypted backups retained.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Profile preparation failed:', type(exc).__name__)
        raise SystemExit(1)
