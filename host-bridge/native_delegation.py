"""Qualified native delegation controls; never launch a process or select a model.

The caller must place these options before the prompt, replace conflicting
sandbox/bypass options, and append the returned instructions to the package.
Only the exact locally qualified Codex build is admitted. Worker reports remain
untrusted input for the existing independent verifier/acceptance workflow.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib

QUALIFIED_CODEX_VERSION = 'codex-cli 0.167.0'


def secure_delegated_codex_command(command: list[str], config_paths: list,
                                  native_args: list[str], runtime_mcp_names=()) -> list[str]:
    """Disable every configured MCP and plugin/app channel for this review run.

    Codex merges an empty MCP table with inherited configuration, so each
    discovered server gets an explicit disabled override. Unknown config
    syntax fails closed; the bridge never writes global policy for one run.
    """
    servers = {'forgehub', *runtime_mcp_names}
    for path in config_paths:
        try:
            data = tomllib.loads(path.read_text())
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ValueError('Codex MCP configuration could not be safely inventoried') from exc
        table = data.get('mcp_servers', {})
        if not isinstance(table, dict):
            raise ValueError('Codex MCP configuration uses an unsupported shape')
        for name in table:
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
                raise ValueError('Codex MCP server name cannot be safely disabled')
            servers.add(name)
    if any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name)
           for name in servers):
        raise ValueError('Codex MCP server name cannot be safely disabled')

    sanitized = []
    index = 0
    forge_override_found = False
    while index < len(command):
        value = command[index]
        if value == '--dangerously-bypass-approvals-and-sandbox':
            index += 1
            continue
        if value == '--sandbox' and index + 1 < len(command):
            index += 2
            continue
        if (value == '--config' and index + 1 < len(command)
                and command[index + 1].startswith('mcp_servers.forgehub=')):
            config = command[index + 1]
            if not config.endswith('}'):
                raise ValueError('ForgeHub MCP override has an unsupported shape')
            if 'enabled=' not in config:
                config = config[:-1] + ',enabled=false}'
            else:
                config = re.sub(r'enabled\s*=\s*true', 'enabled=false', config)
            sanitized.extend(['--config', config])
            forge_override_found = True
            index += 2
            continue
        sanitized.append(value)
        index += 1
    insertion = sanitized.index('-C') if '-C' in sanitized else len(sanitized) - 1
    overrides = list(native_args)
    overrides.extend(['--disable', 'apps', '--disable', 'plugins'])
    if not forge_override_found:
        overrides.extend(['--config', 'mcp_servers.forgehub={command="/usr/bin/true",enabled=false}'])
    for name in sorted(servers):
        if name == 'forgehub':
            # The session-specific ForgeHub MCP table already has a valid
            # stdio transport. Keep it well-formed while disabling launch.
            continue
        overrides.extend(['--config', f'mcp_servers.{name}.enabled=false'])
    return sanitized[:insertion] + overrides + sanitized[insertion:]


def discover_codex_mcp_names(executable: str, project_dir, env: dict[str, str]) -> set[str]:
    """Read the CLI's global/effective MCP inventory without exposing values."""
    try:
        result = subprocess.run([executable, 'mcp', 'list', '--json'], cwd=project_dir,
            env=env, capture_output=True, text=True, timeout=8, check=False)
        if result.returncode != 0 or len(result.stdout) > 1_000_000:
            raise ValueError
        rows = json.loads(result.stdout)
        if not isinstance(rows, list):
            raise ValueError
        names = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str):
                raise ValueError
            names.add(row['name'])
        return names
    except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
        raise ValueError('Codex effective MCP inventory is unavailable') from exc


