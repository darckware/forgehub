#!/usr/bin/env python3
"""Fetch one agent's ForgeHub credential from ForgeVault without writing it to disk."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path

PROFILE_ROOT = Path('/root/.hermes/profiles')
CREDENTIAL_ROOT = Path('/root/.config/forgevault')
VAULT_URL = 'http://127.0.0.1:8080'
_cache = {}
_lock = threading.Lock()


class CredentialUnavailable(RuntimeError):
    pass


def clear_token_cache(profile):
    with _lock:
        _cache.pop(profile, None)


def get_agent_token(profile, *, force=False, timeout=10):
    if profile not in {'maia', 'athos'}:
        raise CredentialUnavailable('Perfil sem configuração de credencial')
    with _lock:
        cached = _cache.get(profile)
        if not force and cached and cached[0] > time.monotonic():
            return cached[1]
        try:
            deadline = time.monotonic() + timeout
            config = json.loads((PROFILE_ROOT / profile / 'forgehub-vault.json').read_text())
            secret_id = str(uuid.UUID(config['secret_id']))
            credential_file = CREDENTIAL_ROOT / f'{profile}-token'
            bootstrap = subprocess.run(
                ['systemd-creds', 'decrypt', f'--name={profile}-token', str(credential_file), '-'],
                check=True, capture_output=True, text=True, timeout=max(0.1, min(3, timeout / 3)),
            ).stdout.strip()
            if not bootstrap.startswith('fv_sa_'):
                raise ValueError('invalid identity')
            request = urllib.request.Request(
                f'{VAULT_URL}/api/v1/secrets/{secret_id}/value?mode=REVEAL',
                headers={'Authorization': f'Bearer {bootstrap}'},
            )
            with urllib.request.urlopen(request, timeout=max(0.1, deadline - time.monotonic())) as response:
                envelope = json.loads(response.read(1_000_001))
            token = envelope['credentials']['value']
            if (str(envelope.get('resource', '')).lower() != secret_id or
                    envelope.get('accessMode') != 'REVEAL' or
                    not isinstance(token, str) or not re.fullmatch(r'agt_[A-Za-z0-9_-]{20,128}', token)):
                raise ValueError('invalid credential response')
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            _cache.pop(profile, None)
            raise CredentialUnavailable('Não foi possível obter a credencial do ForgeHub no ForgeVault') from None
        _cache[profile] = (time.monotonic() + 60, token)
        return token


def main():
    if len(sys.argv) < 3:
        raise SystemExit('Uso: forgehub_vault_token.py <perfil> <comando> [argumentos...]')
    try:
        token = get_agent_token(sys.argv[1])
    except CredentialUnavailable as exc:
        raise SystemExit(str(exc)) from None
    env = os.environ.copy()
    env['FORGEHUB_AGENT_TOKEN'] = token
    os.execvpe(sys.argv[2], sys.argv[2:], env)


if __name__ == '__main__':
    main()
