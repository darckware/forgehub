"""Read only the fixed Maia group inventory; references identify captured records, not DB UUIDs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

GROUP_ID = re.compile(r'^\d+(?:-\d+)?@g\.us$')
REFERENCE = re.compile(r'^[a-f0-9]{64}$')


class GroupSourceError(ValueError):
    pass


def _file(root: Path, name: str, limit: int) -> Path:
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise GroupSourceError('Origem do grupo inválida.')
    try:
        if path.stat().st_size > limit:
            raise GroupSourceError('Histórico do grupo excede o limite de leitura segura.')
    except OSError as exc:
        raise GroupSourceError('Fonte dos grupos monitorados indisponível.') from exc
    return path


def _json(root: Path, name: str):
    try:
        return json.loads(_file(root, name, 2_000_000).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise GroupSourceError('Inventário de grupos indisponível ou inválido.') from exc


def monitored_ids(root: Path) -> set[str]:
    data = _json(root, '_monitoramento.json')
    if not isinstance(data, dict) or not isinstance(data.get('enabled'), list):
        raise GroupSourceError('Seleção de grupos inválida.')
    return {value for value in data['enabled'] if isinstance(value, str) and GROUP_ID.fullmatch(value)}


def monitored_group(root: Path, whatsapp_id: str) -> dict:
    if not GROUP_ID.fullmatch(whatsapp_id):
        raise GroupSourceError('Identificador real do grupo WhatsApp inválido.')
    if whatsapp_id not in monitored_ids(root):
        raise GroupSourceError('Somente grupos monitorados podem ser cadastrados ou capturados.')
    inventory = _json(root, '_grupos.json')
    item = inventory.get(whatsapp_id) if isinstance(inventory, dict) else None
    if not isinstance(item, dict):
        raise GroupSourceError('Grupo ainda não observado pela Maia.')
    name = str(item.get('nome') or '').strip()
    if not name:
        raise GroupSourceError('Nome do grupo não disponível no inventário.')
    return {'whatsapp_id': whatsapp_id, 'name': name[:255], 'last_seen_ts': item.get('ultimo_ts')}


def message_reference(whatsapp_id: str, message: dict) -> str:
    # Current plugin records have no native WhatsApp message ID. Hash the original
    # captured metadata/content without leaking it into references or audit logs.
    payload = {'group': whatsapp_id, 'record': message}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def observed_message(root: Path, whatsapp_id: str, reference: str) -> dict:
    monitored_group(root, whatsapp_id)
    if not REFERENCE.fullmatch(reference):
        raise GroupSourceError('Use a mensagem_ref real retornada pela leitura do grupo.')
    path = _file(root, whatsapp_id.removesuffix('@g.us') + '.jsonl', 32_000_000)
    try:
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict) or record.get('chat') != whatsapp_id:
                    continue
                if message_reference(whatsapp_id, record) == reference:
                    return record
    except (OSError, UnicodeError) as exc:
        raise GroupSourceError('Histórico do grupo indisponível.') from exc
    raise GroupSourceError('Mensagem de origem não encontrada no grupo monitorado; leia o histórico novamente.')