def verify_codex_mcp_disabled(executable: str, project_dir, env: dict[str, str],
                              command: list[str]) -> bool:
    """Ask the installed CLI to resolve the exact disabled MCP overrides."""
    mcp_overrides = []
    expected = set()
    for index, value in enumerate(command[:-1]):
        if value != '--config':
            continue
        override = command[index + 1]
        if not override.startswith('mcp_servers.'):
            continue
        mcp_overrides.extend(['--config', override])
        if '=' in override:
            name = override[len('mcp_servers.'):].split('.', 1)[0].split('=', 1)[0]
            expected.add(name)
    try:
        result = subprocess.run([executable, 'mcp', 'list', '--json', *mcp_overrides],
            cwd=project_dir, env=env, capture_output=True, text=True, timeout=8, check=False)
        if result.returncode != 0 or len(result.stdout) > 1_000_000:
            return False
        rows = json.loads(result.stdout)
        if not isinstance(rows, list):
            return False
        return all(isinstance(row, dict) and isinstance(row.get('name'), str)
                   and row['name'] in expected and row.get('enabled') is False for row in rows)
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return False


def single_strategy_options(runtime: str):
    """Disable supported runtimes' native subagent tool surface explicitly."""
    if runtime == 'codex':
        args = ['--config', 'agents.enabled=false', '--config', 'features.multi_agent=false']
    elif runtime == 'claude':
        args = ['--disallowedTools', 'Agent', 'Task']
    else:
        raise ValueError(f'unsupported native single strategy for {runtime}')
    return args, {}, {'version': 'forge-native-delegation/v1', 'runtime': runtime,
                      'strategy': 'single', 'max_children': 0,
                      'enforcement': 'native-spawn-tools-disabled', 'options': args}


