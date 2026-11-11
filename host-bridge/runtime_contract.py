"""Resolve a versioned execution intent against installed, operator-owned skills.

Only canonical registry descriptors cross the bridge. Task text cannot choose an
arbitrary host path or install instructions. The resulting manifest is persisted
with the existing run, not a second execution registry.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeContractError(ValueError):
    """Safe, user-actionable refusal that never includes source or secret data."""


class SkillRequirement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{0,63}$')
    version: str = Field(min_length=1, max_length=50)
    required: bool = True


class RuntimeIntent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal['forge-runtime-intent/v1'] = 'forge-runtime-intent/v1'
    strategy: Literal['native', 'single', 'delegate'] = 'native'
    max_children: int = Field(default=0, ge=0, le=3)
    skills: list[SkillRequirement] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def bounded_strategy(self):
        if (self.strategy != 'delegate') != (self.max_children == 0):
            raise RuntimeContractError('single requires zero children; delegate requires a positive child limit')
        if len({s.name for s in self.skills}) != len(self.skills):
            raise RuntimeContractError('skill names must be unique')
        return self


SKILL_ROOTS = (Path('/root/.hermes/shared-skills'),)
RUNTIME_SKILLS = Path(__file__).resolve().parent / 'runtime-skills'


def prepare_runtime_contract(intent: RuntimeIntent, runtime: str, prompt: str, *, roots=None):
    if runtime not in {'codex', 'claude', 'agy', 'hermes'}:
        raise RuntimeContractError('unsupported runtime')
    if intent.strategy == 'delegate' and runtime != 'codex':
        raise RuntimeContractError(f'unsupported bounded delegation for {runtime}')
    selected, missing, content = [], [], []
    for requirement in intent.skills:
        found = None
        for root in SKILL_ROOTS if roots is None else roots:
            root = root.resolve()
            path = root / requirement.name / 'SKILL.md'
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                raise RuntimeContractError('skill source escaped the trusted skill root')
            try:
                if not path.is_file():
                    continue
                if path.stat().st_size > 32_000:
                    raise RuntimeContractError('skill content exceeds the runner limit')
                raw = path.read_bytes()
                text = raw.decode('utf-8')
                parts = text.split('---', 2)
                metadata = yaml.safe_load(parts[1]) if len(parts) == 3 and not parts[0].strip() else {}
            except RuntimeContractError:
                raise
            except (OSError, UnicodeError, yaml.YAMLError, RuntimeError) as exc:
                raise RuntimeContractError('skill metadata or content is unavailable or invalid') from exc
            if not isinstance(metadata, dict) or str(metadata.get('version')) != requirement.version:
                raise RuntimeContractError(f'skill {requirement.name} version does not match the registry')
            if metadata.get('name') != requirement.name:
                raise RuntimeContractError('skill name does not match the registry')
            found = {'name': requirement.name, 'version': requirement.version,
                     'sha256': hashlib.sha256(raw).hexdigest()}
            content.append(f'Installed skill {requirement.name} ({requirement.version}):\n{text}')
            break
        if found:
            selected.append(found)
        elif requirement.required:
            raise RuntimeContractError(f'missing mandatory skill {requirement.name}')
        else:
            missing.append({'name': requirement.name, 'reason': 'not installed'})
    runtime_path = RUNTIME_SKILLS / runtime / 'SKILL.md'
    if runtime in {'codex', 'claude', 'agy', 'hermes'}:
        try:
            if not runtime_path.is_file():
                raise RuntimeContractError(f'packaged runtime skill for {runtime} is unavailable')
            if runtime_path.stat().st_size > 32_000:
                raise RuntimeContractError('packaged runtime skill exceeds the runner limit')
            raw = runtime_path.read_bytes()
            runtime_text = raw.decode('utf-8')
        except RuntimeContractError:
            raise
        except (OSError, UnicodeError, RuntimeError) as exc:
            raise RuntimeContractError('packaged runtime skill is unavailable or invalid') from exc
        selected.append({'name': f'forge-runtime-{runtime}', 'version': '1.0.0',
                         'sha256': hashlib.sha256(raw).hexdigest()})
        content.insert(0, runtime_text)
    full_prompt = '\n\n'.join([*content, prompt])
    if len(full_prompt) > 100_000:
        raise RuntimeContractError('resolved runtime prompt exceeds the runner limit')
    manifest = {'version': intent.version, 'runtime': runtime, 'strategy': intent.strategy,
                'max_children': intent.max_children, 'skills': selected, 'unavailable_skills': missing,
                'input_sha256': hashlib.sha256(full_prompt.encode()).hexdigest()}
    manifest['sha256'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return full_prompt, manifest


def runtime_version(executable: str) -> str:
    import subprocess
    try:
        result = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeContractError('runtime version could not be verified') from exc
    version = result.stdout.strip().splitlines()
    if not version or len(version[0]) > 200:
        raise RuntimeContractError('runtime returned an invalid version')
    return version[0]