def delegation_options(runtime: str, max_children: int, *, mode: str = 'plan',
                       runtime_version: str, package_id: str):
    """Return argv options, environment overrides and an auditable manifest.

    max_children bounds simultaneously open native children, not cumulative
    spawns. Depth is one. All participants share a read-only root sandbox;
    this capability cannot execute a writable implementation package.
    """
    if type(max_children) is not int or not 1 <= max_children <= 3:
        raise ValueError('native child limit must be an integer between 1 and 3')
    if runtime != 'codex':
        raise ValueError(f'unsupported bounded native delegation for {runtime}')
    if mode != 'plan':
        raise ValueError('native delegation currently requires read-only plan mode')
    if runtime_version != QUALIFIED_CODEX_VERSION:
        raise ValueError('native delegation runtime version is not qualified')
    if not isinstance(package_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', package_id):
        raise ValueError('invalid native delegation package identity')

    configs = ['agents.enabled=true', 'features.multi_agent=true',
               'agents.max_depth=1',
               f'agents.max_concurrent_threads_per_session={max_children}',
               'approval_policy="never"']
    args = ['--sandbox', 'read-only']
    for config in configs:
        args.extend(['--config', config])
    instructions = (
        f'Native review delegation for package {package_id}. Use spawn_agent for '
        'at least one bounded review subtask and pass this package identity, the '
        'native-reviewer role and relevant scope to each child. Wait for every '
        'child and integrate its report, listing native child IDs, outcomes and '
        'supporting evidence. All participants are read-only. Do not spawn '
        'external processes as substitute agents. A missing, interrupted or '
        'failed child must be reported explicitly; never claim it succeeded. '
        'Child reports are advisory and unverified. Parent aggregation is not '
        'independent verification or mission acceptance.'
    )
    manifest = {
        'version': 'forge-native-delegation/v1', 'runtime': runtime,
        'runtime_version': runtime_version, 'strategy': 'delegate',
        'capability': 'native-read-only-review', 'package_id': package_id,
        'role': 'native-reviewer', 'max_children': max_children,
        'limit_scope': 'concurrently-open-native-children', 'max_depth': 1,
        'write_policy': 'entire-session-read-only',
        'sandbox_scope': 'native-filesystem-tools',
        'external_capabilities': 'caller-must-govern-separately',
        'result_authority': 'advisory-unverified',
        'requires_persistent_session': True,
        'completion_requires': ['native-child-ids', 'all-child-outcomes',
                                'parent-aggregation', 'independent-verification'],
        'instructions': instructions,
        'options': args,
    }
    manifest['sha256'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return args, {}, manifest


def delegation_result(trace: list[dict], *, exit_code: int | None, interrupted: bool = False):
    """Assess runtime-authored rollout records, not a model's final prose.

    This build's JSON stdout omits some collaboration events. Missing rollout
    evidence is therefore uncertain, including when the root exits zero.
    Returned reports may describe failed work; this never judges their truth.
    """
    spawn_calls, acknowledged_calls, children, reports = set(), set(), set(), set()
    failed_spawn = False
    parent_complete = False
    for row in trace:
        if not isinstance(row, dict):
            continue
        payload = row.get('payload')
        if not isinstance(payload, dict):
            continue
        if row.get('type') == 'event_msg' and payload.get('type') == 'task_complete':
            parent_complete = True
        if row.get('type') != 'response_item':
            continue
        kind = payload.get('type')
        call_id = payload.get('call_id')
        if kind == 'function_call' and payload.get('namespace') == 'collaboration' and payload.get('name') == 'spawn_agent':
            if isinstance(call_id, str):
                spawn_calls.add(call_id)
        elif kind == 'function_call_output' and isinstance(call_id, str) and call_id in spawn_calls:
            try:
                output = json.loads(payload.get('output', ''))
            except (ValueError, TypeError):
                continue
            if isinstance(output, dict) and isinstance(output.get('task_name'), str):
                children.add(output['task_name'])
                acknowledged_calls.add(payload['call_id'])
            elif isinstance(output, dict) and output.get('error'):
                failed_spawn = True
        elif kind == 'agent_message' and isinstance(payload.get('author'), str) and payload.get('author') in children:
            metadata = payload.get('internal_chat_message_metadata_passthrough', {})
            if not isinstance(metadata, dict):
                continue
            provenance = metadata.get('content_item_metadata', [])
            if not isinstance(provenance, list):
                continue
            is_native = any(item.get('provenance') == {'type': 'tool', 'namespace': 'collaboration'}
                            for item in provenance)
            content = payload.get('content', [])
            if not isinstance(content, list):
                continue
            if is_native and any(isinstance(item, dict) and item.get('type') == 'input_text' and
                                 isinstance(item.get('text'), str) and item['text'].startswith('Message Type: FINAL_ANSWER\n')
                                 for item in content):
                reports.add(payload['author'])
    status = 'uncertain'
    if not interrupted and exit_code is not None:
        if exit_code != 0 or failed_spawn:
            status = 'failed'
        elif children and children == reports and spawn_calls == acknowledged_calls and parent_complete:
            status = 'reports_returned'
    return {'status': status, 'child_ids': sorted(children),
            'returned_report_ids': sorted(reports), 'accepted': False, 'verified': False}


def read_delegation_trace(stdout: str, *, root=None, max_bytes=20_000_000):
    """Read only a runtime-authored UUID-named rollout, returning no raw content to clients."""
    import os
    import uuid
    from pathlib import Path
    thread = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
            if event.get('type') == 'thread.started':
                thread = str(uuid.UUID(event['thread_id']))
                break
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    if thread is None:
        return []
    root = (Path(root) if root is not None else Path(os.environ.get('CODEX_HOME', '/root/.codex')) / 'sessions').resolve()
    try:
        matches = list(root.glob(f'**/rollout-*-{thread}.jsonl'))
        if len(matches) != 1 or not matches[0].resolve().is_relative_to(root):
            return []
        if matches[0].stat().st_size > max_bytes:
            return []
        rows = [json.loads(line) for line in matches[0].read_text().splitlines() if line.strip()]
        return rows if all(isinstance(row, dict) for row in rows) else []
    except (OSError, ValueError):
        return []
